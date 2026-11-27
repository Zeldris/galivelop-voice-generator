"""The machine lock (D8): one generator at a time on the machine.

Adapter over `grun.machine_lock` (R3; the lock, its wait and the holder record are grun's, on
``$GALIVELOP_STATE_HOME/gpu.lock``). Only `hold` is wrapped: a lock that cannot be opened raises gvoice's
`GvoiceError` (grun raises `GrunError`) and the holder record says ``gvoice`` unless the caller names another app.
`WaitCancelled`, `held_fds` (a tuple, as grun returns it), `busy` and `holder` are grun's."""
from __future__ import annotations

import contextlib

from grun import errors as _grun_errors
from grun import machine_lock as _grun

from . import errors

POLL_S = _grun.POLL_S
WaitCancelled = _grun.WaitCancelled
held_fds = _grun.held_fds
busy = _grun.busy
holder = _grun.holder


@contextlib.contextmanager
def hold(should_cancel=None, on_wait=None, poll_s: float = POLL_S, *, app="gvoice", entry=None):
    """Hold the machine lock for the ``with`` block (see `grun.machine_lock.hold`)."""
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(_grun.hold(should_cancel, on_wait, poll_s, app=app, entry=entry))
        except _grun_errors.GrunError as exc:
            raise errors.from_grun(exc) from None
        yield
