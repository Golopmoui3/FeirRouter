# SYNC — как FeirRouter следит за upstream (честно)

FeirRouter — **реализация с нуля по мотивам** `free-claude-code`, `FreeLLMAPI`, `OmniRoute`,
а не форк. Авто-пулла из их репозиториев нет. Что есть вместо:

1. **Ручная сверка провайдеров** — раз в месяц (или когда upstream релизит):
   - FCC: список бэкендов в README/коде (`providers/`, Admin UI).
   - FreeLLMAPI: каталог на freellmapi.co/models + `server/src/providers/`.
   - OmniRoute: `docs/reference/PROVIDER_REFERENCE.md` + `src/lib/oauth/providers/`.
   - Новое → добавить `ProviderSpec` в `feirrouter/providers/catalog.py` + сид-модели в `MODEL_SEED` + тест в `test_providers_full_union`.
2. **Signed feed** — `POST /api/catalog/sync {url}`: тянет JSON `{models: [...]}`, считает sha256,
   сверяет с `FEIR_CATALOG_PIN`, мержит в `custom_models`. Без pin — мержит с пометкой `unverified`.
   Свой feed можно генерировать скриптом из upstream-источников выше.
3. **Несовместимости**: если upstream меняет формат ключей/протокол — чинится адаптер
   (`providers/base.py`, `translation/`), а не «само обновляется». Это цена независимости от чужих релизов.

Что НЕ покрыто: OAuth browser-флоу подписок, TLS-стелс (wreq-js), десктоп/Electron, i18n.
См. README «Статус проекта».
