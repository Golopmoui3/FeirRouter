# Routing — 20 стратегий + tiers + auto

`FEIR_STRATEGY` (или поле `strategy` в `/v1/chat/completions`):

- `auto` (default) — 16-факторный скор: priority, intelligence, price, penalty, errors, latency, headroom, LKGP, cache, context-fit, task-fit (coding/vision), exploration 10%. `auto/coding`, `auto/fast`, `auto/cheap`, `auto/reasoning`, `auto/vision`, `auto/offline`, `auto/chaos`.
- `lkgp` — sticky к последнему хорошему провайдеру.
- `priority`/`fill-first`/`failover` — порядок fallback-chain (FreeLLMAPI стиль).
- `weighted`, `round-robin`, `p2c`, `least-used`, `random`, `strict-random` — балансировка.
- `cost-optimized` — дешевле первым.
- `headroom` / `reset-window` / `reset-aware` — по остаткам квоты и окнам сброса.
- `context-relay` / `context-optimized` — сессии и большие контексты.
- `cache-optimized` — affinity для prompt-cache.
- `fusion` — панель топ-3 (полный fan-out+judge — roadmap).
- `pipeline` — цепочка шагов (roadmap: выход→вход).

Per-tier (FCC): `opus/sonnet/haiku/fable` в имени модели → `MODEL_OPUS/...` иначе `MODEL`.
4-tier (OmniRoute): внутри цепочки порядок `subscription → api → cheap → free → local`.
Failover: до `FEIR_MAX_ATTEMPTS` (default 20), 429→cooldown 120с penalty+2, 5xx→30с penalty+1, breaker открывает провайдера после 5 ошибок на 60с.
