"""The machine lock (D8): one generator at a time on the machine.

Every job holds an exclusive ``flock`` on ``<state>/gpu.lock`` (`paths.machine_lock_path`) while it runs, so an image
and a voice never share the memory of a Steam Deck. Another process holding it makes the job *wait*, never fail: the
wait polls, so a cancel (``should_cancel``) or a signal still ends it. The kernel drops an ``flock`` when its
process dies, so a worker killed in the middle of a job never leaves the machine locked. The file is never deleted
(deleting it would let two holders lock two different files); it is created with the state folder when missing."""
from __future__ import annotations

import contextlib
import fcntl
import os
import time

from . import paths
from .errors import GvoiceError

POLL_S = 0.05


class WaitCancelled(Exception):
    """`should_cancel()` returned true while waiting for the lock."""


@contextlib.contextmanager
def hold(should_cancel=None, on_wait=None, poll_s: float = POLL_S):
    """Hold the machine lock for the ``with`` block. `on_wait` is called once, when the lock turns out to be busy;
    `should_cancel` is asked while waiting (true raises `WaitCancelled` and takes nothing)."""
    path = paths.machine_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise GvoiceError("machine_lock.unavailable", path=str(path), reason=exc.strerror or str(exc))
    try:
        waited = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not waited:
                    waited = True
                    if on_wait is not None:
                        on_wait()
                if should_cancel is not None and should_cancel():
                    raise WaitCancelled()
                time.sleep(poll_s)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def busy() -> bool:
    """Does another process (or another open descriptor) hold the lock right now? A pure read that creates nothing."""
    try:
        fd = os.open(str(paths.machine_lock_path()), os.O_RDWR)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(fd)
