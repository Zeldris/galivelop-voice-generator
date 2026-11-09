# VoiceStudio: repo de referencia para revisar

Apuntado el 2026-11-08 a partir de una captura de su README que mandó la persona. **Aún no se ha revisado**: falta
leerlo con un subagente que devuelva un resumen con rutas.

**Repo:** <https://github.com/debpalash/VoiceStudio> (antes `OmniVoice-Studio`), localizado el 2026-11-09 con una
búsqueda web; varias fichas externas y su README en `raw.githubusercontent.com/debpalash/VoiceStudio` coinciden.

## Lo que dice la captura

- **VoiceStudio**, «AI voice studio. On your device.»: clonar, diseñar, doblar, dictar, transcribir y narrar en 646
  idiomas, todo en local (portátil, sobremesa, servidor, móvil, tableta), sin cuentas ni claves de API.
- Versión `v0.5.7`, licencia **AGPL-3.0**, ~100 000 estrellas, «#1 Repository Of The Day» en GitHub Trending.
- Tiene web, descargas, documentación, una versión Pro y otra Cloud.
- La interfaz de ejemplo es un estudio de doblaje de vídeo: subir y transcribir (idioma de origen, número de
  hablantes, separación de hablantes), doblar a otros idiomas, traducción local (Argos) o con agente, y calidad de
  traducción «Fast / Autofit / Cinematic».

## Lo que dicen fuentes externas (sin comprobar en el repo)

- App de escritorio local para clonar y diseñar voces, doblar vídeo, transcribir y dictar en tiempo real; una ficha
  habla de 16 motores de TTS y 11 de reconocimiento de voz. Versiones para macOS, Windows y Linux, e imagen Docker.
  Se describe como beta activa.
- **Los modelos tienen su propia licencia:** según una fuente, los pesos por defecto de OmniVoice son CC-BY-NC (no
  comercial). Cualquier modelo que se considere hay que mirarlo uno a uno.
- Las cifras de estrellas no cuadran entre fuentes (de ~10 000 a más de 100 000); no son fiables.

## Qué mirar al revisarlo

- Cómo diseña y clona voces (modelos, formato de la referencia, si guarda algo equivalente a nuestras huellas, D10).
- Qué motor de TTS usa y si corre en la Steam Deck (D15) o sin Python en la máquina final (D2).
- Ideas de interfaz para el ciclo de intentos y elegida.

**Ojo con la licencia:** AGPL-3.0. Se lee para sacar ideas; copiar código obligaría a publicar este proyecto bajo
AGPL. Cualquier copia literal se consulta antes con la persona.
