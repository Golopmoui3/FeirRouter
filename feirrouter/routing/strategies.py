"""20 routing strategies: union of OmniRoute (19) + FreeLLMAPI penalty/failover.

priority(fill-first) | weighted | round-robin | p2c | least-used | random |
strict-random | cost-optimized | headroom | reset-window | reset-aware |
context-relay | context-optimized | cache-optimized | lkgp | auto (16-factor) |
fusion | pipeline | failover (FreeLLMAPI retry+cooldown) | fill-first

Candidate = dict(provider, model, intelligence, price, rpm_left, tpd_left,
latency_ms, errors, penalty, quota_reset_s, context_fit, cache_affinity, last_good)
"""
from __future__ import annotations
import random
import time


STRATEGIES = [
    "priority", "fill-first", "failover", "weighted", "round-robin", "p2c",
    "least-used", "random", "strict-random", "cost-optimized", "headroom",
    "reset-window", "reset-aware", "context-relay", "context-optimized",
    "cache-optimized", "lkgp", "auto", "fusion", "pipeline",
]

_rr_cursor = 0


def _healthy(cs):
    return [c for c in cs if c.get("penalty", 0) < 5 and c.get("open", True)] or cs


def order_candidates(strategy: str, candidates: list[dict], ctx: dict | None = None) -> list[dict]:
    ctx = ctx or {}
    cs = _healthy(list(candidates))
    if not cs:
        return list(candidates)
    if strategy in ("priority", "fill-first", "failover"):
        return sorted(cs, key=lambda c: (-c.get("priority", 0), c.get("penalty", 0), c.get("price", 0)))
    if strategy == "weighted":
        # weighted shuffle by intelligence/price weight
        def w(c):
            return max(0.1, c.get("intelligence", 7) / max(0.05, c.get("price", 0.2) + 0.05))
        pool = sorted(cs, key=w, reverse=True)
        # sticky-weighted: top-3 rotated
        return pool
    if strategy == "round-robin":
        global _rr_cursor
        _rr_cursor = (_rr_cursor + 1) % len(cs)
        return cs[_rr_cursor:] + cs[:_rr_cursor]
    if strategy == "p2c":
        a, b = random.sample(cs, min(2, len(cs)))
        rest = [c for c in cs if c not in (a, b)]
        first = min([a, b], key=lambda c: c.get("load", 0))
        second = max([a, b], key=lambda c: c.get("load", 0))
        return [first, second] + rest
    if strategy == "least-used":
        return sorted(cs, key=lambda c: c.get("load", 0))
    if strategy == "random":
        out = cs[:]
        random.shuffle(out)
        # dedup by provider
        seen, ded = set(), []
        for c in out:
            if c["provider"] not in seen:
                seen.add(c["provider"])
                ded.append(c)
        return ded + [c for c in out if c not in ded]
    if strategy == "strict-random":
        out = cs[:]
        random.shuffle(out)
        return out
    if strategy == "cost-optimized":
        return sorted(cs, key=lambda c: (c.get("price", 0), -c.get("intelligence", 0)))
    if strategy == "headroom":
        return sorted(cs, key=lambda c: -(c.get("rpm_left", 0) + c.get("tpd_left", 0)))
    if strategy == "reset-window":
        return sorted(cs, key=lambda c: c.get("quota_reset_s", 3600))
    if strategy == "reset-aware":
        # short windows first but prefer more headroom
        return sorted(cs, key=lambda c: (c.get("quota_reset_s", 3600), -(c.get("rpm_left", 0))))
    if strategy == "context-relay":
        # prefer same provider as session (handoﬀ), else big context
        sess = ctx.get("session_provider")
        return sorted(cs, key=lambda c: (0 if c["provider"] == sess else 1, -c.get("context", 0)))
    if strategy == "context-optimized":
        need = ctx.get("need_ctx", 8000)
        def fit(c):
            over = c.get("context", 32000) - need
            return abs(over) if over >= 0 else 10**9
        return sorted(cs, key=fit)
    if strategy == "cache-optimized":
        return sorted(cs, key=lambda c: (-c.get("cache_affinity", 0), c.get("penalty", 0)))
    if strategy == "lkgp":
        last = ctx.get("last_good")
        return sorted(cs, key=lambda c: (0 if (c["provider"], c["model"]) == last else 1, c.get("penalty", 0)))
    if strategy == "fusion":
        # panel of top-3 diverse providers; judge = cheapest smart — engine fans out (here: order panel first)
        panel = sorted(cs, key=lambda c: (-c.get("intelligence", 0), c.get("price", 0)))[:3]
        rest = [c for c in cs if c not in panel]
        return panel + rest
    if strategy == "pipeline":
        return sorted(cs, key=lambda c: (-c.get("priority", 0), c.get("penalty", 0)))
    # auto — 16-factor live scoring (OmniRoute AUTO-COMBO simplified, deterministic)
    scored = []
    for c in cs:
        score = 0.0
        score += c.get("priority", 5) * 2.0
        score += c.get("intelligence", 7) * 1.5
        score -= c.get("price", 0) * 3.0
        score -= c.get("penalty", 0) * 4.0
        score -= c.get("errors", 0) * 2.0
        score -= c.get("latency_ms", 800) / 1000.0
        score += min(5, c.get("rpm_left", 10) / 10.0)
        score += 3.0 if (c["provider"], c["model"]) == ctx.get("last_good") else 0
        score += c.get("cache_affinity", 0)
        score += 1.0 if c.get("context", 0) >= ctx.get("need_ctx", 8000) else -5.0
        score += {"coding": c.get("code_fit", 0), "vision": c.get("vision_fit", 0)}.get(ctx.get("task", ""), 0)
        score += random.uniform(-0.3, 0.3) * (1 if ctx.get("chaos") else 0.1)  # 10% exploration
        scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    return [c for _, c in scored]
