# galivelop-voice-generator

[Español](README.md)

Local AI voice generator for development: one service per machine shared by several projects (D1, D2). It uses
`qwentts.cpp` as its engine and the Steam Deck as the reference machine. No dependencies: Python 3 standard library
only. It **knows no domain** (D3): it knows voices, effect chains and lines; races, narrator and which NPC uses which
voice are decided by each project in its `galivelop-voices.json`.

## Status

In development, phase **F0 (skeleton) done**: contract (JSON schemas), validator, es/en texts, examples and tests.
**It does not generate voices yet**: the core arrives in F1 and the real engine in F2.

Details, decisions D1-D17 and exit criteria in [`docs/plan.md`](docs/plan.md) (Spanish); vocabulary in
[`GLOSSARY.md`](GLOSSARY.md) (Spanish).

## Structure

```text
gvoice/                 Python package (stdlib only; code and contract in English)
  schema.py             validator for the JSON Schema subset (copied from gimg, D7)
  i18n.py, locales/     es/en texts
  schemas/              one schema per document
  machine_profiles/     machine profiles (steam-deck, D15)
examples/               one valid example per schema (order: one voice, one line)
tests/                  unittest
```

Schemas in `gvoice/schemas/`:

| Document | Schema |
|---|---|
| Project configuration `galivelop-voices.json` | `project-config.schema.json` |
| Order (`voice` or `line`; `sound` is reserved for F7) | `order.schema.json` |
| Machine profile | `machine-profile.schema.json` |
| Design sheet (the 12 keys plus `extra`) | `design-sheet.schema.json` |
| Effect chain (closed vocabulary) | `effect-chain.schema.json` |
| Voice pack: `pack.json` and `voice.json` | `pack.schema.json`, `voice.schema.json` |
| Shared definitions (`$ref`, one fact in one place) | `common.schema.json` |

Example project configuration: [`examples/galivelop-voices.json`](examples/galivelop-voices.json); the other examples are in [`examples/`](examples/).

## Development

```sh
bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .
```

The repo's workflow (handoffs, branches, review) is in [`AGENTS.md`](AGENTS.md) (Spanish). There is no license yet.
