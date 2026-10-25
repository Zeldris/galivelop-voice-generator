"""opt-ai JSONL log of every engine operation, and the duration estimate (D16).

Copiado de gimg@0d02f51 (D7); cambia: GVOICE_*, `speech_generation` con `app.task` = design|speak|print, campos
`app.audio.*` (con `rtf`) en vez de `app.image.*`, y el estimado agrupa por motor, tarea, modelo y dispositivo."""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone

from . import fsutil, paths

TASKS = ("design", "speak", "print")


def log_path(project: str):
    return paths.project_data_dir(project, "log.bad_project") / "log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_for(task: str, key: str, machine: dict, provider: str, model: str, seed=None, text_chars=None,
               device: str | None = None, result=None, error: str | None = None, ts: str | None = None) -> dict:
    """The log line of one operation: from an `EngineResult` (`result`) or an error message.
    `device` is the job's; the result's wins. Absent values are omitted, never ``null``."""
    duration = getattr(result, "duration_ms", None)
    audio = getattr(result, "audio_ms", None)
    rtf = round(duration / audio, 3) if duration is not None and audio else None
    line = {
        "ts": ts or _now(),
        "gen_ai.operation.name": "speech_generation",
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": model,
        "app.task": task,
        "app.machine_profile": machine.get("name"),
        "app.duration_ms": duration,
        "app.load_ms": getattr(result, "load_ms", None),
        "app.error": error,
        "app.audio.key": key,
        "app.audio.seed": seed,
        "app.audio.device": getattr(result, "device", None) or device,
        "app.audio.text_chars": text_chars,
        "app.audio.audio_ms": audio,
        "app.audio.engine_version": getattr(result, "engine_version", None),
        "app.audio.rtf": rtf,
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
        fh = open(path, "rb")
    except FileNotFoundError:
        return
    with fh:
        for raw in fh:
            try:
                line = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if isinstance(line, dict):
                yield line


def estimate(project: str, provider: str, task: str, model: str, device: str):
    """Median ``app.duration_ms`` (ms, finite and not negative) of the non-error lines with the same provider, task, model and
    device; ``None`` without data."""
    values = []
    for line in _lines(log_path(project)):
        duration = line.get("app.duration_ms")
        if ("app.error" in line or line.get("gen_ai.provider.name") != provider
                or line.get("app.task") != task or line.get("gen_ai.request.model") != model
                or line.get("app.audio.device") != device
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or not math.isfinite(duration) or duration < 0):
            continue
        values.append(duration)
    return statistics.median(values) if values else None
