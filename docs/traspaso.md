<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión, desde `main` en `195bb86`) |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`), en marcha. Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | F1.5 `queue`, `worker` y candado de la máquina; antes F1.3 `orders`, F1.4 `engine`/`limits`/`log`, F1.2 `sheet` |
| **Siguiente paso** | F1.6 `cli` y el test del ciclo completo (`docs/plan.md` § «F1 en detalle»); usa `queue.submit_order`/`new_takes`/`choose`/`undo` (estos dos encolan `prints`), `queue.cancel`/`clear`/`list_entries` y `worker.run` |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 328 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-11 — F1.5: `gvoice/{queue,worker,machine_lock}.py` copiados de `gimg@fa1076e` y adaptados, con sus tests. Cola con tres clases de trabajo (`voice`: `design` con la instrucción; `line`: `line` con la huella del modelo de producción, el primero de `models.produce` del perfil, que debe estar en `printModels`, si no `queue.model_not_printed`, y si falta el archivo `worker.print_missing`; `prints`: una huella por modelo de `orders.missing_prints`). `queue.submit_order/new_takes/choose/undo` envuelven `orders` y encolan `prints` solo si a la toma le faltan huellas (sin duplicar uno en cola o en curso). Candado de la máquina `paths.machine_lock_path()` = `<state>/gpu.lock` (`GVOICE_STATE_HOME`, `$XDG_STATE_HOME/galivelop`, `~/.local/state/galivelop`): `flock` exclusivo durante todo el trabajo, sondeado cada 50 ms (ocupado = espera, cancelable, nunca falla); lo suelta el núcleo si el proceso muere. Cada trabajo escribe su línea D16 (`voice_design`, `speech_generation`, `voice_print`).
1. 2026-11-10 — F1.3: `gvoice/orders.py` copiado de `gimg@fa1076e` y adaptado (sin perfiles, composición, texto, plantillas, borradores ni entrega) con sus tests. Pedido por proyecto + clave en `orders/<clave>/@/order.json`; tomas en `@/attempts/<id>|q<entrada>/audio.wav` y huellas en `prints/<modelo>.spk|.rvq`. `submit` devuelve los avisos de `sheet` (no se guardan); `line` exige voz `voice` con referencia elegida (`order.voice_unknown`, `order.voice_not_fixed`); cada toma de frase guarda su `reference`; `is_stale`/`stale_lines` calculan las desfasadas; `missing_prints`, `set_prints`, `add_attempt(spec con result=EngineResult)` para el trabajador. `choose` exige audio (`audioMs`). `paths.max_key()` lee el `maxLength` (100) del esquema común y se quita el tope por segmento (inalcanzable).
2. 2026-11-10 — F1.4: `gvoice/{engine,limits,log}.py` copiados de `gimg@fa1076e` con sus tests (`FakeEngine`, `EngineResult` D16, registro `app.voice.*`, límites).
3. 2026-11-10 — F1.2: `gvoice/sheet.py` (`instruction`, `warnings`, `is_adult`) con sus tests; textos `warning.sheet.*` y `error.sheet.invalid`, `machine.*`, `limit.*`, `engine.*`, `log.*` en es/en.
4. 2026-11-10 — F1.1: `gvoice/{errors,paths,fsutil,projects}.py` con sus tests. Variables `GVOICE_CONFIG_HOME`/`GVOICE_DATA_HOME`/`GVOICE_MODELS_HOME`, carpetas `galivelop-voice`, `paths.engine_dir()`; `GvoiceError`; `__version__ = "0.1.0"` en `gvoice/__init__.py`.

## Pendiente

- Hallazgos leves de la revisión de F0, sin arreglar en este PR: el mensaje de `propertyNames` sale con «()» vacío cuando el motivo no es un `pattern` (p. ej. un `enum`) y solo cuenta el primer motivo (`gvoice/schema.py`); `i18n.t()` lanza `KeyError` si a un idioma le falta un parámetro del texto y no mira `LANGUAGE`; los commits `81d76f1` y `7cebd24` de F0 tienen `Siguiente:` separado de la atribución por una línea en blanco.
- Escucha del banco y registro del núcleo tras Vulkan: los dos, de la persona (ver «Pendiente» en `docs/plan.md`).
- Para la persona, en `galivelop-image-generator`: su check `bash -n a b c` solo comprueba `a` (R3 de la retro de F0).
- Para proponer al flujo: R2-R3 de `docs/registros/retro-2026-10-25-f0.md`, R2-R4 de `docs/registros/retro-2026-10-25-diseno-voces.md`, y las aplazadas de la retro anterior: rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
