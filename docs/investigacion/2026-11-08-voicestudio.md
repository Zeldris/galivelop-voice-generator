# VoiceStudio: repo de referencia para revisar

Apuntado el 2026-11-08 a partir de una captura de su README que mandó la persona. Revisado el 2026-11-10 con un
subagente (lectura parcial, sin ejecutar nada) sobre el commit `c85a866f19dfddd6a31c50f88ee2e08e644c77ea`: ver
«Revisión del repo» al final.

**Repo:** <https://github.com/debpalash/VoiceStudio> (antes `OmniVoice-Studio`), localizado el 2026-11-09 con una
búsqueda web; varias fichas externas y su README en `raw.githubusercontent.com/debpalash/VoiceStudio` coinciden.

## Lo que dice la captura

- **VoiceStudio**, «AI voice studio. On your device.»: clonar, diseñar, doblar, dictar, transcribir y narrar en 646
  idiomas, todo en local (portátil, sobremesa, servidor, móvil, tableta), sin cuentas ni claves de API.
- Versión `v0.5.7`, licencia **AGPL-3.0**, ~100 000 estrellas, «#1 Repository Of The Day» en GitHub Trending.
- Tiene web, descargas, documentación, una versión Pro y otra Cloud.
- La interfaz de ejemplo es un estudio de doblaje de vídeo: subir y transcribir (idioma de origen, número de
  hablantes, separación de hablantes), doblar a otros idiomas, traducción local (Argos) o con agente, y calidad de
  traducción «Fast / Autofit / Cinematic».

## Lo que dicen fuentes externas (sin comprobar en el repo)

- App de escritorio local para clonar y diseñar voces, doblar vídeo, transcribir y dictar en tiempo real; una ficha
  habla de 16 motores de TTS y 11 de reconocimiento de voz. Versiones para macOS, Windows y Linux, e imagen Docker.
  Se describe como beta activa.
- **Los modelos tienen su propia licencia:** según una fuente, los pesos por defecto de OmniVoice son CC-BY-NC (no
  comercial). Cualquier modelo que se considere hay que mirarlo uno a uno.
- Las cifras de estrellas no cuadran entre fuentes (de ~10 000 a más de 100 000); no son fiables.

## Qué mirar al revisarlo

- Cómo diseña y clona voces (modelos, formato de la referencia, si guarda algo equivalente a nuestras huellas, D10).
- Qué motor de TTS usa y si corre en la Steam Deck (D15) o sin Python en la máquina final (D2).
- Ideas de interfaz para el ciclo de intentos y elegida.

**Ojo con la licencia:** AGPL-3.0. Se lee para sacar ideas; copiar código obligaría a publicar este proyecto bajo
AGPL. Cualquier copia literal se consulta antes con la persona.

## Revisión del repo (2026-11-10, commit `c85a866`)

Rutas relativas a la raíz de VoiceStudio. Lectura parcial: de los 131 módulos de `backend/services/` solo se
abrieron los relevantes.

### Qué es

- Backend en Python con FastAPI (`backend/main.py`, `backend/api/routers/`), estado en SQLite con Alembic
  (`backend/core/db.py`); frontend Electron + React (`electron/`), además de web, móvil, Docker y Nix. Depende de
  torch: mucho más grande que este proyecto. Sirve de catálogo de problemas, no de modelo.

### Motores

- Un adaptador por motor en `backend/engines/` y una interfaz estrecha, `TTSBackend` (`backend/services/tts_backend.py`):
  `generate(...)` devuelve audio mono y frecuencia de muestreo; `is_available()` devuelve `(bool, motivo)`.
- Los motores pesados corren como subproceso (`services/subprocess_backend.py`); `services/engine_memory.py` deja un
  solo motor residente y expulsa los demás antes de cargar otro.
- **Qwen3-TTS** solo en CUDA (`services/qwen_cuda.py`, `faster_qwen3_tts`) y en MLX para Apple Silicon
  (`backend/config/models.yaml`). **qwentts.cpp y llama.cpp: no aparecen.** Kokoro, solo MLX. VoxCPM2, motor propio
  en subproceso. Vulkan, solo para sus motores GGUF (omnivoice.cpp y CosyVoice GGUF).
- Nada de esto cambia D4: para la Deck no aporta un camino Qwen3-TTS por Vulkan.

### Voces

- Tabla `voice_profiles` (`backend/core/db.py`): referencia `.wav` y texto, descripción (`instruct`), semilla,
  `kind` (clon o diseño), receta de diseño en JSON y una toma **bloqueada** (`locked_audio_path`), su equivalente de
  nuestra elegida.
- No guarda huellas por modelo (`.spk`/`.rvq`): la identidad es la referencia más el texto, o la receta más la semilla.
- Una voz bloqueada ignora la semilla pedida (`api/routers/generation.py`, `_design_request_diverges`): conducta sutil;
  aquí debe quedar explícito qué manda.
- Formato portable `.ovsvoice` (`services/persona_bundle.py`): ZIP con manifiesto, referencia, consentimiento,
  licencia SPDX y vista previa.

### Hardware, colas y memoria

- `engines/omnivoice_gguf/` sondea el hardware y elige cuantización según la memoria (`hardware_probe.py`,
  `vulkan_probe.py`, `quants.py`).
- La memoria es un **aviso**, no un bloqueo (`services/memory_budget.py`): un bloqueo duro sobre una estimación
  estropea cargas legítimas.
- Cola serie con cancelación y posición (`core/job_queue.py`); carga y descarga de modelos en un solo sitio
  (`services/model_lifecycle.py`).

### Efectos

- `services/audio_dsp.py`: presets como listas de pasos `{"type": ..., parámetros}` aplicados con `pedalboard`, con el
  paso omitido si la herramienta no carga. Misma forma de datos que nuestra cadena de efectos (D5), otra herramienta.

### Regenerar solo lo cambiado

- `services/incremental.py`: hash determinista por segmento de todas las entradas de generación; solo se regenera lo
  que cambió. Su error #281: un valor por defecto hasheado distinto en servidor y cliente marcaba todo como cambiado.

### Licencias

- Código AGPL-3.0-only con CLA; `omnivoice/` es Apache-2.0. El modelo por defecto (`k2-fsa/OmniVoice`) tiene pesos
  **CC-BY-NC**: fuera de un juego comercial.
- `backend/config/model_licenses.json` (con esquema y test) marca Qwen3-TTS, Kokoro y VoxCPM2 como `apache-2.0` con
  `commercial_use: false`; parece una marca de «sin verificar», no comprobada.

### Ideas para adaptar (sin copiar código)

1. **Desfasadas por hash de entradas** (F1): guardar en cada frase elegida el hash de texto, huella, modelo y cadena
   de efectos, normalizando los valores por defecto antes de hashear.
2. **Licencias de los pesos como dato con esquema** y un test que impida usar pesos no comerciales sin aviso.
3. **Manifiesto del paquete** con procedencia, licencia SPDX y consentimiento de la referencia (para `pack.json`).
4. **Medida frente a estimación en memoria**: el aborto por debajo de 1,5 GB (D15) sobre memoria medida; sobre una
   estimación, solo aviso.
5. **Un motor residente a la vez** si más adelante se usa `tts-server` en lotes (D15).
6. **Paso de efecto omitido con aviso** si falta la herramienta, en vez de fallar toda la cadena.

Ninguna cambia una decisión aprobada; la 1 y la 4 tocan F1 y se deciden con la persona al empezarla.
