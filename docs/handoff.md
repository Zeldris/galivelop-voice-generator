<!-- galivelop-workflow v0.6.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-5e26fc26-igtd9z` (asignada por la sesión; sigue tras el PR #5, con `main` en `d7d5095`) |
| **Fase / tarea** | F2 Motor real. `qwentts.cpp` aceptado como primer candidato (D18: motores y modelos enchufables; al cerrar F2 se bajan más para comparar). Plan detallado en `docs/plan.md` § «F2 en detalle» (pasos F2.1-F2.6). Presupuesto de compactaciones: 2 (la sesión lleva 1 antes de empezar F2) |
| **Último punto estable** | F2.1: catálogo `qwentts` y `gvoice models` (ver el commit «F2.1» de la rama); check verde, 392 tests |
| **Siguiente paso** | F2.2: `QwenTtsEngine` con motor falso (órdenes, carpeta temporal, `audio_ms`, respaldo de dispositivo, cancelar y tope), a un subagente `implementador` |
| **Check** | verde (`bash -n` de cada gancho y `unittest`) |

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-11-14 — F2.1: catálogo del motor `gvoice/engines/qwentts.json` (commit `5916bf7`, 4 modelos con URL de `Serveurperso/Qwen3-TTS-GGUF`, bytes, sha256 y uso) y su esquema `engine-catalog.schema.json`; `gvoice/models.py` (`load`, `status` con sha256 por bloques solo si el tamaño casa, `fetch` a `<archivo>.part` con comprobación de bytes y sha256 y renombrado atómico; sin dejar `.part` si falla) y `gvoice models list|verify|fetch [--engine] [ids]` (`verify` sale 1 si algo no está `ok`). Errores `models.*`, textos es/en, README es/en y `tests/test_models.py` (servidor local en un hilo). El repo del motor en el catálogo es `ServeurpersoCom/qwentts.cpp` (el que citan los documentos del proyecto); el encargo decía `predict-woo/qwentts.cpp`, por confirmar.
2. 2026-11-14 — Flujo Galivelop-workflow 0.3.0 → 0.6.0 con `/gw-update` (rama `ccr-5e26fc26-igtd9z`): scripts, skills (prefijo `gw-`), ganchos (nuevo `commit-msg`), CI y `.claude/settings.json` (ganchos `Stop` de métricas, guardas de `Read`, `Agent` y GitHub). Rutas en inglés: `docs/traspaso.md` → `docs/handoff.md`, `docs/registros/` → `docs/records/` (`reviewed.txt`), `comprobar.yml` → `check.yml`. `AGENTS.md`, `CLAUDE.md`, `REVIEW.md` y `GLOSSARY.md` fundidos con la plantilla 0.6.0 conservando las reglas y términos del proyecto; notas de skill renombradas. `doctorTestDirsIgnore` deja fuera los tests de `.claude/skills/gw-*` (se prueban en el flujo).
3. 2026-11-11 — F1.6: `gvoice/cli.py` y `__main__.py` (`python3 -m gvoice`) copiados de `gimg@fa1076e` y adaptados: `project add|list|remove`, `order submit|list|show`, `attempt new|mark|note`, `choose`, `undo`, `queue list|cancel`, `work`, `version`; `--json` y `--lang`; códigos de salida 0/1/2/130. `order submit` muestra los avisos de la ficha; `order list|show` marcan las frases desfasadas (`stale` en las líneas y `staleLines` en las voces, en `--json`). Textos `cli.*` en es/en. `tests/test_cli.py` y `tests/test_e2e.py` (ciclo completo con las huellas de cada `printModels`, desfasada y deshacer). README es/en con el uso. Sin `doctor`, `serve`, `ui` ni estimado (F2-F5).
4. 2026-11-11 — F1.5: `gvoice/{queue,worker,machine_lock}.py` copiados de `gimg@fa1076e` y adaptados, con sus tests. Cola con tres clases de trabajo (`voice`: `design` con la instrucción; `line`: `line` con la huella del modelo de producción, el primero de `models.produce` del perfil, que debe estar en `printModels`, si no `queue.model_not_printed`, y si falta el archivo `worker.print_missing`; `prints`: una huella por modelo de `orders.missing_prints`). `queue.submit_order/new_takes/choose/undo` envuelven `orders` y encolan `prints` solo si a la toma le faltan huellas (sin duplicar uno en cola o en curso). Candado de la máquina `paths.machine_lock_path()` = `<state>/gpu.lock` (`GVOICE_STATE_HOME`, `$XDG_STATE_HOME/galivelop`, `~/.local/state/galivelop`): `flock` exclusivo durante todo el trabajo, sondeado cada 50 ms (ocupado = espera, cancelable, nunca falla); lo suelta el núcleo si el proceso muere. Cada trabajo escribe su línea D16 (`voice_design`, `speech_generation`, `voice_print`).
5. 2026-11-10 — F1.3: `gvoice/orders.py` copiado de `gimg@fa1076e` y adaptado (sin perfiles, composición, texto, plantillas, borradores ni entrega) con sus tests. Pedido por proyecto + clave en `orders/<clave>/@/order.json`; tomas en `@/attempts/<id>|q<entrada>/audio.wav` y huellas en `prints/<modelo>.spk|.rvq`. `submit` devuelve los avisos de `sheet` (no se guardan); `line` exige voz `voice` con referencia elegida (`order.voice_unknown`, `order.voice_not_fixed`); cada toma de frase guarda su `reference`; `is_stale`/`stale_lines` calculan las desfasadas; `missing_prints`, `set_prints`, `add_attempt(spec con result=EngineResult)` para el trabajador. `choose` exige audio (`audioMs`). `paths.max_key()` lee el `maxLength` (100) del esquema común y se quita el tope por segmento (inalcanzable).

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
- Para proponer al flujo: R1-R5 de `docs/records/retro-2026-11-14-gw-update.md`, R3 de `docs/records/retro-2026-11-11-f1.md`, R2-R3 de `docs/records/retro-2026-10-25-f0.md`, R2-R4 de `docs/records/retro-2026-10-25-diseno-voces.md`, y las aplazadas de la retro anterior: rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recover.py --state`.
