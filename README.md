# FeirRouter — Ultimate Free LLM Router
![status](https://img.shields.io/badge/status-working-green) ![license](https://img.shields.io/badge/license-MIT-blue) ![providers](https://img.shields.io/badge/providers-100%2B-orange) ![strategies](https://img.shields.io/badge/strategies-20-purple)
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
- **100+ провайдеров из коробки** (полный union FCC 50 + FreeLLMAPI 34 + пул OmniRoute: chat, embeddings, audio, images/video, search + 10 локальных + custom)
- **20 стратегий роутинга** + per-tier + 4-tier + auto-combo + fusion + pipeline
- **Все wire-форматы**: OpenAI Chat / Responses / Completions, Anthropic Messages, Gemini native `/v1beta`, Ollama `/api/*` — на одном порту
- **Шифрованный vault ключей + API**, управление fallback-chain через API, self-updating signed-каталог, guardrails (PII), webhooks, memory, evals, A2A-карточка
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
git clone https://github.com/Golopmoui3/FeirRouter
cd FeirRouter
pip install -r requirements.txt
python -m feirrouter setup     # интерактивный визард: стратегия, MODEL, ключи, проверка связи
python -m feirrouter serve     # старт шлюза
# Dashboard: http://127.0.0.1:8081/admin
# API base:  http://127.0.0.1:8081/v1
```

Без визарда — вручную: `copy .env.example .env` (Windows) / `cp .env.example .env` (Linux/Mac), вписать ключи.

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
- `fusion:qwen+deepseek+glm` — панель топ-3 (сейчас: упорядоченная панель, первый здоровый отвечает; полный параллельный fan-out + judge — roadmap)
- `opus / sonnet / haiku / fable` — тиры Claude Code (маппятся на MODEL_OPUS и т.д., пустой оверрайд → MODEL)

## Сколько реально бесплатных токенов?

Честно: **никакой общей цифры мы не заявляем**. Агрегат зависит только от ключей, которые вобьёшь ты:
`python -m feirrouter doctor` покажет готовые провайдеры, ориентиры бюджетов — в `docs/PROVIDERS.md`
(`free_budget` у каждого + живой статус в `GET /api/providers`).
Цифры upstream-проектов (7.4B у FreeLLMAPI, 1.5B у OmniRoute) — их маркетинговая оценка их покрытия,
а не наша. Плюс дедупликация alias-групп (`kimi`/`moonshot`, `qwen`/`dashscope`/`bailian` делят один
quota-счётчик, см. `UPSTREAM_GROUPS` в `routing/engine.py`) сознательно *уменьшает* сумму — зато не врёт.

## Конфиг (.env)

Смотри `.env.example`. Главное:
- `MODEL`, `MODEL_OPUS`, `MODEL_SONNET`, `MODEL_HAIKU`, `MODEL_FABLE` — фолбэк + per-tier (идея FCC)
- `FEIR_STRATEGY=auto` — одна из 20 (см. `docs/ROUTING.md`)
- `*_API_KEY` / `*_BASE_URL` — ключи 100+ провайдеров (см. `docs/PROVIDERS.md`), либо визард `setup`, либо vault API `POST /api/keys`
- `FEIR_UNIFIED_KEY` — единый исходящий ключ (`feir-...`), если пуст — сгенерируется
- `FEIR_MASTER_KEY` — пароль для AES-GCM шифрования ключей в SQLite

## Структура

```
feirrouter/
  server.py          # FastAPI: /v1/* + /v1beta + Ollama /api/* + media + /admin + /mcp + /api
  config.py          # Settings из env
  providers/base.py  # BaseProvider, OpenAICompatibleProvider, AnthropicLike, GeminiLike
  providers/catalog.py # 100+ провайдеров (union FCC+FreeLLMAPI+OmniRoute), free-бюджеты
  routing/strategies.py # 20 стратегий
  routing/engine.py  # QuotaLedger + CircuitBreaker + Penalty + Auto-scorer + FallbackChain
  translation/       # formats / thinking / tools
  optimization/      # probes (5 перехватов FCC) / compression (RTK-lite + Caveman-lite)
  security/keys.py   # AES-GCM + unified key
  observability/store.py # SQLite: usage, logs, vault, chain, memory, webhooks
  admin/ui.html      # Dashboard: Keys / Chain / Logs / Quota
  cli.py             # setup-визард, setup-*, launch-*, doctor, benchmark
docs/ ARCHITECTURE.md PROVIDERS.md ROUTING.md BENCHMARKS.md
tests/ 33 теста: smoke API + стратегии + ledger/breaker/tiers + failover + пайплайн
```

## Статус проекта

Репозиторий: https://github.com/Golopmoui3/FeirRouter (public, `main`).
Это **реализация с нуля по мотивам** трёх проектов (inspired by + портированная логика), а не форк:
автосинхронизации с upstream нет — сверка вручную через `POST /api/catalog/sync` (signed feed) и `docs/SYNC.md`.

Лицензия MIT. ToS-friendly: используем только официальные API и ключи пользователя, чужие ключи не вшиваем,
реверс-инжиниринг не делаем. Ключи из чужих аккаунтов/«позаимствованные» — ответственность запускающего.
