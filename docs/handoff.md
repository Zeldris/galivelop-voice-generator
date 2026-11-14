<!-- galivelop-workflow v0.6.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-5e26fc26-igtd9z` (asignada por la sesión; sigue tras el PR #5, con `main` en `d7d5095`) |
| **Fase / tarea** | F2 Motor real. `qwentts.cpp` aceptado como primer candidato (D18: motores y modelos enchufables; al cerrar F2 se bajan más para comparar). Plan detallado en `docs/plan.md` § «F2 en detalle» (pasos F2.1-F2.6). Presupuesto de compactaciones: 2 (la sesión lleva 1 antes de empezar F2) |
| **Último punto estable** | F2.4: `instalar.sh` (ver el commit «F2.4» de la rama); check verde |
| **Siguiente paso** | F2.5: `gvoice bench` y su tabla (con el motor falso). F2.6 (instalar y probar en la Deck) es de la persona |
| **Check** | verde (`bash -n` de cada gancho y `unittest`) |

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-11-14 — F2.4: `instalar.sh` (D17; bash, `set -euo pipefail`, sin root, idempotente). Entorno por `/.flatpak-info`/`FLATPAK_ID` (flatpak: compila directo y prueba con `flatpak-spawn --host`), `cmake`+`g++`+`git` (native) o `flatpak` (steamos: `flatpak run --user --filesystem=<engine> --command=<x> org.freedesktop.Sdk//25.08`, instalándolo si falta); `GVOICE_INSTALL_ENV` lo fuerza, más `GVOICE_INSTALL_SDK`, `GVOICE_INSTALL_SPIRV`, `GVOICE_INSTALL_JOBS`. Repo, commit y `<datos>/engine` salen de `gvoice` (`models.load`, `paths.engine_dir`), sin duplicar. Clona en `engine/src`, checkout del commit y submódulos; SPIRV-Headers `fbf86836` en `engine/deps/prefix` (salvo native con cabeceras del sistema); CPU con `-DGGML_BLAS=OFF` y Vulkan con `-DGGML_VULKAN=ON -DCMAKE_PREFIX_PATH -DCMAKE_CXX_FLAGS=-I`, ambos con rpath `$ORIGIN` (build e install); `-B engine/bin-cpu|bin-vulkan` y un paso que reúne `qwen-tts`, `qwen-codec`, `tts-server` y los `.so` en la raíz si cmake los dejó en un subdirectorio. Prueba `qwen-tts --help` de cada carpeta (falla con ≥126 o «error while loading shared libraries»), `models fetch` + `verify`, y al final dice cómo activar `GVOICE_ENGINE=qwentts`. Opciones `--cpu-only`, `--skip-models`, `--dry-run` (líneas `DRY-RUN: <orden>`, sin tocar disco). `tests/test_install.py`: 20 tests (órdenes por entorno, rpath literal, ejecución real con `git`/`cmake` falsos, idempotencia, fallo de arranque); incluye `bash -n instalar.sh`. Falta: correrlo en la Deck (F2.6, la persona); `bash -n instalar.sh` no está en `check` de `.claude/gw.json` (protegido; ver «Pendiente»).
2. 2026-11-14 — F2.3: vigilante de memoria (D15). Antes de empezar, con un motor que vigila (`Engine.watches_memory`; `QwenTtsEngine(watch_memory=True)`, lo que construye `get_engine`; el falso no), el trabajador espera con el candado de la máquina ya tomado (así otro generador no se come la memoria entre la comprobación y el arranque) a que `MemAvailable` ≥ `minFreeMemoryMb` (`worker._wait_for_memory`, sondeo de 0,5 s, cancelable, nunca falla por eso; el motivo sale una vez por stderr, `worker.waiting_memory`). Durante la ejecución `engine_qwentts.MemoryWatch` (cada 0,5 s, muestrea al primer tick) lanza `EngineError("engine.low_memory", free, min)` por debajo de `watchMemoryMb` (mata el grupo, sin respaldo), y lleva el mínimo libre y el pico de RSS (`VmHWM`, `None` si no se lee) a `EngineResult.min_free_mb`/`peak_rss_mb` y a la línea D16 (`app.voice.min_free_mb`, `app.voice.peak_rss_mb`). Rutas sustituibles: `GVOICE_MEMINFO` y `GVOICE_PROC_STATUS` (con `{pid}`). Al arrancar, `worker.clean_workdirs` borra las `.qwentts-*` de `<datos>/projects` que dejó un SIGKILL. `limits.check_memory/must_abort/available_memory_mb/timeout_s` ya se usan. Textos `error.engine.low_memory` y `worker.waiting_memory` es/en. Un abortado por memoria no lleva el mínimo/pico en el registro (no hay resultado; los valores van en el mensaje). Tests nuevos: 17 (motor, trabajador, registro, límites); el motor falso gana `FAKE_QT_SLEEP_S`.
3. 2026-11-14 — F2.2: `gvoice/engine_qwentts.py` (`QwenTtsEngine`, `GVOICE_ENGINE=qwentts`): un proceso por intento en su propia sesión (cancelar y tope `timeoutS` matan el grupo con `killpg`), todo a una carpeta temporal junto a la salida y movido solo tras leer el `.wav` con `wave` (`audio_ms` siempre del archivo; `.wav` ausente, ilegible o vacío es `engine.bad_audio`); `design` (VoiceDesign + `--instruct`), `line` (`--ref-spk/--ref-rvq/--ref-text` con la RUTA de un archivo temporal) y `voiceprint` (`qwen-codec` sobre una copia del wav, mueve `.spk/.rvq`). Binarios en `<datos>/engine/bin-vulkan|bin-cpu/` (`GVOICE_QWENTTS_BIN` los sustituye). Respaldo: sale ≠0 sin archivo en 30 s (`STARTUP_WINDOW_S`) → una repetición en `fallbackDevice`; el dispositivo usado, el commit del catálogo y el modelo van en el `EngineResult`. Gancho del vigilante: `QwenTtsEngine(on_tick=proc -> None)`, cada 50 ms, puede lanzar `EngineError` (mata el proceso, sin respaldo). `check_configured`/`get_engine` aceptan `qwentts` y fallan con `engine.binary_missing` / `engine.model_missing` (códigos nuevos con es/en; piden el codec, el modelo de diseño y el primero de `produce`). `DesignJob`/`LineJob`/`PrintJob` ganan `language` (por defecto `Spanish`) y `LineJob.reference_text` (el trabajador lo pasa). Motor falso `tests/fake_qwentts.py` y `tests/test_engine_qwentts.py` (31 tests, ~3 s).
4. 2026-11-14 — F2.1: catálogo del motor `gvoice/engines/qwentts.json` (commit `5916bf7`, 4 modelos con URL de `Serveurperso/Qwen3-TTS-GGUF`, bytes, sha256 y uso) y su esquema `engine-catalog.schema.json`; `gvoice/models.py` (`load`, `status` con sha256 por bloques solo si el tamaño casa, `fetch` a `<archivo>.part` con comprobación de bytes y sha256 y renombrado atómico; sin dejar `.part` si falla) y `gvoice models list|verify|fetch [--engine] [ids]` (`verify` sale 1 si algo no está `ok`). Errores `models.*`, textos es/en, README es/en y `tests/test_models.py` (servidor local en un hilo). El repo del motor en el catálogo es `ServeurpersoCom/qwentts.cpp` (el que citan los documentos del proyecto); el encargo decía `predict-woo/qwentts.cpp`, por confirmar.
5. 2026-11-14 — Flujo Galivelop-workflow 0.3.0 → 0.6.0 con `/gw-update` (rama `ccr-5e26fc26-igtd9z`): scripts, skills (prefijo `gw-`), ganchos (nuevo `commit-msg`), CI y `.claude/settings.json` (ganchos `Stop` de métricas, guardas de `Read`, `Agent` y GitHub). Rutas en inglés: `docs/traspaso.md` → `docs/handoff.md`, `docs/registros/` → `docs/records/` (`reviewed.txt`), `comprobar.yml` → `check.yml`. `AGENTS.md`, `CLAUDE.md`, `REVIEW.md` y `GLOSSARY.md` fundidos con la plantilla 0.6.0 conservando las reglas y términos del proyecto; notas de skill renombradas. `doctorTestDirsIgnore` deja fuera los tests de `.claude/skills/gw-*` (se prueban en el flujo).

## Pendiente

- Proponer a la persona añadir `bash -n instalar.sh` a `check` de `.claude/gw.json` y a `.github/workflows/check.yml` (`.claude/` está protegido); mientras, `tests/test_install.py` lo corre.
- Hallazgos leves de la revisión de F1, sin arreglar en este PR (no vuelven a revisarse en él):
  - `queue.json` borrado o rehecho reinicia `nextId`, y una entrada nueva casa con un intento viejo por `queueEntry` (`worker._take`, carpeta `attempts/q<id>`).
  - Al recuperar una entrada cancelada que ya movió `audio.wav`, el audio queda huérfano (`queue._recover`).
  - Tener audio se decide por `audioMs` y no por el archivo: `QwenTtsEngine` (F2.2) lo da siempre, leído del `.wav`.
  - Rendimiento: `order list` hace `list_orders` por voz (cuadrático); `list_orders` recorre también `attempts/`; `FakeEngine` arma las muestras en una lista; `should_cancel` abre una transacción de cola cada 20-50 ms; `production_model` se comprueba dos veces; `_check_key` valida el esquema varias veces.
  - Sin uso en `gvoice/`: `queue.next_queued`, `clear`, `worker_alive`, `log.estimate`. (`machine_lock.busy` solo lo usan los tests.)
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
