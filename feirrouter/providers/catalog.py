"""Unified provider catalog: full union of FCC (50) + FreeLLMAPI (34) + OmniRoute pool.

prefix = slug used in MODEL, e.g. `groq/llama-3.3-70b`.
chat=False → non-chat surface (media/search/audio/embeddings-only), excluded from chat chain.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    prefix: str
    title: str
    base_url: str
    env_key: str  # "" = keyless/local
    tier: str     # subscription | api | cheap | free | local
    has_free: bool = False
    free_budget: str = ""
    api_format: str = "openai"  # openai | anthropic | gemini
    chat: bool = True


CATALOG: list[ProviderSpec] = [
    # ---- local (FCC + FreeLLMAPI + OmniRoute local) ----
    ProviderSpec("lmstudio", "LM Studio", "http://localhost:1234/v1", "", "local", True, "unlimited"),
    ProviderSpec("llamacpp", "llama.cpp", "http://localhost:8080/v1", "", "local", True, "unlimited"),
    ProviderSpec("ollama", "Ollama", "http://localhost:11434/v1", "", "local", True, "unlimited"),
    ProviderSpec("vllm", "vLLM", "http://localhost:8000/v1", "", "local", True, "unlimited"),
    ProviderSpec("textgen", "TextGen WebUI", "http://localhost:5000/v1", "", "local", True, "unlimited"),
    ProviderSpec("koboldcpp", "KoboldCpp", "http://localhost:5001/v1", "", "local", True, "unlimited"),
    ProviderSpec("jan", "Jan", "http://localhost:1337/v1", "", "local", True, "unlimited"),
    ProviderSpec("gpt4all", "GPT4All", "http://localhost:4891/v1", "", "local", True, "unlimited"),
    ProviderSpec("xinference", "Xinference", "http://localhost:9997/v1", "", "local", True, "unlimited"),
    ProviderSpec("llamafile", "Llamafile", "http://localhost:8080/v1", "", "local", True, "unlimited"),
    # ---- subscription Tier-1 (OmniRoute OAuth pool; BYO token) ----
    ProviderSpec("claude_oauth", "Claude Subscription", "https://api.anthropic.com", "CLAUDE_OAUTH_TOKEN", "subscription", False, "seat", "anthropic"),
    ProviderSpec("codex_oauth", "Codex Subscription", "https://api.openai.com/v1", "CODEX_OAUTH_TOKEN", "subscription", False, "seat"),
    ProviderSpec("gemini_oauth", "Gemini Subscription", "https://generativelanguage.googleapis.com", "GEMINI_OAUTH_TOKEN", "subscription", True, "quota", "gemini"),
    ProviderSpec("antigravity", "Google Antigravity", "https://api.antigravity.google/v1", "ANTIGRAVITY_TOKEN", "subscription", True, "quota"),
    ProviderSpec("github_copilot", "GitHub Copilot", "https://api.githubcopilot.com", "GITHUB_COPILOT_TOKEN", "subscription", False, "seat"),
    ProviderSpec("cursor", "Cursor", "https://api.cursor.com/v1", "CURSOR_TOKEN", "subscription", False, "seat"),
    ProviderSpec("vertex", "Google Vertex AI", "https://us-central1-aiplatform.googleapis.com/v1", "VERTEX_TOKEN", "subscription", False, "quota"),
    ProviderSpec("qoder", "Qoder", "https://api.qoder.com/v1", "QODER_API_KEY", "free", True, "unlimited*"),
    ProviderSpec("kiro", "Kiro", "https://api.kiro.dev/v1", "KIRO_API_KEY", "free", True, "free-forever"),
    ProviderSpec("devin", "Devin", "https://api.devin.ai/v1", "DEVIN_API_KEY", "subscription", False, "seat", "openai", False),
    ProviderSpec("jules", "Jules", "https://api.jules.google/v1", "JULES_API_KEY", "subscription", False, "seat", "openai", False),
    # ---- free-tier giants (FreeLLMAPI core) ----
    ProviderSpec("nvidia_nim", "NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "NVIDIA_NIM_API_KEY", "free", True, "~50-100M"),
    ProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "free", True, "~15-60M"),
    ProviderSpec("cerebras", "Cerebras", "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "free", True, "~30M"),
    ProviderSpec("gemini", "Google AI Studio", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "free", True, "~12-120M"),
    ProviderSpec("mistral", "Mistral La Plateforme", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "free", True, "~50-100M"),
    ProviderSpec("codestral", "Mistral Codestral", "https://codestral.mistral.ai/v1", "MISTRAL_CODESTRAL_API_KEY", "free", True, "trial"),
    ProviderSpec("sambanova", "SambaNova", "https://api.sambanova.ai/v1", "SAMBA_NOVA_API_KEY", "free", True, "~6M"),
    ProviderSpec("github_models", "GitHub Models", "https://models.github.ai/inference", "GITHUB_MODELS_TOKEN", "free", True, "~18M"),
    ProviderSpec("cohere", "Cohere", "https://api.cohere.com/compatibility/v1", "COHERE_API_KEY", "free", True, "~4M trial"),
    ProviderSpec("cloudflare", "Cloudflare Workers AI", "https://api.cloudflare.com/client/v4/accounts", "CLOUDFLARE_API_KEY", "free", True, "~18-45M"),
    ProviderSpec("huggingface", "HuggingFace Router", "https://router.huggingface.co/v1", "HUGGINGFACE_API_KEY", "free", True, "free-tier"),
    ProviderSpec("zai", "Z.ai / Zhipu GLM", "https://api.z.ai/api/paas/v4", "ZAI_API_KEY", "cheap", True, "~30M flash"),
    ProviderSpec("pollinations", "Pollinations", "https://text.pollinations.ai/openai", "POLLINATIONS_API_KEY", "free", True, "unlimited anon"),
    ProviderSpec("opencode_zen", "OpenCode Zen", "https://opencode.ai/zen/v1", "OPENCODE_ZEN_API_KEY", "free", True, "free-tier"),
    ProviderSpec("opencode_go", "OpenCode Go", "https://opencode.ai/go/v1", "OPENCODE_GO_API_KEY", "free", True, "free-tier"),
    ProviderSpec("modelscope", "ModelScope", "https://api-inference.modelscope.cn/v1", "MODELSCOPE_API_KEY", "free", True, "free-tier"),
    ProviderSpec("longcat", "LongCat", "https://api.longcat.chat/v1", "LONGCAT_API_KEY", "free", True, "50M/day"),
    ProviderSpec("kilogateway", "Kilo Gateway", "https://api.kilogateway.com/v1", "KILOGATEWAY_API_KEY", "free", True, "200 req/h"),
    ProviderSpec("llm7", "LLM7", "https://api.llm7.io/v1", "LLM7_API_KEY", "free", True, "100 req/h"),
    ProviderSpec("chutes", "Chutes", "https://llm.chutes.ai/v1", "CHUTES_API_KEY", "free", True, "free"),
    ProviderSpec("avalanche", "Avalanche", "https://api.avalanche.ai/v1", "AVALANCHE_API_KEY", "free", True, "free"),
    ProviderSpec("alpaca", "Alpaca", "https://api.alpaca.ai/v1", "ALPACA_API_KEY", "free", True, "free"),
    # ---- FCC extras ----
    ProviderSpec("open_router", "OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "api", True, "~6M free"),
    ProviderSpec("tokenrouter", "TokenRouter", "https://api.tokenrouter.com/v1", "TOKENROUTER_API_KEY", "free", True, "free"),
    ProviderSpec("nararoute", "NaraRoute", "https://api.nararoute.bynara.com/v1", "NARAROUTE_API_KEY", "free", True, "free"),
    ProviderSpec("wafer", "Wafer", "https://api.wafer.com/v1", "WAFER_API_KEY", "free", True, "free", "anthropic"),
    ProviderSpec("kimi", "Moonshot Kimi", "https://api.moonshot.ai/v1", "KIMI_API_KEY", "api", True, "trial"),
    ProviderSpec("moonshot", "Moonshot (alias)", "https://api.moonshot.ai/v1", "MOONSHOT_API_KEY", "api", True, "trial"),
    ProviderSpec("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "cheap", True, "cheap"),
    ProviderSpec("siliconflow", "SiliconFlow", "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY", "cheap", True, "free-credit"),
    ProviderSpec("bailian", "Bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1", "BAILIAN_API_KEY", "free", True, "free-tier"),
    ProviderSpec("dashscope", "Alibaba DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", "free", True, "free-tier"),
    ProviderSpec("qwen", "Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY", "free", True, "free-tier"),
    ProviderSpec("minimax", "MiniMax", "https://api.minimax.chat/v1", "MINIMAX_API_KEY", "cheap", True, "cheap"),
    ProviderSpec("stepfun", "StepFun", "https://api.stepfun.com/v1", "STEPFUN_API_KEY", "cheap", True, "trial"),
    ProviderSpec("yi", "01.AI Yi", "https://api.lingyiwanwu.com/v1", "YI_API_KEY", "cheap", True, "trial"),
    ProviderSpec("doubao", "Volcengine Doubao", "https://ark.cn-beijing.volces.com/api/v3", "DOUBAO_API_KEY", "cheap", True, "trial"),
    ProviderSpec("hunyuan", "Tencent Hunyuan", "https://api.hunyuan.cloud.tencent.com/v1", "HUNYUAN_API_KEY", "cheap", True, "trial"),
    ProviderSpec("qianfan", "Baidu Qianfan", "https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY", "cheap", True, "trial"),
    ProviderSpec("spark", "iFlytek Spark", "https://spark-api-open.xf-yun.com/v1", "SPARK_API_KEY", "cheap", True, "trial"),
    # ---- classic paid APIs (OmniRoute API pool) ----
    ProviderSpec("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", "api"),
    ProviderSpec("azure", "Azure OpenAI", "https://oai.azure.com/v1", "AZURE_OPENAI_API_KEY", "api"),
    ProviderSpec("anthropic", "Anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "api", False, "", "anthropic"),
    ProviderSpec("xai", "xAI Grok", "https://api.x.ai/v1", "XAI_API_KEY", "api"),
    ProviderSpec("perplexity", "Perplexity", "https://api.perplexity.ai", "PERPLEXITY_API_KEY", "api"),
    ProviderSpec("together", "Together", "https://api.together.xyz/v1", "TOGETHER_API_KEY", "api", True, "credit"),
    ProviderSpec("fireworks", "Fireworks AI", "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "api", True, "credit"),
    ProviderSpec("deepinfra", "DeepInfra", "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY", "api", True, "credit"),
    ProviderSpec("anyscale", "Anyscale", "https://api.endpoints.anyscale.com/v1", "ANYSCALE_API_KEY", "api", True, "credit"),
    ProviderSpec("octoai", "OctoAI", "https://text.octoai.run/v1", "OCTOAI_API_KEY", "api", True, "credit"),
    ProviderSpec("lepton", "Lepton AI", "https://api.lepton.ai/v1", "LEPTON_API_KEY", "api", True, "credit"),
    ProviderSpec("nebius", "Nebius", "https://api.studio.nebius.com/v1", "NEBIUS_API_KEY", "cheap", True, "credit"),
    ProviderSpec("novita", "Novita", "https://api.novita.ai/v3/openai", "NOVITA_API_KEY", "cheap", True, "credit"),
    ProviderSpec("hyperbolic", "Hyperbolic", "https://api.hyperbolic.xyz/v1", "HYPERBOLIC_API_KEY", "cheap", True, "credit"),
    ProviderSpec("parasail", "Parasail", "https://api.parasail.io/v1", "PARASAIL_API_KEY", "cheap", True, "credit"),
    ProviderSpec("kluster", "Kluster", "https://api.kluster.ai/v1", "KLUSTER_API_KEY", "cheap", True, "cheap"),
    ProviderSpec("infermatic", "Infermatic", "https://api.infermatic.ai/v1", "INFERMATIC_API_KEY", "cheap", True, "cheap"),
    ProviderSpec("friendli", "FriendliAI", "https://api.friendli.ai/serverless/v1", "FRIENDLI_API_KEY", "cheap", True, "credit"),
    ProviderSpec("nscale", "Nscale", "https://api.nscale.com/v1", "NSCALE_API_KEY", "cheap", True, "credit"),
    ProviderSpec("ai21", "AI21", "https://api.ai21.com/studio/v1", "AI21_API_KEY", "api"),
    ProviderSpec("alephalpha", "Aleph Alpha", "https://api.aleph-alpha.com/v1", "ALEPHALPHA_API_KEY", "api"),
    ProviderSpec("upstage", "Upstage Solar", "https://api.upstage.ai/v1/solar", "UPSTAGE_API_KEY", "api"),
    ProviderSpec("writer", "Writer", "https://api.writer.com/v1", "WRITER_API_KEY", "api"),
    ProviderSpec("replicate", "Replicate", "https://api.replicate.com/v1", "REPLICATE_API_TOKEN", "api"),
    ProviderSpec("databricks", "Databricks", "https://api.databricks.com/serving-endpoints", "DATABRICKS_TOKEN", "api"),
    ProviderSpec("vercel", "Vercel AI Gateway", "https://ai-gateway.vercel.sh/v1", "VERCEL_AI_GATEWAY_KEY", "api"),
    ProviderSpec("ovhcloud", "OVHcloud AI", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "OVHCLOUD_API_KEY", "api"),
    ProviderSpec("ionos", "IONOS AI", "https://openai.inference.de-txl.ionos.com/v1", "IONOS_API_KEY", "api"),
    ProviderSpec("yandex", "YandexGPT", "https://llm.api.cloud.yandex.net/v1", "YANDEX_API_KEY", "api"),
    ProviderSpec("gigachat", "GigaChat", "https://gigachat.devices.sberbank.ru/api/v1", "GIGACHAT_CREDENTIALS", "api"),
    ProviderSpec("ollama_cloud", "Ollama Cloud", "https://ollama.com/v1", "OLLAMA_CLOUD_KEY", "free", True, "gpu-quota"),
    ProviderSpec("custom", "Custom OpenAI-compatible", "http://localhost:8000/v1", "CUSTOM_API_KEY", "local", True, "user-defined"),
    # ---- embeddings-only ----
    ProviderSpec("voyage", "Voyage AI", "https://api.voyageai.com/v1", "VOYAGE_API_KEY", "api", False, "", "openai", False),
    ProviderSpec("jina", "Jina AI", "https://api.jina.ai/v1", "JINA_API_KEY", "api", True, "free-tier", "openai", False),
    # ---- audio-only ----
    ProviderSpec("elevenlabs", "ElevenLabs", "https://api.elevenlabs.io/v1", "ELEVENLABS_API_KEY", "api", False, "", "openai", False),
    ProviderSpec("deepgram", "Deepgram", "https://api.deepgram.com/v1", "DEEPGRAM_API_KEY", "api", True, "credit", "openai", False),
    ProviderSpec("assemblyai", "AssemblyAI", "https://api.assemblyai.com/v2", "ASSEMBLYAI_API_KEY", "api", True, "credit", "openai", False),
    # ---- image/video generation ----
    ProviderSpec("stability", "Stability AI", "https://api.stability.ai/v2beta", "STABILITY_API_KEY", "api", False, "", "openai", False),
    ProviderSpec("recraft", "Recraft", "https://external.api.recraft.ai/v1", "RECRAFT_API_KEY", "api", True, "credit", "openai", False),
    ProviderSpec("fal", "fal.ai", "https://fal.run/fal-ai", "FAL_KEY", "api", False, "", "openai", False),
    ProviderSpec("runway", "Runway", "https://api.runwayml.com/v1", "RUNWAY_API_KEY", "api", False, "", "openai", False),
    ProviderSpec("luma", "Luma", "https://api.lumalabs.ai/v1", "LUMA_API_KEY", "api", True, "trial", "openai", False),
    # ---- search (web_search-aware routing) ----
    ProviderSpec("tavily", "Tavily", "https://api.tavily.com", "TAVILY_API_KEY", "api", True, "trial", "openai", False),
    ProviderSpec("exa", "Exa", "https://api.exa.ai", "EXA_API_KEY", "api", True, "trial", "openai", False),
    ProviderSpec("brave", "Brave Search", "https://api.search.brave.com/v1", "BRAVE_API_KEY", "api", True, "trial", "openai", False),
    ProviderSpec("serper", "Serper", "https://google.serper.dev", "SERPER_API_KEY", "api", True, "trial", "openai", False),
]

BY_PREFIX: dict[str, ProviderSpec] = {p.prefix: p for p in CATALOG}
CHAT_PREFIXES: list[str] = [p.prefix for p in CATALOG if p.chat]

# Media candidates tried (OpenAI-shape passthrough) for images/audio endpoints
IMAGE_CANDIDATES = ["openai", "together", "fireworks", "nebius", "novita", "deepinfra", "huggingface", "siliconflow", "xai", "azure"]
AUDIO_CANDIDATES = ["openai", "groq", "deepgram", "cerebras"]

# Seed chat catalog: (provider, model, intelligence 0-10, blended $/1M, context)
MODEL_SEED: list[tuple[str, str, float, float, int]] = [
    ("nvidia_nim", "moonshotai/kimi-k2.5", 8.5, 0.0, 256000),
    ("nvidia_nim", "stepfun-ai/step-3.5-flash", 7.0, 0.0, 128000),
    ("nvidia_nim", "nvidia/nemotron-3-super-120b-a12b", 8.0, 0.0, 128000),
    ("nvidia_nim", "z-ai/glm4.7", 8.5, 0.0, 128000),
    ("open_router", "deepseek/deepseek-r1-0528:free", 8.5, 0.0, 128000),
    ("open_router", "openai/gpt-oss-120b:free", 8.0, 0.0, 128000),
    ("open_router", "stepfun/step-3.5-flash:free", 7.0, 0.0, 128000),
    ("open_router", "arcee-ai/trinity-large-preview:free", 8.0, 0.0, 128000),
    ("open_router", "qwen/qwen3-coder:free", 8.5, 0.0, 256000),
    ("groq", "llama-3.3-70b-versatile", 8.0, 0.0, 128000),
    ("groq", "openai/gpt-oss-120b", 8.0, 0.0, 128000),
    ("groq", "qwen/qwen3-32b", 7.5, 0.0, 128000),
    ("cerebras", "qwen-3-235b-a22b", 8.5, 0.0, 128000),
    ("cerebras", "llama-3.3-70b", 8.0, 0.0, 128000),
    ("gemini", "gemini-2.5-flash", 8.0, 0.0, 1000000),
    ("gemini", "gemini-2.5-pro", 9.0, 0.0, 1000000),
    ("gemini", "gemma-3-27b-it", 7.5, 0.0, 128000),
    ("deepseek", "deepseek-chat", 8.5, 0.28, 128000),
    ("deepseek", "deepseek-reasoner", 9.0, 0.55, 128000),
    ("zai", "glm-4.7-flash", 7.5, 0.0, 128000),
    ("zai", "glm-5.1", 8.5, 0.6, 200000),
    ("kimi", "kimi-k2-thinking", 8.5, 0.6, 256000),
    ("kimi", "kimi-k2-0711-preview", 8.5, 0.6, 256000),
    ("qwen", "qwen3-coder-plus", 8.5, 0.0, 256000),
    ("qwen", "qwen3-coder-flash", 7.5, 0.0, 256000),
    ("mistral", "mistral-large-2411", 8.5, 2.0, 128000),
    ("mistral", "mistral-medium-2505", 8.0, 0.4, 128000),
    ("mistral", "mistral-small-2503", 7.0, 0.1, 128000),
    ("codestral", "codestral-latest", 8.0, 0.3, 256000),
    ("codestral", "devstral-medium-latest", 8.0, 0.4, 128000),
    ("sambanova", "DeepSeek-V3-0324", 8.5, 0.0, 128000),
    ("sambanova", "Llama-4-Maverick-17B-128E-Instruct", 8.0, 0.0, 128000),
    ("cohere", "command-r-plus", 8.0, 0.0, 128000),
    ("cohere", "command-a-03-2025", 8.0, 0.0, 256000),
    ("huggingface", "deepseek-ai/DeepSeek-V3", 8.5, 0.0, 128000),
    ("huggingface", "moonshotai/Kimi-K2-Instruct", 8.5, 0.0, 256000),
    ("huggingface", "Qwen/Qwen3-235B-A22B", 8.5, 0.0, 128000),
    ("github_models", "openai/gpt-4.1", 8.5, 0.0, 1000000),
    ("github_models", "openai/gpt-4o", 8.5, 0.0, 128000),
    ("minimax", "MiniMax-M2", 8.0, 0.2, 200000),
    ("stepfun", "step-3.5-flash", 7.0, 0.1, 128000),
    ("doubao", "doubao-seed-1-6", 8.0, 0.3, 256000),
    ("openai", "gpt-4o", 9.0, 2.5, 128000),
    ("openai", "gpt-4o-mini", 7.5, 0.15, 128000),
    ("anthropic", "claude-sonnet-4-5", 9.0, 3.0, 200000),
    ("anthropic", "claude-haiku-4-5", 8.0, 0.8, 200000),
    ("xai", "grok-4", 8.5, 3.0, 256000),
    ("perplexity", "sonar-pro", 8.0, 1.0, 200000),
    ("together", "Qwen/Qwen3-235B-A22B-fp8", 8.5, 0.2, 128000),
    ("fireworks", "accounts/fireworks/models/deepseek-v3", 8.5, 0.9, 128000),
    ("deepinfra", "deepseek-ai/DeepSeek-V3", 8.5, 0.3, 128000),
    ("nebius", "Qwen/Qwen3-235B-A22B", 8.5, 0.2, 128000),
    ("lmstudio", "qwen3.5-coder", 7.5, 0.0, 64000),
    ("ollama", "qwen3.5", 7.5, 0.0, 64000),
    ("llamacpp", "default", 7.0, 0.0, 32000),
    ("pollinations", "openai", 7.5, 0.0, 128000),
    ("qoder", "kimi-k2-thinking", 8.5, 0.0, 256000),
    ("qoder", "qwen3-coder-plus", 8.5, 0.0, 256000),
]


def parse_slug(slug: str) -> tuple[str, str]:
    """'groq/llama-3.3-70b' -> ('groq','llama-3.3-70b'). Без префикса -> ('', slug)."""
    if "/" in slug:
        p, m = slug.split("/", 1)
        if p in BY_PREFIX:
            return p, m
    return "", slug
