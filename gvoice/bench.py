"""`gvoice bench` (F2.5, D18): the measuring matrix of ``docs/investigacion/2026-10-25-banco-deck.md`` with any engine.

For every device asked: *design* (the design model of the profile, a fixed seed, the short and the long phrase),
*print* (one voice print per Base model, from the long design take) and *produce* (every Base model x short and long
phrase, with its print). Every step is one engine call timed with the wall clock (model load included, as in the
doc) and gives one row: step, seed, model, device, phrase, wall, audio, RTF (wall / audio), peak RSS, lowest
``MemAvailable``, status. The whole bench holds the machine lock (D8) and, with an engine that watches memory
(`Engine.watches_memory`), waits before each step for ``minFreeMemoryMb`` like the worker does; each job is
run with ``no_fallback`` so a row is always the device it says.

A step that fails stays in the table with its code and the bench goes on; a step whose input is missing (its design
take or print failed or was not asked for) is ``skipped``. Ctrl-C (SIGINT) cancels the running step, which stays
``cancelled``, and still writes the files. Files in ``out``: the ``.wav`` and ``.spk``/``.rvq`` of the steps,
``bench.json`` (rows, rewritten after every step) and ``bench.md`` (header and table, numbers with a decimal comma)."""
from __future__ import annotations

import contextlib
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from . import engine as engine_mod
from grun import fsutil

from . import i18n, limits, machine_lock, paths
from .errors import GvoiceError

STEPS = ("design", "print", "produce")
DEFAULT_SEED = 7
MEMORY_POLL_S = 0.5
LANGUAGE = "Spanish"
INSTRUCTION = ("A calm adult male narrator with a warm, low voice, speaking Spanish at a steady, unhurried pace.")
# the phrases of the doc were not kept as text: a ~3 s one and a ~12 s one
PHRASES = {
    "short": "Amanece en la Hondonada y no se oye nada.",
    "long": ("Al fondo del valle, los obeliscos de piedra negra se alzaban entre la niebla, y los viajeros que se "
             "acercaban, cansados del camino, bajaban la voz sin saber por qué."),
}
OK, FAILED, SKIPPED, CANCELLED = "ok", "failed", "skipped", "cancelled"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", text).strip("_") or "x"


def split_list(value, default):
    """``a,b`` -> ``["a", "b"]`` (blanks and repeats dropped); no value -> `default`."""
    if value is None:
        return list(default)
    found = []
    for item in value.split(","):
        item = item.strip()
        if item and item not in found:
            found.append(item)
    return found


def plan(out: Path, steps, devices, models, design_model, seed) -> list:
    """The ordered list of steps (dicts) of the matrix; pure, nothing is run. ``needs`` lists the files a step reads."""
    specs = []
    for device in devices:
        tag = _slug(device)
        take = out / ("design-%s-s%d-long.wav" % (tag, seed))
        if "design" in steps:
            for phrase in ("short", "long"):
                specs.append({"step": "design", "model": design_model, "device": device, "phrase": phrase,
                              "seed": seed, "needs": [], "files": [out / ("design-%s-s%d-%s.wav" % (tag, seed, phrase))]})
        prints = {}
        for model in models:
            prints[model] = (out / ("print-%s-%s.spk" % (tag, _slug(model))), out / ("print-%s-%s.rvq" % (tag, _slug(model))))
        if "print" in steps:
            for model in models:
                specs.append({"step": "print", "model": model, "device": device, "phrase": "take", "seed": None,
                              "needs": [take], "files": list(prints[model])})
        if "produce" in steps:
            for model in models:
                for phrase in ("short", "long"):
                    specs.append({"step": "produce", "model": model, "device": device, "phrase": phrase,
                                  "seed": seed, "needs": list(prints[model]),
                                  "files": [out / ("produce-%s-%s-s%d-%s.wav" % (tag, _slug(model), seed, phrase))]})
    return specs


class _Interrupt:
    """SIGINT sets a flag (the running engine call sees it through ``should_cancel``) instead of raising."""

    def __init__(self):
        self.flag = False
        self._old = None

    def __call__(self, signum=None, frame=None):
        self.flag = True

    def __enter__(self):
        try:
            self._old = signal.signal(signal.SIGINT, self)
        except ValueError:  # not the main thread: KeyboardInterrupt keeps working as usual
            self._old = None
        return self

    def __exit__(self, *exc):
        if self._old is not None:
            signal.signal(signal.SIGINT, self._old)


def _wait_for_memory(eng, machine, should_cancel, lang) -> None:
    if not getattr(eng, "watches_memory", False):
        return
    said = False
    while True:
        free = limits.available_memory_mb()
        try:
            limits.check_memory(free, machine)
            return
        except limits.LimitError as exc:
            if not said:
                said = True
                print(i18n.t("bench.waiting_memory", lang, free=exc.params["free"], min=exc.params["min"]),
                      file=sys.stderr)
        if should_cancel():
            raise engine_mod.Cancelled()
        time.sleep(MEMORY_POLL_S)


def _row(spec) -> dict:
    return {"step": spec["step"], "seed": spec["seed"], "model": spec["model"], "device": spec["device"],
            "phrase": spec["phrase"], "wall_s": None, "audio_s": None, "rtf": None, "peak_rss_mb": None,
            "min_free_mb": None, "status": OK, "code": None, "message": None,
            "files": [p.name for p in spec["files"]]}


def _job(spec, machine):
    """The engine method name and the job of a step; its inputs are ``spec["needs"]``, its outputs ``spec["files"]``."""
    common = dict(device=spec["device"], machine=machine, timeout_s=limits.timeout_s(machine), language=LANGUAGE,
                  no_fallback=True)
    files, needs = spec["files"], spec["needs"]
    if spec["step"] == "design":
        return "design", engine_mod.DesignJob(instruction=INSTRUCTION, text=PHRASES[spec["phrase"]],
                                              seed=spec["seed"], output=str(files[0]), model=spec["model"], **common)
    if spec["step"] == "print":
        return "voiceprint", engine_mod.PrintJob(reference=str(needs[0]), text=PHRASES["long"], model=spec["model"],
                                                 spk=str(files[0]), rvq=str(files[1]), **common)
    return "line", engine_mod.LineJob(spk=str(needs[0]), rvq=str(needs[1]), text=PHRASES[spec["phrase"]],
                                      seed=spec["seed"], output=str(files[0]), model=spec["model"],
                                      reference_text=PHRASES["long"], **common)


def _read_first(path, prefix):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(prefix):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def machine_info(machine: dict) -> dict:
    """What can be read without root: profile name, CPU model and total memory (``None`` when unreadable)."""
    return {"profile": machine.get("name"), "cpu": _read_first("/proc/cpuinfo", "model name"),
            "memory_mb": limits.total_memory_mb()}


def run(eng, machine: dict, models, devices, steps, seed, out: Path, lang=None) -> dict:
    """Run the matrix with `eng` and write the files in `out`. Returns the document of ``bench.json``:
    ``{date, engine, engineCommit, engineVersion, machine, out, seed, rows, ok, cancelled}``."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    design_model = (machine.get("models") or {}).get("design")
    specs = plan(out, steps, devices, models, design_model, seed)
    doc = {"date": datetime.now().astimezone().isoformat(timespec="seconds"), "engine": eng.provider,
           "engineCommit": None, "engineVersion": None, "machine": machine_info(machine), "out": str(out),
           "seed": seed, "steps": list(steps), "devices": list(devices), "models": list(models), "rows": [],
           "ok": True, "cancelled": False}
    interrupt = _Interrupt()
    should_cancel = lambda: interrupt.flag

    def save():
        doc["ok"] = bool(doc["rows"]) and all(r["status"] == OK for r in doc["rows"])
        fsutil.write_json(out / "bench.json", doc)

    with interrupt:
        try:
            with machine_lock.hold(should_cancel, on_wait=lambda: print(i18n.t("bench.waiting_lock", lang),
                                                                         file=sys.stderr)):
                for number, spec in enumerate(specs, 1):
                    if interrupt.flag:
                        raise engine_mod.Cancelled()
                    row = _row(spec)
                    doc["rows"].append(row)
                    print(i18n.t("bench.progress", lang, n=number, total=len(specs), step=spec["step"],
                                 model=spec["model"], device=spec["device"], phrase=spec["phrase"]),
                          file=sys.stderr)
                    for path in spec["files"]:  # a file of an earlier run must not pass for this one
                        with contextlib.suppress(OSError):
                            path.unlink()
                    missing = [p.name for p in spec["needs"] if not p.is_file()]
                    if missing:
                        row.update(status=SKIPPED, code="bench.missing_input",
                                   message=i18n.t("bench.missing_input", "en", files=", ".join(missing)))
                        save()
                        continue
                    try:
                        _wait_for_memory(eng, machine, should_cancel, lang)
                        method, job = _job(spec, machine)
                        started = time.monotonic()
                        try:
                            result = getattr(eng, method)(job, should_cancel)
                        finally:  # failed and cancelled rows keep their time too
                            wall = time.monotonic() - started
                            row["wall_s"] = wall
                        if result.audio_ms is not None and spec["step"] != "print":
                            row["audio_s"] = result.audio_ms / 1000
                            if row["audio_s"] > 0:
                                row["rtf"] = wall / row["audio_s"]
                        row.update(peak_rss_mb=result.peak_rss_mb, min_free_mb=result.min_free_mb)
                        if result.device:
                            row["device"] = result.device
                        doc["engineCommit"] = doc["engineCommit"] or result.engine_commit
                        doc["engineVersion"] = doc["engineVersion"] or result.engine_version
                    except engine_mod.Cancelled as exc:
                        row.update(status=CANCELLED)
                        stats = exc.stats or {}
                        row.update(peak_rss_mb=stats.get("peak_rss_mb"), min_free_mb=stats.get("min_free_mb"))
                        doc["cancelled"] = True
                        save()
                        break
                    except engine_mod.EngineError as exc:
                        stats = exc.stats or {}
                        row.update(status=FAILED, code=exc.code or "engine.failed", message=exc.message,
                                   peak_rss_mb=stats.get("peak_rss_mb"), min_free_mb=stats.get("min_free_mb"))
                    except GvoiceError as exc:
                        row.update(status=FAILED, code=exc.code, message=exc.message("en"))
                    save()
        except (machine_lock.WaitCancelled, engine_mod.Cancelled):
            doc["cancelled"] = True
    save()
    (out / "bench.md").write_text(render(doc, lang) + "\n", encoding="utf-8")
    return doc


# -- the table -----------------------------------------------------------------------------------------------------


def num(value, decimals: int = 0) -> str:
    """A number with a decimal comma as in the doc; ``-`` when there is none."""
    if value is None:
        return "-"
    return ("%.*f" % (decimals, value)).replace(".", ",")


def _status(row, lang) -> str:
    if row["status"] == OK:
        return i18n.t("bench.status.ok", lang)
    return i18n.t("bench.status." + row["status"], lang, code=row["code"] or "")


def _step_label(row, lang) -> str:
    label = i18n.t("bench.step." + row["step"], lang)
    return "%s s%d" % (label, row["seed"]) if row["seed"] is not None and row["step"] != "print" else label


def render(doc: dict, lang=None) -> str:
    """The ``bench.md`` text: a header and the table of the rows."""
    machine = doc["machine"]
    cell = lambda value: "-" if value in (None, "") else value
    lines = ["# " + i18n.t("bench.title", lang), "",
             "- %s" % i18n.t("bench.head.date", lang, value=doc["date"]),
             "- %s" % i18n.t("bench.head.engine", lang, value="%s %s" % (doc["engine"], cell(doc["engineVersion"]))),
             "- %s" % i18n.t("bench.head.commit", lang, value=cell(doc["engineCommit"])),
             "- %s" % i18n.t("bench.head.machine", lang, profile=cell(machine["profile"]), cpu=cell(machine["cpu"]),
                             memory=num(machine["memory_mb"])),
             "- %s" % i18n.t("bench.head.seed", lang, value=doc["seed"]), "",
             "| " + " | ".join(i18n.t("bench.col." + c, lang) for c in (
                 "step", "model", "device", "phrase", "wall", "audio", "rtf", "rss", "free", "status")) + " |",
             "|" + "---|" * 10]
    for row in doc["rows"]:
        lines.append("| " + " | ".join([
            _step_label(row, lang), row["model"] or "-", row["device"], i18n.t("bench.phrase." + row["phrase"], lang),
            num(row["wall_s"], 1), num(row["audio_s"], 2), num(row["rtf"], 2), num(row["peak_rss_mb"]),
            num(row["min_free_mb"]), _status(row, lang)]) + " |")
    return "\n".join(lines)


def default_out() -> Path:
    return paths.data_dir() / "bench" / datetime.now().strftime("%Y-%m-%d-%H%M%S")
