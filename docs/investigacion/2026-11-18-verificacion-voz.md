# Verificación automática de voz sintetizada (gallego, castellano, inglés)

Fecha de consulta de todas las fuentes: 2026-11-18. Investigación de solo lectura: no se instaló ni descargó nada.

Convención: **[verificado]** = leído en la ficha o repo citado; **[estimación]** = cifra mía, sin fuente, a medir en la Deck; **[no verificado]** = no apareció en lo consultado.

## 0. Problema y resumen

La comprobación actual (whisper large-v3-turbo `-l gl` + WER contra el guion) falla por diseño: whisper tiene un modelo de lenguaje implícito fuerte que "arregla" lo que oye (castellaniza el gallego) y el WER solo mira palabras, no ruidos, chasquidos ni fonemas mal dichos. Hace falta una **cascada**: (a) ASR propio de la lengua, (b) fonemas/alineado con confianza por palabra, (c) calidad sin referencia por tramos.

Datos externos que lo respaldan: ElevenLabs publica para Whisper large-v3 un WER del 33,4 % en FLEURS gallego (comparativa de un proveedor, no independiente) [elevenlabs.io/speech-to-text/galician](https://elevenlabs.io/speech-to-text/galician). Los fine-tunes en gallego bajan a ~5 % en Common Voice 13 (ver sección 1).

## 1. Gallego (gl)

Motor: Nos_StyleTTS2-Celtia-GL (Apache 2.0). Fonetizador de la propia voz: Cotovía.

### 1.1 Herramientas recomendadas

**ASR gallego (necesidad 1)**

| Candidato | Licencia | Tamaño | CPU | Fiabilidad publicada en gl | Fuente |
|---|---|---|---|---|---|
| `proxectonos/stt_gl_conformer_ctc_large_v1.0` (NeMo, Conformer-CTC large, SentencePiece BPE, 16 kHz) | Apache 2.0 | no indicado en la ficha; **[estimación]** ~120 M parámetros, ~0,5 GB | sí en principio (modelo CTC, no autorregresivo); NeMo en Python 3.13 **[no verificado]** | La ficha da 8,670 de WER idéntico en 4 test sets (CV22, ParlAspeech, OpenHQ-SpeechT GL, FLEURS GL): parece error de copia, no fiarse. Alineado forzado con NeMo: error medio de frontera 47,0 ms y 92,8 % dentro de 100 ms en ParlAspeech | [HF](https://huggingface.co/proxectonos/stt_gl_conformer_ctc_large_v1.0) |
| `HiTZ/whisper-large-v3-gl` (también tiny/base/small/medium/large/large-v2) | Apache 2.0 | ~2 B parámetros (F32) | sí, pero lento (large); small/medium viables | WER 5,01 % en Common Voice 13 gl (large-v2: 5,99 %; small: 10,99 %). Débil en audio ruidoso y habla espontánea. Paper Whisper-LM: [arXiv 2503.23542](https://arxiv.org/abs/2503.23542) | [HF large-v3-gl](https://huggingface.co/HiTZ/whisper-large-v3-gl), [small-gl](https://huggingface-proxy.pages.dev/HiTZ/whisper-small-gl) |
| `BSC-LT/whisper-large-v3-LoS` (es, ca, gl, eu) | no visto | large-v3 (~1,5-2 B) | lento | WER en CV17 anunciado, cifra **[no verificado]** | [HF](https://hface.pages.dev/BSC-LT/whisper-large-v3-LoS) |

Descartados: `ITG/wav2vec2-large-xlsr-gl` y `ITG/whisper-small-gl` son CC-BY-NC-ND 4.0 (no libre; sin WER en la ficha) ([ficha](https://huggingface.co/ITG/wav2vec2-large-xlsr-gl/commit/f5bd548816f49ab1bb26ecfee671db5e0664caca)). `infinitejoy/wav2vec2-large-xls-r-300m-galician`: cifras contradictorias en su ficha ([ficha](https://huggingface.co/infinitejoy/wav2vec2-large-xls-r-300m-galician/blob/main/README.md)). `BuzzASR/galician` y los turbo de `juanjucm`/`mozilla-ai` son de terceros con cifras autoinformadas (mozilla-ai turbo-gl: WER 7,89 tras afinar, desde 25,04 el base). Baseline académico wav2vec 2.0 (Froiz-Míguez et al., XoveTIC 2022): 28,67 % WER en parlamento espontáneo, 18,61 % con LM ([paper](https://1www.easychair.org/publications/open/hdqh)).

Valoración: el Conformer-CTC de Nós es el mejor para esta tarea porque (i) un CTC sin decodificador autorregresivo **no inventa ni normaliza** tanto como whisper, (ii) da alineado forzado nativo, (iii) se entrenó con ParlAspeech/CV/FLEURS gl. El HiTZ large-v3-gl es el respaldo con número claro (5 %).

**Fonemas / confianza por palabra (necesidad 2)**

- Preferente: **alineado forzado CTC con el propio Conformer de Nós** (NeMo `align.py`, salida CTM; ver ficha) y puntuación media de log-prob por palabra. Sirve sin convertir a IPA.
- Alternativa ligera: `ctc-forced-aligner` (BSD-2) con `MahmoudAshraf/mms-300m-1130-forced-aligner` (0,3 B, 158 lenguas, **CC-BY-NC 4.0**, no libre del todo; se puede pasar otro modelo con `--alignment_model`). Uso: `ctc-forced-aligner --audio_path a.wav --text_path t.txt --language glg --romanize`. Las puntuaciones se calculan internamente, pero el JSON de ejemplo solo trae start/end/text: hay que leer `scores` desde Python. Menor memoria que torchaudio (afirmación del README). [repo](https://github.com/MahmoudAshraf97/ctc-forced-aligner), [modelo](https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner). Que `glg` esté en la lista de 158 lenguas **[no verificado]**.
- Reconocimiento de fonemas multilingüe: `facebook/wav2vec2-xlsr-53-espeak-cv-ft` (Apache 2.0, salida fonemas IPA estilo espeak, 16 kHz, base XLSR-53; la ficha no da PER ni lenguas de afinado; paper [arXiv 2109.11680](https://arxiv.org/abs/2109.11680)) [HF](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft). Tamaño **[estimación]** ~1,2 GB, CPU viable. Se compara con los fonemas de Cotovía (hay que mapear el alfabeto de Cotovía a IPA; trabajo propio) con distancia de edición por palabra. Gallego no es lengua de afinado confirmada: esperar PER alto, usar solo como señal relativa (comparar el mismo texto entre variantes de síntesis, no valores absolutos).
- `allosaurus` (GPL-3.0, ~2000 lenguas, CPU por defecto, `python -m allosaurus.run -i a.wav --lang glg`): la ficha avisa de que los modelos preentrenados pueden no ser precisos y no da métricas; inventario `glg` **[no verificado]** ([repo](https://github.com/xinjli/allosaurus)). Tercera opción.

**Calidad sin referencia por tramos (necesidad 3)** (compartido, ver sección 4).

### 1.2 En qué fallan con gallego

- Whisper genérico castellaniza (reemplaza palabras gallegas por castellanas, normaliza grafías): oculta justo lo que se quiere detectar. Los afinados HiTZ reducen el problema pero siguen siendo decodificadores autorregresivos con prior de lenguaje.
- El WER por palabra no ve ruidos entre palabras, chasquidos, geminaciones raras ni vocales abiertas/cerradas mal dichas (e/ɛ, o/ɔ), ni gheada/seseo (el gallego estándar distingue; el modelo CTC genérico no lo penaliza).
- Los modelos multilingües de fonemas tienen poca o nula cobertura declarada de gallego.

### 1.3 Diagnóstico de fallos típicos de StyleTTS2-Celtia

La ficha de Nós [verificado] solo da: alpha 0,8, beta 0,8, t 0,2, 10 pasos de difusión, embedding scale 1,0 como valores recomendados; una sola voz (Celtia); requiere Cotovía; evaluación DNSMOS OVRL (corpus 3,511; StyleTTS2 3,45 en trozos cortos, medios y largos). El resumen que obtuve de la ficha dice que el texto completo trata artefactos y audio de referencia, pero **ese apartado no llegó** en lo recuperado: leer la ficha completa a mano. [HF](https://huggingface.co/proxectonos/Nos_StyleTTS2-Celtia-GL)

Lo que dice la documentación general de StyleTTS2 [verificado en guías de terceros y wrappers, no en el paper]: alpha controla el timbre y beta la prosodia; valores altos = estilo predicho desde el texto (más "libre"), valores bajos = más pegado al embedding de la referencia. Los valores de la ficha de Nós (0,8/0,8) están lejos de los de la librería original (0,3/0,7) [PyPI styletts2](https://pypi.org/project/styletts2/). No hallé ninguna fuente primaria que trate referencias de estilo en otra lengua ni artefactos por alpha/beta bajos.

Hipótesis a contrastar (**[no verificado], marcadas como hipótesis**):

1. Referencia de estilo en castellano con alpha/beta bajos: el estilo arrastra prosodia/fonética del castellano y el difusor genera estilos fuera de distribución → ruidos, vocales mal formadas. Test: sintetizar el mismo texto con (a) referencia en gallego de Celtia, (b) sin referencia (alpha=beta=1, estilo solo del texto), (c) referencia castellana; comparar puntuación por palabra y por tramo.
2. Semilla de difusión: la salida es estocástica; sintetizar 3-5 muestras por trozo y quedarse con la de mejor puntuación (selección automática) mitiga artefactos puntuales.
3. Trozos largos: la ficha mide corto/medio/largo y no da diferencia fuerte en DNSMOS, pero conviene troceo por oraciones.
4. Fonemas: entradas que Cotovía fonetiza mal (siglas, números, extranjerismos) producen sonidos raros localizados; comprobar si los tramos malos coinciden con palabras que Cotovía trató como excepción.

Método de diagnóstico: por cada audio, tabla `palabra | inicio-fin | confianza CTC | distancia de fonemas | UTMOS/DNSMOS del tramo`; marcar palabras con confianza baja o tramos con calidad baja y escucharlas (la persona nativa decide).

## 2. Castellano (es)

Motor: Qwen3-TTS en la Deck (Apache 2.0; lenguas: zh, en, ja, ko, de, fr, ru, pt, es, it) [repo](https://github.com/QwenLM/Qwen3-TTS) [verificado].

### 2.1 Herramientas

- **ASR**: no se investigó a fondo (solo gallego se pidió inicialmente). Opciones razonables: `openai/whisper-large-v3(-turbo)` o `BSC-LT/whisper-large-v3-LoS` (incluye español). Whisper en castellano es mucho más fiable que en gallego, pero mismo defecto de normalizar. Cifras de es **[no verificado]**; medir contra el propio guion.
- **Fonetizador**: `espeak-ng` (voces `es` España y `es-419` Latinoamérica) [verificado](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md); salida IPA con `espeak-ng -v es --ipa -q "texto"`. Licencia GPL-3 **[no verificado en esa página]**. Alternativa `epitran` (spa-Latn, reglas ortográficas; **[no verificado]** aquí). Para comparar el audio: `wav2vec2-xlsr-53-espeak-cv-ft` (misma familia de fonemas que espeak, así el mapeo es directo), español está en los datos de Common Voice **[no verificado en la ficha]**.
- **Alineado**: `ctc-forced-aligner` con `--language spa` (mismo comando, sección 1.1).

### 2.2 En qué fallan con castellano

- `espeak-ng es` es castellano peninsular (zeta ceceante /θ/); `es-419` seseante. Hay que escoger el que corresponda a la voz; si no, el comparador marca un error falso en cada z/c. Un reconocedor de fonemas multilingüe tampoco distingue bien /θ/ vs /s/ si la voz es seseante: fijar la variante antes y no tocar umbrales.
- Whisper normaliza números, abreviaturas y puntuación: normalizar guion y transcripción (minúsculas, sin tildes opcional, números a palabras) antes del WER.

### 2.3 Diagnóstico de fallos de Qwen3-TTS (es)

El README oficial [verificado] **no discute** saltos de texto, repeticiones ni trozos largos. Menciona robustez a texto ruidoso, `max_new_tokens=2048` en la evaluación, usar los parámetros de `generate_config.json`, fijar `language` explícito, y que la clonación sin `ref_text` (`x_vector_only_mode=True`) puede bajar la calidad. El salto de frases en enumeraciones largas lo describe la persona; **no hay fuente primaria** que lo explique. Detección:

- Comparar la transcripción ASR con el guion con alineamiento a nivel de oración (no solo WER): una oración ausente se ve como borrado largo; contar borrados consecutivos > N palabras.
- Comparar duración real con duración esperada (palabras / velocidad media de la voz en trozos buenos): un trozo mucho más corto indica salto, más largo indica repetición o bucle.
- Mitigaciones a probar: trozos más cortos, enumeraciones partidas por elemento, `max_new_tokens` suficiente, reintento automático si el borrado supera el umbral.

## 3. Inglés (en)

Motor: Qwen3-TTS en inglés (voz aún por crear). El README da WER de texto largo en inglés (long-en 1,225 con 25 Hz 1,7B, 2,812 con 12 Hz 1,7B, ambos CustomVoice) [verificado](https://github.com/QwenLM/Qwen3-TTS).

### 3.1 Herramientas

- **ASR**: whisper large-v3(-turbo), el mejor soportado en inglés (cifras propias, medir en nuestra voz). Para ASR no autorregresivo, wav2vec2/CTC en inglés existen; sin investigar a fondo aquí.
- **Fonetizador**: `espeak-ng` (en-us, en-gb RP, etc.) [verificado](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md); `espeak-ng -v en-us --ipa -q "text"`. Para la comparación: `wav2vec2-xlsr-53-espeak-cv-ft` (la ficha muestra salida con símbolos ingleses como ɪ, ɚ, ʌ) o `allosaurus --lang eng` (inventario inglés publicado; no se da PER).
- Elegir variante (en-us o en-gb) según la voz objetivo.

### 3.2 En qué fallan con inglés

- Si la voz se clona de una hispanohablante, habrá acento no nativo (vocales tensas/laxas /i ɪ/, /s/ inicial con e-, /θ ð/, final -ed): el comparador de fonemas lo marcará como error aunque sea "estilo de la voz". Solución: separar "errores del texto" (palabras erradas) de "acento de la voz" calibrando umbrales con un audio de referencia de esa persona leyendo, no comparando con IPA de un hablante nativo.
- Ortografía irregular: espeak resuelve palabras raras y nombres propios con reglas; excepciones al diccionario en caso de fallo.

### 3.3 Diagnóstico de fallos de Qwen3-TTS (en)

Mismo procedimiento que 2.3. Además: fijar `language="English"` explícito (el README recomienda fijar la lengua si se conoce) para evitar que la detección automática mezcle lenguas en voces clonadas con ref en español.

## 4. Compartido entre lenguas (calidad sin referencia y marco)

| Herramienta | Licencia | Tamaño | CPU | Granularidad | Notas |
|---|---|---|---|---|---|
| UTMOSv2 | MIT (código) | **[no verificado]** | **[no verificado]** | un valor por archivo; `model.predict(data=array, sr=16000)` | segmentar el audio en ventanas y llamar por ventana para obtener curva temporal. [repo](https://github.com/sarulab-speech/UTMOSv2) |
| DNSMOS (P.835 y P.808) | repo Microsoft; licencia **[no verificado]** | modelos ONNX pequeños (**[estimación]** pocos MB) | sí | `dnsmos_local.py -t carpeta -o out.csv`; valores SIG/BAK/OVRL (la página no nombró las salidas ni la ventana; **[no verificado]**) | La ficha de Celtia usa DNSMOS OVRL como métrica, así que sirve de comparación directa. [repo](https://github.com/microsoft/DNS-Challenge/tree/master/DNSMOS) |
| NISQA (v2, TTS v1.0) | código MIT, **pesos CC BY-NC-SA 4.0** | **[no verificado]** | **[no verificado]** | por archivo en CSV (la página no cita puntuación por tramo) | `nisqa_tts.tar` predice naturalidad de voz sintética; el modelo v2 da noisiness, coloration, discontinuity, loudness. Discontinuity es lo más cercano a "chasquidos". [repo](https://github.com/gabrielmittag/NISQA) |
| Torchaudio-SQUIM objetivo | pesos CC-BY 4.0 | **[no verificado]** | **[no verificado]** | STOI/PESQ/SI-SDR estimados sin referencia (por la ficha: sin referencia, entrenado con DNS 2020) | pensado para habla con ruido, no TTS: menos útil. [docs](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.SQUIM_OBJECTIVE.html) |

**Ninguna de estas herramientas publica puntuación por segmento de forma nativa** (según lo leído): para localizar tramos hay que cortar en ventanas de 1-3 s con solape y puntuar cada una; NISQA y DNSMOS puntúan archivos cortos sin problema, UTMOS suele tratar clips de unos segundos. Los modelos de calidad se entrenaron sobre todo con inglés/chino; son una **señal de anomalía relativa** (bajón respecto al resto del mismo audio), no un MOS absoluto en gallego. La ficha de Nós usa DNSMOS OVRL y anota 3,45 para su salida, así que una ventana que baje claramente de ahí es sospechosa.

Marco común de detección (independiente de la lengua):

1. Troceo por oraciones (1-10 s), ASR de la lengua, alineado forzado con confianza por palabra.
2. Ventanas deslizantes (p. ej. 2 s, paso 1 s) con DNSMOS y/o UTMOS.
3. Informe por palabra y por ventana; lista de sospechosos ordenada; la persona escucha solo los sospechosos.
4. Rutina de reintento: regenerar el trozo con otra semilla y quedarse con el mejor.

## 5. Recomendación (qué montar y en qué orden)

Una sola vez, común a las tres lenguas (venv Python 3.13, solo CPU):

1. **DNSMOS en ventanas** (ONNX, modelos de pocos MB): barato, localiza chasquidos/ruido por tiempo, y es la métrica que usa Nós. Disco **[estimación]** < 100 MB con onnxruntime; tiempo **[estimación]** muy por debajo de tiempo real (segundos por minuto de audio).
2. **`ctc-forced-aligner`** (+ opcionalmente `wav2vec2-xlsr-53-espeak-cv-ft` para fonemas) como alineado multilingüe: sirve para gl (si `glg` está), es, en. Disco **[estimación]** 1-2 GB; tiempo **[estimación]** alrededor de tiempo real o menos en 4 núcleos, a medir.
3. **UTMOSv2** como segunda opinión de calidad, si cabe en disco/RAM tras medirlo.

Específico por lengua:

- **gl (montar primero, es lo que duele)**: `proxectonos/stt_gl_conformer_ctc_large_v1.0` (ASR CTC + alineado, Apache 2.0, ~0,5 GB **[estimación]**, ~0,1-0,3x tiempo real **[estimación]**), con respaldo `HiTZ/whisper-large-v3-gl` o `whisper-small-gl` (~1 GB / ~4 GB de disco, mucho más lento en CPU). Fonemas esperados: Cotovía (ya disponible). Hacer un test de validación con 5-10 frases con defectos conocidos que la persona haya marcado, y comprobar que la herramienta los señala antes de confiar.
- **es**: `espeak-ng -v es` (o `es-419` según voz) + whisper (large-v3-turbo ya en uso) + mismo alineado/ventanas. Añadir detección de borrados por oración (salto de frases).
- **en**: `espeak-ng -v en-us|en-gb` + whisper + mismo alineado/ventanas; calibrar acento con una lectura de referencia de la hablante.

Coste total orientativo **[estimación, a medir]**: disco 2-4 GB sin los whisper afinados, +1,5-4 GB si se añade HiTZ; tiempo 0,3-1x tiempo real por minuto de audio en CPU de 4 núcleos (es decir, 20-60 s por minuto) para la cascada completa. Siguiendo la regla de la Deck, un solo trabajo pesado a la vez y con `nice`/`ionice`.

Lo que queda sin verificar y condiciona la decisión: (1) WER real del Conformer de Nós (la tabla está corrupta), (2) si `glg` está en el alineador MMS, (3) el apartado de artefactos de la ficha de StyleTTS2-Celtia, (4) tamaños y licencia de UTMOSv2/DNSMOS, (5) si NeMo corre en Python 3.13 sin CUDA, (6) la causa de saltos de frases de Qwen3-TTS (sin fuente).
