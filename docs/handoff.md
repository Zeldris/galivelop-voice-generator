<!-- galivelop-workflow v0.6.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-5e26fc26-igtd9z` (asignada por la sesión; sigue tras el PR #5, con `main` en `d7d5095`) |
| **Fase / tarea** | F5 Interfaz, en la nube (decisión de la persona del 2026-11-15) mientras F2.6 espera a la Deck. Hoja de ruta: `docs/plan.md` § «F5 en detalle». F2 sigue abierta solo por F2.6 (la persona) |
| **Último punto estable** | Hoja de ruta de F5 en `docs/plan.md`; check verde |
| **Siguiente paso** | F5.1: base copiada de `gimg/ui` (`galivelop-image-generator@46248251`, clon en `/home/user/zeldris/` o `git clone --depth 1`) con el simulador `?mock=1`, tokens con el acento de voces, servidor estático con CSP y tests estáticos; fijar el contrato de rutas de la API. En paralelo, la persona: F2.6 en la Deck |
| **Check** | verde (`bash -n` de cada gancho y `unittest`) |

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-11-15 — Hoja de ruta de F5 (interfaz) en `docs/plan.md` § «F5 en detalle»: avance 0 %; estilo de la hoja de voces de GVIG (`galivelop-image-generator@46248251`, bloques vigentes; solo cambia el acento `#d9467a`/`#ce3c71`), código a copiar de `gimg/ui` (vanilla, CSP), audio de cero (ningún front tiene reproductor), pasos F5.0-F5.8 [P] y lo que hay que pedir a la persona (logo, favicon, iconos, nombres de tokens, dudas 3 y 4 de la hoja). Propuesta: F4+F5 juntas tras F3. Sin código. Check verde.
2. 2026-11-14 — F2.5: `gvoice bench` (`gvoice/bench.py` + orden en `cli.py`; D18, cualquier motor que implemente `Engine`). Matriz por dispositivo: diseñar (modelo de diseño del perfil, frases corta y larga, semilla fija, por defecto 7), fijar (una huella por modelo Base, de la toma de diseño larga) y producir (modelo × corta/larga); `--models` (por defecto `models.produce`), `--devices` (por defecto `engine.device`), `--steps`, `--seed`, `--out` (por defecto `<datos>/bench/<AAAA-MM-DD-HHMMSS>/`), `--json`. Toma el candado de la máquina todo el banco y espera `minFreeMemoryMb` antes de cada paso con un motor que vigila memoria. Los trabajos llevan `no_fallback=True` (campo nuevo de `DesignJob`/`LineJob`/`PrintJob`; `QwenTtsEngine._attempts` no usa `fallbackDevice`): cada fila es el dispositivo pedido. Un paso que falla queda con su código y mensaje y el banco sigue; los pasos sin entrada (toma o huella ausente: falló o no estaba en `--steps`; los archivos del paso se borran antes de correrlo) quedan «saltado» (`bench.missing_input`). SIGINT pone una marca (el paso en curso queda «cancelado», se escriben los archivos, salida 130). `bench.json` (se reescribe tras cada paso) y `bench.md` (cabecera: fecha, motor, commit del catálogo, perfil, CPU, memoria; tabla del doc con coma decimal y `-`). Sale 1 si algún paso no está ok (también «saltado»). Las frases del banco no estaban como texto: frase corta («Amanece en la Hondonada y no se oye nada.») y larga (~160 caracteres, obeliscos) en `bench.PHRASES`. Textos es/en y README es/en. `tests/test_bench.py`: 22 tests con `FakeEngine` y con `QwenTtsEngine` + `fake_qwentts.py`. Falta: F2.6 en la Deck (la persona). Check verde.
3. 2026-11-14 — Arreglos de la revisión de bloque F2.1-F2.3 (6 hallazgos): el resultado lleva el dispositivo como el perfil (`cpu`; `device_arg` solo en el argv); un proceso muerto por señal no lanza el respaldo y, con vigilante, este exige `minFreeMemoryMb` otra vez (si no, error del primer intento y nota); el motor hereda el descriptor del candado (`machine_lock.held_fds`, `pass_fds`) para que un motor huérfano siga ocupando la máquina, y `worker.run` no limpia `.qwentts-*` si el candado está ocupado; `EngineError`/`EngineTimeout`/`Cancelled` llevan `stats` (`min_free_mb`, `peak_rss_mb`) y el trabajador las pasa al registro (`log.record_for(stats=)`); pico de RSS exacto con `os.wait4` (`ru_maxrss`; `proc.returncode` fijado a mano con `waitstatus_to_exitcode`; `VmHWM` solo si `wait4` no da nada); tests del vigilante sin reloj (`WATCH_S` parcheable, lecturas de memoria inyectadas). Check verde.
4. 2026-11-14 — F2.4: `instalar.sh` (D17; bash, `set -euo pipefail`, sin root, idempotente). Entorno por `/.flatpak-info`/`FLATPAK_ID` (flatpak: compila directo y prueba con `flatpak-spawn --host`), `cmake`+`g++`+`git` (native) o `flatpak` (steamos: `flatpak run --user --filesystem=<engine> --command=<x> org.freedesktop.Sdk//25.08`, instalándolo si falta); `GVOICE_INSTALL_ENV` lo fuerza, más `GVOICE_INSTALL_SDK`, `GVOICE_INSTALL_SPIRV`, `GVOICE_INSTALL_JOBS`. Repo, commit y `<datos>/engine` salen de `gvoice` (`models.load`, `paths.engine_dir`), sin duplicar. Clona en `engine/src`, checkout del commit y submódulos; SPIRV-Headers `fbf86836` en `engine/deps/prefix` (salvo native con cabeceras del sistema); CPU con `-DGGML_BLAS=OFF` y Vulkan con `-DGGML_VULKAN=ON -DCMAKE_PREFIX_PATH -DCMAKE_CXX_FLAGS=-I`, ambos con rpath `$ORIGIN` (build e install); `-B engine/bin-cpu|bin-vulkan` y un paso que reúne `qwen-tts`, `qwen-codec`, `tts-server` y los `.so` en la raíz si cmake los dejó en un subdirectorio. Prueba `qwen-tts --help` de cada carpeta (falla con ≥126 o «error while loading shared libraries»), `models fetch` + `verify`, y al final dice cómo activar `GVOICE_ENGINE=qwentts`. Opciones `--cpu-only`, `--skip-models`, `--dry-run` (líneas `DRY-RUN: <orden>`, sin tocar disco). `tests/test_install.py`: 20 tests (órdenes por entorno, rpath literal, ejecución real con `git`/`cmake` falsos, idempotencia, fallo de arranque); incluye `bash -n instalar.sh`. Falta: correrlo en la Deck (F2.6, la persona); `bash -n instalar.sh` no está en `check` de `.claude/gw.json` (protegido; ver «Pendiente»).
5. 2026-11-14 — F2.3: vigilante de memoria (D15). Antes de empezar, con un motor que vigila (`Engine.watches_memory`; `QwenTtsEngine(watch_memory=True)`, lo que construye `get_engine`; el falso no), el trabajador espera con el candado de la máquina ya tomado (así otro generador no se come la memoria entre la comprobación y el arranque) a que `MemAvailable` ≥ `minFreeMemoryMb` (`worker._wait_for_memory`, sondeo de 0,5 s, cancelable, nunca falla por eso; el motivo sale una vez por stderr, `worker.waiting_memory`). Durante la ejecución `engine_qwentts.MemoryWatch` (cada 0,5 s, muestrea al primer tick) lanza `EngineError("engine.low_memory", free, min)` por debajo de `watchMemoryMb` (mata el grupo, sin respaldo), y lleva el mínimo libre y el pico de RSS (`VmHWM`, `None` si no se lee) a `EngineResult.min_free_mb`/`peak_rss_mb` y a la línea D16 (`app.voice.min_free_mb`, `app.voice.peak_rss_mb`). Rutas sustituibles: `GVOICE_MEMINFO` y `GVOICE_PROC_STATUS` (con `{pid}`). Al arrancar, `worker.clean_workdirs` borra las `.qwentts-*` de `<datos>/projects` que dejó un SIGKILL. `limits.check_memory/must_abort/available_memory_mb/timeout_s` ya se usan. Textos `error.engine.low_memory` y `worker.waiting_memory` es/en. Un abortado por memoria no lleva el mínimo/pico en el registro (no hay resultado; los valores van en el mensaje). Tests nuevos: 17 (motor, trabajador, registro, límites); el motor falso gana `FAKE_QT_SLEEP_S`.

## Pendiente

- **F5, decisiones y recursos para la persona** (`docs/plan.md` § «F5 en detalle»): confirmar los pasos [P] y el orden F3 → F4+F5; encargar en GVIG el logo (símbolo + lockup) y decidir quién dibuja los iconos de interfaz.
- Hallazgos leves de la revisión de bloque F2.4-F2.5, sin arreglar en este PR: `bench._wait_for_memory` duplica `worker._wait_for_memory`; `instalar.sh --dry-run` dice «modelos: verificados»; `gvoice bench --steps design --models …` ignora `--models` sin avisar y la comprobación de lista vacía de `cli.py` ~297 es enrevesada.
- Hallazgos leves de la revisión de bloque F2.1-F2.3, sin arreglar en este PR (no vuelven a revisarse en él):
  - stdout del motor descartado (`stdout=DEVNULL`): mejor al mismo archivo que stderr.
  - `read_wav_ms` con `wave` no lee WAV en coma flotante: comprobar en F2.6 qué escribe `qwen-tts`.
  - Un respaldo que funcionó no deja rastro (`fallback_from`).
  - Un binario de respaldo ausente falla sin decirlo.
  - `check_installed` no comprueba los modelos de huellas.
  - El rollback de huellas puede borrar el par bueno anterior, y `print_not_written` pasa `path.suffix` en vez de la ruta.
  - Carreras de señales en `_kill_group`/`Popen`.
  - `recover_orphans` antes de `clean_workdirs` deja carpetas `q<entrada>` vacías.
  - Espera de memoria aunque `_take` devuelva un intento ya hecho.
  - El comentario de `engine_qwentts.py:49` sobre el proyecto.
  - `models fetch` concurrentes comparten `.part`, sin fsync de la carpeta y con progreso solo al 0 y 100 %.
  - `is_cancel_requested` cada 50 ms.
  - `MemoryTests` de `tests/test_worker.py` está tras `unittest.main()`.
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
