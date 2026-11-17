# Motores locales para la vía 1 de D19 en la Steam Deck (TTS con clonado en es-ES y conversión de voz)

**Fecha:** 2026-11-17 · **Pregunta:** qué TTS con clonado y qué conversores de voz sirven para las capas 1 y 2 de D19 con una sola Steam Deck
(APU Van Gogh, gfx1033, 8 CU, 16 GB compartidos; sin CUDA; ROCm no oficial) · **Contexto:** `docs/plan.md` D19,
`2026-11-17-lectora-es.md`, `2026-11-17-qwen3tts-voicedesign-prompts.md`, `2026-10-25-banco-deck.md`.

Convención: **Oficial** = README, model card, `LICENSE` o metadatos de la API de Hugging Face/GitHub del propio proyecto, leídos el 2026-11-17.
**Comunidad** = issues, blogs, hilos. **Estimación** = cálculo mío a partir de otra máquina; **no medido en la Deck**. **No encontrado** = se buscó y no hay dato.

## Resumen

1. **Mejor candidato nuevo: Chatterbox Multilingual V3 con el paquete `es-es`** (Resemble AI). Código y pesos MIT, 0,5B, hay un finetune específico «Spanish (Spain)», y existe un port C++/ggml con Vulkan y CPU (`chatterbox.cpp`). Pero: Resemble marcó el repo como «retired research» en agosto de 2026, el port ggml es de un solo autor (6 estrellas), y **ninguna cifra publicada es de la Deck ni de Vulkan multilingüe**.
2. **Control ya medido: Qwen3-TTS Base (0,6B/1,7B) con `qwentts.cpp`**, Apache-2.0, RTF 0,55-0,95 en Vulkan en esta Deck. Lo que falta es un clip de referencia peninsular y oído.
3. **Conversión de voz:** el único con licencia comercial clara, código y pesos, y diseño pensado para esta capa es **OpenVoice V2 (MIT)**: clona solo el timbre y **deja el acento al TTS base**, que es lo que la capa 2 necesita. RVC (MIT) da más calidad pero exige entrenar un modelo por voz destino; kNN-VC (MIT, sin entrenar, WavLM-Large) es la alternativa sin entrenamiento. **Seed-VC es GPL-3.0 y pide GPU.**
4. **Descartados por licencia para uso comercial:** F5-TTS y su finetune español (pesos CC-BY-NC), XTTS-v2 (CPML), OpenAudio S1-mini/Fish Speech (CC-BY-NC-SA en los pesos; la licencia nueva del código limita por ingresos), OuteTTS 1.0-1B (CC-BY-NC-SA).
5. **GPU de la Deck:** Vulkan funciona hoy con ggml (ya medido con `qwentts.cpp`). **ONNX Runtime no ofrece proveedor Vulkan** (no aparece en su lista de proveedores). **PyTorch ROCm con `HSA_OVERRIDE_GFX_VERSION=10.3.0`** tiene evidencia de que funcionó en la Deck con ROCm 5.4.2 y de que el entorno de ROCm 6.1 necesita ese override para no abortar; **no hay evidencia primaria de que funcione con PyTorch/ROCm actuales**, y está por probar.

---

## 1. Motores de TTS con clonado

### 1.1 Chatterbox Multilingual V3 (Resemble AI)

- **Licencia (oficial):** código MIT (README, `LICENSE`); pesos `ResembleAI/chatterbox` y `ResembleAI/Chatterbox-Multilingual-es-es`: `license: mit` en los metadatos de la API de HF. Uso comercial: sí. El audio lleva marca de agua Perth (README).
- **Estado:** README: «As of August 2026, Chatterbox is retired research and is no longer maintained». Sin soporte futuro; los pesos siguen descargables.
- **Español:** el modelo general V3 cubre 23 idiomas incluido `es`; el paquete «Single Language Pack» añade `Chatterbox-Multilingual-es-es` («optimized for Spanish as spoken in Spain», 2,14 GB en float32, finetune de `ResembleAI/chatterbox`, subido 2026-04) y `es-mx-latam`. **La ficha no da datos de entrenamiento por variedad ni MOS** (no encontrado). El modelo base: «0,5M horas de datos limpiados» sin desglose por idioma.
- **Acento al clonar (oficial):** el README avisa de que si el clip de referencia no coincide con la etiqueta de idioma, la salida «may inherit the accent of the reference clip's language»; sugiere `cfg_weight=0`. Con una muestra peninsular y `es` el riesgo es el contrario del que preocupa en Qwen3-TTS (#134), pero **hay que oírlo**. Encaja con D19: el acento sale de la muestra.
- **Cómo correrlo en la Deck:**
  - *PyTorch oficial:* el README admite `cuda`, `cpu` y `mps`; CPU sin cifras para el multilingüe. Pide Python 3.11 (probado en Debian 11); en el anfitrión SteamOS hay Python 3.14 (comprobado), así que iría en un venv o contenedor aparte.
  - *`chatterbox.cpp`* ([gianni-cor/chatterbox.cpp](https://github.com/gianni-cor/chatterbox.cpp), MIT por su `LICENSE`, último push 2026-05-04): C++/ggml, CPU/Metal/CUDA/**Vulkan** (`-DGGML_VULKAN=ON`, `--n-gpu-layers 99`), `tts-cli ... --language es --reference-audio ref.wav`; cuantizaciones f16/q8_0/q5_0/q4_0 para el T3 multilingüe; `--save-voice`/`--ref-dir` para no repetir el preprocesado de la referencia (el README dice ~2 min). Se llama como proceso con `subprocess`, como `qwen-tts`. **No consta que su convertidor acepte el paquete `es-es` ni el S3Gen V3** (el README habla de «23 languages» y no menciona los paquetes): hay que probarlo.
  - *GGUF de terceros:* [hans00/Chatterbox-Multilingual-TTS-GGUF](https://huggingface.co/hans00/Chatterbox-Multilingual-TTS-GGUF) (para `codec.cpp`, no verificado) y el plugin de NVIDIA NVIGI con GGUF multilingües y Vulkan (documentación de NVIDIA; pensado para sus GPU).
- **Velocidad (cifras del README de `chatterbox.cpp`, no son de la Deck):**

  | Modelo | Hardware | RTF |
  |---|---|---|
  | Turbo (inglés) Q4_0 | Vulkan, RTX 5090 | 0,07 |
  | Turbo Q4_0 | CPU AVX, Ryzen 9 9950X | 0,82 |
  | **Multilingüe** Q4_0 | **CPU, 4 hilos, Apple M4** (tras corregir CFG) | **4,32** |

  Sin cifra de Vulkan multilingüe. **Estimación para la Deck:** CPU, RTF ≥ 5 (probablemente 6-12; la Deck tiene 8 hilos Zen 2 pero menos ancho de banda que un M4); Vulkan, sin dato, plausible 1-3 (el README dice que el CFG por lotes solo está optimizado en Metal). PyTorch en CPU: sin cifra; PyTorch ROCm: sin cifra.
- **Memoria:** modelo `es-es` de 2,1 GB en fp32 más S3Gen; con cuantización del port, el Turbo ocupa 1,07-1,25 GB (README, inglés). Cabe en 16 GB.

### 1.2 Qwen3-TTS Base con `qwentts.cpp` (el motor actual, como control)

- **Licencia (oficial):** `Qwen/Qwen3-TTS-12Hz-0.6B-Base`: `license: apache-2.0` (API de HF). El port `qwentts.cpp` ya está en el catálogo del proyecto (D4, D18).
- **Medido en esta Deck** (`2026-10-25-banco-deck.md`): 0,6B Base en Vulkan, frase larga, RTF 0,95 de extremo a extremo y 0,55 con `tts-server` en caliente; 1,7B Base RTF 1,16; en CPU RTF 5,05 (0,6B) y 7,51 (1,7B), 4-6,7 GB de RSS. Entre CPU y Vulkan la semilla no reproduce la toma.
- **Español peninsular:** sin fuente oficial de acentos regionales; el acento se pierde al clonar entre idiomas (#134) y «parece adecuado» en el mismo idioma (comunidad). Detalle en `2026-11-17-qwen3tts-voicedesign-prompts.md`. Con una muestra peninsular real es el control contra el que comparar a Chatterbox.

### 1.3 Otros evaluados

| Motor | Licencia (fuente) | Español / clonado | Deck | Veredicto |
|---|---|---|---|---|
| **Fun-CosyVoice3-0.5B-2512** | Código Apache-2.0 (`LICENSE`); pesos `apache-2.0` (HF API) | 9 idiomas incluido español, clonado zero-shot y entre idiomas (README); sin desglose por variedad | PyTorch; sin port ggml/Vulkan en lo que encontré | Opción de reserva: licencia limpia, pero solo PyTorch (CPU o ROCm sin probar) |
| **Zonos v0.1** (Zyphra) | Apache-2.0 código y pesos | Español entrenado; el README avisa de que «puede retener el acento original» con otro idioma | Pide GPU de 6 GB; en CPU «a lot slower… likely won't be sufficient for interactive use» (README); repo sin cambios desde 2025-03 | Descartar para la Deck |
| **OuteTTS 1.0-0.6B** | `apache-2.0` (HF); el de 1B es `cc-by-nc-sa-4.0` | La tabla de la ficha dice «14+ languages» (0,6B) y 20k h de audio, sin listar español | Tiene ruta llama.cpp según su README (no verificada) | Dudoso: sin evidencia de español peninsular |
| **Kokoro-82M** | Apache-2.0 | Tiene voces en español (`VOICES.md`, no leído); **no hay clonado** de usuario | Pequeño, rápido (sin cifra oficial) | No sirve para clonar; solo como base de lectura si se acepta voz fija |
| **F5-TTS / F5-Spanish** | Código MIT; **pesos CC-BY-NC** «por los datos Emilia» (README); `jpgallegoar/F5-Spanish`: metadatos `cc-by-nc-4.0` y el texto de la ficha dice CC0 (contradictorio) | F5-Spanish: 218 h, español peninsular sobre todo de Voxpopuli, más variedades latinas | Existe port ONNX de terceros | **Descartado: no comercial** |
| **XTTS-v2** (Coqui) | Pesos `other: coqui-public-model-license` (HF API). No pude leer el texto (`coqui.ai/cpml` devuelve 404); es conocida como no comercial | Español entre 17 idiomas; clip de 6 s | PyTorch | **Descartado** hasta verificar el texto de la CPML |
| **OpenAudio S1-mini / Fish Speech** | Pesos CC-BY-NC-SA-4.0 (ficha). El código/materiales pasaron a la «Fish Audio Community License» (2026-10-13): uso comercial solo con ingresos anuales < 500.000 USD, sin servicios alojados | Español entre 13 idiomas; 2 M h en total | PyTorch, repo con acceso condicionado | **Descartado** (pesos NC) |

---

## 2. Conversión de voz (capa 2 de D19)

| Motor | Licencia (fuente) | Qué hace | Deck | Notas |
|---|---|---|---|---|
| **OpenVoice V2** (MyShell) | Código MIT (GitHub); pesos `myshell-ai/OpenVoiceV2` `mit`; README: «Free for both commercial and research use» | Convertidor de **color tonal** a partir de una referencia; el acento y la emoción **no** se clonan: «controlled by the base speaker TTS model» (`docs/QA.md`). V2 admite español de forma nativa (README); el TTS base es MeloTTS (MIT) | PyTorch; MeloTTS dice «fast enough for CPU real-time inference»; la velocidad del convertidor no consta | Mejor encaje con la capa 2: la interpretación y el acento de la capa 1 se conservan, cambia el timbre. Repo sin cambios desde 2025-04. La calidad en es-ES hay que oírla |
| **RVC** (Retrieval-based VC WebUI) | MIT (GitHub); pesos base `lj1995/VoiceConversionWebUI` `mit` | Convierte una toma al timbre de un modelo entrenado con ≥ 10 min de voz limpia del destino; base entrenada con ~50 h de VCTK (inglés) | README: AMD/Intel en Linux usan la ruta CPU; no menciona ROCm | Más calidad probable y destino fijo por raza (receta de D18), pero hay que **entrenar** cada destino (en CPU será lento). Independencia de idioma: no declarada |
| **kNN-VC** (bshall) | MIT (`LICENSE`) | WavLM-Large + regresión kNN sobre referencia (mejora decreciente pasada la referencia de 5 min) + HiFi-GAN; sin entrenar por voz | PyTorch; sin cifras de CPU | Evaluado solo en LibriSpeech (inglés): WER 6,29 %, EER 35,7 %. Licencia de los checkpoints: no declarada |
| **Seed-VC** | **GPL-3.0** (repo, archivado 2025-11-21) | VC zero-shot por difusión; modelos de 25M a 200M | «Strongly recommended to use a GPU»; probado en RTX 3060; sin cifras de CPU | GPL: llamarlo como proceso es posible, pero no se puede empaquetar con el código del proyecto sin decidir la licencia. Descartado de partida |

---

## 3. La GPU de la Deck

### 3.1 Vulkan

- Funciona hoy con ggml: `qwentts.cpp` en Vulkan0 (RADV VANGOGH) da RTF ~1 o menos (`2026-10-25-banco-deck.md`). Cualquier motor ggml con backend Vulkan (`chatterbox.cpp`, `qwentts.cpp`) hereda eso; la ventaja es sobre todo en el prefill y el decodificador del códec.
- Referencia de la comunidad: la tabla de [llama.cpp discussions #10879](https://github.com/ggml-org/llama.cpp/discussions/10879) lista una Steam Deck con Vulkan: 144 t/s (pp512) y 17,5 t/s (tg128) sin flash attention (modelo concreto no verificado por mí).
- **ONNX Runtime no tiene proveedor Vulkan** (no aparece en la página oficial de proveedores de ejecución); en la Deck solo serviría en CPU. El port ONNX de Chatterbox, además, según el README de `chatterbox.cpp`, publica el multilingüe sin el tensor de CFG, así que su calidad no iguala al original.

### 3.2 PyTorch ROCm con `HSA_OVERRIDE_GFX_VERSION=10.3.0`

Evidencia:

- **Funcionó en la Deck con ROCm 5.4.2 + PyTorch/ONNX en Docker**, con el override en cada proceso, pasando los dispositivos, y subiendo en la BIOS el UMA de 1 GB a 4 GB; el autor dice que gfx1033 no está soportado y se trata como gfx1030 ([Element84](https://element84.com/machine-learning/running-rocm-5-4-2-onnx-and-pytorch-on-a-steamdeck/)). **Sin cifras de rendimiento.** Pide desactivar el sólo-lectura de SteamOS y es de 2023.
- **Con ROCm 6.1.2, la `libhsa-runtime64` aborta en gfx1033** con una aserción en `gfx10addrlib`; el workaround de la persona que reportó el fallo es el mismo override ([Debian #1087951](https://bugs.debian.org/1087951), kernel 6.10). Es un informe de un fallo y su workaround; no confirma que PyTorch compute después.
- **Un proyecto actual excluye gfx1033 del override** en su entrada de Docker sin explicar por qué (PR [unslothai/unsloth#17150](https://github.com/unslothai/unsloth/pull/17150): «gfx1033 never gets the override at all»). Sí lo aplica a gfx1030-1036 salvo gfx1033. No es prueba de que falle, pero es una señal de cautela.
- El issue [ROCm #2527](https://github.com/ROCm/ROCm/issues/2527) con el override habla de **gfx1010 (RDNA1)**, no de la Deck; sus roturas a partir de ROCm 5.3 **no se pueden atribuir a gfx1033**.
- Lo que **sí** he comprobado en esta máquina: `/dev/kfd` existe y es `crw-rw-rw-` (visible desde dentro del Flatpak y desde el anfitrión), `/dev/dri/renderD128` también; el anfitrión no tiene `/opt/rocm` (SteamOS no trae ROCm; habría que usar ruedas de PyTorch con ROCm incluido). La compilación de PyTorch del repo oficial incluye `gfx1030` en `PYTORCH_ROCM_ARCH` (`.ci/docker/manywheel/build.sh`), que es el destino del override.
- **No he ejecutado PyTorch aquí**: que `torch.cuda.is_available()` dé `True` y que un kernel real corra en gfx1033 con ROCm 6.x/7.x queda **por probar**. Es el primer experimento barato (venv con rueda ROCm, `HSA_OVERRIDE_GFX_VERSION=10.3.0`, matmul y una frase de CosyVoice3 o Chatterbox).
- Dentro del Flatpak de VS Code: la rueda de PyTorch ROCm es autocontenida, pero el sandbox y la glibc cambian lo que se ve; lo seguro es lanzar con `flatpak-spawn --host` desde un venv del anfitrión, igual que en `docs/investigacion/2026-10-25-banco-deck.md`.
- **Memoria:** la APU reparte los 16 GB; con ROCm la parte «dedicada» (UMA) cuenta aparte, y los datos de Element84 sugieren subirla en BIOS. Hoy la memoria libre en esta sesión es de ~4,8 GB disponibles (otras cosas abiertas), así que el vigilante de D15 importa para estos motores.

---

## 4. Tabla comparativa

«Corre en» = lo que he podido establecer; «RTF» = pared/audio. Medido = en esta Deck. El resto, extrapolado.

| Candidato | Capa | Licencia código / pesos | Uso comercial | es-ES con evidencia | CPU | Vulkan | ROCm (override) | Llamable como proceso |
|---|---|---|---|---|---|---|---|---|
| **Chatterbox MTL V3 + pack `es-es`** | 1 | MIT / MIT | Sí | Finetune «Spain» declarado; sin MOS ni datos por variedad | PyTorch o `chatterbox.cpp`; RTF M4 4,3, **estimado 6-12** en Deck | `chatterbox.cpp`: sin cifra multilingüe; estimado 1-3 | PyTorch sin probar; sin cifra | Sí (`tts-cli`) |
| **Qwen3-TTS Base 0,6B/1,7B** (`qwentts.cpp`) | 1 | Apache-2.0 / Apache-2.0 | Sí | Sin acentos regionales oficiales; depende de la muestra | **Medido** RTF 5,1 / 7,5 | **Medido** RTF 0,55-0,95 / 1,16 | No aplica (ggml) | Sí (ya integrado) |
| **Fun-CosyVoice3-0.5B** | 1 | Apache-2.0 / Apache-2.0 | Sí | Español en 9 idiomas; sin desglose | PyTorch, sin cifra | Sin port | Sin probar | Sí, con venv |
| Zonos v0.1 | 1 | Apache-2.0 / Apache-2.0 | Sí | Español entrenado | «Muy lento» (README) | No | Sin probar | Sí, con venv |
| OuteTTS 1.0-0.6B | 1 | Apache-2.0 / Apache-2.0 | Sí | Sin evidencia | Sin cifra | Sin evidencia | Sin evidencia | Sí |
| F5-Spanish | 1 | MIT / **CC-BY-NC** | **No** | 218 h, peninsular sobre todo (Voxpopuli) | — | — | — | — |
| XTTS-v2 | 1 | — / CPML | **No (a verificar)** | Español en 17 idiomas | — | — | — | — |
| OpenAudio S1-mini | 1 | Community / **CC-BY-NC-SA** | **No** | Español en 13 idiomas | — | — | — | — |
| **OpenVoice V2** | 2 | MIT / MIT | Sí | Conserva el acento del TTS base (V2 incluye español) | PyTorch, velocidad no declarada | No | Sin probar | Sí, con venv |
| **RVC** | 2 | MIT / MIT | Sí | Independiente del acento de la toma (no declarado) | Sí (ruta CPU para AMD); entrenar es lento | No | Sin probar | Sí (CLI) |
| kNN-VC | 2 | MIT / no declarada | Código sí; pesos por confirmar | Solo inglés evaluado | PyTorch, sin cifra | No | Sin probar | Sí |
| Seed-VC | 2 | **GPL-3.0** / GPL-3.0 | Código copyleft | No declarado | No recomendado | No | Sin probar | Sí |

## 5. Recomendación: qué probar primero en la Deck

1. **Chatterbox MTL V3 `es-es`** con la misma frase larga del banco y con una referencia peninsular de 10-15 s:
   (a) `chatterbox.cpp` en CPU y Vulkan (primero comprobar que convierte el paquete `es-es`; si no, el modelo general `es`),
   (b) si el port no acepta el paquete, PyTorch en CPU. Medir RTF, RSS y oír θ y entonación contra Qwen3-TTS.
   Riesgos: proyecto retirado, port de un solo autor, RTF en CPU probablemente > 5.
2. **Qwen3-TTS Base 0,6B (`qwentts.cpp`, Vulkan) con la misma referencia peninsular**: control ya instalado. Si suena igual de peninsular que el candidato 1, no hace falta añadir un motor; si no, el candidato 1 justifica su coste.
3. **OpenVoice V2 (convertidor de timbre)** aplicado a la toma ganadora de 1-2 hacia un destino de referencia, para ver si conserva θ y prosodia y si el timbre cambia de verdad. Si no convence, **RVC** con un destino entrenado (10 min de voz limpia) como siguiente paso, aceptando el coste de entrenar.

Experimento aparte, barato y decisivo para todo lo que sea PyTorch: **una rueda de PyTorch ROCm en un venv en el anfitrión con `HSA_OVERRIDE_GFX_VERSION=10.3.0`** (matmul y `torch.cuda.is_available()`); si falla, esos candidatos quedan en CPU. CosyVoice3 es la reserva con licencia limpia si Chatterbox no suena bien.

## 6. Pendiente y límites

- **Nada de esto lo ha ejecutado esta investigación**: las cifras de Deck solo son las de `qwentts.cpp`; el resto son del README de cada proyecto (otro hardware) o estimaciones marcadas.
- Sin MOS ni evaluación independiente en es-ES para ningún candidato; la comprobación es de oído (persona, en la Deck).
- No pude leer el texto de la CPML de XTTS (404), ni `VOICES.md` de Kokoro, ni la licencia de los checkpoints de kNN-VC.
- No verifiqué que `chatterbox.cpp` convierta el paquete `es-es` ni su Vulkan multilingüe; ni la velocidad del convertidor de OpenVoice.
- Licencia de las voces de datos de referencia (Common Voice es-ES, CC0) ya anotada en el otro documento; una muestra peninsular propia evita el problema.

## Fuentes

- Chatterbox: [repo](https://github.com/resemble-ai/chatterbox), [ficha](https://huggingface.co/ResembleAI/chatterbox), [es-es](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-es), [chatterbox.cpp](https://github.com/gianni-cor/chatterbox.cpp).
- Qwen3-TTS: [Base 0,6B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base), banco local `docs/investigacion/2026-10-25-banco-deck.md`.
- CosyVoice: [repo](https://github.com/FunAudioLLM/CosyVoice), [pesos](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512). Zonos: [repo](https://github.com/Zyphra/Zonos). OuteTTS: [0,6B](https://huggingface.co/OuteAI/OuteTTS-1.0-0.6B). Kokoro: [ficha](https://huggingface.co/hexgrad/Kokoro-82M).
- Descartados: [F5-TTS](https://github.com/SWivid/F5-TTS), [F5-Spanish](https://huggingface.co/jpgallegoar/F5-Spanish), [XTTS-v2](https://huggingface.co/coqui/XTTS-v2), [OpenAudio S1-mini](https://huggingface.co/fishaudio/openaudio-s1-mini), [Fish Speech](https://github.com/fishaudio/fish-speech).
- Conversión: [OpenVoice](https://github.com/myshell-ai/OpenVoice) (+ `docs/QA.md`, [V2](https://huggingface.co/myshell-ai/OpenVoiceV2)), [MeloTTS](https://github.com/myshell-ai/MeloTTS), [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI), [kNN-VC](https://github.com/bshall/knn-vc), [Seed-VC](https://github.com/Plachtaa/seed-vc).
- GPU: [ONNX Runtime, proveedores](https://onnxruntime.ai/docs/execution-providers/), [llama.cpp #10879](https://github.com/ggml-org/llama.cpp/discussions/10879), [Element84](https://element84.com/machine-learning/running-rocm-5-4-2-onnx-and-pytorch-on-a-steamdeck/), [Debian #1087951](https://bugs.debian.org/1087951), [unsloth#17150](https://github.com/unslothai/unsloth/pull/17150), [ROCm #2527](https://github.com/ROCm/ROCm/issues/2527), [PyTorch `build.sh`](https://github.com/pytorch/pytorch/blob/main/.ci/docker/manywheel/build.sh).

## 7. Medido en la Deck (2026-11-17, vía 1 pasos 1-3)

**Referencias:** Common Voice ya no se descarga de Hugging Face sin cuenta; se usó **VoxPopuli** (`facebook/voxpopuli`,
config `es`, split test, CC0-1.0: plenos del Parlamento Europeo, eurodiputadas españolas). Una frase de 12-13 s con
transcripción revisada por hablante: `97024`, `124708`, `103035`, `125041` (ids en `escucha/via1/ref/FUENTE.txt`,
fuera del repo, en `~/.local/share/galivelop-voice/proyectos/portal/`). Audio de pleno: algo de sala.

**Tomas** (semilla 7, frases corta y larga de `gvoice/bench.py`, Q8_0, Vulkan; pared con carga del modelo):

| Motor | Frase larga: pared / audio | RTF | Incidencias |
|---|---|---|---|
| Qwen3-TTS Base 0,6B (`qwentts.cpp`) | 7,5-10,8 s / 8,6-12,6 s | ~0,85 | con `vp-97024` la corta acaba en el fotograma 0-2 en 5 de 9 semillas |
| Chatterbox MTL V3 `es-es` (`chatterbox.cpp`) | 38,5-41,6 s / 11,2-12,2 s | ~3,4 | ninguna; la corta, ~19 s de pared para 3,2 s (carga y preprocesado de la referencia) |

Chatterbox en CPU (prueba de humo, frase corta): RTF 19,9 con carga, 10,9 sin ella; RSS 2,6 GB (KV de ~2,9 GB por el
CFG). Vulkan sin carga: RTF 2,3; RSS 1,3 GB. CPU y Vulkan no dan la misma toma con la misma semilla.

**Montaje de `chatterbox.cpp`** (`ddca05fb`, ggml `58c38058` de `scripts/setup-ggml.sh`), en
`~/.local/share/galivelop-voice/engine/chatterbox.cpp/`:

- Compilación en el Flatpak con el prefijo de `qwentts.cpp` (`P=engine/deps/prefix`): `cmake -S . -B build-vk
  -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DCMAKE_PREFIX_PATH=$P -DCMAKE_CXX_FLAGS=-I$P/include` y
  `CCACHE_DISABLE=1 TMPDIR=$HOME/.cache cmake --build build-vk -j4` (con ccache en `/tmp`, un tmpfs de 1,5 GB, falla en
  silencio en `mul_mm.comp`). Los binarios llevan rpath y corren en el anfitrión con `flatpak-spawn --host`.
- **El paquete `es-es` no basta solo:** trae `t3_es_es.safetensors`, `s3gen_v3.pt` y el tokenizador; `ve.pt`,
  `conds.pt` y `Cangjie5_TC.json` salen de `ResembleAI/chatterbox`. A `s3gen_v3.pt` le falta
  `tokenizer._mel_filters` (sin él: `missing tensor s3tokv2/mel_fb`); se añadió con
  `librosa.filters.mel(sr=16000, n_fft=400, n_mels=128)` — **no comparado con el del `s3gen.pt` general**.
- Conversión con `scripts/convert-t3-mtl-to-gguf.py` y `convert-s3gen-to-gguf.py --variant mtl` (venv con torch CPU).
  GGUF q8_0: T3 604 MB, S3Gen 827 MB; f16: 1,10 GB y 1,06 GB.
- Síntesis: `tts-cli --model <t3> --s3gen-gguf <s3gen> --text "…" --language es --reference-audio ref.wav --seed 7
  --n-gpu-layers 99 --out out.wav`.

**Pendiente de la persona:** oír `escucha/via1/` (`LEEME.txt`): acento peninsular, parecido con la referencia, voz
preferida y motor ganador.
