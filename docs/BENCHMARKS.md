# Benchmarks — FeirRouter pipeline overhead (in-process, без сети)

Measured: `200` iters. Машина: AMD64 (Windows 10), Python 3.14.7. Сеть НЕ включена — это накладные расходы самого роутера.

| Stage | ms/req |
|---|---|
| probes.try_probe_mock | 0.285 |
| compression.L2 (120KB tool output) | 2.702 |
| routing.auto-order (60 cands) | 0.078 |
| translation.oai->anthropic | 0.001 |
| thinking.extract | 0.009 |
| tools.parse | 0.005 |
| **TOTAL** | **3.079** |

Вывод: весь in-process пайплайн — доли миллисекунды; доминирует сеть до провайдера (сотни мс).
Перезамер: `python -m feirrouter benchmark --iters 200 --write`
