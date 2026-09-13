"""Unified provider catalog: union of FCC (50) + FreeLLMAPI (34) + OmniRoute (352 subset).

Each entry: prefix used in MODEL slugs like `groq/llama-3.3-70b`,
default base_url, env key name, tier (subscription|api|cheap|free|local),
has_free flag, rough monthly free budget for docs.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    prefix: str
    title: str
    base_url: str
    env_key: str  # e.g. GROQ_API_KEY ("" = keyless/local)
    tier: str     # subscription | api | cheap | free | local
    has_free: bool = False
    free_budget: str = ""
    api_format: str = "openai"  # openai | anthropic | gemini


CATALOG: list[ProviderSpec] = [
    # ---- local (FCC + FreeLLMAPI) ----
    ProviderSpec("lmstudio", "LM Studio", "http://localhost:1234/v1", "", "local", True, "unlimited", "openai"),
    ProviderSpec("llamacpp", "llama.cpp", "http://localhost:8080/v1", "", "local", True, "unlimited", "openai"),
    ProviderSpec("ollama", "Ollama", "http://localhost:11434/v1", "", "local", True, "unlimited", "openai"),
    ProviderSpec("vllm", "vLLM", "http://localhost:8000/v1", "", "local", True, "unlimited", "openai"),
    # ---- subscription Tier-1 (OmniRoute idea) ----
    ProviderSpec("claude_oauth", "Claude Subscription", "https://api.anthropic.com", "CLAUDE_OAUTH_TOKEN", "subscription", False, "quota", "anthropic"),
    ProviderSpec("codex_oauth", "Codex Subscription", "https://api.openai.com/v1", "CODEX_OAUTH_TOKEN", "subscription", False, "quota", "openai"),
    ProviderSpec("gemini_oauth", "Gemini Subscription", "https://generativelanguage.googleapis.com", "GEMINI_OAUTH_TOKEN", "subscription", True, "quota", "gemini"),
    # ---- free / free-tier heavy (FreeLLMAPI core + OmniRoute free) ----
    ProviderSpec("nvidia_nim", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "NVIDIA_NIM_API_KEY", "free", True, "~50-100M", "openai"),
    ProviderSpec("open_router", "OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "api", True, "~6M free", "openai"),
    ProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "free", True, "~15-60M", "openai"),
    ProviderSpec("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "free", True, "~30M", "openai"),
    ProviderSpec("gemini", "Google AI Studio", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "free", True, "~12-120M", "openai"),
    ProviderSpec("mistral", "Mistral La Plateforme", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "free", True, "~50-100M", "openai"),
    ProviderSpec("codestral", "Mistral Codestral", "https://codestral.mistral.ai/v1", "MISTRAL_CODESTRAL_API_KEY", "free", True, "trial", "openai"),
    ProviderSpec("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "cheap", True, "cheap", "openai"),
    ProviderSpec("zai", "Z.ai / Zhipu GLM", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", "cheap", True, "~30M flash", "openai"),
    ProviderSpec("kimi", "Moonshot Kimi", "https://api.moonshot.ai/v1", "KIMI_API_KEY", "api", True, "trial", "openai"),
    ProviderSpec("moonshot", "Moonshot (alias)", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY", "api", True, "trial", "openai"),
    ProviderSpec("qwen", "Qwen / DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("dashscope", "Alibaba DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("bailian", "Bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1", "BAILIAN_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY", "cheap", True, "free-credit", "openai"),
    ProviderSpec("huggingface", "HuggingFace Router", "https://router.huggingface.co/v1", "HUGGINGFACE_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("github_models", "GitHub Models", "https://models.github.ai/inference", "GITHUB_MODELS_TOKEN", "free", True, "~18M", "openai"),
    ProviderSpec("cohere", "Cohere", "https://api.cohere.com/compatibility/v1", "COHERE_API_KEY", "free", True, "~4M trial", "openai"),
    ProviderSpec("cloudflare", "Cloudflare Workers AI", "https://api.cloudflare.com/client/v4/accounts", "CLOUDFLARE_API_KEY", "free", True, "~18-45M", "openai"),
    ProviderSpec("sambanova", "SambaNova", "https://api.sambanova.ai/v1", "SAMBA_NOVA_API_KEY", "free", True, "~6M", "openai"),
    ProviderSpec("together", "Together", "https://api.together.xyz/v1", "TOGETHER_API_KEY", "api", True, "credit", "openai"),
    ProviderSpec("fireworks", "Fireworks AI", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "api", True, "credit", "openai"),
    ProviderSpec("perplexity", "Perplexity", "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "api", False, "", "openai"),
    ProviderSpec("xai", "xAI Grok", "https://api.x.ai/v1", "XAI_API_KEY", "api", False, "", "openai"),
    ProviderSpec("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", "api", False, "", "openai"),
    ProviderSpec("anthropic", "Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "api", False, "", "anthropic"),
    ProviderSpec("minimax", "MiniMax", "https://api.minimax.chat/v1", "MINIMAX_API_KEY", "cheap", True, "cheap", "openai"),
    ProviderSpec("opencode_zen", "OpenCode Zen", "https://opencode.ai/zen/v1", "OPENCODE_ZEN_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("opencode_go", "OpenCode Go", "https://opencode.ai/go/v1", "OPENCODE_GO_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("tokenrouter", "TokenRouter", "https://api.tokenrouter.com/v1", "TOKENROUTER_API_KEY", "free", True, "free", "openai"),
    ProviderSpec("nararoute", "NaraRoute", "https://api.nararoute.bynara.com/v1", "NARAROUTE_API_KEY", "free", True, "free", "openai"),
    ProviderSpec("wafer", "Wafer", "https://api.wafer.com/v1", "WAFER_API_KEY", "free", True, "free", "anthropic"),
    ProviderSpec("pollinations", "Pollinations", "https://text.pollinations.ai/openai", "POLLINATIONS_API_KEY", "free", True, "unlimited anon", "openai"),
    ProviderSpec("github_copilot", "GitHub Copilot", "https://api.githubcopilot.com", "GITHUB_COPILOT_TOKEN", "subscription", False, "seat", "openai"),
    ProviderSpec("qoder", "Qoder", "https://api.qoder.com/v1", "QODER_API_KEY", "free", True, "unlimited*", "openai"),
    ProviderSpec("kiro", "Kiro", "https://api.kiro.dev/v1", "KIRO_API_KEY", "free", True, "free-forever", "openai"),
    ProviderSpec("longcat", "LongCat", "https://api.longcat.chat/v1", "LONGCAT_API_KEY", "free", True, "50M/day", "openai"),
    ProviderSpec("modelscope", "ModelScope", "https://api-inference.modelscope.cn/v1", "MODELSCOPE_API_KEY", "free", True, "free-tier", "openai"),
    ProviderSpec("chutes", "Chutes", "https://llm.chutes.ai/v1", "CHUTES_API_KEY", "free", True, "free", "openai"),
    ProviderSpec("nebius", "Nebius", "https://api.studio.nebius.com/v1", "NEBIUS_API_KEY", "cheap", True, "credit", "openai"),
    ProviderSpec("novita", "Novita", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY", "cheap", True, "credit", "openai"),
    ProviderSpec("hyperbolic", "Hyperbolic", "https://api.hyperbolic.xyz/v1", "HYPERBOLIC_API_KEY", "cheap", True, "credit", "openai"),
    ProviderSpec("parasail", "Parasail", "https://api.parasail.io/v1", "PARASAIL_API_KEY", "cheap", True, "credit", "openai"),
    ProviderSpec("avalanche", "Avalanche", "https://api.avalanche.ai/v1", "AVALANCHE_API_KEY", "free", True, "free", "openai"),
    ProviderSpec("kilogateway", "Kilo Gateway", "https://api.kilogateway.com/v1", "KILOGATEWAY_API_KEY", "free", True, "200 req/h", "openai"),
    ProviderSpec("llm7", "LLM7", "https://api.llm7.io/v1", "LLM7_API_KEY", "free", True, "100 req/h", "openai"),
    ProviderSpec("alpaca", "Alpaca", "https://api.alpaca.ai/v1", "ALPACA_API_KEY", "free", True, "free", "openai"),
    ProviderSpec("infermatic", "Infermatic", "https://api.infermatic.ai/v1", "INFERMATIC_API_KEY", "cheap", True, "cheap", "openai"),
    ProviderSpec("kluster", "Kluster", "https://api.kluster.ai/v1", "KLUSTER_API_KEY", "cheap", True, "cheap", "openai"),
    ProviderSpec("custom", "Custom OpenAI-compatible", "http://localhost:8000/v1", "CUSTOM_API_KEY", "local", True, "user-defined", "openai"),
]

BY_PREFIX: dict[str, ProviderSpec] = {p.prefix: p for p in CATALOG}

# Небольшой стартовый каталог моделей (расширяется signed-feed / автодискавери / ручным fallback-chain).
# Формат: (provider_prefix, model_id, intelligence 0-10, $/1M blended, context)
MODEL_SEED: list[tuple[str, str, float, float, int]] = [
    ("nvidia_nim", "moonshotai/kimi-k2.5", 8.5, 0.0, 256000),
    ("nvidia_nim", "stepfun-ai/step-3.5-flash", 7.0, 0.0, 128000),
    ("nvidia_nim", "nvidia/nemotron-3-super-120b-a12b", 8.0, 0.0, 128000),
    ("open_router", "deepseek/deepseek-r1-0528:free", 8.5, 0.0, 128000),
    ("open_router", "openai/gpt-oss-120b:free", 8.0, 0.0, 128000),
    ("open_router", "stepfun/step-3.5-flash:free", 7.0, 0.0, 128000),
    ("open_router", "arcee-ai/trinity-large-preview:free", 8.0, 0.0, 128000),
    ("groq", "llama-3.3-70b-versatile", 8.0, 0.0, 128000),
    ("groq", "openai/gpt-oss-120b", 8.0, 0.0, 128000),
    ("cerebras", "qwen-3-235b-a22b", 8.5, 0.0, 128000),
    ("gemini", "gemini-2.5-flash", 8.0, 0.0, 1000000),
    ("gemini", "gemini-2.5-pro", 9.0, 0.0, 1000000),
    ("deepseek", "deepseek-chat", 8.5, 0.28, 128000),
    ("deepseek", "deepseek-reasoner", 9.0, 0.55, 128000),
    ("zai", "glm-4.7-flash", 7.5, 0.0, 128000),
    ("zai", "glm-5.1", 8.5, 0.6, 200000),
    ("kimi", "kimi-k2-thinking", 8.5, 0.6, 256000),
    ("qwen", "qwen3-coder-plus", 8.5, 0.0, 256000),
    ("mistral", "mistral-large-2411", 8.5, 2.0, 128000),
    ("mistral", "codestral-latest", 8.0, 0.3, 256000),
    ("lmstudio", "qwen3.5-coder", 7.5, 0.0, 64000),
    ("ollama", "qwen3.5", 7.5, 0.0, 64000),
    ("llamacpp", "default", 7.0, 0.0, 32000),
    ("pollinations", "openai", 7.5, 0.0, 128000),
]


def parse_slug(slug: str) -> tuple[str, str]:
    """'groq/llama-3.3-70b' -> ('groq','llama-3.3-70b'). Без префикса -> ('', slug)."""
    if "/" in slug:
        p, m = slug.split("/", 1)
        if p in BY_PREFIX:
            return p, m
        # open_router style: open_router/deepseek/... — префикс только первый сегмент
        if p in BY_PREFIX:
            return p, m
    return "", slug
