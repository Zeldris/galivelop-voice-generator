# El generador es una herramienta de desarrollo; el juego usa el motor directamente

A diferencia de las imágenes, parte de la voz se genera mientras se juega: la narración que escribe el LLM no existe
hasta entonces. Aun así, el generador solo corre en desarrollo: diseña las voces, las fija para cada modelo,
pregenera las frases fijas y exporta un paquete de voces. En la máquina del jugador, la voz en el momento la da
`tts-server` de `qwentts.cpp` cargando ese paquete, con la cola y la caché en el backend del juego. Así no hace falta
Python ni este servicio en la máquina del jugador, y `tts-server` ya habla la API de OpenAI.

## Opciones consideradas

- El generador también como servicio de juego: rechazado, obliga a distribuir Python y la cola de desarrollo con
  cada juego.
- Una biblioteca en cada juego que hable con `tts-server`: queda en manos de cada proyecto; aquí solo el formato del
  paquete y una guía de integración.
