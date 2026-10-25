<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/voces-f1` |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`, «F1 en detalle», pasos F1.1-F1.6). Compactaciones: 0 de 1 presupuestada |
| **Último punto estable** | F1.4 (`queue` y `worker`; 336 tests). Antes, F1.3 con sus arreglos (`engine`, `machine`, `machinelock`, `log`), F1.2 (`orders`, `sheet`) y F1.1 |
| **Siguiente paso** | Revisión corta de F1.4 y F1.5: `voices` (fijar, huellas, deshacer, desfasadas, puerta de `line`), moviendo a `voices` los puntos `_fixed_print`/`_print_job`/`_print_commit`/`_print_discard` del trabajador |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 336 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-10-25 — F1.4: `queue` y `worker` copiados de `gimg@0d02f51`; entradas `attempt` (design de `voice`, speak de `line`) y `print` (formato en «F1 en detalle»); `machinelock.hold` solo alrededor del motor (cancelable mientras espera); comprueba otra vez proyecto, pedido y voz antes de llamar al motor; textos es/en; tests de cancelar en cola, esperando el candado y durante el motor, timeout, fallo, trabajador muerto, dos trabajadores, pedido o voz borrados y cola vacía.
2. 2026-10-25 — F1.3: `engine` (jobs `DesignJob`/`SpeakJob`/`PrintJob`, `EngineResult` con `audio_ms` y `device`, `FakeEngine` con WAV 24 kHz de tono por semilla a 60 ms por carácter y huellas `.spk`/`.rvq` deterministas, `GVOICE_ENGINE`/`FAKE_DELAY`/`FAKE_FAIL`), `machine` (perfil de `limits` de `gimg`, sin límites), `machinelock` (D8: `hold(should_cancel)` con `flock` no bloqueante, rechaza enlaces y otro usuario) y `log` (`speech_generation`, `app.audio.*` con `rtf`, estimado por motor, tarea, modelo y dispositivo); textos es/en.
3. 2026-10-25 — F1.2: `orders` copiado de `gimg@0d02f51` (pedidos `voice` y `line`, API `(project, type, key)`, carpeta `orders/<tipo>/<key>/`, audio `.wav`, `voiceReference` como parámetro de `add_attempt`, clave `attempts` reservada) y `sheet` nuevo (`build_instruct` en el orden de `design-sheet.schema.json`, `warnings` con edad y palabras vetadas de D11); `model` y `count` en el esquema de pedido; textos es/en.
4. 2026-10-25 — F1.1: `paths`, `fsutil`, `errors` y `projects` copiados de `gimg@0d02f51` y adaptados (`GVOICE_*`, `galivelop-voice`, `galivelop-voices.json`, `GvoiceError`); `project_data_dir` usa el patrón de `common.schema.json`; sin `check_key` (el límite de la clave es del esquema) ni plantilla/manifiesto; `delivery.dir` se comprueba contra `.git` y el archivo de configuración; `print_models` lee el enum `baseModel`; `gvoice.__version__`.
5. 2026-10-25 — F0 a `main` por el PR #3, con la confirmación de la persona. CI de GitHub sin arrancar (facturación); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.

## Pendiente

- Leve de F1.4: `_print_job` no comprueba que `entry["reference"]` sea la referencia actual de la voz (si cambió entre encolar y ejecutar, la huella llevaría un id viejo); F1.5 decide cómo se sabe (p. ej. `voices/<voz>/reference.json`). El candado de máquina no cuenta en el `timeout` del motor.
- F1.5: `_print_commit` ya escribe `print.json` el último y `_print_discard` borra las huellas si falla (en el trabajador); al moverlo a `voices`, conservarlo. `extract_print` escribe `.spk` y `.rvq` por separado; `voices` escribe `print.json` el último y, si el motor falla, borra o ignora las huellas (si no, «al día» sería falso).
- F2: el fd del candado no se hereda, así que un hijo `qwen-tts` sigue vivo sin candado si muere el trabajador; el estimado de `speak` no tiene en cuenta la longitud del texto (`rtf`/`text_chars` ya están en el registro, a valorar con `opt-ai`).
- Leves de la revisión corta de F1.3: `wav_bytes` del motor de pruebas gasta 283 MB con 4000 caracteres (`array('h')`); `machinelock.hold` deja salir `OSError` (ENOLCK) sin `GvoiceError`, `not_file` no se alcanza con un directorio, no hay tests de `not_file`/`unusable`, y el TOCTOU entre `lstat` de la carpeta y `os.open` (`dir_fd`); los tests de `EngineError` del motor no comprueban el mensaje; el `geteuid` simulado de `test_file_of_another_user_refused` depende del orden de llamadas.
- Leve de la revisión corta de F1.1: `projects._version` confía en el patrón del esquema (seguro hoy, porque siempre se valida antes).
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
