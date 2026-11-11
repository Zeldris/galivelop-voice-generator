# galivelop-voice-generator

[Español](README.md)

Local AI voice generator for development: one service per machine shared by several projects (D1, D2). It uses
`qwentts.cpp` as its engine and the Steam Deck as the reference machine. No dependencies: Python 3 standard library
only. It **knows no domain** (D3): it knows voices, effect chains and lines; races, narrator and which NPC uses which
voice are decided by each project in its `galivelop-voices.json`.

## Status

In development. **F1 (core) done**: contract (JSON schemas), orders, queue, worker and the `gvoice` CLI. **F2 (real
engine) code done**: `instalar.sh`, the `qwentts` engine with a memory and time watchdog, `gvoice doctor` and
`gvoice bench`; still to be checked on the Steam Deck.

Details, decisions D1-D17 and exit criteria in [`docs/plan.md`](docs/plan.md) (Spanish); vocabulary in
[`GLOSSARY.md`](GLOSSARY.md) (Spanish).

## Install

```sh
./instalar.sh --plan        # says where it would build and what it would download, without touching anything
./instalar.sh               # engine (CPU and Vulkan) and models (about 5 GB) in the data folder
./instalar.sh --solo-cpu    # no Vulkan; --sin-modelos skips the models
python3 -m gvoice doctor    # checks what is installed
```

No root and no system packages: without a compiler it builds inside the Flatpak SDK (`--user`). It installs into
`~/.local/share/galivelop-voice/engine/` and the models into `models/` next to it (`GVOICE_MODELS_HOME` moves them
elsewhere, e.g. the SD card). Running it again skips what is done. To use the real engine, set `GVOICE_ENGINE=qwentts`
or `{"engine": "qwentts"}` in `~/.config/galivelop-voice/config.json`; otherwise the test engine (`fake`) is used.

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
`GVOICE_CONFIG_HOME`, `GVOICE_DATA_HOME`, `GVOICE_STATE_HOME`, `GVOICE_ENGINE` (`fake` or `qwentts`), `GVOICE_MODELS_HOME` and `GVOICE_LANG`.

### Engine diagnosis and bench

```sh
python3 -m gvoice doctor            # install, binaries, models with their sha256 and profile; starts no engine
python3 -m gvoice doctor --quick    # model sizes only (the sha256 of 2-4 GB is slow)
python3 -m gvoice bench             # design, fix and produce (short and long) on the device and its fallback
python3 -m gvoice bench --quick --seed 11   # only the profile's device and the first production model
```

`doctor` exits 1 if anything fails (a warning does not count). `bench` takes the machine lock, writes the wavs,
`bench.md` and `bench.json` in `<data>/bench/<date>/` and can be cancelled with Ctrl-C (130). `--rapido` and
`--semilla` also work.

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
bash -n .githooks/pre-commit && bash -n .githooks/pre-push && bash -n instalar.sh && python3 -m unittest discover -s tests -t .
```

The repo's workflow (handoffs, branches, review) is in [`AGENTS.md`](AGENTS.md) (Spanish). There is no license yet.
