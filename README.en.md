# galivelop-voice-generator

[Español](README.md)

Local AI voice generator for development: one service per machine shared by several projects (D1, D2). It uses
`qwentts.cpp` as its engine and the Steam Deck as the reference machine. No dependencies: Python 3 standard library
only. It **knows no domain** (D3): it knows voices, effect chains and lines; races, narrator and which NPC uses which
voice are decided by each project in its `galivelop-voices.json`.

## Status

In development, phase **F1 (core) done**: contract (JSON schemas), orders, queue, worker and the `gvoice` CLI, all with a
test engine. **It does not generate real voices yet**: the real engine arrives in F2.

Details, decisions D1-D17 and exit criteria in [`docs/plan.md`](docs/plan.md) (Spanish); vocabulary in
[`GLOSSARY.md`](GLOSSARY.md) (Spanish).

## Usage

```sh
python3 -m gvoice project add <folder>               # folder with galivelop-voices.json
python3 -m gvoice order submit <project> examples/order-voice.json   # shows the design sheet warnings
python3 -m gvoice work                               # process the queue until it is empty
python3 -m gvoice order show <project> narrator      # takes, voice prints and stale lines
python3 -m gvoice choose <project> narrator 1        # fixes the voice and queues its prints
python3 -m gvoice attempt new <project> narrator     # another take; also `mark`, `note`
python3 -m gvoice undo <project> narrator            # back to the previous reference
python3 -m gvoice queue list                         # also `queue cancel <entry>`
```

`order list` and `order show` mark the chosen lines made with a reference that is no longer the current one (stale,
D10). `--json` gives machine-readable output and `--lang es|en` the language; the rest with `--help`. Variables:
`GVOICE_CONFIG_HOME`, `GVOICE_DATA_HOME`, `GVOICE_STATE_HOME`, `GVOICE_ENGINE` (only `fake` for now) and `GVOICE_LANG`.

## Structure

```text
gvoice/                 Python package (stdlib only; code and contract in English)
  cli.py, __main__.py   the `gvoice` command (`python3 -m gvoice`)
  orders.py, queue.py,
  worker.py, sheet.py   orders and takes, queue, worker, design sheet (plus support modules)
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
