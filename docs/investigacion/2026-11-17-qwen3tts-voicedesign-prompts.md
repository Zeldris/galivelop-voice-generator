# Qwen3-TTS VoiceDesign: cómo escribir el instruct y fijar el castellano de España

**Fecha:** 2026-11-17 · **Pedido:** lectora femenina de castellano de España con distinción (θ) · **Contexto:** `docs/investigacion/2026-11-17-lectora-es.md`

Convención: «Oficial» = fuente primaria (model card, repo, código, paper, docs del binario). «Comunidad, no verificado» = foros, issues
de terceros, blogs, espejos de documentación. «No encontrado» = se buscó y no hay dato.

## Resumen

1. No existe una plantilla oficial del instruct: es lenguaje natural libre, envuelto como turno `user` del chat. Sin límite de longitud en el código.
2. Los ejemplos oficiales están en chino e inglés; ninguna fuente oficial declara «solo zh/en», ni dice qué idioma de instruct rinde mejor.
3. No hay ninguna fuente oficial de acentos regionales de español ni de inglés. Los únicos dialectos oficiales son dos hablantes chinos de CustomVoice (Pekín, Sichuan).
4. El paper no desglosa horas por idioma (solo «más de 5 millones de horas, 10 idiomas») ni da métricas de VoiceDesign en español.
5. La comunidad reporta acento inglés que se cuela en español/francés/italiano con VoiceDesign y con clonado entre idiomas (#230, #134); sin arreglo oficial. El único remedio citado es ajuste fino con datos nativos.
6. `--lang` no es decorativo: con `auto` el código no inyecta id de idioma (prefill «nothink»); con un idioma explícito inyecta su id (prefill «think»). Probar `--lang Spanish` es el experimento más barato.
7. Misma semilla reproduce byte a byte «entre ejecuciones» (Philox); entre dispositivos (CPU/Vulkan) el binario NO lo promete y avisa de que un empate de argmax puede divergir.
8. Flujo oficial para fijar voz entre frases: diseñar un clip con VoiceDesign, crearlo como prompt de clonado en Base y reutilizarlo.
9. Plan B: Common Voice es-ES es CC0 y trae campo de acento (etiquetas de España no verificadas); el acento al clonar entre idiomas se pierde (#134), en el mismo idioma «parece adecuado» (comunidad).
10. Todo lo que decide el acento (idioma del instruct, `--lang`, temp) hay que medirlo en la Deck: las fuentes no lo resuelven.

---

## 1. Cómo se escribe el instruct de VoiceDesign

**Qué es (oficial).** El README del repo dice que con `generate_voice_design` se da «el texto objetivo y una descripción `instruct` en lenguaje
natural» ([README](https://github.com/QwenLM/Qwen3-TTS), [model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign)).
No define sintaxis, campos obligatorios ni plantilla. El README de qwentts.cpp lo describe como «Voice design from a free text attribute
instruction (gender, age, pitch, style)» y «voicedesign is 1.7B only» ([repo](https://github.com/ServeurpersoCom/qwentts.cpp)). Esa lista
(género, edad, tono, estilo) es la de un README de port, no una especificación del modelo.

**Ejemplos oficiales (README del repo).**
- Un ejemplo con texto chino e instruct chino: voz femenina juguetona, infantil, tono más agudo, entonación marcada.
- Un lote con un texto chino y otro inglés, cada uno con su `language` e instruct; el inglés es «Speak in an incredulous tone, but with a hint of panic beginning to creep into your voice.»
- En la sección «Voice Design then Clone»: «Male, 17 years old, tenor range, gaining confidence - deeper breath support now, though vowels still tighten when nervous».
- En CustomVoice, el instruct es de estilo/emoción (`用特别愤怒的语气说`); no es de VoiceDesign.

Es decir, el modelo oficial se muestra con instructs de dos tipos: lista de atributos separada por comas y frase narrativa de actuación.
No hay ejemplo oficial de acento nacional.

**Cómo se monta (código, oficial).** En `qwen_tts/inference/qwen3_tts_model.py` el instruct se envuelve como
`<|im_start|>user\n{instruct}<|im_end|>\n` y el texto como `<|im_start|>assistant\n{text}<|im_end|>\n<|im_start|>assistant\n`
([código](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py)). Un instruct vacío se descarta. En
`modeling_qwen3_tts.py` el instruct tokenizado se proyecta y se antepone a los embeddings de entrada; no se encontró validación ni
truncado de longitud ([código](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/core/models/modeling_qwen3_tts.py); el fichero se
leyó casi entero, faltaron ~125 caracteres). Longitud recomendada: **no encontrada en fuentes oficiales**.

**Idiomas del instruct.** El paper reporta InstructTTSEval por separado en zh y en (tabla 8: VoiceDesign 12Hz-1.7B, ZH 85,2 / 81,1 / 65,1 y
EN 82,9 / 82,4 / 68,4 en APS / DSD / RP) ([paper, arXiv 2601.15621](https://arxiv.org/abs/2601.15621)), de modo que se evaluó con
instrucciones zh y en. Otros idiomas de instruct: **no encontrado**. Nada oficial dice que el chino rinda mejor; el hallazgo del equipo
(zh mejor en tono) es una observación local.

**Entrenamiento del instruct (paper).** Datos en formato ChatML y un «thinking pattern» activado de forma probabilística para mejorar el
seguimiento de descripciones complejas ([paper](https://arxiv.org/abs/2601.15621)). Cuántas descripciones eran de acento, ninguna fuente lo declara.

**Combinación con `language` (código, oficial).** `generate_voice_design(text, instruct, language=None, ...)`; sin idioma, cada texto va
con `"Auto"`. En el modelo, `auto` deja `language_id = None` y el prefill es «nothink, think_bos, think_eos»; con otro idioma el
prefill es «think, think_bos, language_id, think_eos». El override por dialecto solo ocurre para `chinese`/`auto` con un hablante
dialectal de CustomVoice, no aplica a español ([código](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/core/models/modeling_qwen3_tts.py)).
En el binario, `--lang <name>` por defecto `auto`, y `--instruct` «Required for VoiceDesign, optional for CustomVoice, rejected for
Base» ([docs/ARCHITECTURE.md](https://github.com/ServeurpersoCom/qwentts.cpp/blob/master/docs/ARCHITECTURE.md)). La lista de nombres
válidos para `--lang` sale del `codec_language_id` del checkpoint; no se verificó que `Spanish` figure, pero Spanish está en los 10 idiomas
declarados. Conviene mirarlo en el `config.json` del GGUF o probar.

**Comunidad, no verificado.**
- Un espejo de docs (Mintlify) y guías de terceros dicen que el 1.7B es el que mejor sigue instrucciones y que conviene describir la voz,
  no la actuación; una guía desaconseja palabras de ritmo («slow», «deliberate») en el instruct
  ([guía](https://www.mintlify.com/QwenLM/Qwen3-TTS/guides/voice-design), [FAQ](https://www.mintlify.com/QwenLM/Qwen3-TTS/resources/faq)).
  Es un solo origen no oficial.
- No se encontró ninguna comparación publicada de instruct zh frente a en para el mismo tono.

---

## 2. Dialectos y acentos

- **Oficial:** el README/model card declara 10 idiomas (chino, inglés, japonés, coreano, alemán, francés, ruso, portugués, español, italiano)
  y «múltiples perfiles de voz dialectales»; los únicos dialectos nombrados son Dylan (Pekín) y Eric (Sichuan), ambos CustomVoice
  ([model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign), [README](https://github.com/QwenLM/Qwen3-TTS)).
- **Variantes de español o inglés:** no hay nada oficial. **No encontrado** en model card, README, paper ni código.
- **Datos de español:** el paper dice solo «más de 5 millones de horas, 10 idiomas»; no hay horas por idioma ni procedencia
  ([paper](https://arxiv.org/abs/2601.15621)). Lo único medido en español son métricas de clonado del modelo Base (tablas 6 y 9, WER y SIM
  multilingües, sin desglose por variedad) y no hay métrica de VoiceDesign en español.
- **Castellano frente a latino:** nadie lo documenta con evidencia en fuentes primarias.
  - Un resumen de investigación de un tercero dice «Spanish supported but no native-Spanish preset; independent Spanish naturalness tests
    not found» ([sidevoice-engine #102](https://github.com/sidevoice/sidevoice-engine/issues/102), comunidad).
  - La discusión [#300](https://github.com/QwenLM/Qwen3-TTS/discussions/300) (comunidad, no verificado) anuncia 14 voces en español
    «Spain, Mexico, Argentina, Chile, Ibero-America»: 12 clones desde VoxForge y 2 diseñadas. No dice cómo se consiguió el acento, ni
    prompts, ni licencias de VoxForge, ni que el acento se conserve. Repo enlazado, sin revisar: <https://github.com/alblez/qwen3-tts-spanish-voices>.

---

## 3. Qué ha encontrado la comunidad

Todo lo siguiente es **comunidad, no verificado** salvo lo que se indica.

- **Acento inglés en español con VoiceDesign:** [Discussion #230](https://github.com/QwenLM/Qwen3-TTS/discussions/230) «Spanish with unwanted
  English accent». Informan lo mismo en español y francés («80 % con fuerte acento inglés»). Sin respuesta de los mantenedores. La
  solución citada es un LoRA entrenado con ~30 frases nativas generadas por VoiceDesign (y no se muestra el instruct usado).
- **Acento que se cuela al clonar entre idiomas:** [Issue #134](https://github.com/QwenLM/Qwen3-TTS/issues/134): voces inglesas clonadas en
  italiano y alemán salen con acento americano; «only cloning voice in same language seems adequate in base 1.7b model». Cerrado como
  «not planned» el 6-may-2026 sin respuesta oficial. Un ajuste fino con ~3 h de audio con acento africano siguió saliendo americano.
- **Pronunciación y `language`:** el mantenedor de qwentts.cpp reconoce que una sola palabra puede no dar contexto suficiente y planea
  `language` por petición en el servidor ([issue #34](https://github.com/ServeurpersoCom/qwentts.cpp/issues/34)). Esto confirma que
  `language` pesa en la pronunciación, pero no afecta al CLI de gvoice.
- **Fijar el idioma en otro servidor:** [mlx-serve #965](https://github.com/ddalcu/mlx-serve/issues/965) y
  [PR #1013](https://github.com/ddalcu/mlx-serve/pull/1013): portugués leído con fonética española por falta de idioma fijado, corregido
  pasando un campo `language`. Es otro runtime, pero apunta en la misma dirección que `--lang Spanish`.
- **Muestreo recomendado:** por defecto 0,9 / top-k 50 / top-p 1,0 / rep-pen 1,05 (oficial, ver sección 4). Una FAQ no oficial usa temp 0,7
  y top-p 0,9 «más estable»; guías sueltas sugieren ≤0,5 con semilla fija para formato largo
  ([FAQ](https://www.mintlify.com/QwenLM/Qwen3-TTS/resources/faq)). Sin mediciones; no hay guía oficial para greedy.
- **Qwen3-TTS en issues del repo de qwentts.cpp:** solo se vieron títulos abiertos: [#41](https://github.com/ServeurpersoCom/qwentts.cpp/issues/41)
  (fallo Vulkan en Radeon 840M, no es del Deck) y [#10](https://github.com/ServeurpersoCom/qwentts.cpp/issues/10) (extraer voz de Base e
  inyectarla en CustomVoice). Nada sobre acento, semilla o español. No se leyeron issues cerrados.
- **Reddit (r/LocalLLaMA, r/StableDiffusion):** no se encontró ningún hilo con el motor de búsqueda disponible. No sustituye una
  búsqueda manual.

---

## 4. Reproducibilidad

- **Misma semilla, mismo binario y dispositivo:** «a fixed seed replays byte for byte across runs»; el PRNG es Philox y la cadena
  de muestreo es la de Hugging Face: «repetition_penalty -> temperature -> top_k -> top_p -> softmax -> multinomial», con el talker y el
  sub-talker aparte ([docs/ARCHITECTURE.md](https://github.com/ServeurpersoCom/qwentts.cpp/blob/master/docs/ARCHITECTURE.md)). La promesa
  es entre ejecuciones; no se dice del mismo instruct, pero es la entrada obvia del hash.
- **CPU frente a Vulkan:** no hay promesa. El documento explica que «a single argmax tie at the FP epsilon between the GGML and cuBLAS
  kernels flips one token», que cada fotograma condiciona al siguiente y que «End-to-end token or waveform equality is therefore the wrong
  metric» ([ARCHITECTURE.md](https://github.com/ServeurpersoCom/qwentts.cpp/blob/master/docs/ARCHITECTURE.md)). Se habla de cuBLAS, no de
  Vulkan; por analogía divergirán, pero no hay prueba. Hay que medirlo (experimento E5).
- **Defaults del checkpoint (oficial):** `do_sample` activo, temp 0,9, top-p 1,0, top-k 50, rep-pen 1,05, sub-talker con los mismos
  valores ([generation_config.json](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign/raw/main/generation_config.json)); el
  binario coincide. El paper no dice qué muestreo se usó en las pruebas; el README dice que los benchmarks usaron los valores por defecto del checkpoint.
- **Efecto de temp, top-p, greedy:** sin datos oficiales. `--greedy` es argmax en ambos stacks (temperatura 0) y quita el azar, pero
  en TTS autorregresivo el argmax puro puede dar bucles o pausas largas (conocimiento general, no encontrado en fuentes del modelo). Hay que medirlo.
- **Estabilidad de largo plazo:** un paper de terceros (Taming Long-form TTS) mide deriva en Qwen3-TTS-0.6B-CustomVoice en minutos de
  generación ([resumen](https://huggingface.co/papers/2609.16989.md); sin leer a fondo, comunidad).
- **Flujo diseñar → clonar (oficial):** el README define tres pasos: sintetizar un clip corto con VoiceDesign, construir un prompt de
  clonado reutilizable (`create_voice_clone_prompt`) y generar con `generate_voice_clone`; sirve para «voz coherente en muchas líneas»
  ([README](https://github.com/QwenLM/Qwen3-TTS)). Dos modos (código): **x-vector** (`x_vector_only_mode=True`, solo embedding del hablante,
  sin `ref_text`, el model card avisa de que «cloning quality may be reduced») e **ICL** (`ref_text` obligatorio, usa los códigos de
  referencia además del embedding) ([código](https://github.com/QwenLM/Qwen3-TTS/blob/main/qwen_tts/inference/qwen3_tts_model.py)).
  En el binario: `--ref-wav` solo, o con `--ref-text` para ICL; `--ref-spk` y `--ref-rvq` reutilizan lo pre-codificado
  ([docs](https://github.com/ServeurpersoCom/qwentts.cpp/blob/master/docs/ARCHITECTURE.md)). Los modelos Base son los que aceptan
  `--ref-wav`; VoiceDesign no tiene codificador de hablante.

---

## 5. Plan B: clonar desde una muestra peninsular libre

| Fuente | Licencia | Etiqueta de acento | Notas |
|---|---|---|---|
| Common Voice Spanish (Mozilla Data Collective) | CC0-1.0 (en el listado de la ficha) ([ficha v25](https://datacollective.mozillafoundation.org/datasets/cmn4z1n52000knv07h01532dd)) | Campo `accent` autodeclarado por el hablante; la ficha tiene tabla de acentos que no pude leer | Tabla de etiquetas, comprobar en el TSV. Un clasificador (CommonAccent, MIT) usa 6 clases de Common Voice 11, una de ellas «ESPANA SUR PENINSULAR - ANDALUCIA EXTREMADURA MURCIA»; el centro/norte (el castellano buscado) no aparece entre ellas, así que no verificado cómo se etiqueta ([modelo](https://huggingface.co/Jzuluaga/accent-id-commonaccent_xlsr-es-spanish)) |
| CSS10 español | Inconsistente: el repo declara Apache-2.0, otros espejos CC0 o CC BY-SA; el audio de LibriVox es dominio público ([repo](https://github.com/Kyubyong/CSS10)) | Ninguna; un solo lector, no identificado | No se pudo verificar que el lector sea de España. Comprobar licencia en el original |
| OpenSLR | No indicada en el índice | Solo variedades americanas: Argentina (61), Chile (71), Colombia (72), Perú (73), Puerto Rico (74), Venezuela (75). TEDx (67) y MediaSpeech (108) sin origen declarado | No hay SLR de España en el índice ([OpenSLR](https://www.openslr.org/resources.php)) |
| VoxForge (usado por #300) | No verificada | No verificada | Ver sección 2 |

**¿Se conserva el acento al clonar?** Oficial: no hay afirmación. Comunidad: dentro del mismo idioma parece adecuado, entre idiomas se
filtra el acento dominante ([#134](https://github.com/QwenLM/Qwen3-TTS/issues/134)). Para español→español no hay datos de acento
peninsular. Experimento E7. Atención: los clips de Common Voice son de calidad variable; se necesitan 5-15 s limpios con transcripción
exacta para ICL.

---

## Implicaciones para gvoice

### Plantilla mínima de instruct

Sin fuente que fije el idioma. Hipótesis de trabajo, a decidir con E2:

- **Idioma de la instrucción:** chino, porque es lo que dio mejor tono a la persona y el modelo se evaluó en zh y en. Si E2 no muestra ventaja,
  inglés corto.
- **Estructura:** una sola frase o lista de ≤5 atributos, sin los 12 campos. Sin palabras de ritmo (un solo origen, comunidad).
- Propuesta zh (la de la persona, ya validada en tono): `35岁女性，西班牙马德里人，母语西班牙语，马德里口音，有声书朗读语气，清晰干净的录音`
- Propuesta en: `Female, 35 years old, native Castilian Spanish speaker from Madrid, audiobook narration tone, clean studio recording`
- La frase `Locale:` actual (con «θ») no tiene respaldo en las fuentes, y la persona vio que describir la θ no mejora: retirarla de la
  plantilla por defecto salvo que E3 la justifique.
- Pasar siempre `--lang Spanish` en lugar de `auto` (hipótesis a validar con E1; por código es la única palanca real sobre el idioma).

### Parámetros que guardar con cada toma

`seed`, `instruct` literal (con su idioma), `--lang`, `--temp`, `--top-k`, `--top-p`, `--rep-pen`, `--sub-temp`, `--sub-top-k`,
`--sub-top-p`, `--greedy`, modelo y cuantización (nombre y sha del GGUF), `--device`, commit del binario, `--max-new`, hash del texto y
del wav resultante. Si no se pasa `--seed`, generar una explícita y guardarla (el defecto es -1 aleatorio).

### Proceso determinista propuesto

1. **Diseñar N semillas:** N=8-12 con el mismo instruct y texto de prueba corto (que incluya «hace», «cinco», «zona», una pregunta y
   una cifra), `--lang Spanish`, temp 0,9 (o la que gane en E1), semillas fijas 101, 102…, en un único dispositivo.
2. **Criterios de escucha**, en orden eliminatorio: (a) distinción θ en las tres palabras; (b) sin acento inglés ni seseo; (c) sin ruido, eco,
   siseo ni deriva infantil; (d) tono de audiolibro y entonación de la pregunta; (e) estabilidad: repetir la misma semilla y comprobar
   que sale igual. Una tabla por semilla con sí/no por criterio, guardada con las tomas.
3. **Elegir 1-2 candidatas** y generar con ellas un clip de referencia de 8-15 s con texto largo y variado (sin ruido).
4. **Fijar con Base:** pasar el clip a `qwen-codec` (con `--talker` del Base, que escribe `.spk`) y, si se quiere ICL, pre-codificar a `.rvq`;
   guardar `.spk`, `.rvq` y la transcripción exacta. Probar x-vector frente a ICL con los mismos textos (E6).
5. **Validar el clon** con las mismas frases de criterio; si pierde la θ, volver al paso 1 con otra semilla o pasar al plan B (clip CC0 peninsular).
6. **Producir:** cada frase con Base + `.spk`/`.rvq`, semilla fija, parámetros guardados. Una nueva toma no se acepta si no pasa (a)-(c).
7. Todo lo anterior lo puede ejecutar un agente local si los criterios (a)-(c) se pasan a una comprobación humana por lote; la θ no se
   mide bien de forma automática (no se encontró un detector fiable), así que la escucha sigue siendo manual.

### Experimentos baratos en la Deck

Misma frase de prueba y mismas 4 semillas en todos los casos; anotar tiempo y criterios (a)-(c).

- **E1 `--lang Spanish` frente a `auto`**, con el mejor instruct. Es la palanca con más respaldo en el código.
- **E2 instruct zh frente a en corto frente a en largo (los 12 campos)**, con `--lang Spanish`.
- **E3 con y sin referencia explícita a «distinción/θ»**, en zh y en en, para confirmar o no lo que oyó la persona.
- **E4 temp 0,6 / 0,9 / greedy** con la misma semilla: estabilidad entre semillas y presencia de bucles o silencios en greedy.
- **E5 CPU frente a Vulkan** con misma semilla, instruct y flags: comparar hash del wav y, si difiere, escuchar si cambia el acento.
  Aunque el wav difiera, esto decide si hay que fijar un dispositivo para producir.
- **E6 clon x-vector frente a ICL** desde un clip diseñado: ver cuál conserva la θ y la identidad.
- **E7 clon desde un clip Common Voice es-ES CC0** (si se localiza la etiqueta de acento de España centro-norte): ver si el acento se conserva; con un clip de otra variedad, para comparar.
- **E8 semillas repetidas** (misma semilla dos veces) para confirmar la reproducibilidad byte a byte en la Deck.

### Lo que las fuentes no resuelven

Idioma óptimo del instruct, efecto de la θ en el prompt, comportamiento de greedy, diferencia CPU/Vulkan, conservación de acento al clonar
en español, etiquetas de acento de España en Common Voice, y búsqueda en Reddit (no hecha). Un siguiente paso barato es leer la
tabla de acentos de Common Voice en el TSV real y las discusiones cerradas del repo.
