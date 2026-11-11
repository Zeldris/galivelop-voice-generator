<!-- galivelop-workflow v0.3.0 -->
# Glosario

Vocabulario de galivelop-voice-generator. Primero van los términos del flujo; el proyecto añade debajo los de su dominio y los
mantiene al día (skill `domain-modeling`). El flujo nunca sobrescribe este archivo una vez creado.

## Términos del flujo

- **Bitácora**: `docs/traspaso.md`, el estado del trabajo para la siguiente sesión: rama, tarea en curso, siguiente paso,
  check.
- **Relevo**: una sesión que se acaba y otra que sigue desde la bitácora, sin preguntar por dónde iba.
- **Punto estable**: un estado con el check en verde, con commit y subido.
- **Check**: las órdenes del proyecto que tienen que pasar en cada commit que se sube: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && bash -n instalar.sh && python3 -m unittest discover -s tests -t .`.
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
(En `galivelop-image-generator`, «referencia» es otra cosa: una imagen que guía la generación.)
_En código_: reference

**Ficha de diseño**:
La descripción de cómo debe sonar una voz (edad, tono, textura…), de la que el generador saca la instrucción para el
modelo de diseño.
_Evitar_: prompt, instruct (eso es el texto que se arma a partir de la ficha)
_En código_: design sheet

**Huella**:
Lo que se extrae de la referencia de una voz para un modelo concreto (`.spk` + `.rvq`); hay una por modelo y se
rehace desde la referencia.
_Evitar_: embedding, voz fijada
_En código_: voice print

**Frase**:
Un texto dicho por una voz, con clave propia, que se pregenera en desarrollo y se entrega en seco.
_Evitar_: línea, diálogo, clip
_En código_: line

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

**Proyecto**:
Un repositorio que usa el generador: declara su configuración y le manda pedidos. El generador no conoce su dominio.
_Evitar_: cliente, mundo, juego
_En código_: project

**Configuración del proyecto**:
El archivo que un proyecto tiene en su repo para conectarse al generador: sus voces, sus cadenas de efectos, los
modelos para los que fija huellas y su carpeta de entrega.
_En código_: project config (`galivelop-voices.json`)

**Pedido**:
La petición cerrada que hace un proyecto: diseñar una voz, decir una frase o (más adelante) preparar un sonido.
_Evitar_: encargo (es el «encargo a un subagente» del flujo), trabajo, job, petición
_En código_: order (`kind`: `voice`, `line`, `sound`)

**Clave del pedido**:
El nombre estable que el proyecto da a lo que pide (p. ej. `orcos/guerrero-1`); con el tipo, identifica un pedido.
_Evitar_: slug, id
_En código_: order key (`key`)

**Intento**:
Un audio generado para un pedido con una semilla concreta; en un pedido de voz, cada intento es una toma.
_Evitar_: prueba, variante, toma (solo como palabra visible)
_En código_: attempt

**Candidata**:
Un intento que la persona marca como bueno sin elegirlo todavía.
_En código_: candidate

**Descartada**:
Un intento que la persona aparta; sigue en el historial.
_En código_: discarded

**Elegida**:
El intento que la persona escoge para un pedido, como mucho uno; en una voz pasa a ser su referencia, en una frase es
el audio que se entrega.
_En código_: chosen

**Desfasada**:
Una frase elegida cuya voz ha cambiado de referencia desde que se generó; sigue entregada hasta que se regenere.
_En código_: stale

**Cola**:
Los pedidos pendientes de generar, en orden de llegada; se generan de uno en uno.
_En código_: queue

**Candado de la máquina**:
El bloqueo que comparten los generadores de Galivelop para que en un equipo solo genere uno a la vez.
_En código_: machine lock

**Perfil de máquina**:
Los límites con los que el generador trabaja en un equipo concreto (memoria, dispositivo, modelos, tiempo máximo).
_Evitar_: preset, modo
_En código_: machine profile

**Carpeta de entrega**:
La carpeta del proyecto donde el generador deja el paquete de voces.
_En código_: delivery dir

**Máquina de referencia**:
El equipo donde se mide y se valida el generador: la Steam Deck con Linux y Vulkan.
_En código_: reference machine
