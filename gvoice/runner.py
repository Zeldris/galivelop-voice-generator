"""Watched process for the real engine (F2.2): every ``qwen-tts``/``qwen-codec`` run goes through `run`.

The child runs in its own process group so that a timeout, a cancellation or a memory abort kills it and
everything it spawned. Output goes to temp files, not pipes, so a chatty engine cannot deadlock us."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass

from . import limits
from .engine import Cancelled, EngineError, EngineTimeout

TAIL_BYTES = 64 * 1024
TERM_WAIT_S = 2.0


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    wall_ms: int
    min_free_mb: object  # int, or None where memory cannot be read
    peak_rss_mb: object  # int, or None when never read


def _tail(fh) -> str:
    fh.flush()
    size = fh.seek(0, os.SEEK_END)
    fh.seek(max(0, size - TAIL_BYTES))
    return fh.read().decode("utf-8", errors="replace")


def _rss_mb(pid: int):
    """Peak resident set (``VmHWM``) of `pid` in MB, or ``None`` if unreadable (the process may be gone)."""
    try:
        with open(f"/proc/{pid}/status", encoding="ascii", errors="replace") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _kill_group(proc) -> None:
    """SIGTERM to the process group, SIGKILL after `TERM_WAIT_S`; always reap."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        proc.wait(TERM_WAIT_S)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # also reaches grandchildren that ignored SIGTERM
    except OSError:
        pass
    proc.wait()


def run(argv, *, stdin_text=None, env=None, cwd=None, machine: dict, timeout_s=None,
        should_cancel=lambda: False, meminfo="/proc/meminfo", poll_s=0.25) -> RunResult:
    """Run `argv` watched by time, cancellation and free memory; return a `RunResult`.

    Raises `limits.LimitError` (``limit.memory`` before starting, ``limit.memory_abort`` while running),
    `EngineTimeout`, `Cancelled` or `EngineError` (``engine.binary_missing``). A non-zero return code is
    returned, not raised: the engine decides what to do (for example, fall back to another device)."""
    free = limits.available_memory_mb(meminfo)
    limits.check_memory(free, machine)
    min_free = free
    peak = None
    full_env = None if env is None else {**os.environ, **env}
    start = time.monotonic()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err, env=full_env, cwd=cwd,
                                    start_new_session=True)
        except OSError as exc:
            raise EngineError(f"cannot run {argv[0]}: {exc}", "engine.binary_missing", path=str(argv[0]))
        try:
            try:
                if stdin_text is not None:
                    proc.stdin.write(stdin_text.encode("utf-8"))
                proc.stdin.close()
            except OSError:
                pass  # the child closed stdin early; its exit code tells
            while proc.poll() is None:
                if should_cancel():
                    raise Cancelled()
                if timeout_s is not None and time.monotonic() - start > timeout_s:
                    raise EngineTimeout()
                free = limits.available_memory_mb(meminfo)
                if free is not None and (min_free is None or free < min_free):
                    min_free = free
                if limits.must_abort(free, machine):
                    raise limits.LimitError("limit.memory_abort", free=free, watch=machine.get("watchMemoryMb"))
                rss = _rss_mb(proc.pid)
                if rss is not None and (peak is None or rss > peak):
                    peak = rss
                try:
                    proc.wait(poll_s)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if proc.poll() is None:
                _kill_group(proc)
            else:
                try:  # the leader is gone; sweep leftovers of its group
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        return RunResult(proc.returncode, _tail(out), _tail(err), int((time.monotonic() - start) * 1000),
                         min_free, peak)
