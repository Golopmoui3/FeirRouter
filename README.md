# FeirRouter — Ultimate Free LLM Router
### 1 endpoint. Все провайдеры. Ноль даунтайма.

**FeirRouter** = `free-claude-code` + `FreeLLMAPI` + `OmniRoute` во едино.
Забираем лучшее из каждого и складываем в один мощный локальный гейтвей (Python + FastAPI, MIT).

| Что забрали | Откуда | Что это даёт в FeirRouter |
|---|---|---|
| Anthropic-совместимость `/v1/messages`, `/v1/models`, `/count_tokens`, per-tier роутинг `Opus/Sonnet/Haiku/Fable` | **free-claude-code** (Alishahryar1, 50 провайдеров, 10 агентов) | Claude Code / Codex / Cline / OpenCode работают без правок, thinking-блоки, heuristic tool-parser |
| Request optimization (5 тривиальных проб перехватываются локально), smart rate-limit (rolling-window + 429 backoff + concurrency), Admin UI, `BaseProvider`/`OpenAICompatibleProvider`, Discord/Telegram бот, лаунчеры `fcc-*` | **free-claude-code** | Экономия квоты и латентности, ToS-friendly |
| Агрегация free-tier: 34 провайдера / 635 эндпоинтов / ~7.4B токенов/мес, `auto`, `auto:fast/smart`, `fusion`, per-key `RPM/RPD/TPM/TPD` учёт, penalty+decay, AES-256-GCM ключи, unified `feir-...` ключ, signed catalog feed, fallback-chain, `/v1/responses`, `/v1/completions`, `/v1/embeddings`, `/images`, `/audio`, `/v1beta` (Gemini), Ollama-эмуляция, MCP, `setup-*` генераторы | **FreeLLMAPI** (tashfeenahmed) | Один `/v1` на всё, шифрование, самообновляемый каталог |
| 352 провайдера (152 free), 19 стратегий, 4-tier fallback `Subscription→API→Cheap→Free`, `auto` 16-факторный скоринг + LKGP, `context-relay`, `cache-optimized`, `headroom`, `reset-aware`, translation `OpenAI↔Claude↔Gemini↔Responses`, RTK+Caveman компрессия 15–95%, circuit-breaker 3-state, quota-aware scheduling, multi-account round-robin, MCP 110 tools + A2A + REST + webhooks, Memory FTS5+vector, guardrails, evals, TLS stealth, 3-level proxy, Dashboard, 80+ CLI команд, Desktop/PWA | **OmniRoute** (diegosouzapw) | Максимальное покрытие, умный роутинг, продакшн-наблюдаемость |

Итого в FeirRouter:
- **70+ провайдеров из коробки** (union всех трёх + custom OpenAI-compatible: LM Studio, llama.cpp, Ollama, vLLM)
- **20 стратегий роутинга** + per-tier + 4-tier + auto-combo + fusion + pipeline
- **Все wire-форматы**: OpenAI Chat / Responses / Completions, Anthropic Messages, Gemini, Ollama — на одном порту
- **Шифрование ключей, quota-трекинг, circuit-breaker, компрессия, оптимизации, observability, Admin UI, MCP, CLI-лаунчеры для 10+ агентов**

```
Claude Code · Codex · OpenCode · Cline · Cursor · Aider · Gemini CLI · ...
        │  OpenAI / Anthropic / Responses / Gemini / Ollama — один порт :8081
        ▼
┌─────────────────────────────────────────────┐
│ FeirRouter :8081                            │
│ probes → compression → guardrails → routing │
│ tiers(Opus/Sonnet/Haiku/Fable) → 4-tier →   │
│ strategy(20) → circuit-breaker → provider   │
│ translation + thinking + tools + fallback   │
└──────┬──────────────────────────────────────┘
       ├─→ Tier1 Subscription (Claude/Codex/Gemini OAuth)
       ├─→ Tier2 API Key (DeepSeek/Groq/Mistral/NVIDIA/...)
       ├─→ Tier3 Cheap (GLM/MiniMax/...)
       └─→ Tier4 Free (Qoder/Qwen/Kiro/Pollinations/...)
```

## Quick Start (Windows / Linux / Mac)

```powershell
cd C:\Users\EMUL\Desktop\FeirRouter
pip install -r requirements.txt
copy .env.example .env   # впиши ключи
python -m feirrouter --port 8081
# Dashboard: http://127.0.0.1:8081/admin
# API base:  http://127.0.0.1:8081/v1
```

Подключить агента в 1 команду:

```powershell
python -m feirrouter setup-claude   # Claude Code
python -m feirrouter setup-codex    # Codex CLI
python -m feirrouter setup-opencode # OpenCode
python -m feirrouter launch -- claude --help
```

Пример вызова:

```python
from openai import OpenAI
c = OpenAI(base_url="http://127.0.0.1:8081/v1", api_key="feir-твой-ключ")
r = c.chat.completions.create(model="auto", messages=[{"role":"user","content":"hello"}])
print(r.choices[0].message.content)  # + header X-Routed-Via: provider/model
```

```bash
curl http://127.0.0.1:8081/v1/chat/completions \
 -H "Authorization: Bearer feir-..." -H "Content-Type: application/json" \
 -d '{"model":"auto/coding","messages":[{"role":"user","content":"write quicksort"}]}'
```

Модели-алиасы:
- `auto` — баланс (LKGP + 16-факторный скор)
- `auto/coding`, `auto/fast`, `auto/cheap`, `auto/reasoning`, `auto/vision`, `auto/offline`, `auto/chaos`
- `fusion:qwen+deepseek+glm` — параллельный опрос панели + judge-синтез (упрощённо: первый здоровый + пометка)
- ` opus / sonnet / haiku / fable` — тиры Claude Code (маппятся на MODEL_OPUS и т.д.)

## Конфиг (.env)

Смотри `.env.example`. Главное:
- `MODEL`, `MODEL_OPUS`, `MODEL_SONNET`, `MODEL_HAIKU`, `MODEL_FABLE` — фолбэк + per-tier (идея FCC)
- `FEIR_STRATEGY=auto` — одна из 20 (см. `docs/ROUTING.md`)
- `*_API_KEY` / `*_BASE_URL` — ключи 70+ провайдеров (см. `docs/PROVIDERS.md`)
- `FEIR_UNIFIED_KEY` — единый исходящий ключ (`feir-...`), если пуст — сгенерируется
- `FEIR_MASTER_KEY` — пароль для AES-GCM шифрования ключей в SQLite

## Структура

```
feirrouter/
  server.py          # FastAPI: все /v1/* + /admin + /mcp
  config.py          # Settings из env
  providers/base.py  # BaseProvider, OpenAICompatible, AnthropicLike, GeminiLike
  providers/catalog.py # 70+ провайдеров, free-бюджеты
  routing/strategies.py # 20 стратегий
  routing/engine.py  # QuotaLedger + CircuitBreaker + Penalty + Auto-scorer + FallbackChain
  translation/       # formats / thinking / tools
  optimization/      # probes (5 перехватов FCC) / compression (RTK-lite + Caveman-lite)
  security/keys.py   # AES-GCM + unified key
  observability/store.py # SQLite: usage, logs, quota snapshots
  admin/ui.html      # Dashboard: Keys / Chain / Logs / Quota
  cli.py             # setup-*, launch-*, doctor, benchmark
docs/ ARCHITECTURE.md PROVIDERS.md ROUTING.md
tests/ smoke
```

## GitHub — опубликовать свой репозиторий

Локальный git уже проинициализируй и пушь (инструкция ниже в ответе ассистента):

```powershell
git init; git add .; git commit -m "feat: FeirRouter v1 — FCC+FreeLLMAPI+OmniRoute united"
gh repo create FeirRouter --public --source=. --push
# или вручную: создай пустой репо на github.com и:
git remote add origin https://github.com/<ты>/FeirRouter.git; git push -u origin main
```

Лицензия MIT. ToS-friendly: используем только официальные API/ключи, чужие ключи не вшиваем, реверс-инжиниринг не делаем.
