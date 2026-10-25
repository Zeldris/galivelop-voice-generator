# Banco de pruebas de Qwen3-TTS (`qwentts.cpp`) en la Steam Deck, 2026-10-25

## Máquina y motor
- AMD Custom APU 0405 (Van Gogh), 8 hilos; GPU «AMD Custom GPU 0405 (RADV VANGOGH)», Vulkan 1.4.321, memoria unificada;
  RAM 15,1 GB totales (14 GB útiles), swap 8 GB. SteamOS, núcleo 7.2.7-valve2-2-neptune. El shell corre dentro de un Flatpak
  (VS Code), sin `journalctl`, `dmesg`, `ss` ni `/usr/bin/time`.
- Motor: `qwentts.cpp` commit `5916bf7c79dbb4e66fc059cdc507a79a23a28bb4` (2026-10-16), ggml `cc5df49a` (0.27.0).
- **Ruido de la medida:** el equipo no estaba parado (VS Code y otros procesos; carga media de 4 a 12 durante el banco; `MemAvailable`
  de partida ~5-6 GB). Las cifras de CPU pueden salir pesimistas; las de Vulkan, mucho menos.

## Compilación (todo en `~/.local/share/galivelop-voice/engine/`)
- `buildcpu.sh` **falla tal cual**: pide `-DGGML_BLAS=ON` y no hay BLAS (sin `cblas.h`). Sin BLAS, `cmake .. && cmake --build . -j8`
  compila bien en **65 s** (`engine/bin-cpu/`). El tiempo de generación no depende de BLAS en estas pruebas, pero no se midió con él.
- `buildvulkan.sh` falla por falta de **SPIRV-Headers** (sin permiso para instalar paquetes). Segundo intento, sin tocar el sistema:
  se clonó `KhronosGroup/SPIRV-Headers` (`fbf86836`), se instaló en `engine/deps/prefix` y se configuró con
  `-DGGML_VULKAN=ON -DCMAKE_PREFIX_PATH=<prefix> -DCMAKE_CXX_FLAGS=-I<prefix>/include` (solo con el prefijo, falta `spirv/unified1/spirv.hpp`).
  Compila en **113 s** (`engine/bin-vulkan/`). `glslc` y `libvulkan` ya estaban.
- Los binarios no llevan rpath: hace falta `LD_LIBRARY_PATH=<carpeta de compilación>`. No se probó `buildall.sh`.
- **Dónde se compiló:** dentro del Flatpak de VS Code, con el SDK `org.freedesktop.Sdk` 25.08 (de ahí salen `cmake`, `gcc`,
  `glslc` y las cabeceras de Vulkan). El SteamOS anfitrión (glibc 2.43) **no tiene `cmake` ni `gcc`**, pero sí `ffmpeg`, y los
  binarios compilados en el SDK **arrancan en el anfitrión** con `LD_LIBRARY_PATH` (comprobado con `flatpak-spawn --host`).

## Modelos (Serveurperso/Qwen3-TTS-GGUF, Q8_0, en `models/`; tamaños y sha256 coinciden con el árbol de HF)
| Archivo | Bytes | sha256 |
|---|---|---|
| qwen-talker-0.6b-base-Q8_0.gguf | 992 615 488 | d54dbaf10591421fa764ed630d764efa717ae40cd959bd48c66d4eb1af226426 |
| qwen-talker-1.7b-base-Q8_0.gguf | 2 079 448 256 | 4b9a33a236908dd9435a42f7a396e38038329d053b704342a6413c08544c4fda |
| qwen-talker-1.7b-voicedesign-Q8_0.gguf | 2 042 833 824 | 575610ab1ddcca4dca6bd9a64bcd859d93bbad8764f9cab24e1dbc0c51f62276 |
| qwen-tokenizer-12hz-Q8_0.gguf | 291 150 624 | 1883beeed99348fc35e23dd225e9082f93f6f8c109330a33d935baa8acdbfd94 |

## Ejecuciones
Pared incluye la carga del modelo (~2-3 s en Vulkan, 3-6 s en CPU). RTF = pared / audio. «larga» = frase de los obeliscos; «corta» = Hondonada.
La duración del audio cambia con la semilla y el modelo (la «larga» sale entre 10,7 y 16,2 s). Ningún error, ninguna ejecución abortada
ni cerca del umbral de 1,5 GB.

| Paso | Modelo | Disp. | Frase | Pared s | Audio s | RTF | Pico RSS MB | Mín. MemAvail MB | Estado |
|---|---|---|---|---|---|---|---|---|---|
| Diseño s11 | 1.7B VoiceDesign | CPU | larga | 66,1 | 16,16 | 4,09 | 4689 | 2325 | ok |
| Diseño s22 | 1.7B VoiceDesign | CPU | larga | 61,3 | 11,12 | 5,51 | 5050 | 2043 | ok |
| Fijar | tokenizer + 0.6B Base | CPU | toma 11 | 5,8 | - | - | 1204 | 4930 | ok |
| Fijar | tokenizer + 1.7B Base | CPU | toma 11 | 5,2 | - | - | 1167 | 5006 | ok |
| Producir s7 | 0.6B Base | CPU | corta | 33,3 | 3,44 | 9,68 | 3908 | 3214 | ok |
| Producir s7 | 0.6B Base | CPU | larga | 57,7 | 11,44 | 5,05 | 4767 | 3195 | ok |
| Producir s7 | 1.7B Base | CPU | corta | 43,1 | 2,40 | 17,97 | 6049 | 3125 | ok |
| Producir s7 | 1.7B Base | CPU | larga | 80,5 | 10,72 | 7,51 | 6671 | 2623 | ok |
| Diseño s11 | 1.7B VoiceDesign | Vulkan0 | corta | 11,4 | 1,92 | 5,95 | 2232 | 5071 | ok (primera, calentamiento) |
| Diseño s11 | 1.7B VoiceDesign | Vulkan0 | larga | 12,5 | 12,96 | 0,96 | 2281 | 4177 | ok |
| Producir s7 | 0.6B Base | Vulkan0 | corta | 6,2 | 2,56 | 2,42 | 1257 | 5120 | ok |
| Producir s7 | 0.6B Base | Vulkan0 | larga | 11,9 | 12,56 | 0,95 | 1257 | 4131 | ok |
| Producir s7 | 1.7B Base | Vulkan0 | corta | 9,3 | 2,96 | 3,14 | 2221 | 3942 | ok |
| Producir s7 | 1.7B Base | Vulkan0 | larga | 13,0 | 11,20 | 1,16 | 2281 | 3310 | ok |
| `tts-server` 0.6B | 0.6B Base | Vulkan0 | larga | 9,45 / 6,89 | 12,56 | 0,75 / 0,55 | - | - | ok |

Desglose que imprime el motor (`[Perf]`, sin carga): generación pura en Vulkan, 1.7B ~53 ms/fotograma y 0.6B ~35 ms/fotograma
(12,5 fotogramas = 1 s de audio, o sea RTF de generación 0,80 en 0.6B larga y 0,97 en 1.7B larga). En CPU: 0.6B ~130-140 ms/fotograma,
1.7B ~200-260 ms/fotograma; el prefill con ICL cuesta 2,3 s (0.6B) y 7 s (1.7B) en CPU, frente a 0,3 s en Vulkan. El decodificador del códec
tarda 22 s en CPU para 16 s de audio (casi un tercio del total) y ~0,4-1,3 s en Vulkan.

Servidor (`tts-server`, 0.6B Base, Vulkan0, 127.0.0.1:18080): primer byte **2,82 s** en la primera petición (frío) y **0,26 s** en la segunda;
total 9,45 s y 6,89 s para 12,56 s de audio (RTF 0,55 en caliente). Parado después. La salida `pcm` es s16le a 24 kHz mono (48 000 B/s).
En `wav` el códec decodifica al final; en `pcm` va en streaming.

## Vulkan e issue #41
**Sin fallos.** 7 ejecuciones del CLI y 2 peticiones al servidor, 0.6B y 1.7B, sin cuelgues, sin errores en la salida ni en los registros del servidor.
No pude leer el registro del núcleo (`journalctl` y `dmesg` no existen en el entorno Flatpak), así que **no puedo descartar un «DRM Oops» silencioso**;
quien lo quiera comprobar debe mirar `journalctl -k` en el sistema anfitrión. La Deck usa RADV (Mesa), no el controlador de la issue (Radeon 840M).
Primera ejecución Vulkan: 11,4 s para 1,9 s de audio por compilación/calentamiento de sombreadores; a partir de la segunda, normal.

## Órdenes que funcionaron
Variables: `B=~/.local/share/galivelop-voice`, `M=$B/models`, `LD_LIBRARY_PATH=$B/engine/bin-vulkan` (o `bin-cpu`).
```
# diseño (texto por la entrada estándar)
qwen-tts --model $M/qwen-talker-1.7b-voicedesign-Q8_0.gguf --codec $M/qwen-tokenizer-12hz-Q8_0.gguf \
  --instruct "<instruct>" --lang Spanish --seed 11 --device Vulkan0 -o toma11.wav < larga.txt
# fijar: escribe .rvq y .spk JUNTO al wav de entrada (toma11.wav -> toma11.rvq y toma11.spk)
qwen-codec --model $M/qwen-tokenizer-12hz-Q8_0.gguf --talker $M/qwen-talker-0.6b-base-Q8_0.gguf -i toma11.wav --device CPU
# producir: --ref-text es la RUTA de un archivo de texto con la transcripción (no el texto)
qwen-tts --model $M/qwen-talker-0.6b-base-Q8_0.gguf --codec $M/qwen-tokenizer-12hz-Q8_0.gguf \
  --ref-spk toma11.spk --ref-rvq toma11.rvq --ref-text toma11.txt --lang Spanish --seed 7 --device Vulkan0 -o out.wav < frase.txt
```
- Los `.spk` **dependen del talker**: 1024 valores f32 (4096 B) con 0.6B y 2048 (8192 B) con 1.7B; el `.rvq` (4444 B) es igual para ambos.
  Hay que generar un `.spk` por talker; los de `ref/0.6b/` y `ref/1.7b/` no son intercambiables.
- Servidor: `tts-server --model <0.6b-base> --codec <tokenizer> --device Vulkan0 --host 127.0.0.1 --port 18080 --lang Spanish`;
  `POST /v1/audio/voices` con `{"name","ref_text" (el TEXTO aquí),"spk_b64","rvq_b64"}` devuelve `{"name":"voz-t11","status":"registered"}`;
  `POST /v1/audio/speech` con `{"input","voice","language":"Spanish","response_format":"pcm","seed":7}`.

## Para escuchar (rutas absolutas, en `/home/deck/.local/share/galivelop-voice/bench/`)
- Diseño CPU, semilla 11: `diseno-cpu-s11.wav` (16,2 s); semilla 22: `diseno-cpu-s22.wav` (11,1 s). Diseño Vulkan: `diseno-vk-larga.wav`
  (misma semilla 11, pero salida distinta de la de CPU: 13,0 s frente a 16,2 s; el muestreo no es idéntico entre dispositivos), `diseno-vk-corta.wav`.
- Producción 0.6B: `prod-cpu-0.6b-{corta,larga}.wav`, `prod-vk-0.6b-{corta,larga}.wav`, `server-1.wav` (servidor).
- Producción 1.7B: `prod-cpu-1.7b-{corta,larga}.wav`, `prod-vk-1.7b-{corta,larga}.wav`.
- Referencia fijada: `ref/toma11.wav` + `ref/toma11.txt`, `ref/{0.6b,1.7b}/toma11.{spk,rvq}`.
- **No he escuchado nada:** si el español suena natural y si la voz se mantiene lo juzga la persona.

## Sorpresas
- `buildcpu.sh` y `buildvulkan.sh` no compilan en SteamOS sin dependencias (BLAS; SPIRV-Headers); la segunda se resuelve en local sin root.
- La frase «de unos 10 s» sale de 10,7 a 16,2 s según semilla y modelo: la duración no es estable entre tomas.
- El CLI de Base con el mismo `--seed` da duraciones distintas entre CPU y Vulkan (cálculo numérico distinto): una semilla no reproduce la toma entre dispositivos.
- La carga cuenta mucho en frases cortas: la «corta» tiene RTF 2,4-3,1 en Vulkan por 3-4 s de carga y prefill; el servidor lo evita.
- El decodificador del códec es un tercio del tiempo en CPU.
- `qwen-tts` usa solo 4 hilos de CPU por defecto («CPU threads: 4»); no se probó `-t`/más hilos (no hay opción en la ayuda).

## Conclusión
En la Deck, **Vulkan es obligatorio para tiempo casi real**: 0.6B Base ~0,55-0,95 de RTF, 1.7B ~1,0-1,2; en CPU el RTF es 4-18 y consume 4-6,7 GB de RSS.
Nivel recomendado: **0.6B Base en Vulkan0 detrás de `tts-server`** (RSS ~1,3 GB, primer byte 0,26 s en caliente, RTF 0,55) para producir; **1.7B VoiceDesign
en Vulkan0** (RTF ~1, 2,3 GB) para diseñar voces, fuera de línea; 1.7B Base como opción de calidad si la escucha lo justifica. La CPU solo como respaldo
no interactivo.
