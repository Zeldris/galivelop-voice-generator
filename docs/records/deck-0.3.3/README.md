# 0.3.3 en la Deck: voz desde muestra con Qwen3 Base, frente a `lectora-es`

Objetivo: comprobar **a oído** si una voz clonada desde una muestra humana peninsular (Qwen3 Base) suena mejor que la
`lectora-es` actual. Aquí solo hay motor falso: todo esto se corre en la Deck con el motor real. Si usas VS Code en
Flatpak, antepón `flatpak-spawn --host` a cada orden del anfitrión (ver
[`docs/investigacion/2026-10-25-banco-deck.md`](../../investigacion/2026-10-25-banco-deck.md)).

## 1. Grabar `muestra.wav`

- 10-15 s leyendo la frase de `text` de [`order-voice-lectora-muestra-es.json`](order-voice-lectora-muestra-es.json)
  (tiene z, ce y ci). Léela con tu acento, a ritmo normal, sin teatro.
- Sitio silencioso, sin eco, sin música ni ruido de fondo; micrófono a unos 15-20 cm.
- Formato: **WAV** (PCM, lo que lee el módulo `wave` de Python), mono recomendado, 24 o 44,1 kHz. Máximo **64 MB** y
  no vacío; si no, `order.sample_not_wav`, `order.sample_too_big` u `order.sample_empty`.
- Guárdalo como `muestra.wav` **en esta carpeta** (la ruta de `sample.audio` es relativa al JSON).
- Si lees otra frase, **edita `sample.text`** con lo que dices de verdad (es la transcripción; si no coincide, la
  voz sale peor), y rellena `source` y `license`. No se puede corregir la transcripción de un audio ya enviado
  (`order.sample_changed`): hay que grabar otro audio o usar otra clave.

## 2. Pedir la voz y elegir la toma 1

```sh
cd docs/records/deck-0.3.3
python3 -m gvoice project list                       # el proyecto tiene que estar registrado
python3 -m gvoice order submit portal order-voice-lectora-muestra-es.json
python3 -m gvoice order show portal lectora-muestra-es
python3 -m gvoice choose portal lectora-muestra-es 1
```

Una voz de muestra no encola tomas de diseño: la toma 1 es la propia muestra. Al elegirla se encolan sus huellas de
voz.

## 3. Las mismas frases con las dos voces

```sh
for f in order-line-lectora-muestra-es-escucha-0*.json order-line-lectora-es-escucha-0*.json; do
  python3 -m gvoice order submit portal "$f"
done
python3 -m gvoice work
```

`gvoice work` procesa la cola hasta vaciarla (primero las huellas, luego las frases). Con `python3 -m gvoice queue --help`
se ve el estado de la cola si algo se queda parado.

## 4. Dónde escuchar

Cada toma es `audio.wav` en
`~/.local/share/galivelop-voice/projects/portal/orders/<clave>/@/attempts/<id>/audio.wav` (el `<id>` sale en
`python3 -m gvoice order show portal <clave>`; con `GVOICE_DATA_HOME` o `XDG_DATA_HOME` la raíz cambia). Por ejemplo:
`.../orders/lectora-es/escucha-01/@/attempts/q<n>/audio.wav`. Ábrelo con cualquier reproductor de la Deck.
Escucha por frase, alternando `lectora-muestra-es/escucha-0N` y `lectora-es/escucha-0N`.

## 5. Lista de escucha

- [ ] **θ peninsular:** «hace», «cinco», «zona», «cielo», «Zaragoza», «cerveza» suenan con zeta de España, no con seseo.
- [ ] **Entonación de la pregunta** (frase 2): sube al final, sin sonar a afirmación.
- [ ] **Limpieza:** sin ruido de la muestra, ecos, clics ni cortes al final.
- [ ] **Misma voz** en las tres frases (timbre y velocidad estables).
- [ ] **Frente a `lectora-es`:** ¿cuál prefieres en cada frase y por qué?

## 6. Veredicto

Anótalo en una nota nueva `docs/investigacion/2026-11-xx-voz-desde-muestra-deck.md` (fecha real) o, si es corto, en la
fila 0.3.3 de [`docs/plan.md`](../../plan.md) (y pásala a «hecho»). Si la muestra gana, es la base de la vía 1 de D19;
si no, se queda `lectora-es` y se prueba Chatterbox (D18).
