"""The engine interface (D-9): what a worker needs from an application's generator.

The application supplies an object with ``run``; ``grun`` never imports an application. An engine may also define
``min_free_memory_mb(job) -> int | None`` (a threshold per model); the worker asks for it when it is there."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from typing import Protocol
except ImportError:  # pragma: no cover - Python 3.7
    Protocol = object


@dataclass
class Job:
    """One entry to run: a copy of the queue entry (with the application's own fields) and the loaded machine
    profile."""
    entry: dict
    machine: dict


class Engine(Protocol):
    def run(self, job: Job, on_progress, should_cancel, pass_fds: tuple):
        """Run the job and return the application's result.

        `on_progress({"step", "steps", "etaS"[, "preview"]})` reports progress; `should_cancel()` says whether to
        stop (raise `Cancelled`); `pass_fds` goes to the engine's ``Popen`` so a child keeps the machine lock."""
        ...


class EngineError(Exception):
    """The engine failed. `code` (optional) names a text ``error.<code>``; `params` fill it."""

    def __init__(self, message, code=None, **params):
        super().__init__(message)
        self.message = message
        self.code = code
        self.params = params


class EngineTimeout(EngineError):
    """The engine ran past the time limit of the machine profile."""


class Cancelled(Exception):
    """The engine stopped because `should_cancel()` became true."""
