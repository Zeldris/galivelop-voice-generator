"""Safety limits from a machine profile (time, memory) and the memory readers.

Adapted from gvoice@8a17618 gvoice/limits.py. The profile arrives as a dict: loading it is the consumer's job
(ProfileLoader, D-12)."""
from __future__ import annotations

import os

from .errors import GrunError


class LimitError(GrunError):
    """A job exceeds a limit of the machine profile."""


def timeout_s(machine: dict) -> int:
    """Time limit of one attempt, in seconds (``timeoutS``)."""
    return machine["timeoutS"]


def check_memory(free_mb, machine: dict) -> None:
    """Raise `LimitError` if `free_mb` is below ``minFreeMemoryMb`` (to start a job). ``None`` (unknown) passes."""
    minimum = machine.get("minFreeMemoryMb")
    if free_mb is not None and minimum is not None and free_mb < minimum:
        raise LimitError("limit.memory", free=free_mb, min=minimum)


def must_abort(free_mb, machine: dict) -> bool:
    """Whether a running job has to be aborted: free memory fell below ``watchMemoryMb``."""
    watch = machine.get("watchMemoryMb")
    return free_mb is not None and watch is not None and free_mb < watch


MEMINFO_ENV = "GRUN_MEMINFO"  # tests: a file with the format of /proc/meminfo
PROC_STATUS_ENV = "GRUN_PROC_STATUS"  # tests: a file in the format of /proc/<pid>/status; ``{pid}`` is replaced


def _meminfo_mb(field: str, meminfo: str | None = None):
    """Field `field` of ``/proc/meminfo`` (kB) in MB, or ``None`` where it cannot be read. `meminfo` defaults to
    ``$GRUN_MEMINFO``, else ``/proc/meminfo``."""
    meminfo = meminfo or os.environ.get(MEMINFO_ENV) or "/proc/meminfo"
    try:
        with open(meminfo, encoding="ascii") as fh:
            for line in fh:
                if line.startswith(field + ":"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def available_memory_mb(meminfo: str | None = None):
    """``MemAvailable`` in MB, or ``None`` where it cannot be read."""
    return _meminfo_mb("MemAvailable", meminfo)


def total_memory_mb(meminfo: str | None = None):
    """``MemTotal`` in MB, or ``None`` where it cannot be read (same source as `available_memory_mb`)."""
    return _meminfo_mb("MemTotal", meminfo)


def peak_rss_mb(pid: int):
    """Peak resident memory (``VmHWM``) of process `pid` in MB, or ``None`` if it cannot be read (it is gone, or
    there is no ``/proc``). The file is ``$GRUN_PROC_STATUS`` (``{pid}`` replaced) when set."""
    template = os.environ.get(PROC_STATUS_ENV) or "/proc/{pid}/status"
    try:
        with open(template.format(pid=pid), encoding="ascii", errors="replace") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None
