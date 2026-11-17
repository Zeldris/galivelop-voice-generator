# Motores de TTS en gallego nativo para el Portal (voz femenina adulta, Steam Deck sin CUDA)

**Fecha:** 2026-11-17 · **Pregunta:** qué motor y qué voz gallega nativa (mujer adulta) puede generar los WAV de guion del Portal en la Deck, con licencia compatible con publicar los audios en una web pública · **Contexto:** `2026-11-17-motores-via1-deck.md` (Qwen3-TTS y Chatterbox no cubren gallego), `2026-11-17-timbre-objetivo.md` (menciona Nos_Celtia-GL en la línea ~153; aquí se amplía), `2026-10-25-banco-deck.md`.

Convención: **Oficial** = ficha de Hugging Face, README, página del proyecto o del dataset, leída el 2026-11-17. **Comunidad** = terceros. **Deducción** = mía, no comprobada en la fuente. **No encontrado** = se buscó y no hay dato. **Nada se ha descargado ni ejecutado**; las páginas se leyeron con una herramienta de extracción de texto, así que los textos de licencia son resúmenes de esa herramienta, no copias literales (las fichas con 401 no pudieron leerse en bruto).

## Resumen

1. **La mejor opción es la voz Celtia del Proxecto Nós (USC)**: voz femenina profesional de estudio, la única femenina adulta con pesos Apache-2.0 y con varias arquitecturas publicadas (VITS, Matcha-TTS, StyleTTS2). No hay otra alternativa gallega seria con licencia limpia: MMS no tiene gallego, Piper oficial tampoco, y los TTS multilingües con clonado no listan gallego.
2. **Alerta de licencia (hay que resolverla antes de publicar):** las fichas de Celtia dicen Apache-2.0, pero los «Terms and conditions» de la misma ficha limitan la **finalidad** a «investigación y desarrollo de aplicaciones de TTS en gallego» y exigen reconocer a Proxecto Nós/USC. Publicar audios sintéticos en una web pública no está prohibido por escrito en lo que leí, pero tampoco autorizado de forma explícita. **Deducción:** conviene escribir a el contacto del Proxecto Nós (en su web) (contacto que citan las fichas) y guardar la respuesta. Los **datos** de Celtia (corpus) sí son de acceso restringido y no se necesitan para usar el modelo.
3. **Ruta recomendada 1 (la más ligera): `HiTZ/TTS-gl_celtia`**, VITS en **ONNX de 60 MB**, corrible con `onnxruntime` en CPU y sin PyTorch; ejecuta con el repo `hitz-zentroa/aHoTTS`. Duda: qué front-end de texto lleva.
4. **Ruta recomendada 2 (la de mayor calidad probable): `Nos_StyleTTS2-Celtia-GL`** (octubre de 2026, Apache-2.0), pero exige Python 3.10, PyTorch y Cotovía; sin ONNX ni Vulkan.
5. **Descartados:** MMS-TTS (no hay gallego, y es CC-BY-NC), Piper oficial (sin `gl`), VoxCPM2 y demás multilingües (no listan gallego), Cotovía como voz (síntesis por selección de unidades, calidad anticuada), sherpa-onnx (sin modelo `gl`).

---

## 1. Tabla comparativa

| Motor / voz | Voz femenina adulta | Licencia pesos | Datos | Runtime | Front-end | Veredicto |
|---|---|---|---|---|---|---|
| **Nós Celtia VITS** (`proxectonos/Nos_TTS-celtia-vits-graphemes`) | Sí (Celtia, locutora profesional) | Apache-2.0 + T&C (investigación y desarrollo de TTS gallego; reconocer a USC) | Nos_Celtia-GL, CC BY 4.0 con acceso restringido | `pip install TTS` (Coqui), PyTorch; CPU | Cotovía solo para normalizar (números, siglas); entrena con grafemas | Candidato |
| **Nós Celtia Matcha** (`…celtia-matcha-graphemes`) | Sí | Apache-2.0 + mismos T&C | 13.000 frases, 15,5 h | `pip install matcha-tts` + vocoder `hifigan_univ_v1`; PyTorch | Cotovía para normalizar | Candidato (más moderno, mismo coste) |
| **HiTZ `TTS-gl_celtia`** | Sí | Apache-2.0 (modelo); voz bajo «CC BY 4.0» (la ficha escribe «Creative Commond») | Nos_Celtia-GL | **ONNX 60,3 MB**; `aHoTTS` (Apache-2.0) con `libonnxruntime` 1.13.1 incluida | No documentado | **Candidato 1** |
| **Nós StyleTTS2 Celtia** (`Nos_StyleTTS2-Celtia-GL`) | Sí | Apache-2.0 (sin T&C extra visibles) | Nos_Celtia-GL | Python 3.10, `requirements.txt`, PyTorch; sin ONNX | **Cotovía obligatorio** (G2P y normalización), PL-BERT gl, ASR alineador | **Candidato 2** |
| Nós Sabela VITS (`…sabela-vits-phonemes`) | Sí (la ficha de Cotovía la lista como «female»; la ficha de Nós habla de «locutor profesional de radio»: contradicción en las fuentes) | Apache-2.0 + T&C de investigación; datos CC BY 4.0 (UVigo) | Sabela, 9.999 frases | Coqui TTS | **Cotovía obligatorio** (fonemas) | Reserva |
| Nós Icía (Matcha fonemas) | Sí (aficionada) | Apache-2.0 | 2.950 frases, finetune de Celtia | Matcha-TTS | **Cotovía obligatorio** | Descartar: corpus pequeño y aficionada |
| Nós Brais / HiTZ Iago, Paulo | **No, voces masculinas** | Apache-2.0 | | | | Fuera de requisito |
| Cotovía (UVigo) | Sabela | Motor GPL-3.0+; voces: unas de SourceForge «libres para uso comercial y no comercial», otra «solo no comercial» | | C++, Linux | propio | Solo como front-end, no como voz |
| MMS-TTS (Meta) | — | CC-BY-NC-4.0 | | PyTorch/ONNX | | **Descartado:** no hay `glg` y es NC |
| Piper (`rhasspy/piper-voices`) | — | | | ONNX | espeak-ng | **Descartado:** sin `gl` |
| sherpa-onnx | — | | | ONNX | | Sin modelo `gl`; solo vale como runtime si se convierte un VITS |
| VoxCPM2, XTTS-v2, otros multilingües | — | | | | | No listan gallego (ver §3) |

## 2. Detalle de los candidatos

### 2.1 Proxecto Nós / USC: voz Celtia

- **Quién y qué (oficial):** voz «Celtia», una única locutora profesional elegida entre cuatro candidatas por una prueba perceptiva con más de 50 participantes; ~25 h, 20.000 frases, estudio. La ficha del dataset agradece a la locutora por nombre. Corpus: [Zenodo 7716958](https://zenodo.org/record/7716958) y [ficha USC](https://investigacion.usc.es/documentos/668fc40fb9e7c03b01bd3891?lang=es).
- **Licencia, lo que dice cada fuente:**
  - Ficha del modelo [VITS](https://huggingface.co/proxectonos/Nos_TTS-celtia-vits-graphemes) y [Matcha](https://huggingface.co/proxectonos/Nos_TTS-celtia-matcha-graphemes): `apache-2.0`. La de VITS añade «Terms and conditions»: la finalidad es investigación y desarrollo de aplicaciones de TTS en gallego; prohíbe actividades ilegales, vulneración de derechos, desinformación, odio, violación de privacidad y **atribuir el modelo a otro**; exige reconocer al titular (Proxecto Nós, USC). La ficha de Matcha no trae esos T&C pero sí el contacto el contacto del Proxecto Nós (en su web).
  - [StyleTTS2-Celtia](https://huggingface.co/proxectonos/Nos_StyleTTS2-Celtia-GL): Apache-2.0, «sin condiciones de uso específicas»; pide citar el modelo si sirve para una investigación.
  - Dataset [Nos_Celtia-GL](https://huggingface.co/datasets/proxectonos/Nos_Celtia-GL): etiqueta `cc-by-4.0`, pero **con términos propios**: uso para investigación y herramientas de IA con fines lingüísticos; acceso para entidades colaboradoras del Centro Ramón Piñeiro/USC; **prohíbe difundir las grabaciones** en abierto; propiedad cedida a la USC durante 15 años (datos borrados desde el 30/11/2037). En Zenodo el acceso es «Restricted» (hay que solicitarlo). Esto afecta a las grabaciones originales, no a los audios sintéticos, pero **no habría que usar el corpus como muestra de clonado ni publicarlo**.
  - Hay un detalle comercial: no encontré ninguna frase que **permita** o **prohíba** expresamente el uso comercial del audio sintético. **Deducción:** como el proyecto del Portal es público y probablemente comercial, hay que pedir confirmación escrita.
- **Calidad reportada:**
  - Paper [Nós-TTS (PROPOR 2024)](https://aclanthology.org/2024.propor-2.31.pdf): compara las tres voces con MOS; el texto que pude extraer dice que Celtia queda como «la opción más robusta y satisfactoria» por calidad de audio, pronunciación, precisión de fonemas y prosodia natural, atribuido a la calidad del corpus. No pude extraer la tabla numérica (PDF comprimido). Los modelos se describen como experimentales.
  - StyleTTS2-Celtia: DNSMOS OVRL 3,452/3,444/3,460 (texto corto/medio/largo) contra 3,424/3,248/3,329 del VITS de referencia; el audio original da 3,511 (ficha oficial). Es una métrica automática, no oyentes.
  - Matcha-TTS y StyleTTS2 deberían mejorar a VITS en textos largos (los DNSMOS de largo lo sugieren para StyleTTS2); **no encontré MOS humano de Matcha-Celtia**.
- **Muestras para escuchar:** [Space Galician TTS de Proxecto Nós](https://huggingface.co/spaces/proxectonos/Nos_TTS_galician) (en la lectura estaba «sleeping»: pulsar «Restart this Space»; es un demo, sin garantía de contener todas las arquitecturas). Las fichas de StyleTTS2 y VITS no incluyen audios. **No encontré muestras públicas estáticas.**

### 2.2 `HiTZ/TTS-gl_celtia` + aHoTTS (candidato 1)

- **Qué es (oficial):** colección de HiTZ/Aholab (UPV/EHU), financiada con fondos NextGenerationEU, con VITS en euskera, gallego (brais, celtia, iago, icia, paulo, sabela), catalán y español. Ficha [TTS-gl_celtia](https://huggingface.co/HiTZ/TTS-gl_celtia): formato ONNX, `vits.onnx` de **60,3 MB**, `config.json` vacío (la ficha avisa de JSON no válido).
- **Licencia (oficial):** modelo Apache-2.0; las voces gallegas figuran con la «Public Creative Commond Attribution 4.0 International License» (sic) y la ficha pide citar el corpus Nos_Celtia-GL (Vázquez Abuín et al., 2023). [aHoTTS](https://github.com/hitz-zentroa/aHoTTS): código Apache-2.0. Sigue valiendo la duda de §2.1 (los T&C de la USC no se repiten aquí).
- **Ejecución:** `python3 synthesize.py -t "texto" -l gl -m celtia -o nombre`; descarga la voz de Hugging Face (`huggingface_hub`) y escribe un WAV en `output/`. El repo incluye `libonnxruntime.so.1.13.1`, lo que **sugiere** ONNX Runtime en CPU (deducción: el README no lo dice). Sin PyTorch.
- **Duda abierta:** el README no describe el preprocesado (normalización de números, siglas) ni si el modelo es de grafemas o fonemas; la ficha del Nós de la misma Celtia entrena con grafemas, así que **probablemente** acepta texto directo (deducción), pero habría que probarlo con cifras y siglas. Si hace falta, Cotovía como normalizador (§4).
- **Calidad:** no encontré MOS de estos ONNX. Son VITS (la arquitectura más sencilla de la familia): esperable calidad correcta, con más riesgo de prosodia plana en párrafos de 100 palabras que Matcha o StyleTTS2 (deducción).
- **Velocidad:** no hay cifra. VITS ONNX de 60 MB en 8 hilos Zen 2 debería ir bastante por debajo de RTF 1 (deducción por tamaño; **no medido**).

### 2.3 `Nos_StyleTTS2-Celtia-GL` (candidato 2, el de mayor calidad probable)

- **Oficial:** StyleTTS2 con decodificador iSTFTNet, difusión de estilo y entrenamiento adversarial con HuBERT; 24 kHz; PL-BERT gl (`PL-ModernBERT-gl`) y un alineador adaptado a Cotovía; 69 tokens; un solo hablante. Cotovía hace G2P y normalización. Dependencias: Python 3.10 (conda), `requirements.txt`, Cotovía (`Utils/cotovia/README.md`). Inferencia: `python inference.py --config Configs/inference_config.yml --text "..." --device 0`; ajuste recomendado `--alpha 0.8 --beta 0.8 --t 0.2`, 10 pasos de difusión.
- **No consta** tamaño de pesos, RTF, ONNX ni soporte de Vulkan. `--device` apunta a CUDA; en la Deck habría que probar `cpu` (o ROCm con `HSA_OVERRIDE_GFX_VERSION=10.3.0`, sin evidencia reciente; véase el informe de motores). **Deducción:** StyleTTS2 con difusión en CPU de 8 hilos será lento (probablemente RTF > 1), pero el trabajo es por lotes y pregrabado, así que minutos por párrafo es verosímil.
- Rama dada de alta en octubre de 2026; es la más reciente del proyecto y trae menos recorrido (sin discusiones ni reportes de terceros que encontrara).

### 2.4 Cotovía (UVigo)

- **Oficial:** [SourceForge](https://sourceforge.net/projects/cotovia/): GPL-3.0+; descarga `cotovia-lang_0.5.tar.gz` (13,4 MB); «Beta»; última actualización 2018-01-02. Las voces de SourceForge son libres para uso comercial y no comercial; otra solo para no comercial (enlaces externos). La [página de UVigo](https://gtm.uvigo.es/en/transfer/software/cotovia/) lista Sabela (mujer), Iago (hombre) y David (hombre, castellano).
- **Es un sintetizador de selección de unidades**, mucho más antiguo que los neuronales de Nós. **Deducción:** como voz sonará robótica frente a Celtia. Su valor real es el **front-end** (normalización y fonetización gallega), que usan todas las voces de Nós. Se instala con los paquetes Debian `cotovia_0.5_amd64.deb` y `cotovia-lang-gl_0.5_all.deb`.

### 2.5 Sabela e Icía (Nós)

- Sabela (VITS, fonemas, 9.999 frases): Apache-2.0 con los mismos T&C de investigación; el corpus es de UVigo CRPIH, CC BY 4.0 según la ficha de HiTZ. Necesita Cotovía para fonetizar. **Las fuentes se contradicen sobre si es voz femenina o masculina** (la ficha de Cotovía de UVigo la pone como mujer; la ficha de Nós dice «locutor profesional de radio»). Quedaría solo como reserva y hay que oírla.
- Icía: finetune de Celtia sobre 2.950 frases de una aficionada, 6.500 épocas. Descartar por corpus pequeño.

## 3. Descartes con motivo

| Motor | Motivo | Fuente |
|---|---|---|
| **MMS-TTS de Meta** | La lista oficial de idiomas MMS-TTS no contiene `glg` ni «Galician» (leída en [dl.fbaipublicfiles.com](https://dl.fbaipublicfiles.com/mms/tts/all-tts-languages.html)); además la colección lleva `cc-by-nc-4.0` (listados de HF). La ficha `facebook/mms-tts-glg` devolvió 401 y no pude abrirla. | Oficial + comunidad |
| **Piper** | `rhasspy/piper-voices` no tiene carpeta `gl` (lista: …`fi, fr, he`…). Un buscador de terceros (tts.ai) dice «listar voces gallegas», pero su propia lista no las incluye. Muchas voces Piper heredan licencia NC de sus grabaciones. | Oficial (lista de carpetas) |
| **sherpa-onnx** | No encontré modelo `gl` en su catálogo. Solo sería un runtime si se convirtiera un VITS de Nós/HiTZ. | No encontrado |
| **VoxCPM2** (OpenBMB, Apache-2.0) | 30 idiomas con español y portugués, **gallego no está**; el README sugiere probar o hacer fine-tuning. Pide CUDA ≥ 12 en PyTorch, con ports GGML/Vulkan comunitarios (RTF ~1,76 en M4 Pro). Una apuesta al azar sobre un idioma no entrenado, y no tendría pronunciación gallega de verdad. | Oficial |
| **XTTS-v2, F5-TTS, Fish/OpenAudio, Voxtral TTS** | No listan gallego en lo que leí; los tres últimos son NC (ver informe de motores; Voxtral TTS CC BY-NC 4.0 según un resumen de terceros). | Informe de motores + comunidad |
| **Qwen3-TTS, Chatterbox** | Sin gallego (dado por la persona; no se reverificó). | — |
| **Voces masculinas** (Brais, Iago, Paulo) | No cumplen el requisito de voz de mujer. | Oficial |
| **Clonado cruzado** (castellano con acento gallego) | Fuera de alcance: la persona pide pronunciación gallega real. **Deducción:** un TTS sin gallego leería la ortografía como castellano. | — |

No hallé ESPnet ni un modelo multilingüe reciente que liste gallego con licencia permisiva. La búsqueda de TTS multilingües con clonado devolvió artículos y blogs genéricos sin evidencia de gallego, así que **«no encontrado» no equivale a «no existe»**: un modelo muy reciente podría haberse escapado. Tampoco revisé servicios en la nube (cuestión distinta: no son locales).

## 4. Recomendación

**Probar primero, en este orden:**

**A. `HiTZ/TTS-gl_celtia` (ONNX + aHoTTS).** Es lo más barato de ensayar (60 MB, sin PyTorch, en el espíritu de D1: una llamada a proceso). Pasos (cuando la persona dé permiso para descargar; todo fuera del repo, en un directorio de trabajo aparte):
1. En un venv: `pip install huggingface_hub onnxruntime numpy` (el repo trae su propia `libonnxruntime.so.1.13.1`; comprobar si hace falta o basta con la de pip).
2. `git clone https://github.com/hitz-zentroa/aHoTTS`; leer su `requirements`/`synthesize.py`.
3. `python3 synthesize.py -t "..." -l gl -m celtia -o prueba`; oír con 3 párrafos del Portal (30-120 palabras, con cifras y siglas).
4. Medir tiempo por párrafo en CPU y consumo de RAM.
5. Si falla la normalización, instalar Cotovía (paso C) y pasarle el texto antes.

**B. `Nos_TTS-celtia-matcha-graphemes` (o StyleTTS2-Celtia, si A y B no convencen).** Pasos:
1. Entorno con Python 3.10 (conda/micromamba o contenedor aparte: el anfitrión SteamOS trae Python 3.14 según el informe de motores) y PyTorch en CPU. `pip install matcha-tts`.
2. **Cotovía sin `sudo`:** en el Flatpak no hay `dpkg -i`. Bajar `cotovia_0.5_amd64.deb` y `cotovia-lang-gl_0.5_all.deb` de SourceForge y extraerlos con `dpkg-deb -x` (o `ar x` + `tar`) a un prefijo propio; comprobar que el binario `cotovia` corre en el SDK de freedesktop (deducción: depende de bibliotecas de 2018). Se usa `cotovia -p -n -S` para normalizar y `iconv` para la codificación.
3. Descargar `celtia.ckpt` y el vocoder `hifigan_univ_v1` y correr `matcha-tts --text "..." --checkpoint_path celtia.ckpt --vocoder hifigan_univ_v1 --output_folder . --speaking_rate 1`.
4. Si se prefiere StyleTTS2: clonar `Nos_StyleTTS2-Celtia-GL`, `pip install -r requirements.txt`, `inference.py --device cpu`, con los parámetros recomendados de la ficha.

**C. Antes de publicar nada:** escribir a el contacto del Proxecto Nós (en su web) preguntando si el audio sintético con Celtia puede publicarse en una web pública del proyecto (con o sin fin comercial) y con qué atribución. Guardar la respuesta en `docs/`. Mientras no conteste, los audios gallegos deben tratarse como **no publicables**.

**Atribución en cualquier caso:** reconocer a Proxecto Nós/USC (T&C de VITS), citar el corpus Nos_Celtia-GL si se usa la ruta HiTZ, y no decir que el modelo es propio.

## 5. Dudas abiertas

- **Licencia efectiva del audio sintético** (§2.1); la respuesta de la USC decide todo.
- ¿Qué front-end lleva `aHoTTS` y si normaliza cifras y siglas?
- RTF real en la Deck de cada candidato: **sin cifras de nadie** (todo lo de velocidad es deducción).
- Si la voz de Sabela es mujer o hombre (fuentes contradictorias).
- MOS humano de Celtia VITS/Matcha/StyleTTS2: no pude extraer la tabla del paper (PDF comprimido). El mejor modo de resolverlo es escuchar el demo.
- `Cotovía` 0.5 de 2018: no comprobado que corra en el SDK actual.
- `mms-tts-glg`: ausente de la lista de Meta; la ficha directa dio 401.

## Fuentes

- Nós: [perfil HF](https://huggingface.co/proxectonos), [Celtia VITS](https://huggingface.co/proxectonos/Nos_TTS-celtia-vits-graphemes), [Celtia Matcha](https://huggingface.co/proxectonos/Nos_TTS-celtia-matcha-graphemes), [StyleTTS2 Celtia](https://huggingface.co/proxectonos/Nos_StyleTTS2-Celtia-GL), [StyleTTS2 Brais](https://huggingface.co/proxectonos/Nos_StyleTTS2-Brais-GL), [Sabela](https://huggingface.co/proxectonos/Nos_TTS-sabela-vits-phonemes), [Icía](https://huggingface.co/proxectonos/Nos_TTS-icia-matcha-phonemes), [dataset Celtia](https://huggingface.co/datasets/proxectonos/Nos_Celtia-GL), [dataset Brais](https://huggingface.co/datasets/proxectonos/Nos_Brais-GL), [Zenodo Celtia](https://zenodo.org/record/7716958), [USC](https://investigacion.usc.es/documentos/668fc40fb9e7c03b01bd3891?lang=es), [Space demo](https://huggingface.co/spaces/proxectonos/Nos_TTS_galician), [paper Nós-TTS](https://aclanthology.org/2024.propor-2.31.pdf).
- HiTZ: [TTS-gl_celtia](https://huggingface.co/HiTZ/TTS-gl_celtia), [aHoTTS](https://github.com/hitz-zentroa/aHoTTS).
- Cotovía: [SourceForge](https://sourceforge.net/projects/cotovia/), [UVigo GTM](https://gtm.uvigo.es/en/transfer/software/cotovia/).
- Descartes: [lista MMS-TTS](https://dl.fbaipublicfiles.com/mms/tts/all-tts-languages.html), [colección mms-tts](https://huggingface.co/facebook/mms-tts), [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main), [VoxCPM](https://github.com/OpenBMB/VoxCPM), [tts.ai Piper](https://tts.ai/voices/piper/?lang=gl).


## Decisión (2026-11-17)

La persona aprueba Celtia como base tras escuchar la demo de Nós. No se consulta a la USC: el uso es sin ánimo de lucro y nace de la investigación del propio generador; basta con la atribución «Voz gallega: Celtia, Proxecto Nós (USC), Apache-2.0» en el README del generador y en el Portal. La conveniencia de escribir a la USC (apartado C) queda descartada por decisión de la persona.
