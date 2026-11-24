<!-- galivelop-workflow v0.8.2 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/via1-clonado` (desde `main` en `17b4255`, 2026-11-17; `origin/main` fusionado en `aeca90d`, flujo v0.8.2 y F5.9, el 2026-11-24) |
| **Fase / tarea** | **0.3.0** (`docs/plan.md` § Versiones): D19 vía 1, capa 1 (clonado desde referencia peninsular) + B1 (barrido de leves de `gvoice/effects.py`). Investigación de partida: `docs/investigacion/2026-11-17-motores-via1-deck.md` |
| **Último punto estable** | 0.2.0 publicada: PR #7 fusionado con CI de GitHub en verde (vuelve a funcionar), `v0.1.0` y `v0.2.0` con su release. Retro: `docs/records/retro-2026-11-17-v0-2-0.md`. Conectores MCP Claude Docs y easel desactivados por la persona. **Limpieza 2026-11-21:** borrados de `~/.local/share/galivelop-voice` Chatterbox (modelos, venv, compilación), StyleTTS2-Celtia y aHoTTS; quedan Qwen, whisper, `verif`, Matcha-Celtia y Nós (35→12 GiB) |
| **Siguiente paso** | **Generación de audio parada** (la persona, 2026-11-24). 0.3.0: B1, B2 y C1 hechos; diseño de clonado y filtro con las decisiones de la persona en `docs/plan.md` § «0.3.0 en detalle». C1, C2 y C3 hechos (`clip` en esquema y `orders`; `gvoice voice clone` y la interfaz; `say` y `split` en `line`). Siguiente: **C8** (huella sola); C4-C7 (filtro) pueden ir en otro PR |
| **Check** | verde salvo dos tests que ya fallan en `main` en la Deck (`test_install…no_compiler_and_no_flatpak` 127 y `test_peaks…is_fast` por tiempo) |

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-11-15 — F5.2: vistas de proyectos y pedidos. `ui/js/components/projects-view.js` (lista, registrar por ruta de carpeta, quitar con `confirm` y aviso de que los archivos se quedan), `project-view.js` (pedidos con filtros `type` = todos|voice|line y `chosen` = todos|true|false que quedan en el hash con `router.replaceHash`, sin repintar; fila con clave, tipo, voz, texto, tomas y «✓ Elegida · toma N» o «Sin elegir»; carga, vacío y error) y `new-order.js` (diálogo: `voice` con clave, texto de prueba, los 12 campos de la ficha y `extra` «nombre: texto» por línea; `line` con voz del `config` y de los pedidos `voice`, id y texto; semilla y tomas). Lógica pura sin DOM en `ui/js/order-model.js` (`filtersFromQuery`, `filtersToQuery`, `orderSummary`, `parseExtra`, `lineKey`, `buildOrder`); `router.to.project(p, tab, query)` y `replaceHash`. `app.js`: cada vista devuelve `{node, cleanup}` y `render` llama a `cleanup` (arregla el `current.cleanup` que nunca existía). Textos es/en `ui.projects.*`, `ui.project.*` y `ui.newOrder.*`; estilos en `components.css`. 10 tests nuevos en `tests/test_ui_js.py` (los pedidos construidos se validan en Python con `gvoice/schema.py` contra `order.schema.json`; filtros ida y vuelta; el simulador filtra por `type` y `chosen`). Recorrido con `?mock=1` en Chrome a 1280 y 360 px. Falta: «con el motor falso» (cuando F4 implemente la API); los avisos de la ficha son F5.3. Check verde.
2. 2026-11-15 — F5.1: `gvoice/ui/` copiada de `gimg@46248251` (index, CSS, fuentes, núcleo JS, toast/confirm/tema) con acento `#d9467a`; `gvoice/api_contract.py` (`ROUTES`, 24 rutas) + `docs/api.md`; `gvoice/server.py` (CSP estricta, no-cache, 501 en `/api/*`) y `gvoice ui`; simulador `ui/mock/api-mock.js`; `tests/test_ui.py`. Desvío: `--accent-text` claro `#ce3c71` da 4,28:1 sobre `--surface-2` (bajo AA), el test solo exige los pares que pasan.
3. 2026-11-15 — Hoja de ruta de F5 (interfaz) en `docs/plan.md` § «F5 en detalle»: avance 0 %; estilo de la hoja de voces de GVIG (`galivelop-image-generator@46248251`, bloques vigentes; solo cambia el acento `#d9467a`/`#ce3c71`), código a copiar de `gimg/ui` (vanilla, CSP), audio de cero (ningún front tiene reproductor), pasos F5.0-F5.8 [P] y lo que hay que pedir a la persona (logo, favicon, iconos, nombres de tokens, dudas 3 y 4 de la hoja). Propuesta: F4+F5 juntas tras F3. Sin código. Check verde.
4. 2026-11-14 — F2.5: `gvoice bench` (`gvoice/bench.py` + orden en `cli.py`; D18, cualquier motor que implemente `Engine`). Matriz por dispositivo: diseñar (modelo de diseño del perfil, frases corta y larga, semilla fija, por defecto 7), fijar (una huella por modelo Base, de la toma de diseño larga) y producir (modelo × corta/larga); `--models` (por defecto `models.produce`), `--devices` (por defecto `engine.device`), `--steps`, `--seed`, `--out` (por defecto `<datos>/bench/<AAAA-MM-DD-HHMMSS>/`), `--json`. Toma el candado de la máquina todo el banco y espera `minFreeMemoryMb` antes de cada paso con un motor que vigila memoria. Los trabajos llevan `no_fallback=True` (campo nuevo de `DesignJob`/`LineJob`/`PrintJob`; `QwenTtsEngine._attempts` no usa `fallbackDevice`): cada fila es el dispositivo pedido. Un paso que falla queda con su código y mensaje y el banco sigue; los pasos sin entrada (toma o huella ausente: falló o no estaba en `--steps`; los archivos del paso se borran antes de correrlo) quedan «saltado» (`bench.missing_input`). SIGINT pone una marca (el paso en curso queda «cancelado», se escriben los archivos, salida 130). `bench.json` (se reescribe tras cada paso) y `bench.md` (cabecera: fecha, motor, commit del catálogo, perfil, CPU, memoria; tabla del doc con coma decimal y `-`). Sale 1 si algún paso no está ok (también «saltado»). Las frases del banco no estaban como texto: frase corta («Amanece en la Hondonada y no se oye nada.») y larga (~160 caracteres, obeliscos) en `bench.PHRASES`. Textos es/en y README es/en. `tests/test_bench.py`: 22 tests con `FakeEngine` y con `QwenTtsEngine` + `fake_qwentts.py`. Falta: F2.6 en la Deck (la persona). Check verde.
5. 2026-11-14 — Arreglos de la revisión de bloque F2.1-F2.3 (6 hallazgos): el resultado lleva el dispositivo como el perfil (`cpu`; `device_arg` solo en el argv); un proceso muerto por señal no lanza el respaldo y, con vigilante, este exige `minFreeMemoryMb` otra vez (si no, error del primer intento y nota); el motor hereda el descriptor del candado (`machine_lock.held_fds`, `pass_fds`) para que un motor huérfano siga ocupando la máquina, y `worker.run` no limpia `.qwentts-*` si el candado está ocupado; `EngineError`/`EngineTimeout`/`Cancelled` llevan `stats` (`min_free_mb`, `peak_rss_mb`) y el trabajador las pasa al registro (`log.record_for(stats=)`); pico de RSS exacto con `os.wait4` (`ru_maxrss`; `proc.returncode` fijado a mano con `waitstatus_to_exitcode`; `VmHWM` solo si `wait4` no da nada); tests del vigilante sin reloj (`WATCH_S` parcheable, lecturas de memoria inyectadas). Check verde.
## Pendiente

Lo pendiente está en [`docs/records/pending.md`](records/pending.md); se añade y se quita allí.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
