# Estado de la voz local a 2026-10-25

Revisión del documento de origen, `World-Maker-Fantasy/docs/arquitectura/reutilizables/02-voces-y-sonidos-locales.md`
(escrito y comprobado el 2026-10-13, sin cambios desde entonces), contra las fuentes primarias. Lo leyó un subagente
con búsqueda web; lo que no encontró en fuente primaria va marcado **(sin verificar)**.

## Motor: `qwentts.cpp`

- **Activo:** último commit del 2026-10-16 («ggml: fork rebase»), ggml 0.26.0 desde el 7-oct, `--device` desde el
  12-oct. <https://github.com/ServeurpersoCom/qwentts.cpp/commits>
- **No publica binarios:** no hay releases. Hay que compilarlo (`buildcpu.sh`, `buildvulkan.sh`, `buildcuda.sh`,
  `buildall.sh` con todos los motores cargados en ejecución) o usar sus imágenes Docker (solo CPU y CUDA). Se fija
  un commit concreto.
- **Riesgo en la Deck:** la issue #41, «[Vulkan] libggml-vulkan fault and concurrent DRM Oops on Radeon 840M»
  (2026-10-17), es una APU AMD con Vulkan, como la de la Deck. Hay que probar pronto y tener `--device CPU` de
  respaldo.
- **Opciones** (`docs/ARCHITECTURE.md` del repo):
  - `qwen-tts`: el texto entra por la entrada estándar; `-o -` saca el audio por la salida estándar.
    `--instruct` es **obligatorio en VoiceDesign, opcional en CustomVoice y rechazado en Base**. `--ref-rvq` exige
    `--ref-spk` y `--ref-text` (modo ICL). También admite `--ref-wav` directo en Base, `--format wav16|wav24|wav32`,
    `--stream-by-line`, `--seed`, `--greedy`, `--temp`, `--top-k`, `--top-p`, `--rep-pen`, `--max-new` y
    `--device` (`Vulkan0`, `CPU`…).
  - `qwen-codec --talker <Base> -i referencia.wav` escribe `.spk` y `.rvq`, y `--talker` solo acepta un talker Base.
  - `tts-server`: `--host` (127.0.0.1 por defecto), `--port`, `--lang`, `--max-batch`, `--alias` y `--device`.
- **API de `tts-server`:** `POST /v1/audio/voices` (`name`, `ref_text`, `spk_b64`, `rvq_b64`, o un WAV) y
  `POST /v1/audio/speech` (`input`, `voice`, `language`, `response_format` `pcm` s16le en streaming o `wav`, y
  `seed`, `temperature`, `top_k`, `top_p`, `repetition_penalty`, `max_new_tokens`).

## Modelos (`Serveurperso/Qwen3-TTS-GGUF`)

- Archivos `qwen-talker-{0.6b,1.7b}-{base,customvoice}-{F32,BF16,Q8_0,Q4_K_M}.gguf`,
  `qwen-talker-1.7b-voicedesign-*.gguf` y `qwen-tokenizer-12hz-*.gguf`. El autor recomienda Q8_0.
- Tamaños de Q8_0: 0.6b-base 993 MB, 1.7b-base 2,08 GB, 1.7b-voicedesign 2,04 GB, tokenizer 291 MB. En Q4_K_M:
  0.6b-base 629 MB y 1.7b-base 1,22 GB.
- **CustomVoice existe** (0.6B y 1.7B): nueve hablantes de serie con `--speaker` e instrucción opcional. La ficha de
  Hugging Face describe al revés Base y CustomVoice; el repo de Qwen y el `ARCHITECTURE.md` dicen que Base clona.
- No hay versión nueva de Qwen-TTS desde la del 2026-01-22. Que la clonación haya llegado a `llama.cpp` (PR #26254)
  lo dice una fuente secundaria **(sin verificar)**.

## Lo que el documento dejaba sin verificar

| Duda | Resultado |
|---|---|
| Español | **Confirmado**: Qwen3-TTS tiene 10 idiomas y el español es uno de ellos (<https://github.com/QwenLM/Qwen3-TTS>). |
| «Instruct de 12 claves» | **No es oficial**: el instruct es texto libre. Las 12 claves son una convención propia. |
| VoiceDesign solo en 1.7B | Confirmado. |
| RTF en la Deck | No hay cifras publicadas para ningún equipo: hay que medirlo. |

## Alternativas y licencias

- **Piper ya es GPL-3.0** (`OHF-Voice/piper1-gpl`; el `rhasspy/piper` original está archivado). Deja de servir como
  plan de emergencia en algo que se distribuye, salvo que se acepte el copyleft.
- **Kokoro** v1.0: código y pesos Apache-2.0, con español y sin clonación. Pasa a ser el único plan de emergencia.
- **VoxCPM2** (OpenBMB, abril de 2026): Apache-2.0, 30 idiomas, diseño por texto y clonación, GGUF, 2B y ~8 GB de
  VRAM, con un RTF de ~1,76 en un Apple M4 Pro. Es la alternativa a vigilar; probablemente va lenta en la Deck.
- **MOSS-TTS**: Apache-2.0 pero de 8B, con pesos de acceso condicionado. **OuteTTS 1.0**: Apache-2.0 según una fuente
  secundaria **(sin verificar)**.

## Efectos y fauna

- **Stability AI Community License** (versión del 2024-07-05): uso comercial gratis con menos de 1 M$ de ingresos
  anuales, previo registro. Stable Audio Open no queda prohibido para un indie, pero sí atado a una licencia con
  umbral.
- **MOSS-SoundEffect** (OpenMOSS): texto a audio, Apache-2.0 según la ficha **(sin verificar en el repo oficial)**.
  Sony Woosh: licencia **(sin verificar)**.

## Aprendizajes del generador de imágenes (revisión del 01, 2026-10-24)

- En la Deck, la VRAM es memoria compartida: un límite de VRAM mal puesto (`vulkan0=6`) bloqueó la máquina. Hay que
  medir la memoria mínima libre en cada prueba.
- Cada componente tiene su propia licencia (allí, un VAE no comercial): hay que revisarlas todas, no solo la del modelo
  principal.
- Versiones fijas y checksum. El diseño del generador de imágenes (`galivelop-image-generator/docs/plan.md`, D1-D27)
  es la referencia de forma.
