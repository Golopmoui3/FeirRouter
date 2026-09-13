# Providers — FeirRouter (union FCC + FreeLLMAPI + OmniRoute)

Полный список — `feirrouter/providers/catalog.py` (60+). Ключи — env (`GROQ_API_KEY` и т.д.), локальные — `*_BASE_URL`.
`python -m feirrouter doctor` покажет готовые.

| prefix | title | tier | free |
|---|---|---|---|
| lmstudio / llamacpp / ollama / vllm / custom | local | local | yes unlimited |
| claude_oauth / codex_oauth / gemini_oauth | subscriptions | subscription | seat/quota |
| nvidia_nim / groq / cerebras / gemini / mistral / codestral | free-tier giants | free | yes |
| open_router / together / fireworks / huggingface / github_models | aggregators | api/free | partial |
| deepseek / zai / kimi / siliconflow / minimax / nebius / novita | cheap | cheap | cheap/credit |
| qwen / dashscope / bailian / modelscope | china labs | free | yes |
| cohere / cloudflare / sambanova / perplexity / xai / openai / anthropic | classic | api | varies |
| opencode_zen / opencode_go / tokenrouter / nararoute / wafer | FCC extras | free | yes |
| pollinations / qoder / kiro / longcat / chutes / kilogateway / llm7 | OmniRoute free-forever | free | yes |

ToS-friendly: только официальные ключи пользователя, без вшитых ключей и обходов.
