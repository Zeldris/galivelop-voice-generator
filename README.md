# galivelop-voice-generator

[English](README.en.md)

Generador de voces con IA local para desarrollo: un servicio por máquina que comparten varios proyectos (D1, D2). Usa
`qwentts.cpp` como motor y la Steam Deck como máquina de referencia. Sin dependencias: Python 3 solo con la biblioteca
estándar. **No conoce el dominio** (D3): sabe de voces, cadenas de efectos y frases; razas, narrador y qué NPC usa qué
voz lo decide cada proyecto en su `galivelop-voices.json`.

## Estado

En desarrollo, fase **F1 (núcleo) hecha**: contrato (esquemas JSON), pedidos, cola, trabajador y CLI `gvoice`, todo con un
motor de pruebas. **Aún no genera voces de verdad**: el motor real llega en F2.

Detalle, decisiones D1-D17 y criterios de cierre en [`docs/plan.md`](docs/plan.md); vocabulario en
[`GLOSSARY.md`](GLOSSARY.md).

## Uso

```sh
python3 -m gvoice project add <carpeta>              # carpeta con galivelop-voices.json
python3 -m gvoice order submit <proyecto> examples/order-voice.json   # muestra los avisos de la ficha
python3 -m gvoice work                               # procesa la cola hasta vaciarla
python3 -m gvoice order show <proyecto> narrator     # tomas, huellas y frases desfasadas
python3 -m gvoice choose <proyecto> narrator 1       # fija la voz y encola sus huellas
python3 -m gvoice attempt new <proyecto> narrator    # otra toma; también `mark`, `note`
python3 -m gvoice undo <proyecto> narrator           # vuelve a la referencia anterior
python3 -m gvoice queue list                         # también `queue cancel <entrada>`
```

`order list` y `order show` marcan las frases elegidas con una referencia que ya no es la vigente (desfasadas, D10).
`--json` da la salida legible por máquina y `--lang es|en` el idioma; el resto con `--help`. Variables:
`GVOICE_CONFIG_HOME`, `GVOICE_DATA_HOME`, `GVOICE_STATE_HOME`, `GVOICE_ENGINE` (por ahora solo `fake`) y `GVOICE_LANG`.

## Estructura

```text
gvoice/                 paquete Python (solo stdlib; código y contrato en inglés)
  cli.py, __main__.py   orden `gvoice` (`python3 -m gvoice`)
  orders.py, queue.py,
  worker.py, sheet.py   pedidos y tomas, cola, trabajador, ficha de diseño (más módulos de apoyo)
  schema.py             validador del subconjunto de JSON Schema (copiado de gimg, D7)
  i18n.py, locales/     textos es/en
  schemas/              un esquema por documento
  machine_profiles/     perfiles de máquina (steam-deck, D15)
examples/               un ejemplo válido por esquema (el pedido, uno voice y uno line)
tests/                  unittest
```

Esquemas en `gvoice/schemas/`:

| Documento | Esquema |
|---|---|
| Configuración del proyecto `galivelop-voices.json` | `project-config.schema.json` |
| Pedido (`voice` o `line`; `sound` queda reservado para F7) | `order.schema.json` |
| Perfil de máquina | `machine-profile.schema.json` |
| Ficha de diseño (las 12 claves más `extra`) | `design-sheet.schema.json` |
| Cadena de efectos (vocabulario cerrado) | `effect-chain.schema.json` |
| Paquete de voces: `pack.json` y `voice.json` | `pack.schema.json`, `voice.schema.json` |
| Definiciones compartidas (`$ref`, un dato en un solo sitio) | `common.schema.json` |

Ejemplo de configuración de proyecto: [`examples/galivelop-voices.json`](examples/galivelop-voices.json); el resto de ejemplos están en [`examples/`](examples/).

## Desarrollo

```sh
bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .
```

El flujo de trabajo del repo (relevos, ramas, revisión) está en [`AGENTS.md`](AGENTS.md). Todavía no hay licencia.
