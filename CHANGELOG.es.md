# Registro de cambios

[English](CHANGELOG.md)

Aquí se apuntan todos los cambios notables del proyecto.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Corregido

- Interfaz: los errores sin texto de la API enseñan `ui.error.code` (también en la barra de cola) en vez de una
  cadena fija en inglés.
- `gvoice fx apply` da un error claro si la salida es un directorio, no tiene nombre o no es un `.wav`, escribe a
  través de un enlace simbólico en vez de sustituirlo y usa un temporal no adivinable creado en exclusiva.
- `gvoice fx apply` rechaza el mismo archivo como entrada y salida, escribe a un temporal y solo sustituye la
  salida si ffmpeg acaba bien; un archivo de cadena local gana a un preset del mismo nombre, y los nombres de preset
  se limitan a `[a-z0-9_-]`.
- Interfaz: la ayuda de atajos solo enseña los de la vista abierta (la A/B ya no lista U/C/D/G).
- Barra de cola: un estado o tipo desconocido se muestra tal cual, una fallida sin texto enseña su código y cada
  entrada es un grupo accesible.

## [0.2.0] - 2026-11-17

### Añadido

- `locale` en los pedidos `voice` (`es-ES`, `es-419`, `en-US`, `en-GB`); una `line` hereda el de su voz (ejemplo:
  `examples/order-voice-lectora-es.json`).
- Pasos de efectos `denoise`, `dereverb` (aproximado con `agate`), `trimSilence` y `loudnorm` (dos pasadas),
  compilados a ffmpeg, y el preset `lectura`.
- `gvoice fx apply`: aplica una cadena de efectos a un audio (`--json`).
- Versionado como en `gimg`: `releases.py` (`suggest`, `bump`, `notes`, `verify-tag`, `check`) y estos CHANGELOG.

### Corregido

- Arreglos de la revisión: el locale de las tomas, `loudnorm` en silencio y la frecuencia de los WAV.
- Las líneas se comparan con el locale de su toma de referencia; si la toma elegida de la voz no existe, la línea sale
  desfasada en vez de romper los listados.
- `releases.py check` comprueba la etiqueta aunque no haya `gh` y la release por la API REST de GitHub.

## [0.1.0] - 2026-11-16

### Añadido

- F0, esqueleto: esquemas JSON, textos de interfaz en español e inglés, README.
- F1, núcleo: pedidos `voice` y `line`, huellas, detección de desfasadas, cola, candado de máquina, registro JSONL,
  avisos de la ficha, CLI `gvoice` y motor de pruebas.
- F2.1-F2.5: catálogo de modelos y `gvoice models`, `QwenTtsEngine` con qwentts.cpp, vigilante de memoria,
  `instalar.sh` y `gvoice bench`.
- F5.1-F5.7: interfaz web con proyectos, pedidos, ficha con avisos, galería de tomas, comparación A/B y barra de cola.
