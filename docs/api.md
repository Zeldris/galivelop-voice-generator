# API local de gvoice

Contrato de rutas de la interfaz web (F5.1). Fuente: `gvoice/api_contract.py` (`ROUTES`); `tests/test_ui.py`
comprueba que `gvoice/ui/js/api.js`, el simulador (`?mock=1`) y esta tabla usan exactamente esas rutas. F4 las
implementa; hasta entonces `gvoice ui` responde 501 (`api.not_implemented`) a todas salvo `GET /api/locales/{lang}`.

- Cuerpos y respuestas en JSON, salvo el audio (WAV). Un fallo es `{"error": {"code", "params", "message"}}`, con
  `message` en el idioma pedido (`?lang=es|en`); códigos de `gvoice/locales/*.json` (`error.<código>`).
- `{key}` es la clave de un pedido en **un solo segmento** (`narrator/intro-01` viaja como `narrator%2Fintro-01`).
- Solo se atiende la cabecera `Host` local (403 `api.bad_host`); una ruta con otro método responde 405.
- `gvoice ui --host` solo acepta direcciones locales (`127.0.0.1`, `localhost`, `::1`); otra se rechaza sin enlazar
  (`cli.ui_host_not_local`). Con `::1` el servidor escucha en IPv6 y la URL es `http://[::1]:<puerto>/`.
- Un segmento vacío en la ruta (`/api/projects//orders`) es 404 `api.not_found`; una sola barra final se tolera.
- El cuerpo de una petición se lee según `Content-Length` y se descarta mientras F4 no lo use: por encima de 1 MiB, 413
  `api.body_too_large`; un `Content-Length` no numérico o negativo, 400 `api.bad_param`.

| Ruta | Qué hace |
|---|---|
| `GET /api/health` | Service state: version, worker alive, queue counts |
| `GET /api/locales/{lang}` | All interface texts of a language (gvoice/locales/<lang>.json) |
| `GET /api/projects` | List the registered projects |
| `POST /api/projects` | Register a project from a folder path (body: path) |
| `GET /api/projects/{p}` | One project: root and its galivelop-voices.json config |
| `POST /api/projects/{p}/remove` | Unregister a project (its files stay) |
| `GET /api/projects/{p}/orders` | List orders; query: type=voice|line, chosen=true|false |
| `POST /api/projects/{p}/orders` | Submit an order and queue its takes (body: order, count; a voice from a sample queues none and ignores count) |
| `GET /api/projects/{p}/orders/{key}` | One order with its takes, chosen take and stale marks |
| `GET /api/projects/{p}/orders/{key}/sheet` | Design sheet of a voice: instruction text and warnings |
| `POST /api/sheet/check` | Check a design sheet without storing it (body: designSheet) |
| `POST /api/projects/{p}/orders/{key}/attempts` | Queue more takes (body: count, seed) |
| `POST /api/projects/{p}/orders/{key}/attempts/{id}/mark` | Mark a take new|candidate|discarded (body: state) |
| `POST /api/projects/{p}/orders/{key}/attempts/{id}/note` | Set the note of a take (body: text) |
| `POST /api/projects/{p}/orders/{key}/attempts/{id}/rate` | Set the listening sheet of a take (body: marks {criterion: yes|no|null}, note) |
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

## Pruebas sin oído y ficha de escucha en la toma (0.4.4)

- `GET .../orders/{key}`: cada toma trae lo guardado por el núcleo (`checks` con las métricas y `warnings`
  `[{code, params}]`, sin `message`: la interfaz traduce `warning.<code>`; `sampling`) y, además,
  `listening`: una fila por criterio como `listening.view` (`[{id, label, eliminatory, mark}]`, con `label` en el idioma
  pedido y `mark` `yes`, `no` o `null`, «sin oír»); `listeningNote`: el texto de la nota de la ficha (`""` sin nota);
  y `listeningSummary`: `listening.summary` (`{yes, no, total, noIds}` o `null` si no hay marcas ni nota).
  En la toma, `listening` es esa vista y no el `{marks, note, at}` guardado.
- `POST .../attempts/{id}/rate`: cuerpo `{marks: {<criterio>: "yes"|"no"|null}, note}`. Como `orders.rate` y
  `gvoice take rate`: `null` borra la marca (vuelve a «sin oír»), una marca no citada no se toca, `note` ausente no toca
  la nota y `""` la borra; una ficha que queda vacía se borra. Un criterio que no es del proyecto es 400
  `listening.criterion_unknown` (solo se puede borrar su marca si la toma la tiene), una marca que no es `yes`, `no` o
  `null` es 400 `api.bad_param` (`marks`). Responde con la toma, en la forma del detalle de arriba.
- `POST .../choose`: la respuesta lleva `warnings` (`[{code: "listening.eliminatory_failed", params: {ids}, message}]`)
  solo si la toma tiene un «no» en un criterio eliminatorio; elegir ocurre igualmente.
