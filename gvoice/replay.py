"""``gvoice take replay`` (0.4.2): regenerate a take with exactly what it stored and compare the audio's sha256.

The job is built with `worker.build_job` from the take's own record (seed, text, instruction or voice and reference,
sampling, locale, model, and the device it ran on with ``no_fallback``), run with the same engine under the machine
lock the worker uses, written to a temporary folder next to the take (always removed) and hashed. The expected hash is
the take's ``sha256``, or, for an older take without one, the hash of its stored audio. The take keeps the last
``replay``: ``{at, device, sha256, same}``. A sample take cannot be replayed (``take.replay_sample``)."""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone

from . import checks, limits, machine_lock, orders, queue, sampling, worker
from . import engine as engine_mod
from .errors import GvoiceError


REPLAY_PREFIX = ".replay-"


def _params(project: str, order: dict, take: dict) -> dict:
    p = {"kind": order["type"], "seed": take["seed"], "text": take["text"],
         "sampling": take.get("sampling") or sampling.defaults()}
    if order["type"] == "voice":
        p.update(instruction=take["instruction"], locale=take.get("locale"))
    else:
        p.update(voice=take["voice"], reference=take["reference"])
    return p


def replay(project: str, key: str, take_id: int, engine=None, lang=None) -> dict:
    """Replay take `take_id` of order `key`; returns ``{at, device, sha256, same, expected}`` (what is stored on the
    take is the same without ``expected``). Raises ``take.replay_sample`` for a sample take and
    ``take.replay_no_audio`` when there is nothing to compare with. It writes no line in the D16 log on purpose: a
    replay is a check of a take, not the generation of an order."""
    order = orders.get(project, key)
    take = next((a for a in order["attempts"] if a["id"] == take_id), None)
    if take is None:
        raise GvoiceError("order.attempt_unknown", attempt=take_id, order=key)
    if take.get("source") == "sample":
        raise GvoiceError("take.replay_sample", take=take_id, order=key)
    expected = take.get("sha256")
    if expected is None:
        audio = orders.attempt_audio(project, key, take)
        if not audio.is_file():
            raise GvoiceError("take.replay_no_audio", take=take_id, order=key)
        expected = checks.sha256_of(audio)
    eng = engine or engine_mod.get_engine()
    folder = tempfile.mkdtemp(prefix=REPLAY_PREFIX, dir=str(orders.attempt_dir(project, key, take)))
    try:
        with machine_lock.hold():
            machine = limits.load_machine()
            worker._wait_for_memory({"id": "replay"}, eng, machine, lambda: False, lang)
            model = take.get("model") or (queue.production_model(project, machine) if order["type"] == "line" else None)
            if model is not None:
                limits.check_model("design" if order["type"] == "voice" else "produce", model, machine)
            output = folder + "/replay.wav"
            job, _extra = worker.build_job(project, _params(project, order, take), output, machine, model,
                                           device=take.get("device"), no_fallback=True)
            result = worker.run_job(eng, job, lambda: False)
        found = checks.sha256_of(output)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    stored = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "device": result.device,
              "sha256": found, "same": found == expected}
    orders.set_replay(project, key, take_id, stored)
    return dict(stored, expected=expected)
