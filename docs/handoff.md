<!-- galivelop-workflow v0.9.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-2447cc83-5kxr8j` (asignada por la sesión; desde `main` tras el PR #12 y la vendorización de `grun`) |
| **Fase / tarea** | **R3 (adoptar `grun`), pasos 1 y 2 hechos** (detalle en «Hecho»). Pendiente: paso 3, `worker` → `grun.worker.Worker` (el script de desalojo de Ollama no existe en gvoice: nada que retirar) |
| **Último punto estable** | R3 paso 2 (commits `refactor(R3)` y `feat(R3)` de los textos `queue.*`): suite completa en verde (764 tests), tests nuevos rojos sin el arreglo |
| **Siguiente paso** | R3 paso 3: `worker` → `grun.worker.Worker`. F2.6 sigue esperando a la Deck. Antes de `main`, revisión de bloque (el bloque de R3 pasa de 1000 líneas) |
| **Check** | verde (`bash -n` de cada gancho, `unittest` 764 tests y `ci-local.py --validate`) |

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-11-27 — R3 paso 2: `gvoice/queue.py` sobre `grun.queue.Queue` (sin cabecera «Copiado de gimg»). Propio: tipos voice/line/prints, `production_model`, servicios sobre `orders`, `enqueue_prints` (candado `queue.prints`: grun no tiene «encolar salvo que»), `clean_pending` del audio, `error_text`/`entry_view` con textos de gvoice; `GrunError` sale como `GvoiceError`. Forma de las entradas intacta (`tests/fixtures/queue-views-main.json`, de `origin/main`; solo se añaden `position` y `orphanCount`; las tomas no son lote); queue.json antiguo sin migrar. Por diseño de grun: dos orfandades fallan la entrada (`queue.orphaned`); un `kind` desconocido ya no es `queue.corrupt`. Textos es/en de los `queue.*` de grun. Suite en verde (764).
2. 2026-11-15 — F5.2: vistas de proyectos y pedidos. `ui/js/components/projects-view.js` (lista, registrar por ruta de carpeta, quitar con `confirm` y aviso de que los archivos se quedan), `project-view.js` (pedidos con filtros `type` = todos|voice|line y `chosen` = todos|true|false que quedan en el hash con `router.replaceHash`, sin repintar; fila con clave, tipo, voz, texto, tomas y «✓ Elegida · toma N» o «Sin elegir»; carga, vacío y error) y `new-order.js` (diálogo: `voice` con clave, texto de prueba, los 12 campos de la ficha y `extra` «nombre: texto» por línea; `line` con voz del `config` y de los pedidos `voice`, id y texto; semilla y tomas). Lógica pura sin DOM en `ui/js/order-model.js` (`filtersFromQuery`, `filtersToQuery`, `orderSummary`, `parseExtra`, `lineKey`, `buildOrder`); `router.to.project(p, tab, query)` y `replaceHash`. `app.js`: cada vista devuelve `{node, cleanup}` y `render` llama a `cleanup` (arregla el `current.cleanup` que nunca existía). Textos es/en `ui.projects.*`, `ui.project.*` y `ui.newOrder.*`; estilos en `components.css`. 10 tests nuevos en `tests/test_ui_js.py` (los pedidos construidos se validan en Python con `gvoice/schema.py` contra `order.schema.json`; filtros ida y vuelta; el simulador filtra por `type` y `chosen`). Recorrido con `?mock=1` en Chrome a 1280 y 360 px. Falta: «con el motor falso» (cuando F4 implemente la API); los avisos de la ficha son F5.3. Check verde.
3. 2026-11-15 — F5.1: `gvoice/ui/` copiada de `gimg@46248251` (index, CSS, fuentes, núcleo JS, toast/confirm/tema) con acento `#d9467a`; `gvoice/api_contract.py` (`ROUTES`, 24 rutas) + `docs/api.md`; `gvoice/server.py` (CSP estricta, no-cache, 501 en `/api/*`) y `gvoice ui`; simulador `ui/mock/api-mock.js`; `tests/test_ui.py`. Desvío: `--accent-text` claro `#ce3c71` da 4,28:1 sobre `--surface-2` (bajo AA), el test solo exige los pares que pasan.
4. 2026-11-15 — Hoja de ruta de F5 (interfaz) en `docs/plan.md` § «F5 en detalle»: avance 0 %; estilo de la hoja de voces de GVIG (`galivelop-image-generator@46248251`, bloques vigentes; solo cambia el acento `#d9467a`/`#ce3c71`), código a copiar de `gimg/ui` (vanilla, CSP), audio de cero (ningún front tiene reproductor), pasos F5.0-F5.8 [P] y lo que hay que pedir a la persona (logo, favicon, iconos, nombres de tokens, dudas 3 y 4 de la hoja). Propuesta: F4+F5 juntas tras F3. Sin código. Check verde.
5. 2026-11-14 — F2.5: `gvoice bench` (`gvoice/bench.py` + orden en `cli.py`; D18, cualquier motor que implemente `Engine`). Matriz por dispositivo: diseñar (modelo de diseño del perfil, frases corta y larga, semilla fija, por defecto 7), fijar (una huella por modelo Base, de la toma de diseño larga) y producir (modelo × corta/larga); `--models` (por defecto `models.produce`), `--devices` (por defecto `engine.device`), `--steps`, `--seed`, `--out` (por defecto `<datos>/bench/<AAAA-MM-DD-HHMMSS>/`), `--json`. Toma el candado de la máquina todo el banco y espera `minFreeMemoryMb` antes de cada paso con un motor que vigila memoria. Los trabajos llevan `no_fallback=True` (campo nuevo de `DesignJob`/`LineJob`/`PrintJob`; `QwenTtsEngine._attempts` no usa `fallbackDevice`): cada fila es el dispositivo pedido. Un paso que falla queda con su código y mensaje y el banco sigue; los pasos sin entrada (toma o huella ausente: falló o no estaba en `--steps`; los archivos del paso se borran antes de correrlo) quedan «saltado» (`bench.missing_input`). SIGINT pone una marca (el paso en curso queda «cancelado», se escriben los archivos, salida 130). `bench.json` (se reescribe tras cada paso) y `bench.md` (cabecera: fecha, motor, commit del catálogo, perfil, CPU, memoria; tabla del doc con coma decimal y `-`). Sale 1 si algún paso no está ok (también «saltado»). Las frases del banco no estaban como texto: frase corta («Amanece en la Hondonada y no se oye nada.») y larga (~160 caracteres, obeliscos) en `bench.PHRASES`. Textos es/en y README es/en. `tests/test_bench.py`: 22 tests con `FakeEngine` y con `QwenTtsEngine` + `fake_qwentts.py`. Falta: F2.6 en la Deck (la persona). Check verde.
## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
