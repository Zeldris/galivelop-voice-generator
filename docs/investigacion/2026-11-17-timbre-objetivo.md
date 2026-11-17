# Cómo conseguir un timbre objetivo cuando el clonado copia la referencia y el retoque no basta

**Fecha:** 2026-11-17 · **Pregunta:** qué hace la gente que narra, hace audiolibros, juegos indie o doblaje sintético cuando el
clonado copia la referencia tal cual y el postproceso no basta; en concreto, para una lectora de castellano de España (mujer
madura, timbre cálido medio-grave, dicción de doblaje, ritmo pausado, toma de estudio), con uso comercial y todo local en la
Steam Deck · **Contexto:** `docs/plan.md` D19, `2026-11-17-motores-via1-deck.md`, `2026-11-17-qwen3tts-voicedesign-prompts.md`.
El referente de escucha (la dobladora de Galadriel) es solo para comparar: no se usa su voz ni audio de la película.

Convención: **Oficial** = README, ficha de modelo o código del propio proyecto, leído el 2026-11-17. **Comunidad** = fichas de
terceros, blogs, foros, anuncios. **Estimación** = deducción mía, **no medida**. **No encontrado** = se buscó y no hay dato.
Este documento no ha ejecutado ningún modelo; las lecturas de páginas las hizo una herramienta de resumen, así que las citas
literales son las que ella devolvió, no las he cotejado contra la fuente original.

## Resumen

1. **Mezclar huellas es lo más barato y tiene precedente directo, pero ninguna prueba de calidad en Qwen3-TTS.** Una ficha de
   la comunidad ([marksverdhei](https://huggingface.co/marksverdhei/Qwen3-Voice-Embedding-12Hz-1.7B)) extrae el vector ECAPA-TDNN del
   Base (1024 floats en 0,6B, 2048 en 1,7B), da una función `slerp` y dice que se puede interpolar o promediar; **no dice
   que el resultado suene bien**. Kokoro lo hace de serie (media ponderada de voces), con muchas herramientas de la comunidad. Es
   el primer experimento: 10 minutos de trabajo, sin entrenar.
2. **El modo solo-huella (`x_vector_only`) captura menos al hablante que el clonado con referencia y transcripción**
   (Baseten, comunidad). Eso juega a favor aquí: cuanto menos copia, más margen de moverse, pero también menos parecido y
   estabilidad. Un promedio (centroide) de varios clips de la misma voz da mejor huella que un clip suelto (Baseten: coseno ~0,7
   entre clips, ~0,85 con el centroide).
3. **Conversión de voz:** no hay comparativa independiente en español de OpenVoice V2, RVC ni Seed-VC (no encontrado). Todos
   necesitan un destino real con licencia; sin él, solo mueven el problema. Seed-VC es GPL-3.0.
4. **Ajuste fino:** Qwen3-TTS trae scripts oficiales (`finetuning/`: `prepare_data.py`, `sft_12hz.py`), solo un hablante,
   ejemplos con GPU CUDA. Baseten, con 1,5 h y una H100, **no superó al clonado sin entrenar en parecido ni MOS**; solo mejoró expresividad. En
   esta máquina (sin CUDA) no hay receta probada. Chatterbox tiene finetunes comunitarios con LoRA (Amharic, Telugu, Uzbek, eslovaco), sin cifras de datos mínimos.
5. **Fuentes con licencia:** no existe corpus abierto de estudio de una mujer madura peninsular que yo haya encontrado. Lo más
   cercano abierto: Sharvard (una mujer y un hombre peninsulares, CC BY 4.0 en Zenodo, ~700 frases cortas). De pago: DataOcean
   (14 hablantes de estudio, 48 kHz, condiciones sin publicar) y la contratación directa de una locutora (ofertas
   públicas de 750 USD por un conjunto; 3.000 USD+ por 8-10 h en Voices.com; 40-130 USD/h en un anuncio). En España, los
   convenios del doblaje piden prohibir el uso de la voz para entrenar IA salvo pacto expreso: la licencia hay que pedirla por escrito.
6. **El «pitido» de `chatterbox.cpp`:** no hay issue conocido. Lo más probable (**estimación**) es que el port no soporte el S3Gen V3
   del paquete `es-es`: su README no menciona V3 ni `es-es` y su variante `--variant mtl` es la del multilingüe anterior.
7. **Estilo:** en Chatterbox, `exaggeration` y `cfg_weight` (oficial); en Qwen, la instrucción de VoiceDesign/`--instruct`
   cambia ritmo y énfasis, **no** la identidad (comunidad). La cadena de narración estándar es poco procesada: paso alto,
   compresión suave, de-esser, limitador; las voces sintéticas ya vienen tratadas, por eso no se nota.

---

## 1. Mezclar o interpolar huellas de hablante

### 1.1 Qwen3-TTS

- **Qué hay (comunidad):** [`marksverdhei/Qwen3-Voice-Embedding-12Hz-1.7B`](https://huggingface.co/marksverdhei/Qwen3-Voice-Embedding-12Hz-1.7B)
  extrae el codificador de hablante (ECAPA-TDNN, x-vector) del 1,7B Base. La ficha dice: se puede interpolar entre voces con
  SLERP o media ponderada y da una función SLERP (normaliza, calcula el ángulo, vuelve a lineal si casi coinciden), con un ejemplo a t=0,5.
  Avisos de la ficha: solo sirve la huella del **Base** (CustomVoice y VoiceDesign no admiten huella); **no mezclar tamaños**
  (0,6B = 1024, 1,7B = 2048); sin transcripción de referencia, la calidad «puede bajar algo» frente al clonado completo.
  **La ficha no dice si el resultado de un promedio suena bien.**
- **Cómo se inyecta (comunidad, misma ficha):** en `qwen_tts` oficial con un `VoiceClonePromptItem` con `ref_code=None`,
  la huella en `ref_spk_embedding`, `x_vector_only_mode=True`, `icl_mode=False`. Eso salta el codificador de texto de la referencia.
- **Otro proyecto con la misma idea de reutilización:** [qwen3-tts en C puro](https://dev.to/gabrielemastrapasqua/extending-qwen3-tts-clone-voices-once-reuse-everywhere-pure-c-271o)
  guarda la huella (1024 floats ECAPA, 4 KB) y reutiliza la voz; el artículo **no** habla de mezclar. Dice que `--instruct` cambia ritmo y
  énfasis, pero «la identidad de la voz se mantiene».
- **El `.spk` de `qwentts.cpp`:** la ficha de [faster-qwen3-tts](https://pypi.org/project/faster-qwen3-tts/0.3.1/) lo cita como
  caché de latentes de hablante (con `.rvq` para el acústico). No pude leer el README de `qwentts.cpp`, así que **el formato exacto y
  si el `.spk` es solo el vector o incluye más no está verificado aquí**: hay que abrir un `.spk` y comprobar que su tamaño es 1024 o 2048 floats × 4 bytes.
- **Evidencia de que alguien lo haga con Qwen3-TTS y lo cuente:** no encontrada (no hay hilo de Reddit ni issue sobre promediar huellas).
- **Aviso conceptual (comunidad):** una guía sobre mezcla de voces avisa de que un 50/50 rara vez suena «mitad y mitad» y hay que
  ajustar los pesos de oído; ese texto es de Cartesia, no de Qwen. **Estimación:** el espacio de ECAPA se entrena para
  distinguir hablantes, no para ser lineal; un punto medio puede caer fuera de la distribución y salir apagado o inestable, sobre todo
  con huellas de hablantes muy distintos. Mezclar voces **similares** (todas mujeres maduras de LibriVox) y promediar
  varios clips de una misma voz es más seguro que cruzar mujer y hombre.
- **Qué ofrece la literatura:** [Interpolating Speaker Identities in Embedding Space for Data Expansion](https://arxiv.org/pdf/2508.19210)
  usa interpolación de huellas para crear hablantes nuevos con un TTS controlable por huella (no Qwen). Es precedente académico
  de que el método funciona en otros sistemas; no valida Qwen.

### 1.2 Kokoro y otros que mezclan voces (comunidad)

Kokoro tiene voces como tensores de estilo y varios proyectos hacen media ponderada: [Make Custom Voices With Kokoro](https://huggingface.co/spaces/limcheekin/Make_Custom_Voices_With_KokoroTTS/blob/main/app.py)
(fórmula de voces, guarda `.pt`), [Kokoro-FastAPI](https://github.com/skyiron/Kokoro-FastAPI-TTS) (`af_bella(2)+af_heart(1)`),
[pykokoro](https://pykokoro.readthedocs.io/en/stable/advanced_features.html) (`af_bella*0.7 + af_sarah*0.3`) y el
[kokoro-inno-clone-tuner](https://huggingface.co/remsky/kokoro-inno-clone-tuner) (ajusta mezclas de voces a una grabación; su autor
dice que no clona identidad fuerte). Esto es práctica real y extendida, pero **Kokoro no clona** y su voz es fija: sirve de
precedente de que la media de espacios de estilo da voces nuevas, no como motor para nosotros.

### 1.3 Chatterbox

`chatterbox.cpp` ([README](https://github.com/gianni-cor/chatterbox.cpp)) guarda con `--save-voice` cinco `.npy` (`speaker_emb`,
`cond_prompt_speech_tokens`, `embedding`, `prompt_token`, `prompt_feat`, ~160 KB) y los reutiliza con `--ref-dir`. **No describe
mezcla.** Aquí el condicionante no es un solo vector: hay tokens de prompt y rasgos de mel de una grabación concreta, así que
promediar solo `speaker_emb` y dejar el resto de la referencia daría una voz mezclada a medias. **Estimación**, no probada.

---

## 2. Conversión de voz hacia un destino

Todos los conversores necesitan un destino con voz real que se pueda usar. Sin esa voz, la conversión solo cambia de sitio el problema.

- **Cómo eligen el destino (evidencia):** en Seed-VC y RVC, el destino es un clip (Seed-VC, referencia en la inferencia) o un modelo
  entrenado con voz del destino (RVC, ≥ 10 min según su README; ver `2026-11-17-motores-via1-deck.md` §2). No encontré ninguna guía
  que explique cómo elegir un destino cuando no se puede usar la voz deseada; lo que se hace es **escoger una voz con licencia
  que se parezca lo bastante** (la persona que lo narra, un actor de pago, una voz de un corpus abierto).
- **Español, calidad real:** [no encontrado] ninguna comparativa independiente de OpenVoice V2, RVC o Seed-VC en español o con acento
  conservado. Las evaluaciones de Seed-VC son [propias](https://huggingface.co/spaces/soiz1/seed-vc3/blob/main/EVAL.md), en inglés, chino y canto: más parecido
  que RVCv2 en canto, DNSMOS algo inferior; contra OpenVoice, mejor en inteligibilidad y parecido (inglés y chino). Su README (comunidad/oficial) presenta la v2
  como conversión de voz y de acento, es decir, **puede cambiar el acento**, un riesgo aquí.
- **Chatterbox VC:** el repo oficial trae `example_vc.py` y una app de Gradio (README); sin ajustes ni cifras. No encontré
  evaluación; usa el S3Gen del mismo modelo, de modo que arrastra el problema de V3 de la sección 6 si se usa el port.
- **Encaje con este proyecto:** OpenVoice V2 (MIT) deja el acento al TTS base y solo cambia el timbre (oficial, `docs/QA.md`, ya
  citado en el otro documento). **Estimación:** cambiará el timbre, pero un conversor aplicado a una voz con timbre ya copiado
  de LibriVox heredará artefactos de las dos etapas. Su valor es limitado si el destino es otra locutora real sin licencia.

---

## 3. Ajuste fino (fine-tuning / LoRA)

### 3.1 Qwen3-TTS (Oficial / Comunidad)

- **Scripts oficiales: sí.** La carpeta `finetuning/` de [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS/tree/main/finetuning):
  `prepare_data.py` (JSONL → códigos de audio con el tokenizador 12Hz) y `sft_12hz.py` (SFT; checkpoint por época).
  Datos: JSONL con `audio`, `text`, `ref_audio` (recomienda el mismo `ref_audio` en todas las muestras). **Solo un hablante**;
  multihablante «en versiones futuras». Los ejemplos del README asumen GPU CUDA, bf16 y FlashAttention 2; el README no da mínimos de hardware.
- **Variantes de la comunidad:** [Qwen3-TTS-finetune](https://github.com/sruckh/Qwen3-TTS-finetune) (envoltorio), una variante LoRA
  (`sft_12hz_lora.py`) citada en una ficha de modelo, y [fichas de finetunes en otros idiomas](https://huggingface.co/beyoru/Qwen3-TTS-12Hz-1.7B-Vi).
  Una réplica del flujo recomienda 16 GB+ de GPU para el 1,7B y 32 GB de RAM; **no es oficial**.
- **Evidencia de resultado:** [Baseten](https://www.baseten.co/blog/fine-tuning-qwen3-tts-for-high-quality-voice-cloning/):
  800 clips de LJ Speech (~1,5 h), una H100, ~1 h, 8 épocas, tasa de aprendizaje ≤ 1e-5. **«No superó materialmente al clonado sin
  entrenar en parecido ni MOS»**; las ganancias fueron de expresividad/prosodia en las muestras de escucha, y ~16 % menos latencia al primer audio
  frente al modo con referencia. Dato útil: la huella usada era el **centroide de 64 clips**.
- **Viabilidad sin NVIDIA (estimación):** no encontré ninguna receta de fine-tuning de Qwen3-TTS en AMD, CPU ni APU. El 0,6B en PyTorch con
  ROCm sin probar (el estado de ROCm en la Deck está en el otro documento) o en CPU sería lento; con una Deck, un SFT de 0,6B no es realista como primer paso. **Nube alquilada** (una hora de GPU
  puntual) para entrenar y volver a correr local con `qwentts.cpp` sería la vía viable; que `qwentts.cpp` cargue un checkpoint ajustado **no está verificado**.

### 3.2 Chatterbox (Comunidad)

Hay varias recetas: LoRA en el T3 más reentrenar la matriz de texto y la cabeza para vocabulario nuevo:
[gabar-tech/chatterbox-amharic](https://huggingface.co/gabar-tech/chatterbox-amharic),
[shankarpandala/chatterbox-telugu](https://huggingface.co/shankarpandala/chatterbox-telugu) (~34,5k clips, 10.000 pasos),
[Ahmed-Ezzat20/chatterbox-finetuning-multilingual](https://gh.hhj520.top/Ahmed-Ezzat20/chatterbox-finetuning-multilingual) y
[la nota sobre el eslovaco](https://dev.to/pekisko/fine-tuning-chatterbox-on-a-low-resource-language-7-things-that-mattered-13e1)
(MIT; consejos de inferencia, ver §5). **No hay mínimo de datos ni hardware publicado en lo que leí.** Para la **voz** (no el idioma) una LoRA del T3 con
una hora de una locutora sería lo equivalente, pero el finetune del idioma ya existe (`es-es`). Chatterbox está retirado (agosto 2026) y el
port a C++ no carga LoRA (no documentado).

### 3.3 Otros

F5-TTS: pesos CC-BY-NC, descartado por licencia (otro documento). StyleTTS2 y similares: **no investigado** en esta pasada.

---

## 4. Fuentes de voz con licencia

### 4.1 Corpus abiertos

| Corpus | Qué es | Licencia | Encaje |
|---|---|---|---|
| [Sharvard](https://zenodo.org/records/3547446) | 700-720 frases (tipo Harvard) leídas por **una mujer y un hombre peninsulares**; 264 MB | **CC BY 4.0** (Zenodo). La ficha de Piper dice CC BY 3.0: [conflicto, verificar](https://huggingface.co/rhasspy/piper-voices/raw/23fc3f9dd3c46fa7f2235964caa7be4e9b2e2e6f/es/es_ES/sharvard/medium/MODEL_CARD) | Cabe en una referencia o un fine-tuning pequeño. **Estudio no confirmado**, frases cortas de audiología (no narración), edad de la hablante **no encontrada** |
| OpenSLR (euskera, catalán, gallego) | Corpus de estudio de Iberia | CC BY-SA 4.0 | **No es castellano** |
| [Nos_Celtia-GL](https://investigacion.usc.es/documentos/668fc40fb9e7c03b01bd3891?lang=es) | Voz femenina de estudio, **gallego** | CC BY 4.0 con solicitud | No es castellano |
| [DataOcean, Spain Spanish multi-speaker](https://dataoceanai.com/?p=1101) | 14 hablantes (8 mujeres), estudio, 48 kHz/24 bit | Comercial; **precio y licencia sin publicar** | Habría que pedir presupuesto; no se sabe si hay mujer madura |
| VoxPopuli, LibriVox, Common Voice | Ya probados | CC0 / dominio público / CC0 | Ruido de sala, o es lo que da el parecido «copiado» que no gusta |

No encontré (**no encontrado**) un corpus abierto de narración de estudio de una mujer castellana madura con licencia comercial.

### 4.2 Contratar a una locutora o usar un mercado

- **Anuncios públicos de grabación para IA en castellano peninsular (comunidad, de listados):**
  [Upwork: 750 USD fijos](https://www.upwork.com/freelance-jobs/apply/Native-Spain-Spanish-Voice-Actor-Needed-Consented-Speech-Dataset-Recording-750-Fixed-Fee_~022070550061868476393/)
  por un conjunto de habla consentido;
  [Mediabistro: 40-130 USD/h](https://www.mediabistro.com/jobs/3542401742-remote-peninsular-spanish-voice-actor-for-ai-voice-cloning-40-130-hour);
  [Voices.com](https://www.voices.com/solutions/voice-ai): proyectos «opt-in» de licencia de voz (un proyecto bilingüe a
  3.000 USD+ por 8-10 h; **no pude abrir la página**, el dato viene de un resumen de búsqueda). **Son precios de ofertas de
  trabajo, no tarifas de venta de una voz.** Al menos uno de los anuncios prohíbe la reventa y el reuso fuera del caso de uso.
- **Marketplaces con licencia:** [Respeecher](https://www.respeecher.com/voice-actors/sacha-criado) lista una actriz española
  con voces «licenciadas legalmente»; [ElevenLabs](https://elevenlabs.io/sv/iconic-voices) tiene un mercado de voces de
  famosos con contrato por territorios y duración (comunidad). Ambos son **servicios en la nube**: no dan el audio ni los pesos
  para correr en local. **Qué cubre la licencia de un uso local y dentro de una web propia: no encontrado**.
- **Royalties típicos (Camb.ai, blog de proveedor):** [0,03-0,20 USD por 1.000 caracteres](https://www.camb.ai/es/blog-post/how-voice-actors-license-their-voice-to-ai); valor orientativo.
- **Modelo contractual en España:** la [NAVA AI Rider](https://navavoices.org/wp-content/uploads/2025/07/NAVA-AI-Rider-en-espanol-con-instrucciones.pdf)
  existe en español; los convenios de doblaje que recoge [Ecija](https://www.ecija.com/en/news-and-insights/voces-en-defensa-propia-la-batalla-legal-frente-a-la-clonacion-por-ia/)
  excluyen el uso de la voz para entrenar IA o más allá de la producción. **Lo que se necesita es un contrato escrito** de
  cesión para entrenar/clonar con uso comercial, territorios y plazo; la LO 1/1982 protege la voz. Conviene abogado propio.
- **Alternativa de coste cero:** la persona que lo monta, un familiar o una amiga que grabe unas horas con permiso escrito. La
  cadena de licencia es la más limpia y el material «de estudio» lo pone una cabina doméstica bien tratada. La edad y el timbre se cuentan en el casting, no en el postproceso.

---

## 5. Control de estilo y cadena de postproceso

### Chatterbox (Oficial)

[README](https://github.com/resemble-ai/chatterbox): `exaggeration=0,5` y `cfg_weight=0,5` por defecto; para voces de referencia rápidas,
bajar `cfg_weight` a ~0,3; para más dramatismo, `cfg_weight` ~0,3 y `exaggeration` ≥ 0,7; «un `exaggeration` más alto tiende a acelerar el habla»
(para **lento**, `exaggeration` bajo y `cfg_weight` más bajo); `cfg_weight=0` si el clip no coincide con el idioma (para no heredar el acento del clip).
`chatterbox.cpp` expone `--cfg-weight`, `--exaggeration`, `--min-p`, `--cfm-steps`, `--seed` (README).
Notas de [la experiencia con el eslovaco](https://dev.to/pekisko/fine-tuning-chatterbox-on-a-low-resource-language-7-things-that-mattered-13e1) (comunidad, un solo caso):
temperatura 0,6 (por defecto 0,8), `top_p` 0,92, penalización de repetición 1,25; **reintentar con cinco semillas** si sale corto;
un clip de referencia **ruidoso** pasa el ruido a todas las tomas; limpiar con unos -12 dB de reducción de ruido, y -18 dB «suena metálico»;
añadir una frase de calentamiento por si la primera palabra sale rara.

### Qwen3-TTS

La instrucción (`--instruct`/VoiceDesign) cambia «ritmo, pausa y énfasis» y mantiene la identidad (comunidad, artículo en C puro;
el otro documento ya trata los prompts de VoiceDesign). **No hay parámetro documentado de «grave»**; VoiceDesign no da acento peninsular fiable.
Semillas: la semilla cambia la toma, y entre CPU y Vulkan no se reproduce (medido, otro documento). **Estimación:** elegir la semilla por escucha entre ~8-10 tomas es barato (RTF ~0,9) y es lo que el propio otro documento ya hace.

### Cadena de narración (Comunidad, foros de audio)

Consenso de [Audacity](https://forum.audacityteam.org/t/effects-order-for-audiobook-narration/85217),
[Steinberg](https://forums.steinberg.net/t/what-settings-are-you-using-for-narration-vo-channel-strip/78453),
[Violet Recording](https://violetrecording.com/how-to-mix-spoken-word-vocals/): paso alto (~80 Hz) → reducción de ruido suave →
EQ → compresión → de-esser → limitador al final; hay desacuerdo sobre si el de-esser va antes o después del compresor. Todos avisan de **no
sobreprocesar**. Estándar de entrega de audiolibros (ACX): RMS de -23 a -18 dB, pico ≤ -3 dB, suelo de ruido < -60 dB, ~0,5 s de silencio de sala
al principio y ~3,5 s al final (de foros; **verificar con ACX**); algunas fuentes dan LUFS en lugar de RMS. Dos matices:

- Una voz sintética ya sale sin ruido ni sibilancia de cabina y con compresión implícita: la cadena **no cambia el timbre**; coincide con lo que
  ya observó la persona (EQ y compresión no se notan). El postproceso sirve para igualar el nivel y la salida, no para fabricar timbre.
- **Estimación:** el timbre «cálido medio-grave» de una actriz viene en gran parte del **micrófono y la distancia** (efecto proximidad), de la
  edad y de la resonancia del tracto; un cambio de tono con formantes conservados (lo que ya probó, rubberband) cambia la sensación de la altura pero no la del tracto. Un cambio de tono **con** formantes (mover los dos a la vez, algo menos de 1 semitono) o un realce suave a 150-250 Hz sería lo que hay que probar, **sin evidencia** de que guste.

---

## 6. El «pitido» de `chatterbox.cpp` con `es-es` (opcional)

- **Issue conocido:** **no encontrado**. El único abierto del port es el [#4](https://github.com/gianni-cor/chatterbox.cpp/issues) («error reading model», GGUF).
  Los problemas del repo oficial son otros: ruido y silencios al final ([#287](https://github.com/resemble-ai/chatterbox/issues/287),
  [#271](https://github.com/resemble-ai/chatterbox/issues/271)), y que [V3 va peor que V2](https://github.com/resemble-ai/chatterbox/issues/551)
  en danés y finlandés. Ninguno es un tono fijo ni habla de `s3gen_v3` ni de mel.
- **Qué dice el README del port ([chatterbox.cpp](https://github.com/gianni-cor/chatterbox.cpp)):** no menciona «V3», `s3gen_v3` ni `es-es`;
  `--language` acepta códigos como `es`, no `es-es`; calcula los **filtros mel en la conversión y los guarda en los GGUF** (24 kHz de 80 canales y fbank Kaldi de 16 kHz).
  La [ficha de `es-es`](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-es) lista `s3gen_v3.pt` y no dice nada de mel ni de ajustes.
- **Estimación (no medida):** la causa más probable es que el conversor del port está hecho para el S3Gen del multilingüe anterior, y el V3 cambia
  la estructura o el tokenizador de voz (de ahí el `mel_fb` que falta); un mel de 128 bandas puesto «a mano» con `librosa` no es comparable con el del
  extractor original (el README del port habla de 80 canales en un sitio y la persona usó 128 para el `s3tokv2`: **esa diferencia es una pista, no una prueba**).
  Un tono fijo de ~6 kHz con RMS bajo es lo que sale de un vocoder que recibe un mel casi constante o fuera de rango.
- **Comprobaciones baratas (sin ejecutar nada nuevo salvo el propio port):** (a) sintetizar con el T3 `es-es` **y el S3Gen del modelo general `es`** (V2) y ver
  si hay voz: aísla el S3Gen V3; (b) comparar el tensor `mel_fb` añadido con el que lleve el S3Gen general; (c) abrir un issue en
  `gianni-cor/chatterbox.cpp` con esa tabla. El proyecto de origen está **retirado**, así que no cabe esperar arreglo.

---

## 7. Recomendación para nosotros

Ordenados por probabilidad de éxito × coste en esta máquina.

### Camino A (primero): fabricar la voz en el espacio de huellas de Qwen3-TTS con `qwentts.cpp`

Probabilidad de que dé una voz distinta de las de LibriVox: media; coste: horas, sin entrenar, todo local; reversible.
1. Del `.spk` de la lectora elegida y de 3-5 más de las 11 de LibriVox (mujeres maduras, graves), sacar la huella de cada una (0,6B: 1024 floats).
   Comprobar antes el tamaño del `.spk` (1024 × 4 bytes) y que los **vectores de varios clips de una misma voz** se promedian
   (centroide, como en Baseten).
2. Generar `.spk` nuevos con un script de unas 20 líneas: (i) `slerp` 50/50 entre la elegida y otra; (ii) **centroide de las 3-5 voces más graves** (una voz «media» sin la marca de ninguna);
   (iii) la elegida más una dirección «medio-grave» = media de las graves menos media de las agudas, con peso 0,3-0,7. Normalizar a la
   norma original de los vectores (la media baja la norma).
3. Misma frase larga, 8 semillas, `--ref-spk` con cada `.spk`. **Criterio:** que no sea la voz de nadie en particular, sin artefactos, cálida y estable. Si el `.spk`
   solo-huella se oye peor que el clonado con referencia, **probar el centroide de muchos clips**, no un único clip.
**Riesgos:** huellas fuera de distribución (voz apagada, deriva); el modo solo-huella pierde parecido y estabilidad; la licencia de las lectoras de LibriVox (dominio público, ya aceptada en el proyecto) **no aclara** si una huella derivada de una persona real, mezclada, deja de ser su voz (en España la voz es un derecho de la personalidad: una mezcla suficientemente lejana de todas es la respuesta práctica).

### Camino B: contratar o grabar una voz propia y usarla como referencia (y, si hace falta, como centroide de huella)

Probabilidad de éxito: **alta** para el timbre buscado; coste: dinero y tiempo, no máquina. Es lo único con la cadena de licencia limpia y con la
calidad de estudio por construcción.
1. Redactar un contrato de cesión (guion de la NAVA AI Rider en español) con: uso comercial, entrenamiento y clonado local, territorios, plazo, sin límite de reproducciones. Consulta a un abogado.
2. Encargar a una locutora de timbre cálido medio-grave **15-30 min** de lectura pausada, limpia, 48 kHz, con casting por una muestra de 1 min; extraer el
   **centroide de huella** de ~64 trozos de 10 s y probar a clonar con `qwentts.cpp`. Con 15-30 min ya basta para referencia y huella; el ajuste fino
   (Camino C) pide más y **no** mejoró el parecido en el único caso medido.
3. Primer experimento barato: pedir 3 muestras de prueba de 1 min a 3 locutoras de listados (Upwork/agencias) con el texto de la frase larga y compararlas con las voces de LibriVox,
   antes de firmar nada.

### Camino C (último): ajuste fino del 0,6B Base con esa misma voz

Probabilidad: baja a media; coste: alto (GPU alquilada; en la Deck, no probado). Solo si B da una voz que se copia bien pero sin la expresividad (ritmo, calidez) que se busca,
que es donde Baseten sí vio ganancia.
1. Con 1-2 h de B, usar `finetuning/prepare_data.py` + `sft_12hz.py` en una GPU de alquiler durante ~1 h (tasa ≤ 1e-5, mismo `ref_audio`).
2. Primer experimento: **comprobar antes** que `qwentts.cpp` convierte y carga el checkpoint resultante (convertidor a GGUF) con un finetune de la comunidad ya publicado, por ejemplo el [Vi](https://huggingface.co/beyoru/Qwen3-TTS-12Hz-1.7B-Vi), antes de gastar horas de GPU.

### No recomendado ahora
- **Conversión de voz (OpenVoice/RVC/Seed-VC)** sin un destino con licencia: no hay evidencia en español y se apila con los artefactos del TTS. Tiene sentido **después** de B, para mover una toma de cualquier motor al timbre de la locutora contratada, si el clonado directo no basta.
- **Chatterbox `es-es`** mientras el pitido no se aísle (§6); el paso (a) de §6 tarda minutos y decide si merece la pena volver.
- Más postproceso: no cambia el timbre (§5).

## 8. Límites

- Nada de esto se ha ejecutado. No he leído el README ni el código de `qwentts.cpp` (ficheros `.spk`, `--ref-spk`) ni el de `qwen_tts`; las afirmaciones sobre ellos vienen de fichas y búsquedas de la comunidad.
- Varias lecturas (Voices.com, precios de anuncios, el README de Qwen3-TTS) las hizo una herramienta de resumen; la página de Voices.com devolvió 403 en la lectura directa.
- Sin comparativa independiente de conversión de voz en español, ni evidencia pública de mezcla de huellas en Qwen3-TTS, ni cifras de datos mínimos para Chatterbox.
- No investigado: StyleTTS2, otros bancos de voces (Common Voice/CML-TTS/MLS por acentos), marketplaces de actrices de voz en España concretos, precios de agencias españolas.
- El estado legal de una voz derivada (mezcla de huellas de personas reales) no lo he podido verificar; **no es asesoramiento jurídico**.

## Fuentes

- Qwen3-TTS: [repo y `finetuning/`](https://github.com/QwenLM/Qwen3-TTS/tree/main/finetuning), [huella ECAPA, SLERP](https://huggingface.co/marksverdhei/Qwen3-Voice-Embedding-12Hz-1.7B), [Baseten, fine-tune](https://www.baseten.co/blog/fine-tuning-qwen3-tts-for-high-quality-voice-cloning/), [qwen3-tts en C](https://dev.to/gabrielemastrapasqua/extending-qwen3-tts-clone-voices-once-reuse-everywhere-pure-c-271o), [faster-qwen3-tts (`.spk`)](https://pypi.org/project/faster-qwen3-tts/0.3.1/), [finetune Vi](https://huggingface.co/beyoru/Qwen3-TTS-12Hz-1.7B-Vi), [finetune comunitario](https://github.com/sruckh/Qwen3-TTS-finetune).
- Interpolación: [arXiv 2508.19210](https://arxiv.org/pdf/2508.19210); Kokoro: [Make Custom Voices](https://huggingface.co/spaces/limcheekin/Make_Custom_Voices_With_KokoroTTS/blob/main/app.py), [Kokoro-FastAPI](https://github.com/skyiron/Kokoro-FastAPI-TTS), [pykokoro](https://pykokoro.readthedocs.io/en/stable/advanced_features.html), [inno-clone-tuner](https://huggingface.co/remsky/kokoro-inno-clone-tuner).
- Chatterbox: [repo](https://github.com/resemble-ai/chatterbox), [`es-es`](https://huggingface.co/ResembleAI/Chatterbox-Multilingual-es-es), [chatterbox.cpp](https://github.com/gianni-cor/chatterbox.cpp), issues [#287](https://github.com/resemble-ai/chatterbox/issues/287), [#271](https://github.com/resemble-ai/chatterbox/issues/271), [#551](https://github.com/resemble-ai/chatterbox/issues/551); finetunes [amárico](https://huggingface.co/gabar-tech/chatterbox-amharic), [telugu](https://huggingface.co/shankarpandala/chatterbox-telugu), [multilingüe](https://gh.hhj520.top/Ahmed-Ezzat20/chatterbox-finetuning-multilingual), [eslovaco](https://dev.to/pekisko/fine-tuning-chatterbox-on-a-low-resource-language-7-things-that-mattered-13e1).
- Conversión: [Seed-VC EVAL](https://huggingface.co/spaces/soiz1/seed-vc3/blob/main/EVAL.md).
- Voces y licencias: [Sharvard (Zenodo)](https://zenodo.org/records/3547446), [Piper sharvard](https://huggingface.co/rhasspy/piper-voices/raw/23fc3f9dd3c46fa7f2235964caa7be4e9b2e2e6f/es/es_ES/sharvard/medium/MODEL_CARD), [DataOcean](https://dataoceanai.com/?p=1101), [Nos_Celtia-GL](https://investigacion.usc.es/documentos/668fc40fb9e7c03b01bd3891?lang=es), [Respeecher](https://www.respeecher.com/voice-actors/sacha-criado), [Voices.com](https://www.voices.com/solutions/voice-ai), [Camb.ai](https://www.camb.ai/es/blog-post/how-voice-actors-license-their-voice-to-ai), [NAVA AI Rider](https://navavoices.org/wp-content/uploads/2025/07/NAVA-AI-Rider-en-espanol-con-instrucciones.pdf), [Ecija](https://www.ecija.com/en/news-and-insights/voces-en-defensa-propia-la-batalla-legal-frente-a-la-clonacion-por-ia/), anuncios [Upwork](https://www.upwork.com/freelance-jobs/apply/Native-Spain-Spanish-Voice-Actor-Needed-Consented-Speech-Dataset-Recording-750-Fixed-Fee_~022070550061868476393/) y [Mediabistro](https://www.mediabistro.com/jobs/3542401742-remote-peninsular-spanish-voice-actor-for-ai-voice-cloning-40-130-hour).
- Postproceso: [Audacity](https://forum.audacityteam.org/t/effects-order-for-audiobook-narration/85217), [Steinberg](https://forums.steinberg.net/t/what-settings-are-you-using-for-narration-vo-channel-strip/78453), [Violet Recording](https://violetrecording.com/how-to-mix-spoken-word-vocals/).

## Resultado en la Deck (2026-11-17)

Medido con `qwentts.cpp` (Base 0,6B, Vulkan), escuchado por la persona; tomas fuera del repo en
`~/.local/share/galivelop-voice/proyectos/portal/escucha/via1/`.

| ronda | qué | resultado |
|---|---|---|
| 1 `mezcla-r1/` | mezclas de huellas de 11 lectoras de LibriVox (dirección «grave», centroide, slerp, acentuar) en modo solo huella | descartada: suena igual que DreamVoz aunque el F0 baje ~25 Hz. Las huellas de LibriVox se parecen mucho entre sí (coseno 0,95-0,97) |
| 2 `diseno-r2/` | timbre diseñado con VoiceDesign 1.7B desde descripción → huella con el talker 0,6B → Base 0,6B en español | la persona elige el timbre de **V1-s101**, pero sesea y suena latinoamericana: el acento viaja en la huella |
| 3 `acento-r3/` | V1 + DreamVoz (slerp 25/40/55 %), V1 + ICL de DreamVoz, V1 en Base 1.7B | gustan slerp 40 % y 55 % |
| 4 `afinado-r4/` | slerp 40/47/55 % × 4 semillas con un párrafo cargado de zetas | **aprobada: slerp 55 %, semilla 7** |

Receta y huella: `proyectos/portal/voz/lectora-es/` (`RECETA.md`). Lo que funcionó: **timbre de una voz
diseñada + acento de una voz real peninsular, mezclados en el espacio de huellas**. Ni el postproceso (EQ,
tono) ni mezclar voces parecidas movieron el timbre. Whisper comprueba el texto, pero no oye el seseo: eso
sigue siendo de oído. Precaución: la Deck se colgó con dos cargas de GPU a la vez (una sola cada vez).
