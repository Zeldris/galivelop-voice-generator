# Plan: generador de voces local reutilizable

Un generador de voces con IA local, para desarrollo, que cualquier proyecto puede usar: diseña voces, las fija para
cada modelo, pregenera frases y exporta un paquete de voces que el juego reproduce con su propio motor. Nace de
`World-Maker-Fantasy/docs/arquitectura/reutilizables/02-voces-y-sonidos-locales.md` (WMF), revisado el 2026-10-25 en
[investigacion/2026-10-25-estado-voz.md](investigacion/2026-10-25-estado-voz.md). Vocabulario en
[GLOSSARY.md](../GLOSSARY.md).

## Decisiones de diseño

Tomadas con `grilling` el 2026-10-25.

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Gemelo de `galivelop-image-generator`**: un servicio local por máquina con API HTTP, CLI y web; Python 3 solo stdlib con `unittest` como check; pedidos con clave, intentos, una elegida con deshacer y cola persistente; perfil de máquina con las protecciones de la Deck; registro JSONL en el formato de `opt-ai`; contrato y código en inglés, textos visibles en es/en | El diseño de imágenes ya está cerrado (su `docs/plan.md`, D1-D27) y los proyectos usan los dos igual |
| D2 | **Herramienta de desarrollo, no de juego**: diseña, fija, pregenera y exporta un **paquete de voces** (referencia `.wav`/`.txt`, `.spk`/`.rvq` por modelo, cadena de efectos como datos); en el juego, la voz en el momento la da `tts-server` de `qwentts.cpp` cargando el paquete, con la cola y la caché en el backend del juego. Este repo da el formato del paquete y una guía de integración | Sin Python en la máquina del jugador; `tts-server` ya habla la API de OpenAI. ADR [0001](adr/0001-herramienta-de-desarrollo.md) |
| D3 | **No conoce el dominio**: sabe de voces, cadenas de efectos y frases; razas, narrador y qué NPC usa qué voz los decide cada proyecto en su configuración | Si no, quedaría atado a Tarkor. ADR [0002](adr/0002-generador-sin-dominio.md) |
| D4 | Motor **`qwentts.cpp` con commit fijo**, compilado por `instalar.sh` (en el sistema si tiene herramientas de compilación; si no, en un contenedor), **Vulkan primero y CPU de respaldo**; modelos Qwen3-TTS GGUF Q8_0. **Kokoro** (Apache-2.0) es el plan de emergencia; Piper queda fuera por ser GPL-3.0; VoxCPM2 se revisa más adelante | No publica binarios; español confirmado; riesgo de Vulkan en APU AMD (issue #41) |
| D5 | **Fauna dentro del alcance, en la fase final**: fuentes CC0 con registro de licencia por archivo y cadenas de efectos aplicadas en desarrollo con `ffmpeg`. El audio generativo queda fuera hasta verificar su licencia. **Un solo formato de cadena de efectos** para voces (las aplica el juego al reproducir) y fauna (se aplican aquí al preparar) | Mismo trabajo de oído y mismo dato para los dos usos |
| D6 | **Banco de pruebas en la Deck antes de cerrar el diseño**: compilar con CPU y Vulkan, medir RTF y memoria con 0,6B y 1,7B, probar el español | Si Vulkan falla o el RTF no da, cambian los niveles de hardware o el motor |

## Pendiente del diseño

- Ronda 2 de `grilling`: código compartido con el generador de imágenes, exclusión mutua en la máquina, nombre de la
  orden, tipos de pedido, ficha de diseño, formato de la cadena de efectos y del paquete de voces.
- Resultado del banco (D6) → niveles de hardware y perfil de máquina `steam-deck`.
- Fases de implementación, para aprobarlas al cerrar el diseño.
