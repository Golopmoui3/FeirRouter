# Architecture — FeirRouter

```
clients (Claude Code/Codex/OpenCode/Cline/Cursor/Aider/Gemini CLI/...)
 → FastAPI :8081 (/v1/* + /admin + /mcp)
 → probes (5 FCC-перехватов) → compression (RTK-lite+Caveman-lite)
 → tier resolve (MODEL_OPUS/SONNET/HAIKU/FABLE)
 → chain build (4-tier Subscription→API→Cheap→Free→Local) × strategy(20)
 → for each candidate: ledger.allow → provider.chat → success? log : fail+cooldown+breaker → next
 → thinking/tools normalization → X-Routed-Via
 → SQLite observability (requests/kv)
```

- `providers/`: `BaseProvider` ABC (FCC), `OpenAICompatibleProvider` default executor (OmniRoute DefaultExecutor), `catalog.py` — 60+ specs + MODEL_SEED.
- `routing/strategies.py`: 20 стратегий (OmniRoute 19 + failover FreeLLMAPI).
- `routing/engine.py`: QuotaLedger RPM/RPD/TPM/TPD + penalty decay (FreeLLMAPI), CircuitBreaker 3-state (OmniRoute), TierRouter (FCC×OmniRoute).
- `translation/`: OpenAI↔Anthropic↔Gemini↔Responses, thinking-блоки, heuristic tool parser.
- `optimization/`: probes + compression.
- `security/keys.py`: AES-256-GCM + unified `feir-` ключ.
- `observability/store.py`: SQLite.
- `server.py`: все wire-форматы на одном порту. `cli.py`: setup-*/launch/doctor.
