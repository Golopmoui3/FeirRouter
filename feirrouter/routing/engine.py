"""Quota-aware routing engine: FreeLLMAPI ledger + OmniRoute circuit-breaker + FCC tiers.

- QuotaLedger: per (provider,model,key) RPM/RPD/TPM/TPD + cooldowns + penalty decay (FreeLLMAPI)
- CircuitBreaker: 3-state closed/open/half-open per provider (OmniRoute)
- TierRouter: per-tier Opus/Sonnet/Haiku/Fable (FCC) x 4-tier Subscription→API→Cheap→Free (OmniRoute)
- FallbackChain: order via strategies.order_candidates, retry up to N with key rotation
"""
from __future__ import annotations
import time
from collections import defaultdict
from .strategies import order_candidates
from ..providers.catalog import BY_PREFIX


class QuotaLedger:
    def __init__(self):
        self.minute: dict[tuple, list[float]] = defaultdict(list)
        self.day: dict[tuple, list[float]] = defaultdict(list)
        self.tokens_min: dict[tuple, list[tuple[float, int]]] = defaultdict(list)
        self.penalty: dict[tuple, float] = defaultdict(float)
        self.cooldown_until: dict[tuple, float] = defaultdict(float)

    def _prune(self, now: float):
        for k in list(self.minute):
            self.minute[k] = [t for t in self.minute[k] if now - t < 60]
            self.day[k] = [t for t in self.day[k] if now - t < 86400]
            self.tokens_min[k] = [(t, n) for t, n in self.tokens_min[k] if now - t < 60]

    def allow(self, key: tuple, rpm=40, rpd=10000, tpm=200000) -> bool:
        now = time.time()
        self._prune(now)
        if now < self.cooldown_until.get(key, 0):
            return False
        if len(self.minute.get(key, [])) >= rpm:
            return False
        if len(self.day.get(key, [])) >= rpd:
            return False
        toks = sum(n for _, n in self.tokens_min.get(key, []))
        if toks >= tpm:
            return False
        return True

    def record(self, key: tuple, tokens: int = 0):
        now = time.time()
        self.minute[key].append(now)
        self.day[key].append(now)
        if tokens:
            self.tokens_min[key].append((now, tokens))
        # decay penalty: -1 per 120s handled lazily on fail/success
        self.penalty[key] = max(0.0, self.penalty.get(key, 0.0) - 0.1)

    def fail(self, key: tuple, status: int | None = None):
        now = time.time()
        self.penalty[key] = self.penalty.get(key, 0.0) + (2.0 if status == 429 else 1.0)
        # cooldown: 429 → 120s, 5xx → 30s (FreeLLMAPI idea)
        wait = 120 if status == 429 else 30
        self.cooldown_until[key] = now + wait


class CircuitBreaker:
    """3-state per provider: closed → open (after 5 fails) → half-open after 60s."""

    def __init__(self):
        self.fails: dict[str, int] = defaultdict(int)
        self.opened_at: dict[str, float] = {}

    def is_open(self, provider: str) -> bool:
        if provider not in self.opened_at:
            return False
        if time.time() - self.opened_at[provider] > 60:
            # half-open: allow one probe
            del self.opened_at[provider]
            self.fails[provider] = 0
            return False
        return True

    def success(self, provider: str):
        self.fails[provider] = 0

    def error(self, provider: str):
        self.fails[provider] += 1
        if self.fails[provider] >= 5:
            self.opened_at[provider] = time.time()


TIER_ORDER = ["subscription", "api", "cheap", "free", "local"]

# ---- дедупликация upstream: разные префиксы — один реальный апстрим ----
# Без этого qwen/dashscope/bailian (все — Alibaba) или kimi/moonshot получили бы
# независимые quota-счётчики и втрое превысили бы реальный лимит ключа.
UPSTREAM_GROUPS: dict[str, str] = {
    "kimi": "moonshot", "moonshot": "moonshot",
    "qwen": "alibaba", "dashscope": "alibaba", "bailian": "alibaba",
    "gemini": "google", "gemini_oauth": "google",
    "anthropic": "anthropic", "claude_oauth": "anthropic",
    "openai": "openai", "codex_oauth": "openai",
    "opencode_zen": "opencode", "opencode_go": "opencode",
    "codestral": "mistral", "mistral": "mistral",
    "lmstudio": "local", "llamacpp": "local", "ollama": "local", "vllm": "local",
    "textgen": "local", "koboldcpp": "local", "jan": "local", "gpt4all": "local",
    "xinference": "local", "llamafile": "local", "custom": "local",
}


def ledger_key(provider: str, model: str) -> tuple:
    """Канонический ключ quota-учёта: alias-группы делят один счётчик."""
    return (UPSTREAM_GROUPS.get(provider, provider), model, "")


def resolve_tier_slug(requested_model: str, settings) -> str:
    """FCC per-tier: opus/sonnet/haiku/fable substrings → MODEL_* override else MODEL/auto."""
    m = (requested_model or "").lower()
    if "fable" in m:
        return getattr(settings, "MODEL_FABLE", "") or settings.MODEL
    if "opus" in m:
        return settings.MODEL_OPUS or settings.MODEL
    if "sonnet" in m:
        return settings.MODEL_SONNET or settings.MODEL
    if "haiku" in m:
        return settings.MODEL_HAIKU or settings.MODEL
    if requested_model and requested_model not in ("auto",) and not requested_model.startswith("auto"):
        # explicit slug passes through (incl. provider/model)
        if "/" in requested_model or requested_model in ("opus", "sonnet", "haiku", "fable"):
            base = {"opus": settings.MODEL_OPUS, "sonnet": settings.MODEL_SONNET,
                    "haiku": settings.MODEL_HAIKU, "fable": getattr(settings, "MODEL_FABLE", "")}.get(requested_model, "")
            return base or settings.MODEL
        return requested_model
    return settings.MODEL


def build_chain(model_slug: str, strategy: str, ledger: QuotaLedger, breaker: CircuitBreaker,
               seed_models: list[dict], ctx: dict | None = None) -> list[dict]:
    """Apply 4-tier grouping then strategy ordering inside each tier."""
    ctx = ctx or {}
    # auto/* variants map to auto with task hints
    task = ""
    chaos = False
    if model_slug.startswith("auto"):
        parts = model_slug.split("/")
        if len(parts) > 1:
            task = parts[1].split(":")[0]
            chaos = task == "chaos"
        strategy = "auto"
        ctx = {**ctx, "task": task, "chaos": chaos}
    # tier of requested slug first (if explicit provider)
    ordered: list[dict] = []
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for c in seed_models:
        spec = BY_PREFIX.get(c["provider"])
        tier = spec.tier if spec else "api"
        c = {**c, "penalty": ledger.penalty.get(ledger_key(c["provider"], c["model"]), 0.0),
             "open": not breaker.is_open(UPSTREAM_GROUPS.get(c["provider"], c["provider"]))}
        by_tier[tier].append(c)
    # requested explicit provider jumps queue (LKGP-friendly)
    for tier in TIER_ORDER:
        group = by_tier.get(tier, [])
        if not group:
            continue
        ordered.extend(order_candidates(strategy, group, ctx))
    # global auto re-score across tiers? No — 4-tier fallback: Subscription→...→Free strictly.
    return ordered
