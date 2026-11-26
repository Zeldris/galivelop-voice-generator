# Pedido del Portal Galivelop, 2026-11-24: regrabación de guiones de lectura

- **Proyecto:** `portal`. **Idioma:** castellano. **Voz:** `lectora-es` (la misma de los audios ya aprobados del portal).
- **Destino:** cada trozo va a `final/es/<página>/<nn>-<seccion>.wav` y **sustituye** al WAV que haya con ese nombre.
- **Generación:** con el motor real, en la Deck (no en la nube: aquí solo hay motor falso).
- **Al entregar:** decir a la persona qué trozos están **aprobados**, para pasarlos a MP3 en el portal.

## Pronunciación

| Palabra | Cómo se dice |
|---|---|
| Galivelop | ga-li-ve-LOP |
| IG | letra a letra, «i-ge» |
| workflow | a la inglesa (uórk-flou) |
| Developer, Evaluator | a la inglesa (diveloper, ivaliueitor) |
| Steam Deck | a la inglesa (estim dek) |
| World-Maker-Fantasy | a la inglesa (uérld méiker fántasi) |
| Management Center | a la inglesa (mánach-ment cénter) |
| Discord | a la inglesa |

## Trozos

| # | Archivo | Nota | Estado |
|---|---|---|---|
| 1 | `galivelop-image-generator/02-vistazo.wav` | regrabación | pendiente |
| 2 | `galivelop-image-generator/08-participar.wav` | regrabación | pendiente |
| 3 | `galivelop-workflow/07-avance.wav` | regrabación | pendiente |
| 4 | `galivelop-workflow/08-participar.wav` | regrabación | pendiente |
| 5 | `equipo/02-alvaro-garcia-grana.wav` | regrabación | pendiente |
| 6 | `inicio/05-participa.wav` | regrabación: ya no acaba en «Gracias por escuchar» | pendiente |
| 7 | `inicio/06-productos.wav` | trozo nuevo | pendiente |

### 1. `galivelop-image-generator/02-vistazo.wav`

¿En qué punto está? Está en desarrollo, con el código abierto. La última versión publicada es la cero punto seis, y la
cero punto siete, con la hoja de marca como datos, ya está terminada y a falta de publicarse. Ahora trabaja en la pieza
de marca, la versión cero punto ocho. Y faltan cosas importantes, y lo contamos igual: comprobar a mano en la Steam Deck
el recorrido completo de la interfaz, y probar el servicio con el juego World-Maker-Fantasy. Lo último que ha cambiado
lo tienes en las novedades, más abajo.

### 2. `galivelop-image-generator/08-participar.wav`

Galivelop IG está abierto a colaboración, y el código es público. Si quieres aportar, aprender o simplemente saber más,
escríbenos y te contamos cómo. Y si quieres que lo implantemos en tu proyecto, cuéntanoslo también. Gracias por
escuchar.

### 3. `galivelop-workflow/07-avance.wav`

En el avance ves el camino. Las primeras versiones y los pilotos ya están hechos, y también las que añadieron la base,
la medida del gasto, las preguntas con otros agentes y, la última, la interfaz, con idiomas configurables, perfiles de
instalación y pruebas de interfaz. Lo que falta: la versión cero punto diez, una versión estable, con un repaso de la
documentación y la seguridad. Y la uno punto cero llegará con un panel local, el Management Center, para consultar y
configurar. Debajo están las novedades, semana a semana.

### 4. `galivelop-workflow/08-participar.wav`

Galivelop-workflow está abierto a colaboración, y el código es público. Si quieres aportar, aprender o simplemente saber
más, escríbenos y te contamos cómo. Y si quieres que lo implantemos en tu proyecto, cuéntanoslo también. Gracias por
escuchar.

### 5. `equipo/02-alvaro-garcia-grana.wav`

Empezamos por Álvaro García Graña, fundador del taller. Es arquitecto de software e ingeniero de sistemas de
inteligencia artificial, y le interesa sobre todo la infraestructura que funciona en local. Creó Tarkor,
Galivelop-workflow y Galivelop IG, y forma parte del equipo de toVeriAI. Además, lleva dos productos del taller:
Galivelop Developer y Galivelop Evaluator. Pulsa Ver perfil para conocer más de él.

### 6. `inicio/05-participa.wav` (se regraba: ya no acaba en «Gracias por escuchar»)

Para terminar, una pregunta: ¿creamos juntos? Galivelop crece con las personas que se suman. No pedimos experiencia:
pedimos ganas de construir, de aprender y de hacerlo en equipo. Hay tres caminos. Puedes colaborar en un proyecto
abierto, con código, arte, textos, pruebas o investigación. Puedes proponernos ese proyecto que parece imposible. O
puedes venir a aprender, que el mejor sitio para hacerlo es un proyecto de verdad. Funciona así: nos escribes, hablamos
para ver dónde encajas, empiezas con una tarea pequeña y, desde ahí, creces a tu ritmo. Si tienes un proyecto propio,
algunos miembros del equipo aceptan encargos, cada uno por su cuenta: en su perfil ves su trabajo y cómo escribirle. Y
si quieres conocernos antes, o solo lanzar una idea, te esperamos en Discord.

### 7. `inicio/06-productos.wav` (trozo nuevo)

Y antes de irte, una cosa más: del taller salen también dos productos de Álvaro, Galivelop Developer y Galivelop
Evaluator. Los ves en la página de productos. Gracias por escuchar.

## En la Deck

Los 7 pedidos ya están escritos, con el texto **como se pronuncia**, en
[`pedido-portal-2026-11-24/`](pedido-portal-2026-11-24/) (el texto original queda arriba, en este archivo). Si usas
VS Code en Flatpak, las órdenes del anfitrión van con `flatpak-spawn --host` delante (ver
[`docs/investigacion/2026-10-25-banco-deck.md`](../investigacion/2026-10-25-banco-deck.md)).

### Pronunciación usada

Es una **primera propuesta, a confirmar escuchando**. Si una suena mal, se corrige editando el `text` del JSON y
volviendo a enviarlo (`order submit` con la misma clave; después `attempt new` para las tomas nuevas; si `order submit` rechaza el cambio, se dice en su mensaje).

| Original | Escrito como se pronuncia |
|---|---|
| Galivelop | Galivelóp |
| IG (en «Galivelop IG») | i ge |
| workflow | uórkflou |
| Galivelop-workflow | Galivelóp uórkflou |
| Developer | Divéloper |
| Evaluator | Iváliueitor |
| Steam Deck | Estím Dek |
| World-Maker-Fantasy | Uérld Méiker Fántasi |
| Management Center | Mánachment Cénter |
| Discord | Díscord |

### Órdenes

Desde la raíz del repo (los comandos son `python3 -m gvoice ...`; todos verificados con `--help`):

```sh
# 1. El proyecto «portal» registrado y la voz lectora-es elegida
python3 -m gvoice project list                      # si falta: python3 -m gvoice project add <carpeta del portal>
python3 -m gvoice order show portal lectora-es      # tiene que salir con una toma elegida
python3 -m gvoice order list portal --type voice --chosen

# 2. Enviar los 7 pedidos (una toma cada uno; --count 3 para tener donde elegir)
for f in docs/records/pedido-portal-2026-11-24/*.json; do
  python3 -m gvoice order submit portal "$f" --count 3
done

# 3. Generar (procesa la cola hasta vaciarla)
python3 -m gvoice work
```

Si `lectora-es` no está elegida, se pide y se elige antes con `examples/order-voice-lectora-es.json` y
`python3 -m gvoice choose portal lectora-es <toma>`.

**Dónde caen las tomas:** `~/.local/share/galivelop-voice/projects/portal/orders/<clave>/@/attempts/<id>/audio.wav`
(con `GVOICE_DATA_HOME` o `XDG_DATA_HOME` cambia la raíz). La clave es, por ejemplo,
`lectora-es/inicio/06-productos`, y `<id>` (`1`, `q3`...) sale en `python3 -m gvoice order show portal <clave>`.

**Escuchar y decidir, trozo a trozo:**

```sh
python3 -m gvoice order show portal lectora-es/inicio/06-productos
python3 -m gvoice attempt mark portal lectora-es/inicio/06-productos 2 candidate   # new | candidate | discarded
python3 -m gvoice attempt note portal lectora-es/inicio/06-productos 2 "«Díscord» bien; pausa larga tras «más»"
python3 -m gvoice choose portal lectora-es/inicio/06-productos 2
# ¿Suena mal una palabra? Editar el text del JSON, volver a enviarlo y pedir tomas nuevas:
python3 -m gvoice order submit portal docs/records/pedido-portal-2026-11-24/07-inicio-productos.json
python3 -m gvoice attempt new portal lectora-es/inicio/06-productos --count 2   # tomas extra con otra semilla
```

**Obtener el WAV final** (cadena `lectura` sobre la toma elegida; sustituye al que haya con ese nombre). Ejemplo del
trozo 7, con `T` la ruta del `audio.wav` de la toma elegida y `final/` en la raíz del portal:

```sh
T=~/.local/share/galivelop-voice/projects/portal/orders/lectora-es/inicio/06-productos/@/attempts/<id>/audio.wav
python3 -m gvoice fx apply lectura "$T" <portal>/final/es/inicio/06-productos.wav
```

Se repite para cada trozo con su destino de la tabla de trozos (`final/es/<página>/<nn>-<seccion>.wav`). Hay que crear
antes la carpeta de destino si no existe, y comprobar que `fx apply` la acepta (necesita `ffmpeg`).

**Límites del CLI:** no hay una orden que copie la toma elegida a `final/` ni que diga la ruta del WAV elegido (hay
que sacarla de `order show` y de la carpeta de datos), y `gvoice` no escribe la columna «Estado» de este archivo.

**Al terminar:** en la tabla «Trozos», cambiar «pendiente» por «aprobado» en los trozos cuya toma se ha escuchado y
dado por buena, y decir a la persona cuáles están aprobados para pasarlos a MP3 en el portal.
