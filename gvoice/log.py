"""opt-ai JSONL log of every engine operation, and the duration estimate (D16).

Copiado de gimg@fa1076e (D7); adaptado a gvoice: the line carries device, seed, engine commit and model (D16)."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from . import fsutil, paths

OP_DESIGN = "voice_design"
OP_LINE = "speech_generation"
OP_PRINT = "voice_print"


def log_path(project: str):
    return paths.project_data_dir(project, "log.bad_project") / "log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick_stat(result, stats: dict, name: str):
    value = getattr(result, name, None)
    return stats.get(name) if value is None else value


def record_for(key: str, task: str, spec: dict, machine: dict, provider: str | None,
               result=None, error: str | None = None, ts: str | None = None, operation: str = OP_LINE,
               stats: dict | None = None) -> dict:
    """The log line of one operation: from an `EngineResult` (`result`) or an error message.
    `spec` may hold ``seed``, ``model``, ``device`` and ``text``; what the result reports wins over the spec.
    `operation` is ``gen_ai.operation.name``. `stats` (``min_free_mb``, ``peak_rss_mb``) are the memory figures of a
    failed run (`EngineError.stats`); a result's own figures win. Absent values are omitted, never ``null``."""
    def pick(name):
        value = getattr(result, name, None)
        return spec.get(name) if value is None else value

    stats = stats or {}
    text = spec.get("text")
    line = {
        "ts": ts or _now(),
        "gen_ai.operation.name": operation,
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": pick("model"),
        "app.task": task,
        "app.machine_profile": machine.get("name"),
        "app.duration_ms": getattr(result, "duration_ms", None),
        "app.load_ms": getattr(result, "load_ms", None),
        "app.error": error,
        "app.voice.key": key,
        "app.voice.seed": pick("seed"),
        "app.voice.device": pick("device"),
        "app.voice.engine_commit": getattr(result, "engine_commit", None),
        "app.voice.engine_version": getattr(result, "engine_version", None),
        "app.voice.text_chars": len(text) if isinstance(text, str) else None,
        "app.voice.audio_ms": getattr(result, "audio_ms", None),
        "app.voice.min_free_mb": pick_stat(result, stats, "min_free_mb"),
        "app.voice.peak_rss_mb": pick_stat(result, stats, "peak_rss_mb"),
        "app.voice.backend": getattr(result, "backend", None),
        "app.voice.command": getattr(result, "command", None),
    }
    return {k: v for k, v in line.items() if v is not None}


def append(project: str, record: dict) -> None:
    """Append one JSON line to the project's log."""
    path = log_path(project)
    text = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with fsutil.lock(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()


def _lines(path):
    try:
        fh = open(path, encoding="utf-8")
    except FileNotFoundError:
        return
    with fh:
        for raw in fh:
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if isinstance(line, dict):
                yield line


def estimate(project: str, provider: str, operation: str, model: str, device: str):
    """Median ``app.duration_ms`` (ms) of the non-error lines with the same provider, operation, model and device
    (the same model is slower on the CPU than on Vulkan: D14); ``None`` without data."""
    values = []
    for line in _lines(log_path(project)):
        duration = line.get("app.duration_ms")
        if ("app.error" in line or line.get("gen_ai.provider.name") != provider
                or line.get("gen_ai.operation.name") != operation
                or line.get("gen_ai.request.model") != model
                or line.get("app.voice.device") != device
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)):
            continue
        values.append(duration)
    return statistics.median(values) if values else None
