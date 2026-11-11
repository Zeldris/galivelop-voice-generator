"""`gvoice bench` (F2.5): repeat the measures of the Deck bench with the configured engine.

Per device (the profile's ``device`` and, if there is one and it is installed, ``fallbackDevice``): one design take
with ``models.design``; then, for each model of ``models.produce``, the voice print of that take and a short and a
long line. Every job is forced onto its device (``job.device``) and gets a machine profile without
``fallbackDevice``, so the engine never falls back by itself and mixes the results of two devices. A failed job puts
its error in its row and the bench goes on. The caller holds the machine lock (D8) around `run`.

`EngineResult` carries no RSS peak, so ``peak_rss_mb`` is always ``None`` (a hole, not a guess)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from . import engine as engine_mod, install
from .engine import DesignJob, EngineError, LineJob, PrintJob

DESIGN_INSTRUCTION = ("A calm adult male narrator with a warm, deep voice, clear Spanish diction and a measured "
                      "pace, as in an audiobook.")
DESIGN_TEXT = ("En la hondonada, al caer la tarde, los obeliscos de piedra proyectaban sombras tan largas que "
               "el viajero tardó un buen rato en cruzarlas, y cuando por fin alcanzó el otro lado, el viento había "
               "cesado y el silencio lo cubría todo.")
SHORT_TEXT = "Nadie baja a la hondonada de noche."
LONG_TEXT = ("Los obeliscos se alzaban sobre la llanura como dedos de piedra, y quien los miraba demasiado tiempo "
             "juraba que cambiaban de sitio cuando se apartaba la vista, de modo que los pastores aprendieron a "
             "cruzar la llanura de espaldas a ellos.")
LANGUAGE = "Spanish"
FIELDS = ("task", "model", "device", "duration_ms", "audio_ms", "rtf", "min_free_mb", "peak_rss_mb", "error")


def devices_for(provider: str, machine: dict, quick: bool) -> list:
    """The profile's device, plus its fallback if it exists and (for the real engine) is installed."""
    cfg = machine.get("engine") or {}
    found = [cfg.get("device") or "cpu"]
    fallback = cfg.get("fallbackDevice")
    if fallback and not quick and fallback.lower() != found[0].lower():
        if provider != "qwentts" or fallback.lower() in {
                str(d).lower() for d in (install.read_install() or {}).get("devices", [])}:
            found.append(fallback)
    return found


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in ".-" else "-" for c in text.lower())


def _row(task, model, device, result=None, error=None) -> dict:
    audio = getattr(result, "audio_ms", None)
    duration = getattr(result, "duration_ms", None)
    return {"task": task, "model": model, "device": device, "duration_ms": duration, "audio_ms": audio,
            "rtf": round(duration / audio, 3) if duration is not None and audio else None,
            "min_free_mb": getattr(result, "min_free_mb", None), "peak_rss_mb": None, "error": error}


def _attempt(rows, task, model, device, call):
    """Run `call`; append its row; return the result or None. Ctrl-C and cancels are not caught."""
    try:
        result = call()
    except EngineError as exc:
        rows.append(_row(task, model, device, error=exc.message))
        return None
    except engine_mod.Cancelled:
        raise KeyboardInterrupt
    rows.append(_row(task, model, device, result=result))
    return result


def run(eng, machine: dict, out_dir, seed: int = 11, quick: bool = False,
        should_cancel: Callable[[], bool] = lambda: False) -> list:
    """Run the bench into `out_dir` (created); returns the rows."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    models = machine.get("models") or {}
    design_model = models.get("design") or "1.7b-voicedesign"
    produce = list(models.get("produce") or ["0.6b-base"])
    if quick:
        produce = produce[:1]
    config = {k: v for k, v in (machine.get("engine") or {}).items() if k != "fallbackDevice"}
    timeout = machine.get("timeoutS")
    rows, first_take = [], None
    for device in devices_for(eng.provider, machine, quick):
        job_machine = dict(machine, engine=dict(config, device=device))
        tag = _slug(device)
        take = out / ("design-%s-%s.wav" % (_slug(design_model), tag))
        made = _attempt(rows, "design", design_model, device, lambda: eng.design(DesignJob(
            instruction=DESIGN_INSTRUCTION, text=DESIGN_TEXT, seed=seed, output=str(take), model=design_model,
            device=device, machine=job_machine, timeout_s=timeout, language=LANGUAGE), should_cancel))
        if made is not None and first_take is None:
            first_take = take
        reference = take if made is not None else first_take
        for model in produce:
            stem = out / ("%s-%s" % (_slug(model), tag))
            spk, rvq = Path(str(stem) + ".spk"), Path(str(stem) + ".rvq")
            if reference is None:
                rows.append(_row("print", model, device, error="no design take to fix"))
                printed = None
            else:
                printed = _attempt(rows, "print", model, device, lambda: eng.voiceprint(PrintJob(
                    reference=str(reference), text=DESIGN_TEXT, model=model, spk=str(spk), rvq=str(rvq),
                    device=device, machine=job_machine, timeout_s=timeout), should_cancel))
            for task, text in (("line-short", SHORT_TEXT), ("line-long", LONG_TEXT)):
                if printed is None:
                    rows.append(_row(task, model, device, error="no voice print"))
                    continue
                wav = Path(str(stem) + "-" + task + ".wav")
                _attempt(rows, task, model, device, lambda: eng.line(LineJob(
                    spk=str(spk), rvq=str(rvq), text=text, seed=seed, output=str(wav), model=model, device=device,
                    machine=job_machine, timeout_s=timeout, language=LANGUAGE, ref_text=DESIGN_TEXT),
                    should_cancel))
    return rows


def _cell(value) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(rows: list, title: str = "") -> str:
    lines = (["# " + title, ""] if title else [])
    lines.append("| " + " | ".join(FIELDS) + " |")
    lines.append("|" + "---|" * len(FIELDS))
    for row in rows:
        lines.append("| " + " | ".join(_cell(row[f]) for f in FIELDS) + " |")
    return "\n".join(lines) + "\n"


def write(out_dir, rows: list, info: dict) -> None:
    """``bench.json`` (`info` + ``rows``) and ``bench.md``, each written whole through a temp file."""
    out = Path(out_dir)
    for name, text in (("bench.json", json.dumps(dict(info, rows=rows), ensure_ascii=False, indent=2) + "\n"),
                       ("bench.md", markdown(rows, out.name))):
        fd, tmp = tempfile.mkstemp(dir=str(out), prefix="." + name + ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, out / name)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
