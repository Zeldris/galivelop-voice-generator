"""JSONL log of operations and the duration estimate.

Adapted from gvoice@8a17618 gvoice/log.py: the file is given by the caller and the estimate filters on any
fields; the per-application record layout (``gen_ai.*``, ``app.voice.*``) stays in the application."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from . import fsutil


def now() -> str:
    """UTC timestamp for a log line, ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(path, record: dict) -> None:
    """Append one JSON line to the log file `path` (under the file lock)."""
    text = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with fsutil.lock(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()


def lines(path):
    """Yield the JSON objects of the log file `path`; a missing file is empty and bad lines are skipped."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")  # an invalid byte spoils its line only
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


def estimate(path, duration_key: str = "app.duration_ms", error_key: str = "app.error", **match):
    """Median of `duration_key` over the non-error lines whose fields equal `match` (keyword names cannot hold
    dots: pass a dict with ``**{"gen_ai.request.model": m}``); ``None`` without data."""
    values = []
    for line in lines(path):
        duration = line.get(duration_key)
        if (error_key in line or any(line.get(k) != v for k, v in match.items())
                or not isinstance(duration, (int, float)) or isinstance(duration, bool)):
            continue
        values.append(duration)
    return statistics.median(values) if values else None
