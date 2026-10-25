# Plan: generador de voces local reutilizable

Un generador de voces con IA local, para desarrollo, que cualquier proyecto puede usar: diseña voces, las fija para
cada modelo, pregenera frases y exporta un paquete de voces que el juego reproduce con su propio motor. Nace de
`World-Maker-Fantasy/docs/arquitectura/reutilizables/02-voces-y-sonidos-locales.md` (WMF), revisado el 2026-10-25 en
[investigacion/2026-10-25-estado-voz.md](investigacion/2026-10-25-estado-voz.md). Vocabulario en
[GLOSSARY.md](../GLOSSARY.md).

## Decisiones de diseño

Tomadas con `grilling` el 2026-10-25, en tres rondas. Investigación: [estado de la voz](investigacion/2026-10-25-estado-voz.md) y
[banco de pruebas en la Deck](investigacion/2026-10-25-banco-deck.md).

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Gemelo de `galivelop-image-generator`**: un servicio local por máquina con API HTTP, CLI y web; Python 3 solo stdlib con `unittest` como check; pedidos con clave, intentos, una elegida con deshacer y cola persistente; perfil de máquina con las protecciones de la Deck; registro JSONL en el formato de `opt-ai`; contrato y código en inglés, textos visibles en es/en | El diseño de imágenes ya está cerrado (su `docs/plan.md`, D1-D27) y los proyectos usan los dos igual |
| D2 | **Herramienta de desarrollo, no de juego**: diseña, fija, pregenera y exporta un **paquete de voces** (referencia `.wav`/`.txt`, `.spk`/`.rvq` por modelo, cadena de efectos como datos); en el juego, la voz en el momento la da `tts-server` de `qwentts.cpp` cargando el paquete, con la cola y la caché en el backend del juego. Este repo da el formato del paquete y una guía de integración | Sin Python en la máquina del jugador; `tts-server` ya habla la API de OpenAI. ADR [0001](adr/0001-herramienta-de-desarrollo.md) |
| D3 | **No conoce el dominio**: sabe de voces, cadenas de efectos y frases; razas, narrador y qué NPC usa qué voz los decide cada proyecto en su configuración | Si no, quedaría atado a Tarkor. ADR [0002](adr/0002-generador-sin-dominio.md) |
| D4 | Motor **`qwentts.cpp` con commit fijo**, compilado por `instalar.sh` (en el sistema si tiene herramientas de compilación; si no, en un contenedor), **Vulkan primero y CPU de respaldo**; modelos Qwen3-TTS GGUF Q8_0. **Kokoro** (Apache-2.0) es el plan de emergencia; Piper queda fuera por ser GPL-3.0; VoxCPM2 se revisa más adelante | No publica binarios; español confirmado; riesgo de Vulkan en APU AMD (issue #41) |
| D5 | **Fauna dentro del alcance, en la fase final**: fuentes CC0 con registro de licencia por archivo y cadenas de efectos aplicadas en desarrollo con `ffmpeg`. El audio generativo queda fuera hasta verificar su licencia. **Un solo formato de cadena de efectos** para voces (las aplica el juego al reproducir) y fauna (se aplican aquí al preparar) | Mismo trabajo de oído y mismo dato para los dos usos |
| D6 | **Banco de pruebas en la Deck antes de cerrar el diseño**: compilar con CPU y Vulkan, medir RTF y memoria con 0,6B y 1,7B, probar el español | Si Vulkan falla o el RTF no da, cambian los niveles de hardware o el motor |
| D7 | El núcleo genérico se **copia de `gimg`** (rutas, proyectos, pedidos, límites, registro, esquemas, textos) a `gvoice/`, con el origen anotado (`gimg@<sha>`) en cada módulo; al estar estables los dos, se propone al repo de imágenes extraer un núcleo común | Un núcleo compartido ya ataría dos repos a mitad de su F1, y desde aquí no se modifica el de imágenes |
| D8 | **Candado por máquina** compartido por los generadores: `flock` sobre `~/.local/state/galivelop/gpu.lock` mientras se genera; lo que llega mientras tanto espera en la cola. Se propone al de imágenes | En la Deck no caben una imagen y una voz a la vez |
| D9 | Orden **`gvoice`**, configuración del proyecto **`galivelop-voices.json`**, carpeta de datos **`~/.local/share/galivelop-voice/`** (motor en `engine/`, modelos en `models/`) | Mismo patrón que `gimg` / `galivelop-images.json` |
| D10 | **Tres tipos de pedido** sobre el mismo núcleo: `voice` (diseño: intentos = tomas con semilla, la elegida es la referencia), `line` (frase: voz + texto, la elegida es el audio entregado) y, en la fase final, `sound` (fauna). Al elegir una referencia, el generador **fija** la voz (una **huella** por cada modelo Base que declare el proyecto); si cambia la referencia, sus frases elegidas quedan **desfasadas** y no se regeneran solas | Mismo ciclo de intentos y elegida que las imágenes; regenerar en bloque lo decide la persona |
| D11 | **Ficha de diseño** con las 12 claves de la plantilla como campos opcionales más `extra` libre; el generador arma el instruct en inglés en orden fijo. Semilla y texto de prueba van en el pedido. **Aviso** (no bloqueo) por deriva infantil: edad no adulta o sin decir, y palabras vetadas (`bright`, `cute`, `small`, `light`, `childlike`, `high-pitched`), sugiriendo `airy`, `breathy`, `soft-spoken`, `whispering` | El instruct es texto libre (no hay claves oficiales); lo comprobable lo hace un script |
| D12 | **Cadenas de efectos definidas por su significado en `ffmpeg`**, con vocabulario cerrado: paso alto, paso bajo, ecualizador, ganancia, saturación suave, reverberación por convolución (respuesta de impulso en el paquete), coro y tono en semitonos (`asetrate`+`atempo`, mueve también los formantes). El generador las compila a un grafo de filtros para la escucha previa y la fauna; **el juego aplica el mismo grafo con `ffmpeg` en su backend** (LGPL, proceso aparte). Web Audio queda en la guía como aproximación para juegos solo de navegador | Cambia el documento de origen: Web Audio no cambia el tono sin cambiar la velocidad, y lo que se oye al ajustar debe ser lo que suena en el juego. Desplazar solo los formantes necesita `rubberband`, que este `ffmpeg` no trae |
| D13 | **Paquete de voces** en la carpeta de entrega del proyecto: `pack.json` (commit del motor, modelos con sha256, versión del formato), `voices/<clave>/` (`voice.json`, `reference.wav`, `reference.txt`, `prints/<modelo>.spk/.rvq`), `effects/<nombre>.json` con sus respuestas de impulso y `lines/<clave>.wav`. Las frases pregeneradas van **en seco**: el juego les aplica la cadena igual que a las del momento | Un solo camino de reproducción; con la referencia dentro, el juego rehace una huella si cambia de modelo |
| D14 | **Niveles de hardware del juego**: Deck/mínimo, 0.6B Base en Vulkan con `tts-server` cargado mientras se juega (~1,3 GB); GPU dedicada de 6 GB o más, 1.7B Base; sin Vulkan usable, Kokoro solo para narración. La CPU, solo para el generador en desarrollo. La configuración del proyecto declara para qué modelos se sacan huellas (por defecto 0.6B y 1.7B Base) | Banco: Vulkan da RTF ~1 (0.6B con `tts-server` 0,55 y primer audio en 0,26 s en caliente); la CPU, de 4 a 18 |
| D15 | **Perfil de máquina `steam-deck`**: `Vulkan0` con respaldo en CPU, más de 4 GB libres para empezar, aborta por debajo de 1,5 GB, tope de tiempo por intento; 1.7B VoiceDesign para diseñar, 0.6B/1.7B Base para producir. El motor se lanza **una vez por intento** (`qwen-tts`); usar `tts-server` en lotes de frases se mide después con `opt-ai` | Nada cargado en memoria entre generaciones; la carga cuesta ~3 s por frase |
| D16 | **Reproducible solo en el mismo dispositivo**: registro y manifiesto guardan dispositivo, semilla, commit del motor y modelos; la fuente de verdad es el `.wav` elegido | La misma semilla da tomas distintas en CPU y en Vulkan |
| D17 | **`instalar.sh` compila en el SDK de Flatpak** (`org.freedesktop.Sdk//25.08`, `flatpak --user`, sin root): motor en el commit `5916bf7`, SPIRV-Headers en local, sin BLAS, `rpath $ORIGIN`, checksum de los modelos y prueba de que el binario arranca en el anfitrión; en otras distribuciones con compilador, directo. Sin `distrobox`. Llevar el motor a la máquina del jugador es cosa del instalador del juego (lo explica la guía) | SteamOS no trae compilador; los binarios del SDK arrancan en el anfitrión (glibc 2.43); `buildcpu.sh`/`buildvulkan.sh` no compilan tal cual |

## Fases (aprobadas el 2026-10-25)

Cada fase es una rama y un pull request a `main`, con las tres fases de revisión de `AGENTS.md`.

| Fase | Qué trae | Hecha cuando |
|---|---|---|
| F0 Esqueleto | Estructura del repo; JSON Schema de la configuración del proyecto, el pedido, el perfil de máquina, la ficha de diseño, la cadena de efectos y el paquete de voces; textos es/en; README es/en; `check` real (`python3 -m unittest`) | El check corre tests y los esquemas validan los ejemplos |
| F1 Núcleo | Núcleo copiado de `gimg` (D7) + pedidos `voice`/`line`, huellas, desfasadas, cola persistente, candado de la máquina, registro JSONL, avisos de la ficha y CLI `gvoice` básica; todo con un **motor de pruebas** que no genera de verdad | Tests en verde del ciclo completo con el motor de pruebas |
| F2 Motor real | `instalar.sh` (D17); envoltorio de `qwen-tts`/`qwen-codec` con el perfil `steam-deck` (D15) y vigilante de memoria; **banco como orden** (`gvoice bench`) que repite las medidas de `docs/investigacion/2026-10-25-banco-deck.md` y escribe su tabla | Diseñar, fijar y producir una voz real en la Deck (comprobación manual de la persona) |
| F3 Efectos y paquete | Cadenas de efectos compiladas a `ffmpeg` (D12) con escucha previa; exportación del paquete de voces (D13); guía de integración (`tts-server`, `ffmpeg`, Web Audio aproximado, niveles D14) | Un paquete exportado se reproduce con `tts-server` + `ffmpeg` siguiendo la guía |
| F4 API y arranque | API HTTP (solo localhost) y arranque bajo demanda; unidad `systemd --user` opcional | Tests de la API; `gvoice` arranca el servicio solo |
| F5 Interfaz | Proyectos; pedidos; galería de tomas con reproductor y comparación; ficha con avisos; efectos con escucha; es/en | Recorrido completo en el navegador |
| F6 Piloto WMF | Configuración de ejemplo con narrador y orco; propuesta para el repo de WMF (integración y corrección de su documento 02 con lo aprendido aquí) | WMF reproduce una voz del paquete sin el generador |
| F7 Fauna | Pedidos `sound`, registro de licencias CC0 por archivo, cadenas por especie | Una especie con sus variantes por acción |

## Pendiente

- **Escucha del banco** (la persona, en la Deck): si el español suena natural y si la voz se mantiene entre frases,
  en `~/.local/share/galivelop-voice/bench/` (`diseno-cpu-s11.wav`, `diseno-cpu-s22.wav`, `prod-vk-0.6b-larga.wav`,
  `prod-vk-1.7b-larga.wav`). Si no convence, se revisa D4 antes de F2.
- **Registro del núcleo tras Vulkan** (la persona, en el anfitrión): `journalctl -k | grep -i -E "amdgpu|drm"` tras
  generar, para descartar el fallo silencioso de la issue #41.
- Proponer al repo de imágenes el candado de la máquina (D8) y, más adelante, el núcleo común (D7).
