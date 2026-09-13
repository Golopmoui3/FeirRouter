# LIVE_TESTS — что проверяется только руками с реальными ключами

Моки покрывают логику, но не сеть, не живые лимиты и не поведение judge на реальных ответах.
Прогонять на **бесплатной** панели (`FEIR_STRATEGY=auto`, chain из free-провайдеров),
чтобы не сжечь платную квоту. Сервер: `python -m feirrouter serve`.

## 1. X-Routed-Via и failover вживую

```powershell
curl http://127.0.0.1:8081/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}' -i | Select-String "X-Routed-Via"
curl http://127.0.0.1:8081/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"fusion","messages":[{"role":"user","content":"compare quicksort and mergesort"}]}' -i | Select-String "X-Routed-Via"
```

Зафиксировать: какие `provider/model` реально отвечали, совпадает ли панель fusion с `GET /api/chain`.
Негатив: временно указать `MODEL=ollama/nonexistent` при выключенной Ollama → в `X-Routed-Via`
должен быть следующий живой провайдер, а в `GET /api/logs` — запись со `status != 200` перед успехом.

## 2. Latency-распределение fusion (p50/p95/p99)

Теория «общее время ≈ max» проверяется 20–30 запросами:

```powershell
python -c "
import time, statistics, httpx
ts = []
for i in range(25):
    t0 = time.time()
    r = httpx.post('http://127.0.0.1:8081/v1/chat/completions',
        json={'model': 'fusion', 'messages': [{'role': 'user', 'content': 'say hi'}]}, timeout=300)
    ts.append((time.time() - t0) * 1000)
    print(i, r.headers.get('X-Routed-Via'), round(ts[-1]), 'ms')
print('p50', round(statistics.median(ts)), 'p95', round(statistics.quantiles(ts, n=100)[94]), 'max', round(max(ts)))
"
```

Ожидание: p95 заметно меньше суммы медиан одиночных запросов к тем же провайдерам.
Если p95 ≈ сумме — fan-out где-то сериализуется, это баг.

## 3. Quota-каскад вживую

Быстро отправить 50+ запросов подряд (см. скрипт выше, `model: auto`, цикл на 60),
затем `GET /api/logs?n=80`: должны быть видны переключения провайдеров после 429
(разные `provider` при одном `strategy`), а не сплошные 502 наружу.

## 4. OAuth-refresh под нагрузкой

Дождаться/форсировать протухание `gemini_oauth` (`oauth status`), затем 5 параллельных
запросов через него. В `GET /api/logs` должна быть **одна** запись `oauth-refresh`
(singleflight), остальные запросы — либо свежий токен, либо failover, но не 5 refresh подряд.
Дополнительно: failover при 401 **один раз** перечитывает токен из vault и повторяет ту же
кандидатуру (покрыто моком `test_oauth_401_reresolves_once`) — вживую проверить, что повтор
уходит с новым токеном, а не со старым (смотреть пару записей в `/api/logs`).

## 5. Judge на расходящихся ответах

```powershell
curl ... -d '{"model":"fusion","messages":[{"role":"user","content":"вопрос с подвохом, где модели обычно расходятся"}]}'
```

Проверить глазами: вердикт не пустой, не склейка кусков, без меток «Candidate N».
Примеры удачных/неудачных вердиктов складывать в этот файл ниже.

## Результаты прогонов

| Дата | П.1 via | П.2 p50/p95 | П.3 каскад | П.4 refresh | П.5 judge | Примечания |
|---|---|---|---|---|---|---|
| _не прогонялось_ | | | | | | |
