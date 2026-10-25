"""Machine lock shared by the Galivelop generators (D8): one exclusive `flock` while an engine operation runs.

Nuevo en gvoice (se propone al repo de imágenes). The lock is ``$XDG_STATE_HOME/galivelop/gpu.lock`` (by default
``~/.local/state/galivelop/gpu.lock``). The folder is created with 0700; the folder or the file are refused if
they are symbolic links or belong to another user."""
from __future__ import annotations

import contextlib
import fcntl
import os
import stat
import time
from pathlib import Path
from typing import Callable

from .engine import Cancelled
from .errors import GvoiceError

POLL_S = 0.05


def lock_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if not base or not os.path.isabs(base):  # the XDG spec says to ignore relative values
        base = str(Path.home() / ".local" / "state")
    return Path(base) / "galivelop" / "gpu.lock"


def _check(st, path) -> None:
    if stat.S_ISLNK(st.st_mode):
        raise GvoiceError("machinelock.symlink", path=str(path))
    if st.st_uid != os.geteuid():
        raise GvoiceError("machinelock.foreign", path=str(path))


def _open() -> int:
    path = lock_path()
    folder = path.parent
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(folder, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(folder)
    _check(st, folder)
    if not stat.S_ISDIR(st.st_mode):
        raise GvoiceError("machinelock.not_dir", path=str(folder))
    try:
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        if os.path.islink(path):
            raise GvoiceError("machinelock.symlink", path=str(path))
        raise GvoiceError("machinelock.unusable", path=str(path), reason=str(exc))
    try:
        st = os.fstat(fd)
        _check(st, path)
        if not stat.S_ISREG(st.st_mode):
            raise GvoiceError("machinelock.not_file", path=str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd


@contextlib.contextmanager
def hold(should_cancel: Callable[[], bool] = lambda: False, poll_s: float = POLL_S):
    """Wait until this process has the machine lock, then hold it for the block.

    While waiting it polls without blocking and checks `should_cancel`; if it says so, raises `Cancelled`
    without taking the lock."""
    fd = _open()
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if should_cancel():
                    raise Cancelled()
                time.sleep(poll_s)
        yield
    finally:
        os.close(fd)  # closing releases the lock
