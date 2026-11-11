<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión; reiniciada desde `main` en `5f67bd4` tras fusionar F1) |
| **Fase / tarea** | F2 Motor real (`docs/plan.md` § «F2 en detalle»), pasos F2.1-F2.6. La escucha del banco sigue pendiente de la persona: F2 avanza con lo que no depende de ella. Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | F2.1-F2.4 fusionadas y revisadas |
| **Siguiente paso** | F2.5 (`gvoice bench` y `gvoice doctor`) en un subagente; luego F2.6 (README) |
| **Check** | verde (`bash -n` de cada gancho y de `instalar.sh`, y `unittest`) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-11 — F2.3: `gvoice/qwentts.py` (`QwenEngine`, `GVOICE_ENGINE=qwentts`): `design` y `line` con `qwen-tts` (texto por stdin, `--ref-text` a un archivo temporal), `voiceprint` con `qwen-codec` sobre una copia de la toma; un proceso por intento con `runner.run`; reserva una vez a `fallbackDevice` si sale con código distinto de 0, con el tiempo contado desde el primer intento; se saltan los dispositivos que no lista `install.json` (`engine.device_not_installed`, arreglo de la revisión); `cpu` se pasa como `CPU` (ggml). Wav comprobado con `wave` antes de colocarlo; errores `engine.not_installed`, `engine.exit` (cola de stderr), `engine.output_missing`, `engine.bad_audio`. `tests/test_qwentts.py` (20 tests).
1. 2026-11-11 — F2.4: `instalar.sh` (`--ayuda`, `--solo-cpu`, `--sin-modelos`, `--plan`): compila qwentts.cpp en el commit fijado directo, en el SDK de Flatpak (`flatpak run --user`) o dentro del sandbox (pruebas con `flatpak-spawn --host`); `bin-cpu/` y `bin-vulkan/` con rpath `$ORIGIN`; modelos con sha256 (descarga a `.part` y `mv`); prueba de arranque (un Vulkan que no arranca sale de `install.json`; la carga del códec solo avisa). `bash -n instalar.sh` entra en el check. `tests/test_instalar.py` (11 tests). Compilación de CPU probada en el contenedor.
2. 2026-11-11 — F2.1: `language` opcional en `galivelop-voices.json` (por defecto `auto`, se pasa a `--lang`), `DesignJob.language`, `LineJob.language` y `LineJob.ref_text` (texto de la toma de referencia) desde el trabajador; `gvoice/install.py` (binarios por dispositivo, modelos y códec con tamaño y sha256 del banco, `install.json`, `ENGINE_COMMIT`), que delega en `paths.engine_dir`/`models_dir` (`GVOICE_MODELS_HOME`). Una toma de diseño con el proyecto quitado falla ahora con `project.unknown`.
3. 2026-11-11 — F2.2: `gvoice/runner.py` (`run` → `RunResult`): comprueba `minFreeMemoryMb` antes de lanzar, grupo de procesos propio, salida a archivos temporales (cola de 64 KiB), sondeo de cancelación, tiempo y `watchMemoryMb` (`limit.memory_abort`), mínimo de memoria libre y pico de RSS (`VmHWM` del proceso principal); SIGTERM y SIGKILL al grupo en cualquier salida; binario ausente → `engine.binary_missing`. Un código de salida distinto de 0 se devuelve, no se lanza. `tests/test_runner.py` (10 tests).
4. 2026-11-11 — F1.6: `gvoice/cli.py` y `__main__.py` (`python3 -m gvoice`) copiados de `gimg@fa1076e` y adaptados: `project add|list|remove`, `order submit|list|show`, `attempt new|mark|note`, `choose`, `undo`, `queue list|cancel`, `work`, `version`; `--json` y `--lang`; códigos de salida 0/1/2/130. `order submit` muestra los avisos de la ficha; `order list|show` marcan las frases desfasadas (`stale` en las líneas y `staleLines` en las voces, en `--json`). Textos `cli.*` en es/en. `tests/test_cli.py` y `tests/test_e2e.py` (ciclo completo con las huellas de cada `printModels`, desfasada y deshacer). README es/en con el uso. Sin `doctor`, `serve`, `ui` ni estimado (F2-F5).

## Pendiente

- `instalar.sh` sin probar fuera del contenedor: Vulkan y SPIRV-Headers, descarga de modelos, caminos de Flatpak (SDK y sandbox de VS Code) y binarios compilados en el SDK corriendo en SteamOS. Lo comprueba la persona en la Deck (F2.6).
- Leve de F2.2 (`runner.run`): tras terminar el proceso principal se manda SIGKILL a su grupo para barrer restos; en teoría el número de grupo podría haberse reutilizado si no quedaba nadie en él.
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
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && bash -n instalar.sh && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
