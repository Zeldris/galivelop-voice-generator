"""`grun doctor`: who holds the machine lock, what waits in the queue, which entries are orphans, which locks are taken.

`diagnose` is a pure read (D-15): it creates no file or folder, takes no lock (the probes of `machine_lock` and
`fsutil.held` are shared and non-blocking), recovers nothing and never writes ``queue.json``; it reports, it does not
repair. Lock files are never deleted (invariant 5). `diagnose` is public API (``gimg doctor`` calls it) and prints
nothing; `main` is the command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import fsutil, i18n, machine_lock, paths
from .errors import GrunError

STATES = ("queued", "running", "done", "failed", "cancelled")  # as in `queue.STATES`
LOCKS = (("worker.lock", paths.worker_lock_path), ("queue.json.lock", paths.queue_lock_path),
         ("serve.lock", lambda data: Path(data) / "serve.lock"))


def _valid(data) -> bool:
    """The criterion of `Queue._load` for a readable queue (without raising)."""
    return (isinstance(data, dict) and isinstance(data.get("entries"), list)
            and type(data.get("nextId")) is int
            and all(isinstance(e, dict) and e.get("state") in STATES and type(e.get("id")) is int
                    for e in data["entries"]))


def _pos(entry: dict):
    """Run order of a queued entry, as `queue._pos`: its ``position`` (else its id), then its id."""
    pos = entry.get("position")
    return (pos if isinstance(pos, (int, float)) and not isinstance(pos, bool) else entry["id"], entry["id"])


def _exists(path: Path) -> bool:
    """`path.exists()` that is False, not an exception, when the folder cannot be searched (EACCES)."""
    try:
        return path.exists()
    except OSError:
        return False


def _read_queue(path: Path):
    """``(exists, entries or None, error code or None)`` without creating anything."""
    try:
        with open(str(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return False, [], None
    except (OSError, ValueError):
        return True, None, "queue.corrupt"
    if not _valid(data):
        return True, None, "queue.corrupt"
    return True, data["entries"], None


def diagnose(data, *, app: str | None = None) -> dict:
    """The state of the machine lock, the queue of `data`, its orphans and its locks. A pure read (see the module)."""
    data = Path(data)
    problems = []
    busy = machine_lock.busy()
    holder = machine_lock.holder() if busy else None
    machine = {"path": str(paths.machine_lock_path()), "busy": busy, "holder": holder}
    if busy and holder == {}:
        problems.append({"code": "doctor.machine_holder_unknown", "params": {"path": machine["path"]}})

    qpath = paths.queue_path(data)
    exists, entries, error = _read_queue(qpath)
    counts = {}
    for entry in entries or ():
        counts[entry["state"]] = counts.get(entry["state"], 0) + 1
    queue = {"path": str(qpath), "exists": exists, "readable": error is None,
             "paused": _exists(paths.pause_path(data)), "counts": counts,
             "queued": [e["id"] for e in sorted((e for e in entries or () if e["state"] == "queued"), key=_pos)],
             "running": sorted(e["id"] for e in entries or () if e["state"] == "running"), "error": error}
    if error:
        problems.append({"code": "doctor.queue_unreadable", "params": {"path": str(qpath), "error": error}})

    locks = []
    for name, locate in LOCKS:
        path = locate(data)
        locks.append({"name": name, "path": str(path), "held": fsutil.held(path), "exists": _exists(path)})
        if locks[-1]["held"] is None:
            problems.append({"code": "doctor.lock_unknown", "params": {"name": name, "path": str(path)}})

    worker = locks[0]["held"]  # worker.lock; None: not known, so no orphan is declared
    orphans = queue["running"] if worker is False else []
    if orphans:
        problems.append({"code": "doctor.orphans", "params": {"count": len(orphans),
                                                               "ids": ", ".join(str(i) for i in orphans)}})
    return {"app": app, "machine": machine, "queue": queue, "orphans": orphans, "locks": locks, "problems": problems}


def render(report: dict, lang: str | None = None) -> str:
    """The report as readable text in `lang` (default: the environment's)."""
    lang = lang or i18n.default_lang()
    t = lambda key, **params: i18n.t(key, lang, **params)
    lines = [t("doctor.title")]
    machine = report.get("machine")
    if machine:
        if not machine["busy"]:
            lines.append(t("doctor.machine_free", path=machine["path"]))
        elif machine["holder"]:
            h = machine["holder"]
            lines.append(t("doctor.machine_busy", path=machine["path"], app=h.get("app") or "?",
                           entry=h.get("entry") if h.get("entry") is not None else "?",
                           pid=h.get("pid") if h.get("pid") is not None else "?", since=h.get("since") or "?"))
        else:
            lines.append(t("doctor.machine_busy_unknown", path=machine["path"]))
    queue = report.get("queue")
    if queue:
        if not queue["exists"]:
            lines.append(t("doctor.queue_missing", path=queue["path"]))
        elif queue["readable"]:
            counts = ", ".join("%s %d" % (s, queue["counts"][s]) for s in STATES if s in queue["counts"])
            lines.append(t("doctor.queue", path=queue["path"], counts=counts or t("doctor.empty")))
            if queue["queued"]:
                lines.append(t("doctor.queue_order", ids=", ".join(str(i) for i in queue["queued"])))
            if queue["running"]:
                lines.append(t("doctor.queue_running", ids=", ".join(str(i) for i in queue["running"])))
        if queue["paused"]:
            lines.append(t("doctor.queue_paused"))
    for lock in report.get("locks", ()):
        state = "unknown" if lock["held"] is None else "held" if lock["held"] else "free" if lock["exists"] else "absent"
        lines.append(t("doctor.lock_" + state, name=lock["name"], path=lock["path"]))
    problems = report.get("problems", [])
    if problems:
        lines.append(t("doctor.problems"))
        lines += ["- " + t(p["code"], **p["params"]) for p in problems]
    else:
        lines.append(t("doctor.ok"))
    return "\n".join(lines)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("%s: error: %s\n" % (self.prog, message))
        raise SystemExit(2)


def main(argv=None) -> int:
    """``python -m grun doctor --data <dir> [--json] [--lang xx]``. Exit 0 without problems, 1 with problems, 2 on bad
    usage. A `GrunError` becomes a problem, never a traceback."""
    parser = _Parser(prog="grun")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("doctor", help="report the machine lock, the queue, the orphans and the locks")
    cmd.add_argument("--data", required=True, help="the application's data folder")
    cmd.add_argument("--json", action="store_true", help="print the report as JSON")
    cmd.add_argument("--lang", help="language of the text (default: the environment's)")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    lang = i18n.normalise(args.lang) if args.lang else None
    try:
        report = diagnose(Path(args.data))
    except GrunError as exc:
        report = {"problems": [{"code": "doctor.error", "params": {"message": exc.message(lang)}}]}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(render(report, lang))
    return 1 if report["problems"] else 0
