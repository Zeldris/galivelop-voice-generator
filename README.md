# galivelop-voice-generator

[English](README.en.md)

Generador de voces con IA local para desarrollo: un servicio por máquina que comparten varios proyectos (D1, D2). Usa
`qwentts.cpp` como motor y la Steam Deck como máquina de referencia. Sin dependencias: Python 3 solo con la biblioteca
estándar. **No conoce el dominio** (D3): sabe de voces, cadenas de efectos y frases; razas, narrador y qué NPC usa qué
voz lo decide cada proyecto en su `galivelop-voices.json`.

## Estado

En desarrollo, fase **F0 (esqueleto) hecha**: contrato (esquemas JSON), validador, textos es/en, ejemplos y tests.
**Aún no genera voces**: el núcleo llega en F1 y el motor real en F2.

| Fase | Qué trae |
|---|---|
| F0 Esqueleto | Esquemas, validador, textos es/en, ejemplos, README y tests |
| F1 Núcleo | Pedidos `voice`/`line`, huellas, cola persistente y CLI `gvoice` básica |
| F2 Motor real | `instalar.sh`, envoltorio de `qwen-tts`/`qwen-codec` y banco |
| F3 Efectos y paquete | Cadenas a `ffmpeg` y exportación del paquete de voces |
| F4-F7 | API, interfaz, piloto WMF y fauna |

Detalle, decisiones D1-D17 y criterios de cierre en [`docs/plan.md`](docs/plan.md); vocabulario en
[`GLOSSARY.md`](GLOSSARY.md).

## Estructura

```text
gvoice/                 paquete Python (solo stdlib; código y contrato en inglés)
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

Ejemplo de configuración de proyecto (el resto, en [`examples/`](examples/)):

```json
{
  "minVersion": "0.1.0",
  "name": "example-world",
  "voices": {"narrator": {"description": "Main narrator"}, "orc": {"effects": "orc"}},
  "printModels": ["0.6b-base", "1.7b-base"],
  "delivery": {"dir": "uploads/voices"}
}
```

## Desarrollo

```sh
bash -n .githooks/pre-commit .githooks/pre-push && python3 -m unittest discover -s tests -t .
```

El flujo de trabajo del repo (relevos, ramas, revisión) está en [`AGENTS.md`](AGENTS.md). Todavía no hay licencia.
