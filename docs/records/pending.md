# Pendiente

Lo que queda abierto; la bitácora solo apunta aquí. Se añade y se quita en este archivo.

## Pendiente

- Hallazgos leves de la revisión de bloque de la lectora es (F2-F3, locale y efectos), sin arreglar en este PR (no vuelven a revisarse en él):
  - Un locale desconocido lanza `ValueError` en vez de un `GvoiceError` traducido (`worker.py:183`, `speech_locale.py:17`).
  - `gvoice/queue.py:239` usa un criterio truthy para `locale` y `orders.py` usa `is not None`: unificarlos.
  - `tests/test_install.py:235` se salta en Flatpak en vez de hacer configurable la ruta de `/.flatpak-info`.
  - `tests/test_peaks.py`: el umbral de 1,0 s de `is_fast` es frágil (falla en la Deck).
  - `tests/test_examples.py` no tiene un ejemplo roto de locale (p. ej. `es-MX`).

- Hallazgo leve de la revisión de bloque F5.5, sin arreglar en este PR: el cableado de teclado y mando (`mergeSources`, filtros de `onKey` y de `startGamepad`) y `loading()` están copiados entre `order-view.js` y `compare-view.js`; sacar un `bindShortcuts(perform)` a `shortcuts.js`. La ayuda de atajos de la vista A/B lista también U/C/D/G, que allí no hacen nada (filtrarla por vista).

- Mando por Gamepad API sin probar en la Deck (de la persona, F5.8); F5.4 solo lo cubre con tests.
  La revisión de bloque F5.4 añadió deduplicar teclado y mando (Steam Input convierte el mando en teclas): comprobar en la Deck que cada pulsación actúa una sola vez.

- Hallazgos leves de la revisión de bloque F5.4, sin arreglar en este PR: `peaks.py` toma la duración y las cubetas de la cabecera de un WAV truncado, no de los frames leídos; `loading()` está copiado en `projects-view.js`, `project-view.js` y `order-view.js`.

- Hallazgos leves de la revisión de bloque F5.3, sin arreglar en este PR: `sheetWarnings` de `sheet-warnings.js` solo lo usan los tests y el respaldo del icono está en dos sitios (`warningItems` y `warningIcon`); el botón que abre el diálogo de la ficha se pierde si la lista se rehace con el diálogo abierto, y el foco cae a `body`.
- Hallazgo leve de la revisión de bloque F5.2, sin arreglar en este PR: los tests del JS pasaron de `test_ui.py` (estáticos) a `test_ui_js.py`, que se salta entero sin `node` ≥ 18; en la Deck (Flatpak) el check local no los corre: comprobar si hay `node` allí o dejar los estáticos como respaldo.
- **F5, decisiones y recursos para la persona** (`docs/plan.md` § «F5 en detalle»): confirmar los pasos [P] y el orden F3 → F4+F5; encargar en GVIG el logo (símbolo + lockup) y decidir quién dibuja los iconos de interfaz.
- `gvoice ui --host ::1` (IPv6) sin probar: el contenedor de la nube no tiene IPv6 y `test_ipv6_loopback_is_served` se salta; lo comprueba la persona en la Deck o su equipo.
- Hallazgos leves de la revisión de bloque F5.1, sin arreglar en este PR: el simulador devuelve `blob` para el audio, pero `api.js` `request` solo devuelve `json` y `<audio src>` iría al servidor real (resolver en F5.4); `describeError` nunca llega a `ui.error.code`; carrera en `i18n.load` con cambios rápidos de idioma; `api.bad_host` no hace caso de `?lang=`; `cli.py` importa `server` en cada orden; `server.main` repite el argparse de `gvoice ui`; `api.js` tiene `withHeaders` y `put` muertos; `api_contract.match` parte los patrones y `i18n.available()` hace glob en cada petición.
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
- Leves de la revisión de bloque de F5.7 (2026-11-16), sin arreglar:
  - `queue-model.js` `errorOf`: un `error.code` sin clave `error.<code>` ni `errorText` deja la fallida sin motivo; recurrir a un texto con el código.
  - `queue-bar.js`: un `state` o `kind` desconocido enseña la clave en crudo (`ui.queue.state.x`); usar el valor crudo si `i18n` no la tiene.
  - `queue-bar.js`: `aria-label` en un `div` sin rol (la entrada); darle `role: 'group'`.
  - `store.queueCounts()` repite `queue-model.counts()` y nadie lo usa.
  - `tests/test_ui_browser.py`: `setUpClass` crea `cls.tmp` y nadie lo usa.
  - `tests/test_ui_browser.py`: sin Chrome se salta también en el CI (REVIEW.md pide fallar allí); y `find_chrome()` corre al importar (en el Flatpak, un `flatpak-spawn --host flatpak info` en cada `discover`): moverlo a `setUpClass`.
  - `tests/browser.py` `goto()`: espera `readyState === 'complete'`, que ya es cierto en el documento anterior; esperar `Page.loadEventFired` o el cambio de `location.href`.
- **Motor en la Deck (2026-11-17):** (1) los binarios de `engine/bin-*` son de la compilación del banco, con RPATH a `engine/build-vk` y `engine/build-cpu2`; puestos dos enlaces simbólicos con esos nombres para que arranquen; el arreglo es volver a pasar `instalar.sh` (F2.6). (2) Dentro del Flatpak de VS Code `qwen-tts` solo ve `CPU` (Vulkan0 «not found»): `gvoice work` lanzado desde VS Code cae siempre a CPU; con `flatpak-spawn --host` sí ve Vulkan (~12 s por toma frente a ~60 s). Decidir si el motor se lanza por `flatpak-spawn --host` cuando corre en Flatpak. (3) Sin `GVOICE_ENGINE=qwentts` el generador usa el motor falso sin avisar.
- Leves de la revisión de 0.2.0 (2026-11-17), sin arreglar:
  - `tests/test_changelog.py` `has_entries` repite el recorrido de `releases.section`; reutilizarla.
  - `releases.py` `suggest` corre la regex antes de `if not subject: continue`; ponerla después.
  - `tests/test_changelog.py`: la constante `GIMG` conserva el nombre de la copia (es de gvoice); renombrarla.
- Dos tests fallan en la Deck ya en `main`: `test_install…no_compiler_and_no_flatpak_fails_clearly` (127 != 1 dentro del Flatpak) y `test_peaks…is_fast` (0,82-0,86 s frente a 0,7 s).
- Preset `lectura` sin afinar con voz real (denoise 0,5, dereverb 0,4, trimSilence -50 dB/150 ms); el primer commit de efectos pasa de 400 líneas.
- 2026-11-17 — Llevar a `gvoice` lo que se hizo a mano para el Portal (scripts en `proyectos/portal/escucha/via1/run/`, fuera del repo):
  - Clonado por huella (`--ref-spk`) para `lectora-es`; hoy el código la genera con VoiceDesign e instrucción.
  - Comprobación automática de cada toma: nivel y cruces por cero (`check.py`) y, con whisper.cpp, WER contra el guion y **omisiones de 3 o más palabras** (`wer.py`; los números en cifras no cuentan). Las tomas de Chatterbox se dieron por buenas y eran un pitido, y Qwen se salta frases en trozos largos con enumeraciones.
  - Trozos largos frase a frase con 0,45 s de pausa (`frases.sh`) cuando una toma omite texto; probar semillas antes.
  - Pronunciación desde las `notas` del guion (`pron.py`): tildes en nombres inventados; los nombres en inglés se dejan tal cual (la persona); `toVeriAI` → «to Veri AI».
  - Leer los guiones del Portal (`Portal-Galivelop/src/data/guiones/<pagina>.json`) y dejar lo aprobado en `final/es/<pagina>/<nn>-<seccion>.wav`.
- 2026-11-17 — Gallego (`gl`) para `final/gl/`: ni Qwen3-TTS ni Chatterbox lo declaran y `locale` no lo admite; buscar motor o probar si se defienden. La persona elige (2026-11-17) **voz gallega nativa, de mujer adulta** (no la huella de `lectora-es`); investigación en `docs/investigacion/2026-11-17-voz-gallega.md`; los guiones `gl` los escribe el Portal. **Tono:** el mismo que `lectora-es` (referente de oído: la Galadriel del doblaje de España: serena, cálida, solemne sin teatro) con el acento y la entonación gallegos; la persona, gallega, será exigente con la pronunciación. **Base elegida (2026-11-17): Celtia** (la persona aprueba la muestra de la demo, `escucha/gl-demo/`). Licencia: la persona decide **no consultar a la USC**: uso sin ánimo de lucro, nacido de la investigación del generador, con atribución «Voz gallega: Celtia, Proxecto Nós (USC), Apache-2.0» en el README del generador y en el Portal (créditos o pie).
- 2026-11-18 — Portal `final/es`: la voz de la cabecera de `inicio` y la de `equipo` (y quizá otras páginas) no suenan a la misma persona. El modelo a seguir es la **primera voz generada, la de `inicio`**; revisar y rehacer las que se aparten **al cerrar el gallego** (lo pide la persona).
- 2026-11-18 — **Para la retro de 0.3.0 (lo pide la persona): convertir en regla determinista** que ningún audio generado se presente a la persona sin pasar un filtro automático. Casuística: dos rondas de audio gallego (`escucha/gl-portal/`, `escucha/gl-ficha/`) se le pasaron para escuchar con ruidos y cortes. El único control era whisper genérico con WER, que castellaniza el gallego y no ve ruidos ni cortes; los resultados se le daban en tabla sin aprobar ni suspender nada. Propuesta: un script de filtro (ASR calibrado con voz humana de la lengua, detector de cortes y DNSMOS por tramos) con umbral, que se corre al final de cada lote y deja en una carpeta aparte solo lo que pasa; y una regla en `AGENTS.md` o una comprobación que impida decir «escúchalo» sin su informe. Vale para gl, es y en.
- **Interpretación en castellano sin medir (2026-11-18):** los 10 audios de `final/es` rehechos con otra semilla
  no difieren en sonido (NISQA) de los aprobados: se rechazaron por la interpretación. El filtro no mide entonación;
  hace falta una comprobación de prosodia (y apuntar el motivo de cada rechazo en `engine/verif/corpus/juicios.csv`).
- **`gw-opt-ai` no cubre voz (2026-11-18, para el repo del flujo, Galivelop-workflow):** la skill está hecha para
  modelos de texto (tok/s, primer token, caché KV, `num_ctx`, RAG). La persona decide **ampliarla, no crear otra
  skill**: una referencia por tipo de modelo (`references/speech.md`; luego `image.md` para `gimg`) con sus medidas,
  ajustes y calidad; el paso 2 pasa de «RAG» a «calidad del tipo de modelo» (en voz, el filtro de audio y los juicios
  de oído); `measure.py` saca el factor de tiempo real (`app.duration_ms` / `app.voice.audio_ms`) cuando la línea trae
  audio, y tok/s solo con tokens. Se hace desde una sesión en el repo del flujo, no editando la copia de aquí.
- **Los motores de 0.3.0 no escriben el registro por llamada (2026-11-18):** `engine/*/gen.py` (Matcha-Celtia,
  StyleTTS2) corren fuera del trabajador y no dejan líneas en `log.jsonl`, así que su rendimiento no se puede medir.
  Hacer que escriban el mismo formato (`gvoice/log.py`: perfil, dispositivo, `duration_ms`, `load_ms`, `audio_ms`,
  memoria). Además, rellenar `.claude/gw/gw-opt-ai.md` (banco de pruebas, tiempos aceptables, script de parada):
  el único registro (`portal`, 17-nov) es una prueba de humo y no vale como ronda.
