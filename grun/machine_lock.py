"""The machine lock: one generator at a time on the machine, with a holder record.

Extracted from gvoice@8a17618, gvoice/machine_lock.py (GrunError, and the holder record is new).

Every job holds an exclusive ``flock`` on ``<state>/gpu.lock`` (`paths.machine_lock_path`) while it runs, so an image
and a voice never share the memory of a Steam Deck. Another process holding it makes the job *wait*, never fail: the
wait polls, so a cancel (``should_cancel``) or a signal still ends it. The kernel drops an ``flock`` when its process
dies, so a worker killed in the middle of a job never leaves the machine locked. A child that inherits the descriptor
(`held_fds`) keeps the lock after its parent dies. The file is never deleted nor replaced (that would let two holders
lock two different files); it is created with the state folder when missing.

While held, the file contains the holder record (``grun.lock/0``), written in place through the locked descriptor
(never an atomic replace: it would change the inode and break the lock). It is informative only: the lock is the
``flock``, and a holder that writes nothing (e.g. ``flock(1)``) is still a holder."""
from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import os
import time

from . import paths
from .errors import GrunError

POLL_S = 0.05
SCHEMA = "grun.lock/0"
_held = []  # descriptors of the locks this process holds right now (see `held_fds`)


class WaitCancelled(Exception):
    """`should_cancel()` returned true while waiting for the lock."""


def _write_holder(fd: int, app, entry) -> None:
    """Write the holder record into the locked descriptor, in place. Best effort: the lock does not depend on it."""
    record = {"schema": SCHEMA, "app": app, "pid": os.getpid(), "entry": entry,
              "since": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(record).encode("utf-8"))
    except OSError:
        pass


@contextlib.contextmanager
def hold(should_cancel=None, on_wait=None, poll_s: float = POLL_S, *, app=None, entry=None):
    """Hold the machine lock for the ``with`` block. `on_wait` is called once, when the lock turns out to be busy;
    `should_cancel` is asked while waiting (true raises `WaitCancelled` and takes nothing). `app` and `entry` go into
    the holder record."""
    path = paths.machine_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise GrunError("machine_lock.unavailable", path=str(path), reason=exc.strerror or str(exc))
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
        _held.append(fd)
        _write_holder(fd, app, entry)
        yield
    finally:
        if fd in _held:
            _held.remove(fd)
            try:
                os.ftruncate(fd, 0)  # still locked here: clear the record before letting go
            except OSError:
                pass
        os.close(fd)  # closing releases the lock


def held_fds() -> tuple:
    """The descriptors of the lock held now. The engine process gets them through ``pass_fds``: the ``flock``
    belongs to the open file, so it stays taken while that process lives even if this one is killed (an orphaned
    engine keeps the machine busy and the next job waits instead of running at the same time)."""
    return tuple(_held)


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


def holder():
    """``None`` if nobody holds the lock; else the holder record (a dict), or ``{}`` when the file is empty or does not
    hold a JSON object (the holder wrote nothing, or something else). Creates nothing."""
    if not busy():
        return None
    try:
        with open(str(paths.machine_lock_path()), "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
