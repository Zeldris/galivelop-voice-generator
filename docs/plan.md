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
| D18 | **Motores y modelos como candidatos enchufables**: `qwentts.cpp` + Qwen3-TTS (D4) es el primero; cada motor es una clase con las tres operaciones de `Engine` (diseñar, fijar, producir) y su **catálogo de modelos como datos** (archivo, URL, bytes, sha256, uso). `gvoice bench` mide cualquier candidato instalado con la misma tabla, para comparar y ofrecer más de uno | La persona acepta `qwentts.cpp` como candidato a probar y, al cerrar con él, se bajan más modelos para comparar (2026-11-14) |
| D19 | **Dos vías de voz** (2026-11-17). **Vía 1, calidad (Tarkor):** tres capas: (1) interpretación humana limpia en castellano de España con un TTS que clona desde una muestra peninsular (el acento sale de la muestra, no de la instrucción); (2) timbre de la raza con conversión de voz hacia un destino fijo por raza; (3) rasgos inexistentes con la cadena de efectos (F3: formantes, tono, saturación, capas, reverb, coro). Cada voz es una receta guardada (muestra, destino, cadena). **Vía 2, rápida (Portal, prototipos, PNJ secundarios, inventar destinos de timbre):** VoiceDesign con proceso determinista (semillas fijas, parámetros de muestreo guardados por toma, ficha de escucha, fijar con Base). Motor de la vía 1 por elegir con investigación: licencia comercial, corre en la Deck (o en otra máquina, por decidir), castellano de España al clonar, determinismo, calidad en el banco | VoiceDesign no da acento peninsular ni control fino (`docs/investigacion/2026-11-17-qwen3tts-voicedesign-prompts.md`); ningún TTS cumple descripciones de criaturas de forma fiable |

## Fases (aprobadas el 2026-10-25)

Cada fase es una rama y un pull request a `main`, con las tres fases de revisión de `AGENTS.md`.

| Fase | Qué trae | Hecha cuando |
|---|---|---|
| F0 Esqueleto | Estructura del repo; JSON Schema de la configuración del proyecto, el pedido, el perfil de máquina, la ficha de diseño, la cadena de efectos y el paquete de voces; textos es/en; README es/en; `check` real (`python3 -m unittest`) | El check corre tests y los esquemas validan los ejemplos |
| F1 Núcleo (**hecha**) | Núcleo copiado de `gimg` (D7) + pedidos `voice`/`line`, huellas, desfasadas, cola persistente, candado de la máquina, registro JSONL, avisos de la ficha y CLI `gvoice` básica; todo con un **motor de pruebas** que no genera de verdad | Tests en verde del ciclo completo con el motor de pruebas |
| F2 Motor real | `instalar.sh` (D17); envoltorio de `qwen-tts`/`qwen-codec` con el perfil `steam-deck` (D15) y vigilante de memoria; **banco como orden** (`gvoice bench`) que repite las medidas de `docs/investigacion/2026-10-25-banco-deck.md` y escribe su tabla | Diseñar, fijar y producir una voz real en la Deck (comprobación manual de la persona) |
| F3 Efectos y paquete | Cadenas de efectos compiladas a `ffmpeg` (D12) con escucha previa; exportación del paquete de voces (D13); guía de integración (`tts-server`, `ffmpeg`, Web Audio aproximado, niveles D14) | Un paquete exportado se reproduce con `tts-server` + `ffmpeg` siguiendo la guía |
| F4 API y arranque | API HTTP (solo localhost) y arranque bajo demanda; unidad `systemd --user` opcional | Tests de la API; `gvoice` arranca el servicio solo |
| F5 Interfaz | Proyectos; pedidos; galería de tomas con reproductor y comparación; ficha con avisos; efectos con escucha; es/en. Hoja de ruta en § «F5 en detalle» | Recorrido completo en el navegador |
| F6 Piloto WMF | Configuración de ejemplo con narrador y orco; propuesta para el repo de WMF (integración y corrección de su documento 02 con lo aprendido aquí) | WMF reproduce una voz del paquete sin el generador |
| F7 Fauna | Pedidos `sound`, registro de licencias CC0 por archivo, cadenas por especie | Una especie con sus variantes por acción |

## Versiones (aprobadas el 2026-11-17)

Pedido de la persona: versionar y publicar releases como `gimg`. SemVer en 0.x: la menor es una fase o una capacidad
nueva (puede romper en 0.x), el parche son arreglos y la mayor rompe la configuración del proyecto, el pedido o la API.
Cada versión que llega a `main` lleva su etiqueta `vX.Y.Z` y una release en GitHub con las notas de su sección del
CHANGELOG (es y en). Herramientas copiadas de `gimg` (D7): `releases.py` (`suggest`, `bump`, `notes`, `verify-tag`,
`check`) y `CHANGELOG.md`/`CHANGELOG.es.md`. Como el CI de GitHub no arranca (facturación), la release se crea por la
API con `curl` y las notas de `releases.py notes`, tras el check en local confirmado por la persona. A lo sumo una
release al día; solo la última menor recibe parches. El historial anterior se publica como una sola **0.1.0** en
`2236444` (`__version__` nunca se subió).

| Versión | Qué trae | Estado |
|---|---|---|
| 0.1.0 | F0, F1, F2.1-F2.5 y F5.1-F5.7 (todo lo de `main` en `2236444`) | Etiqueta `v0.1.0` y release (2026-11-17) |
| 0.2.0 | Rama `claude/lectora-es`: `locale` en los pedidos, pasos `denoise`/`dereverb`/`trimSilence`/`loudnorm`, preset `lectura`, `gvoice fx apply`; herramientas de versión | `__version__` 0.2.0 y CHANGELOG en `971a8dd`; falta revisión, PR y etiqueta |
| 0.3.0 | D19 vía 1, capa 1: clonado desde referencia peninsular (clips CC0), Qwen3 Base frente a Chatterbox (motor enchufable si gana, D18); voz `lectora-es` del Portal entregada; **B1**: barrido de los 5 leves de `gvoice/effects.py` de `docs/records/pending.md` (`samefile`, temporal + `os.replace`, nombre del preset, `_SUPPORTED` doble, `_n`; retro 2026-11-17, P5) | — |
| 0.4.0 | D19 vía 2 determinista: semilla y muestreo por toma, pruebas sin oído, ficha de escucha; cierre de F2.6 | — |
| 0.5.0 | Cierre de F3: paquete de voces (D13), guía de integración, efectos de la capa 3 (formantes, tono, coro) | — |
| 0.6.0 | D19 vía 1, capa 2: conversión de voz (OpenVoice V2) y voces como receta (muestra, destino, cadena) | — |
| 0.7.0 | F4: API HTTP y arranque bajo demanda | — |
| 0.8.0 | F5.6, F5.9 y F5.8 | — |
| 0.9.0 | F6 piloto WMF | — |
| 0.10.0 | F7 fauna | — |
| 1.0.0 | Contrato (configuración, pedido, API) estable tras el piloto WMF | Por decidir |

## F1 en detalle

Decisiones de implementación de la sesión que abre F1 (2026-11-10), dentro de D1-D17; la persona puede revisarlas
antes del PR. Origen del núcleo: `gimg@fa1076e55825bf38d59b654341873f58322b190f` (su F1, `docs/plan.md` § «Pasos de F1»).

- **Datos** en `~/.local/share/galivelop-voice/` (D9), con la variable de entorno propia que siga el patrón de `gimg`
  para los tests. Sin entrega en F1: el paquete de voces llega en F3.
- **Pedido `voice`:** cada intento es una toma con semilla, texto de prueba e instrucción armada desde la ficha
  (`sheet`, D11). **Elegir** una toma la hace referencia y **fija** la voz: encola un trabajo `prints` que saca una
  huella por modelo de `printModels` (por defecto los de D14, aplicado al cargar la configuración). Las huellas se
  guardan junto a la toma, así **deshacer** vuelve a la referencia anterior sin repetir trabajo si ya las tiene.
- **Pedido `line`:** exige que su voz sea un pedido `voice` del proyecto con referencia elegida; si no, se rechaza al
  crearlo con su motivo. Cada intento apunta la toma de referencia con la que se hizo; una elegida hecha con otra
  referencia que la vigente está **desfasada** (se calcula, no se guarda) y no se regenera sola (D10). El modelo de
  producción sale del perfil de máquina y tiene que estar en `printModels`.
- **Cola** persistente con un solo trabajador (como `gimg`), orden de llegada: el trabajo `prints` de una voz va antes
  que las frases pedidas después. **Candado de la máquina** (D8): `flock` exclusivo sobre
  `$XDG_STATE_HOME/galivelop/gpu.lock` (por defecto `~/.local/state/galivelop/gpu.lock`) mientras dura cada trabajo.
- **Motor de pruebas** (`FakeEngine`): escribe un `.wav` PCM de 16 bits mono, determinista por semilla y texto, con
  `wave` de la stdlib, y huellas `.spk`/`.rvq` falsas derivadas del audio y el modelo.
- **Registro** JSONL en el formato de `opt-ai` (copiado de `gimg`), con dispositivo, semilla, commit del motor y
  modelo (D16).

### Pasos de F1

| Paso | Qué | Hecho cuando |
|---|---|---|
| F1.1 | `errors`, `paths`, `fsutil`, `projects` copiados de `gimg` y adaptados (D9, `printModels` por defecto) | Tests de la guardia de rutas, del registro de proyectos y de la carga de la configuración |
| F1.2 | `sheet`: instrucción en inglés en orden fijo y avisos de deriva infantil (D11) | Tests del orden, de cada aviso y de la sugerencia |
| F1.3 | `orders`: pedidos `voice`/`line`, intentos, estados, notas, elegir y deshacer, referencia vigente y desfasadas | Tests de reenvío, estados, pila de elegidas, línea sin voz fijada y desfasada tras cambiar la referencia |
| F1.4 | `engine` (`FakeEngine`), `limits`, `log` y estimado | Tests del `.wav`, las huellas, los límites, el formato del registro y la mediana |
| F1.5 | `queue`, `worker` y candado de la máquina; trabajo `prints` al elegir | Tests de orden, cancelar, reinicio, un solo trabajador, candado ocupado y huellas por modelo |
| F1.6 | `cli` `gvoice` y prueba del ciclo completo; README es/en con el uso | Test de extremo a extremo: añadir proyecto, diseñar y elegir voz, fijar, pedir frase, elegir, cambiar referencia y ver la frase desfasada |

**F1 hecha** (F1.1-F1.6, 2026-11-11): `tests/test_e2e.py` recorre el ciclo por la CLI (`tests/test_cli.py` cubre las órdenes). Pendiente: revisión de F1 antes de `main` (fases de `AGENTS.md`).

## F2 en detalle

Decisiones de implementación de la sesión que abre F2 (2026-11-14), dentro de D1-D18; la persona puede revisarlas
antes del PR. Banco de referencia: [banco en la Deck](investigacion/2026-10-25-banco-deck.md) (órdenes, cifras y
sorpresas).

- **Catálogo** por motor en `gvoice/engines/<motor>.json` (esquema propio): commit del motor, y por modelo su id
  (`0.6b-base`, `1.7b-base`, `1.7b-voicedesign`, `tokenizer-12hz`), archivo, URL, bytes, sha256 y uso (`design`,
  `base`, `codec`). Los ids son los de los perfiles de máquina y de `printModels`.
- **`gvoice models list|verify|fetch`**: lista lo instalado en `<datos>/models/`, comprueba tamaño y sha256, y baja
  lo que falte con `urllib` (archivo `.part`, comprobación y renombrado atómico). Sin dependencias (D1).
- **`QwenTtsEngine`** (`GVOICE_ENGINE=qwentts`): las órdenes del banco por `subprocess`, una vez por intento (D15):
  `qwen-tts` para diseñar (VoiceDesign + `--instruct`) y producir (Base + `--ref-spk/--ref-rvq/--ref-text` como
  **ruta**), `qwen-codec` para fijar (escribe `.spk/.rvq` junto al `.wav`: se trabaja en una carpeta temporal y se
  mueve). Texto por la entrada estándar; `LD_LIBRARY_PATH` innecesario con `rpath $ORIGIN` (D17). Binarios en
  `<datos>/engine/bin-vulkan/` (dispositivo `Vulkan*`) o `bin-cpu/` (otro), con `qwen-tts` y `qwen-codec` en cada uno;
  `GVOICE_QWENTTS_BIN` sustituye ambas carpetas (tests). Código en `gvoice/engine_qwentts.py`; idioma `Spanish` si el
  trabajo no trae otro (los trabajos no lo traen aún). Dispositivo del
  perfil y, si el motor falla al abrirlo (sale ≠0 sin archivo en 30 s), **una** repetición en `fallbackDevice`, que
  queda en el resultado (D16).
  `audio_ms` sale siempre del `.wav` (pendiente de F1). Cancelar y el tope de tiempo matan el grupo del proceso.
- **Vigilante de memoria** (D15): antes de empezar, `minFreeMemoryMb` libres o el trabajo espera en la cola; durante
  la ejecución, `MemAvailable` cada 0,5 s y, por debajo de `watchMemoryMb`, mata el proceso y el intento falla con
  su motivo. Pico de RSS (`VmHWM`) y mínimo de memoria libre van al registro.
- **`instalar.sh`** (D17): en la Deck, `flatpak --user` con `org.freedesktop.Sdk//25.08`; clona el motor en el
  commit del catálogo, SPIRV-Headers en un prefijo local, compila CPU y Vulkan sin BLAS con `rpath $ORIGIN`, baja los
  modelos con `gvoice models fetch` y prueba que el binario arranca en el anfitrión (`flatpak-spawn --host`). En otra
  distribución con compilador, directo. Idempotente; `--dry-run` imprime las órdenes (lo que prueban los tests).
- **`gvoice bench`**: repite la matriz del banco (diseñar, fijar, producir; frase corta y larga; cada modelo y
  dispositivo pedidos) con cualquier motor instalado y escribe la tabla en Markdown con motor, commit, modelo,
  dispositivo, pared, audio, RTF, pico de RSS, mínimo libre y estado. Los `.wav` quedan en `<datos>/bench/<fecha>/`.
- **Tests sin motor real**: un `qwen-tts`/`qwen-codec` falso en Python dentro de `tests/` imita sus argumentos y
  salidas (y sus fallos). Lo que necesita la Deck queda en «Pendiente» para la persona.

### Pasos de F2

| Paso | Qué | Hecho cuando |
|---|---|---|
| F2.1 | Catálogo `gvoice/engines/qwentts.json` y su esquema; `gvoice models` (`list`, `verify`, `fetch`) | Tests de verificación, descarga con servidor local, sha256 que no casa y archivo a medias |
| F2.2 | `QwenTtsEngine` con motor falso: órdenes, carpeta temporal, `audio_ms`, respaldo de dispositivo, cancelar y tope | Tests de cada orden armada, respaldo, cancelar, tope y errores del motor con su motivo |
| F2.3 | Vigilante de memoria en el trabajador y el motor (D15), con `limits` | Tests de espera por memoria, aborto por debajo del umbral y valores en el registro |
| F2.4 | `instalar.sh` (D17) con `--dry-run` | Tests de las órdenes en la Deck y en otra distribución; `bash -n` en el check |
| F2.5 | `gvoice bench` y su tabla (hecho) | Tests de la matriz y de la tabla con el motor falso |
| F2.6 | Comprobación en la Deck (la persona): instalar, diseñar, fijar y producir una voz real; `gvoice bench` | La persona lo confirma; resultados en `docs/investigacion/` |

## F5 en detalle (hoja de ruta, 2026-11-15)

Borrador para la persona; solo F5.1-F5.4 están implementados. **Avance: F5.1-F5.4 hechos (4 de 9 pasos, ~44 %).** Hay base de interfaz, contrato y simulador; no hay API (F4) ni efectos
(F3). La base que usará ya existe: proyectos, pedidos, tomas, elegir y deshacer, cola, avisos de la ficha y textos
es/en (F1), además del motor real (F2).

### De dónde sale

- **Estilo:** la hoja de voces de GVIG, `galivelop-image-generator@46248251` `docs/marcas/galivelop-voice-generator/hoja.md`.
  Solo valen los bloques vigentes: Identidad (l.32), Interfaz (l.89), Recursos (l.126) y Familia (l.155). Las
  secciones 0-15, `biblia.md` y los SVG de `logos/` son histórico.
  - Hereda del Portal papel, tinta, cerúleo `#0072a8`, peligro `#a3135f`, chaflanes 28/14/10, retícula de 24 px y
    las tipografías Big Shoulders Display, Literata y JetBrains Mono (OFL).
  - Solo cambia el acento:

    | Token | Claro | Oscuro | Uso |
    |---|---|---|---|
    | vivo | `#d9467a` | `#d9467a` | foco, punto y marca; nunca lleva texto encima |
    | hondo | `#ce3c71` | `#ce3c71` | bloques, logo y texto de acento; texto blanco encima (4,66:1) |
    | enlace | hondo | `#e75485` | enlaces |
    | tinte | `#f7e6ed` | `#321f2f` | fondos suaves |

  - Reglas:
    - Tema claro por defecto.
    - No se añade un cuarto color.
    - El peligro va siempre con ✗ y texto, y se comprueba en la primera pantalla.
    - La toma elegida se marca con un visto o un subrayado, nunca solo con color.
    - Los iconos son una serie propia, de línea simple y legibles a 24 px, sin lucide.
- **Código:** la interfaz de GVIG (`gimg/ui/`, su F4, hecha en la 0.4.0).
  - Es de JS vanilla con módulos ES, sin build y con CSP estricta. El DOM se arma con `h()`, sin `innerHTML`.
  - Se copian casi tal cual, con la cabecera `Copiado de gimg@46248251` (D7):
    - **Núcleo JS:** `dom`, `router`, `store`, `i18n`, `api` (con transporte simulado y `?mock=1`) y `queue-poll`.
    - **Componentes JS:** `toast`, `confirm`, `lightbox` (como diálogo), `theme`, `shortcuts` (teclado y mando de
      la Deck), `queue-bar`, `projects-view`, `project-view`, `compare-view` y `new-order`.
    - **Estilos y fuentes:** `tokens.css` (con el acento cambiado), `base.css`, `layout.css`, `fonts/` y `OFL.txt`.
    - **Servidor estático:** el de `gimg/server.py` (`_static`, CSP y `no-cache`).
    - **Tests:** `test_ui.py` (CSP, imports, claves es/en y rutas de la API) y el arnés de Chrome de
      `test_ui_browser.py`.
  - No sirve lo que es solo de imágenes: tarjeta de intento, plantillas, composición, taller y medidas de marca.
- **Otros fronts:** el Portal (React) es la fuente de los tokens (`src/estilos/global.css`). Ni el Portal, ni el
  instalador WMF, ni WMF tienen reproductor ni forma de onda, así que **el audio se escribe de cero**. Se usará
  `<audio>` nativo y la forma de onda en `<canvas>`, las dos cosas permitidas por la CSP.

### Pasos propuestos [P]

F5 necesita la API (F4) y, para los efectos, F3. **Decisión de la persona (2026-11-15):** F5 empieza ya en la nube, mientras
F2.6 espera a la Deck. Se trabaja con el simulador (`?mock=1`, transporte falso de `api.js`) y el contrato de rutas de
la API se fija en F5.1; F4 lo implementa después y `test_ui.py` comprueba que coinciden. F5.6 (efectos) espera a F3.
Mientras no haya logo ni iconos, nombre en texto y tokens con los nombres de `gimg` (propuesta, la persona puede cambiarlos).
**Cada paso F5.n cierra con su revisión de bloque** (`/code-review` desde el último `Findings:`), sin esperar al aviso
de `changeSize.block`; el comportamiento del JS se prueba con `node` en `tests/test_ui_js.py` (retro F5.1, aprobada).

| Paso | Qué | Hecho cuando |
|---|---|---|
| F5.0 | Recursos de marca (los pide la persona en una sesión de GVIG; ver abajo) | Archivos en `gvoice/ui/assets/` |
| F5.1 | **Hecho (2026-11-15).** Base copiada de `gimg/ui`: `index.html`, tokens con el acento de voces, CSS, fuentes, núcleo JS, servidor estático con CSP y tests estáticos; contrato en `docs/api.md` | Tests de CSP, imports y claves es/en; contraste de los tokens |
| F5.2 | **Hecho (2026-11-15).** Proyectos (lista, registrar por carpeta, quitar con confirmación), pedidos del proyecto con filtros `type`/`chosen` en la URL (`#/p/<p>/orders?type=&chosen=`) y «Nuevo pedido» (`voice` con ficha de diseño y `line` con voz e id; cuerpo validado como `order.schema.json`); `app.js` ya limpia cada vista al cambiar de ruta; lógica pura en `ui/js/order-model.js` | Recorrido con `?mock=1` hecho en Chrome (1280 y 360 px, sin errores de consola ni de CSP). **Pendiente:** «con el motor falso» queda para cuando F4 implemente la API |
| F5.3 | **Hecho (2026-11-15).** Ficha de diseño con avisos (`sheet.py`), cada uno con icono y texto: componente `sheet-warnings.js` (instrucción en monoespaciada y avisos con icono SVG propio y `aria-live`), comprobación en vivo en «Nuevo pedido» con espera de 300 ms que descarta respuestas viejas (`sheet-check.js`) y acción «Ficha» por pedido `voice` en el proyecto | Tests de cada aviso en pantalla |
| F5.4 | **Hecho (2026-11-15).** Vista de pedido con galería de tomas (`order-view.js`, `take-card.js`, `waveform.js`, `take-model.js`): reproductor, forma de onda en canvas con picos, estado/nota, elegir con marca visto, deshacer, huellas y más tomas; atajos de teclado y mando en `shortcuts.js` (copiado de `gimg@46248251`). Pendiente: el mando por Gamepad API en la Deck, de la persona (F5.8) | Reproducir, elegir y deshacer con teclado y mando |
| F5.5 | **Hecho (2026-11-15).** Comparación A/B en `#/p/<p>/o/<clave>/ab?a=&b=` (`compare-view.js`, `compare-model.js`): dos tomas del mismo pedido, un solo transporte, cambio al mismo punto (`switchPoint`; la más corta queda al final y no suena), elegir A o B, cambiar la toma de cada lado; atajo `swap` (`x`, LB/RB) y «Comparar A/B» en el pedido. Pendiente: LB/RB en la Deck (F5.8) | Test del cambio con `node` y recorrido en Chromium con `?mock=1` (1280 y 360 px): el otro lado arranca en el mismo punto, sin errores de consola ni de CSP |
| F5.6 | Efectos con escucha previa: editor de la cadena de vocabulario cerrado (D12), escucha generada por `ffmpeg` en el servidor | Escucha previa igual al grafo exportado |
| F5.7 | **Hecho (2026-11-16).** Barra de cola (`queue-bar.js` de `gimg@46248251` y `queue-model.js`): píldora «N en marcha · M en cola», cajón con filtros, cancelar por entrada y vaciar (todo o del proyecto) con confirmación; fallidas con ✗ y el motivo. Sin mover ni pausar (el contrato no los tiene). Arnés de Chrome (`tests/browser.py`, `tests/test_ui_browser.py`) con `?mock=1`: es/en, tema, cuatro pantallas y el cajón a 360, 768 y 1280 px | `test_ui_browser` en verde |
| F5.8 | Recorrido en la Deck, con mando, y en escritorio (la persona) | La persona lo confirma |
| F5.9 | Barrido de leves de la interfaz (retro `docs/records/retro-2026-11-16-pr-f5.md`, P4): `loading()` y `bindShortcuts(perform)` comunes en `shortcuts.js` para las cuatro vistas, ayuda de atajos filtrada por vista; leves de `queue-bar.js`/`queue-model.js` (estado o tipo desconocido, fallida sin motivo, `role: 'group'`, `store.queueCounts()` muerto); arnés: sin Chrome falla en el CI, `find_chrome()` en `setUpClass`, sin `cls.tmp`, `goto()` que espera la página nueva. Encargo a `implementador` sonnet; quita esas entradas de `docs/records/pending.md` | Tests de JS y arnés de Chrome en verde; el CI falla si falta Chrome |

### Lo que hay que pedir a la persona

- **Logo:** símbolo y lockup, sin dibujar todavía (hoja l.131-133).
  - Símbolo: monograma en `#fbfcfd` sobre cuadrado con chaflán en `#ce3c71`, hecho con `gimg brand square`.
  - Lockup: hecho con `gimg brand wordmark "GALIVELOP VOICE GENERATOR"`.
  - Hasta tenerlo, la interfaz lleva el nombre en texto.
- **Favicon:** el símbolo, a 16 px.
- **Iconos de interfaz:** tomas, huella, cola, efectos, reproducir/pausa y A/B. La hoja los deja para F5. Hay que
  decidir quién los dibuja: GVIG con `gimg brand` o este repo a mano siguiendo la hoja.
- **Nombres de los tokens de acento:** la hoja los deja a este repo. La propuesta es usar los de `gimg/ui/css/tokens.css`
  (`--accent`, `--accent-text`, `--accent-fill`, `--accent-soft`).
- **Dudas abiertas de la hoja que tocan a la interfaz:** la 4 (el acento se parece al peligro: 7° de tono y 1,60:1) y
  la 3 (texto sobre el vivo).
- **Audio de ejemplo para el simulador:** no hace falta pedirlo. Se genera con `wave` en los tests.

## Pendiente

- **Correr `gvoice bench` en la Deck** (la persona, F2.6): `gvoice bench --devices Vulkan0,cpu` con el motor real; su tabla (`bench.md`) va a `docs/investigacion/`. Los tests solo prueban la matriz y la tabla con el motor falso (`tests/fake_qwentts.py`). Las frases corta y larga son las de `gvoice/bench.py` (las del banco no se guardaron como texto).
- **Correr `instalar.sh` de verdad en la Deck** (la persona, F2.6): los tests solo prueban las órdenes (`--dry-run`) y
  una ejecución con `git`/`cmake` falsos. Quedan por ver con la máquina real: dónde deja `cmake` los binarios de
  `qwentts.cpp` (el script reúne `qwen-tts`, `qwen-codec`, `tts-server` y los `.so` en la raíz de `bin-*`), que el rpath
  `$ORIGIN` llegue al binario (`readelf -d`) y que `qwen-tts --help` arranque en el anfitrión.
- **Escucha del banco** (la persona, en la Deck; 2026-11-14: `qwentts.cpp` se acepta como primer candidato, D18): si el español suena natural y si la voz se mantiene entre frases,
  en `~/.local/share/galivelop-voice/bench/` (`diseno-cpu-s11.wav`, `diseno-cpu-s22.wav`, `prod-vk-0.6b-larga.wav`,
  `prod-vk-1.7b-larga.wav`). Al cerrar F2 se bajan más modelos para comparar con `gvoice bench`.
- **Registro del núcleo tras Vulkan** (la persona, en el anfitrión): `journalctl -k | grep -i -E "amdgpu|drm"` tras
  generar, para descartar el fallo silencioso de la issue #41.
- Proponer al repo de imágenes el candado de la máquina (D8) y, más adelante, el núcleo común (D7).
