# Changelog

[Español](CHANGELOG.es.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `gvoice fx apply` refuses the same file as input and output, writes to a temporary file and replaces the output
  only when ffmpeg succeeds; a local chain file wins over a preset of the same name, and preset names are
  restricted to `[a-z0-9_-]`.
- UI: the shortcut help lists only the shortcuts of the open view (the A/B view no longer lists U/C/D/G).
- Queue bar: an unknown state or kind is shown as is, a failed entry without text shows its code, and each entry
  is an accessible group.

## [0.2.0] - 2026-11-17

### Added

- `locale` in `voice` orders (`es-ES`, `es-419`, `en-US`, `en-GB`); a `line` inherits the locale of its voice
  (example: `examples/order-voice-lectora-es.json`).
- Effect steps `denoise`, `dereverb` (approximated with `agate`), `trimSilence` and `loudnorm` (two passes), compiled
  to ffmpeg, and the `lectura` preset.
- `gvoice fx apply`: applies an effect chain to an audio file (`--json`).
- Versioning as in `gimg`: `releases.py` (`suggest`, `bump`, `notes`, `verify-tag`, `check`) and these CHANGELOG files.

### Fixed

- Review fixes: the locale of takes, `loudnorm` on silence and the WAV sample rate.
- Lines are compared against the locale of their reference take; if the voice's chosen take does not exist, the
  line shows as stale instead of breaking the listings.
- `releases.py check` checks the tag even without `gh`, and the release through GitHub's REST API.

## [0.1.0] - 2026-11-16

### Added

- F0 skeleton: JSON Schemas, user-facing texts in Spanish and English, README.
- F1 core: `voice` and `line` orders, fingerprints, stale detection, queue, machine lock, JSONL log, sheet warnings,
  the `gvoice` CLI and a test engine.
- F2.1-F2.5: model catalog and `gvoice models`, `QwenTtsEngine` on qwentts.cpp, memory watchdog, `instalar.sh` and
  `gvoice bench`.
- F5.1-F5.7: web interface with projects, orders, sheet with warnings, take gallery, A/B comparison and queue bar.
