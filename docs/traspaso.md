<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión, desde `main` en `195bb86`) |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`) cerrada: revisada (fases 1, 2 y 3) y fusionada en `main` por el pull request #4, con confirmación de la persona (2026-11-11). Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | Fase 3 de la revisión de F1: los commits de la fase 2 son todo contenido (`.md`, `content` de `gw.json`), sin código que revisar; marca de revisión con `revisado.sh`. Antes, fase 2 (retro aprobada y aplicada) y fase 1 (17 hallazgos, los medios arreglados); F1 completa |
| **Siguiente paso** | `/clear` y F2 (`docs/plan.md`) en una rama nueva desde `main`, apuntada aquí nada más empezar |
| **Check** | verde (`bash -n` de cada gancho y `unittest`) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-11 — F1.6: `gvoice/cli.py` y `__main__.py` (`python3 -m gvoice`) copiados de `gimg@fa1076e` y adaptados: `project add|list|remove`, `order submit|list|show`, `attempt new|mark|note`, `choose`, `undo`, `queue list|cancel`, `work`, `version`; `--json` y `--lang`; códigos de salida 0/1/2/130. `order submit` muestra los avisos de la ficha; `order list|show` marcan las frases desfasadas (`stale` en las líneas y `staleLines` en las voces, en `--json`). Textos `cli.*` en es/en. `tests/test_cli.py` y `tests/test_e2e.py` (ciclo completo con las huellas de cada `printModels`, desfasada y deshacer). README es/en con el uso. Sin `doctor`, `serve`, `ui` ni estimado (F2-F5).
1. 2026-11-11 — F1.5: `gvoice/{queue,worker,machine_lock}.py` copiados de `gimg@fa1076e` y adaptados, con sus tests. Cola con tres clases de trabajo (`voice`: `design` con la instrucción; `line`: `line` con la huella del modelo de producción, el primero de `models.produce` del perfil, que debe estar en `printModels`, si no `queue.model_not_printed`, y si falta el archivo `worker.print_missing`; `prints`: una huella por modelo de `orders.missing_prints`). `queue.submit_order/new_takes/choose/undo` envuelven `orders` y encolan `prints` solo si a la toma le faltan huellas (sin duplicar uno en cola o en curso). Candado de la máquina `paths.machine_lock_path()` = `<state>/gpu.lock` (`GVOICE_STATE_HOME`, `$XDG_STATE_HOME/galivelop`, `~/.local/state/galivelop`): `flock` exclusivo durante todo el trabajo, sondeado cada 50 ms (ocupado = espera, cancelable, nunca falla); lo suelta el núcleo si el proceso muere. Cada trabajo escribe su línea D16 (`voice_design`, `speech_generation`, `voice_print`).
2. 2026-11-10 — F1.3: `gvoice/orders.py` copiado de `gimg@fa1076e` y adaptado (sin perfiles, composición, texto, plantillas, borradores ni entrega) con sus tests. Pedido por proyecto + clave en `orders/<clave>/@/order.json`; tomas en `@/attempts/<id>|q<entrada>/audio.wav` y huellas en `prints/<modelo>.spk|.rvq`. `submit` devuelve los avisos de `sheet` (no se guardan); `line` exige voz `voice` con referencia elegida (`order.voice_unknown`, `order.voice_not_fixed`); cada toma de frase guarda su `reference`; `is_stale`/`stale_lines` calculan las desfasadas; `missing_prints`, `set_prints`, `add_attempt(spec con result=EngineResult)` para el trabajador. `choose` exige audio (`audioMs`). `paths.max_key()` lee el `maxLength` (100) del esquema común y se quita el tope por segmento (inalcanzable).
3. 2026-11-10 — F1.4: `gvoice/{engine,limits,log}.py` copiados de `gimg@fa1076e` con sus tests (`FakeEngine`, `EngineResult` D16, registro `app.voice.*`, límites).
4. 2026-11-10 — F1.2: `gvoice/sheet.py` (`instruction`, `warnings`, `is_adult`) con sus tests; textos `warning.sheet.*` y `error.sheet.invalid`, `machine.*`, `limit.*`, `engine.*`, `log.*` en es/en.

## Pendiente

- Hallazgos leves de la revisión de F1, sin arreglar en este PR (no vuelven a revisarse en él):
  - `queue.json` borrado o rehecho reinicia `nextId`, y una entrada nueva casa con un intento viejo por `queueEntry` (`worker._take`, carpeta `attempts/q<id>`).
  - Al recuperar una entrada cancelada que ya movió `audio.wav`, el audio queda huérfano (`queue._recover`).
  - Tener audio se decide por `audioMs` y no por el archivo: el motor real de F2 debe dar siempre `audio_ms`.
  - Rendimiento: `order list` hace `list_orders` por voz (cuadrático); `list_orders` recorre también `attempts/`; `FakeEngine` arma las muestras en una lista; `should_cancel` abre una transacción de cola cada 20-50 ms; `production_model` se comprueba dos veces; `_check_key` valida el esquema varias veces.
  - Sin uso en `gvoice/`: `queue.next_queued`, `clear`, `worker_alive`, `machine_lock.busy`, `limits.timeout_s`/`check_memory`/`must_abort`/`available_memory_mb`, `log.estimate`. El vigilante de memoria (D15) es de F2.
  - Las lecturas de la cola toman `worker.lock` compartido, y un sondeo muy seguido puede impedir arrancar `gvoice work` (`worker.already_running`).
- Hallazgos leves de la revisión de F0, sin arreglar en este PR: el mensaje de `propertyNames` sale con «()» vacío cuando el motivo no es un `pattern` (p. ej. un `enum`) y solo cuenta el primer motivo (`gvoice/schema.py`); `i18n.t()` lanza `KeyError` si a un idioma le falta un parámetro del texto y no mira `LANGUAGE`; los commits `81d76f1` y `7cebd24` de F0 tienen `Siguiente:` separado de la atribución por una línea en blanco.
- Escucha del banco y registro del núcleo tras Vulkan: los dos, de la persona (ver «Pendiente» en `docs/plan.md`).
- Para la persona, en `galivelop-image-generator`: su check `bash -n a b c` solo comprueba `a` (R3 de la retro de F0).
- Para proponer al flujo: R3 de `docs/registros/retro-2026-11-11-f1.md`, R2-R3 de `docs/registros/retro-2026-10-25-f0.md`, R2-R4 de `docs/registros/retro-2026-10-25-diseno-voces.md`, y las aplazadas de la retro anterior: rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
