<!-- galivelop-workflow v0.3.0 -->
# Glosario

Vocabulario de galivelop-voice-generator. Primero van los términos del flujo; el proyecto añade debajo los de su dominio y los
mantiene al día (skill `domain-modeling`). El flujo nunca sobrescribe este archivo una vez creado.

## Términos del flujo

- **Bitácora**: `docs/traspaso.md`, el estado del trabajo para la siguiente sesión: rama, tarea en curso, siguiente paso,
  check.
- **Relevo**: una sesión que se acaba y otra que sigue desde la bitácora, sin preguntar por dónde iba.
- **Punto estable**: un estado con el check en verde, con commit y subido.
- **Check**: las órdenes del proyecto que tienen que pasar en cada commit que se sube: `true`.
- **Commit `WIP:`**: un commit subido con algo a medias o en rojo; la bitácora dice qué falla y por qué.
- **Rama protegida**: `main`, lo publicado; solo recibe trabajo revisado, con confirmación
  de la persona.
- **Marca de revisión**: `docs/registros/revisado.txt`, el archivo versionado con el sha del último commit revisado; los ganchos
  aceptan código hasta él.
- **Contenido frente a código**: el contenido (lo que casa con `content` de `.claude/gw.json`) no necesita revisión
  de código; todo lo demás es código.
- **Encargo a un subagente**: lo que recibe un subagente: objetivo, rutas, restricciones, el check que debe pasar y
  qué tiene que devolver.
- **Retro**: la retrospectiva de la sesión antes de ir a la rama protegida; sus propuestas se presentan a la persona y
  lo que confirme se aplica en la rama.
- **Propuesta (`.gw-nuevo`)**: un archivo del flujo que la actualización no pudo aplicar sin perder cambios locales;
  se fusiona a mano y luego se borra.

## Términos del proyecto

<!-- **Término**: definición, y dónde vive en el código. -->

**Generador**:
El servicio local de desarrollo, uno por máquina, que diseña y fija voces, pregenera frases y exporta paquetes de
voces para los proyectos.
_Evitar_: servidor, `tts-server` (eso es el motor)
_En código_: generator

**Motor**:
El programa que sintetiza la voz (`qwentts.cpp`); el generador lo lanza en desarrollo y el juego lo usa directamente.
_Evitar_: modelo (el modelo es el archivo de pesos que carga el motor)
_En código_: engine

**Voz**:
Una persona sintética reconocible, definida por su referencia elegida; suena igual en todas sus frases.
_Evitar_: hablante, timbre, embedding
_En código_: voice

**Referencia**:
El audio elegido de una voz y su transcripción: la fuente de verdad de la voz, válida con cualquier motor futuro.
_En código_: reference

**Cadena de efectos**:
Una lista de efectos de audio guardada como datos, con nombre, que da su identidad a un grupo de voces o a una
especie; el juego la aplica al reproducir o el generador al preparar sonidos.
_Evitar_: filtro, preset
_En código_: effects chain

**Paquete de voces**:
Lo que el generador exporta para que un juego reproduzca sus voces sin el generador: referencias, lo fijado para cada
modelo y cadenas de efectos.
_Evitar_: banco de voces, librería
_En código_: voice pack
