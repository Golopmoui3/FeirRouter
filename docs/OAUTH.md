# OAuth — подписочные тиры (Tier-1)

FeirRouter умеет ходить в подписки тремя путями. Общее правило: токен лежит в **шифрованном vault**
(`POST /api/keys` или CLI), при запросе расшифровывается в памяти, протухший Google-токен
обновляется сам, остальные — повторным `import`.

## Google (gemini_oauth) — настоящий OAuth2 PKCE

1. Создай OAuth-клиент типа **Desktop app** в Google Cloud Console → APIs & Services → Credentials
   (бесплатно, 5 минут). Понадобится только `client_id` (secret для desktop не нужен).
2. `python -m feirrouter oauth login google --client-id <id>`
   Откроется браузер →同意→ токен упадёт в vault. Флаг `--no-browser` — только URL в терминал.
3. Refresh — автоматический при каждом запросе (`resolve_if_oauth`).

## Claude Code / Codex CLI / Gemini CLI — import своих токенов

Это то же «local login import» из CCR/OmniRoute: читаем **твои же** локальные файлы
официальных CLI **только когда ты сам запускаешь команду** (запуск = согласие):

```powershell
python -m feirrouter oauth import   # claude + codex + gemini, что найдётся
python -m feirrouter oauth status   # источник, срок, refreshable или нет
```

Источники: `~/.claude/.credentials.json`, `~/.codex/auth.json`, `~/.muse/oauth_creds.json`.
Refresh у них проприетарный → при протухании повтори `import` (status честно скажет EXPIRED).

## Как токен ходит в запрос

- `claude_oauth` идёт **нативным** Anthropic `/v1/messages` (`AnthropicMessagesProvider`):
  `Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20`. Обычный `anthropic` — через `x-api-key`.
- Остальные подписки — через их OpenAI-совместимые входы тем же ключом.

## Честные ограничения

- GitHub device-flow **не делаем**: токен OAuth App не даёт `models:read` — для GitHub Models нужен PAT вручную.
- Claude/Codex OAuth через браузер **не реверсим** (недокументировано) — только import.
- Чужие/«позаимствованные» токены — ответственность запускающего (см. README).
