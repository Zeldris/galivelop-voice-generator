# API local de gvoice

Contrato de rutas de la interfaz web (F5.1). Fuente: `gvoice/api_contract.py` (`ROUTES`); `tests/test_ui.py`
comprueba que `gvoice/ui/js/api.js`, el simulador (`?mock=1`) y esta tabla usan exactamente esas rutas. F4 las
implementa; hasta entonces `gvoice ui` responde 501 (`api.not_implemented`) a todas salvo `GET /api/locales/{lang}`.

- Cuerpos y respuestas en JSON, salvo el audio (WAV). Un fallo es `{"error": {"code", "params", "message"}}`, con
  `message` en el idioma pedido (`?lang=es|en`); códigos de `gvoice/locales/*.json` (`error.<código>`).
- `{key}` es la clave de un pedido en **un solo segmento** (`narrator/intro-01` viaja como `narrator%2Fintro-01`).
- Solo se atiende la cabecera `Host` local (403 `api.bad_host`); una ruta con otro método responde 405.

| Ruta | Qué hace |
|---|---|
| `GET /api/health` | Service state: version, worker alive, queue counts |
| `GET /api/locales/{lang}` | All interface texts of a language (gvoice/locales/<lang>.json) |
| `GET /api/projects` | List the registered projects |
| `POST /api/projects` | Register a project from a folder path (body: path) |
| `GET /api/projects/{p}` | One project: root and its galivelop-voices.json config |
| `POST /api/projects/{p}/remove` | Unregister a project (its files stay) |
| `GET /api/projects/{p}/orders` | List orders; query: type=voice|line, chosen=true|false |
| `POST /api/projects/{p}/orders` | Submit an order and queue its takes (body: order, count) |
| `GET /api/projects/{p}/orders/{key}` | One order with its takes, chosen take and stale marks |
| `GET /api/projects/{p}/orders/{key}/sheet` | Design sheet of a voice: instruction text and warnings |
| `POST /api/sheet/check` | Check a design sheet without storing it (body: designSheet) |
| `POST /api/projects/{p}/orders/{key}/attempts` | Queue more takes (body: count, seed) |
| `POST /api/projects/{p}/orders/{key}/attempts/{id}/mark` | Mark a take new|candidate|discarded (body: state) |
| `POST /api/projects/{p}/orders/{key}/attempts/{id}/note` | Set the note of a take (body: text) |
| `GET /api/projects/{p}/orders/{key}/attempts/{id}/audio` | The WAV audio of a take |
| `GET /api/projects/{p}/orders/{key}/attempts/{id}/peaks` | Waveform peaks of a take; query: n=<points> |
| `POST /api/projects/{p}/orders/{key}/choose` | Choose a take (a voice also queues its prints) (body: attempt) |
| `POST /api/projects/{p}/orders/{key}/undo` | Go back to the previously chosen take |
| `GET /api/queue` | List queue entries; query: state=queued|running|done|failed|cancelled |
| `POST /api/queue/{id}/cancel` | Cancel a queued or running entry |
| `POST /api/queue/clear` | Cancel every queued entry, of one project if given (body: project) |
| `GET /api/models` | Model files and their state; query: engine |
| `POST /api/models/verify` | Check size and hash of model files (body: engine, ids) |
| `POST /api/models/fetch` | Download missing model files (body: engine, ids) |
