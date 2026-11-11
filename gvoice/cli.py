"""Command line front end (`python3 -m gvoice`): a thin layer over the core modules.

Copiado de gimg@fa1076e (D7); adaptado a gvoice (D9, D10): sin perfiles, composición, medición ni servicio (F4-F5);
los pedidos son ``voice`` o ``line`` y se identifican por proyecto + clave.

Exit codes: 0 ok, 1 a `GvoiceError` or an unexpected error (the message goes to stderr), 2 usage error, 130
interrupted. ``--json`` prints the data instead of text; ``--lang`` picks the language of the messages."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from . import __version__, i18n, orders, projects, queue, sheet, worker
from .errors import GvoiceError

LANGS = ("es", "en")


def _prescan_lang(argv) -> str:
    probe = argparse.ArgumentParser(add_help=False)
    probe.add_argument("--lang", choices=LANGS)
    found, _rest = probe.parse_known_args(argv)
    return found.lang or i18n.default_lang()


def _build(lang: str) -> argparse.ArgumentParser:
    def t(key, **params):
        return i18n.t(key, lang, **params)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=t("cli.help.lang"))
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=t("cli.help.json"))

    parser = argparse.ArgumentParser(prog="gvoice", description=t("cli.description"), parents=[common])
    top = parser.add_subparsers(dest="cmd", metavar="<command>", required=True)

    def leaf(group, name, help_key, *args):
        p = group.add_parser(name, help=t(help_key), description=t(help_key), parents=[common])
        for flags, kwargs in args:
            kwargs = dict(kwargs)
            if "help" in kwargs:
                kwargs["help"] = t(kwargs["help"])
            p.add_argument(*flags, **kwargs)
        return p

    def group(parent, name, help_key):
        p = parent.add_parser(name, help=t(help_key), description=t(help_key), parents=[common])
        return p.add_subparsers(dest="sub", metavar="<command>", required=True)

    def arg(name, help_key, **kw):
        return ((name,), dict(help=help_key, **kw))

    def opt(name, help_key, **kw):
        return ((name,), dict(help=help_key, **kw))

    project = arg("project", "cli.arg.project")
    okey = arg("key", "cli.arg.key")
    attempt = arg("attempt", "cli.arg.attempt", type=int)

    g = group(top, "project", "cli.cmd.project")
    leaf(g, "add", "cli.cmd.project_add", arg("path", "cli.arg.path"))
    leaf(g, "remove", "cli.cmd.project_remove", project)
    leaf(g, "list", "cli.cmd.project_list")

    g = group(top, "order", "cli.cmd.order")
    leaf(g, "submit", "cli.cmd.order_submit", project, arg("file", "cli.arg.file"),
         opt("--count", "cli.arg.count", type=int, default=1))
    lst = leaf(g, "list", "cli.cmd.order_list", project, opt("--type", "cli.arg.type", choices=orders.TYPES))
    mutex = lst.add_mutually_exclusive_group()
    mutex.add_argument("--chosen", action="store_true", help=t("cli.arg.chosen"))
    mutex.add_argument("--unchosen", action="store_true", help=t("cli.arg.unchosen"))
    leaf(g, "show", "cli.cmd.order_show", project, okey)

    g = group(top, "attempt", "cli.cmd.attempt")
    leaf(g, "new", "cli.cmd.attempt_new", project, okey,
         opt("--seed", "cli.arg.seed", type=int), opt("--count", "cli.arg.count", type=int, default=1))
    leaf(g, "mark", "cli.cmd.attempt_mark", project, okey, attempt,
         arg("state", "cli.arg.state", choices=orders.STATES))
    leaf(g, "note", "cli.cmd.attempt_note", project, okey, attempt, arg("text", "cli.arg.text"))

    leaf(top, "choose", "cli.cmd.choose", project, okey, attempt)
    leaf(top, "undo", "cli.cmd.undo", project, okey)

    g = group(top, "queue", "cli.cmd.queue")
    leaf(g, "list", "cli.cmd.queue_list", opt("--state", "cli.arg.queue_state", choices=queue.STATES))
    leaf(g, "cancel", "cli.cmd.queue_cancel", arg("entry", "cli.arg.entry", type=int))

    leaf(top, "work", "cli.cmd.work", opt("--once", "cli.arg.once", action="store_true"))
    leaf(top, "version", "cli.cmd.version")
    return parser


class _Out:
    def __init__(self, lang: str, as_json: bool):
        self.lang, self.as_json = lang, as_json

    def t(self, key, **params):
        return i18n.t(key, self.lang, **params)

    def data(self, value) -> None:
        print(json.dumps(value, ensure_ascii=False, indent=2))

    def line(self, key, **params) -> None:
        print(self.t(key, **params))

    def none(self, value):
        return self.t("cli.out.none") if value is None else value


def _read_order(source: str) -> dict:
    try:
        if source == "-":
            text = sys.stdin.read()
        else:
            with open(source, encoding="utf-8") as fh:
                text = fh.read()
        return json.loads(text)
    except (OSError, ValueError) as exc:  # includes UnicodeDecodeError
        raise GvoiceError("cli.order_unreadable", path=source, reason=str(exc))


def _queued(out: _Out, entries: list, **extra) -> None:
    if out.as_json:
        out.data(dict(extra, entries=[queue.entry_view(e, out.lang) for e in entries]))
    else:
        out.line("cli.out.queued", count=len(entries), ids=", ".join(str(e["id"]) for e in entries) or "-")


def _stale_view(project: str, record: dict) -> dict:
    """The record plus what is stale (D10): ``stale`` for a line, ``staleLines`` for a voice."""
    item = dict(record)
    if record["type"] == "line":
        item["stale"] = orders.is_stale(project, record["key"])
    else:
        item["staleLines"] = orders.stale_lines(project, record["key"])
    return item


def _stale_mark(out: _Out, stale: bool) -> str:
    return out.t("cli.out.stale_mark") if stale else ""


def _order(args, sub, out: _Out) -> None:
    if sub == "submit":
        record, entries = queue.submit_order(args.project, _read_order(args.file), args.count)
        warnings = record.pop("warnings", [])
        texts = [sheet.Warning(w["code"], w["params"]).message(out.lang) for w in warnings]
        if out.as_json:
            _queued(out, entries, order=record, warnings=[dict(w, message=m) for w, m in zip(warnings, texts)])
            return
        for text in texts:
            out.line("cli.out.warning", text=text)
        _queued(out, entries)
    elif sub == "list":
        chosen = True if args.chosen else False if args.unchosen else None
        found = [_stale_view(args.project, r) for r in orders.list_orders(args.project, args.type, chosen)]
        if out.as_json:
            out.data(found)
        elif not found:
            out.line("cli.out.order_none")
        for o in found if not out.as_json else ():
            out.line("cli.out.order_line", order=o["key"], type=o["type"], chosen=out.none(o["chosen"]),
                     attempts=len(o["attempts"]), stale=_stale_mark(out, o.get("stale", False)))
            if o["type"] == "voice" and o["staleLines"]:
                out.line("cli.out.stale_lines", lines=", ".join(o["staleLines"]))
    else:
        o = _stale_view(args.project, orders.get(args.project, args.key))
        if out.as_json:
            out.data(o)
            return
        out.line("cli.out.order_head", order=o["key"], type=o["type"])
        out.line("cli.out.order_seed", seed=out.none(o["seed"]))
        if o["type"] == "voice":
            out.line("cli.out.order_test_text", text=o["testText"])
            out.line("cli.out.order_instruction", text=sheet.instruction(o["designSheet"]))
        else:
            out.line("cli.out.order_voice", voice=o["voice"], reference=out.none(orders.reference(args.project,
                                                                                                  o["voice"])))
            out.line("cli.out.order_text", text=o["text"])
        out.line("cli.out.order_chosen", chosen=out.none(o["chosen"]), stale=_stale_mark(out, o.get("stale", False)))
        if o["type"] == "voice" and o["staleLines"]:
            out.line("cli.out.stale_lines", lines=", ".join(o["staleLines"]))
        if not o["attempts"]:
            out.line("cli.out.attempts_none")
        for a in o["attempts"]:
            out.line("cli.out.attempt_line", id=a["id"], state=a["state"], seed=a["seed"], audio=a["audio"])
            if o["type"] == "line":
                out.line("cli.out.attempt_reference", reference=a["reference"])
            else:
                out.line("cli.out.attempt_prints", models=", ".join(a.get("prints") or {}) or out.t("cli.out.none"))
            if a.get("note"):
                out.line("cli.out.attempt_note", note=a["note"])


def _attempt(args, sub, out: _Out) -> None:
    if sub == "new":
        _queued(out, queue.new_takes(args.project, args.key, args.count, seed=args.seed))
    elif sub == "mark":
        item = orders.mark(args.project, args.key, args.attempt, args.state)
        out.data(item) if out.as_json else out.line("cli.out.marked", id=item["id"], state=item["state"])
    else:
        item = orders.note(args.project, args.key, args.attempt, args.text)
        out.data(item) if out.as_json else out.line("cli.out.noted", id=item["id"])


def _choose_undo(args, out: _Out) -> None:
    if args.cmd == "choose":
        result = queue.choose(args.project, args.key, args.attempt)
    else:
        result = queue.undo(args.project, args.key)
    if out.as_json:
        out.data(dict(result, entries=[queue.entry_view(e, out.lang) for e in result["entries"]]))
        return
    out.line("cli.out.chosen" if args.cmd == "choose" else "cli.out.undone",
             new=out.none(result["new"]), old=out.none(result["old"]))
    if result["entries"]:
        _queued(out, result["entries"])


def _queue(args, sub, out: _Out) -> None:
    if sub == "list":
        entries = queue.list_entries(None if args.state is None else [args.state])
        if out.as_json:
            out.data([queue.entry_view(e, out.lang) for e in entries])
        elif not entries:
            out.line("cli.out.queue_none")
        for e in entries if not out.as_json else ():
            out.line("cli.out.queue_line", id=e["id"], state=e["state"], kind=e["kind"], project=e["project"],
                     order=e["key"], detail=out.t("cli.out.queue_take", take=e["take"]) if e["kind"] == "prints"
                     else out.t("cli.out.queue_seed", seed=e["seed"]))
            text = queue.error_text(e, out.lang)
            if text:
                out.line("cli.out.queue_error", error=text)
    else:
        entry = queue.cancel(args.entry)
        if out.as_json:
            out.data(queue.entry_view(entry, out.lang))
        elif entry["state"] == "running":
            out.line("cli.out.cancel_requested", id=entry["id"])
        else:
            out.line("cli.out.cancelled", id=entry["id"])


def _run(args, out: _Out) -> int:
    cmd, sub = args.cmd, getattr(args, "sub", None)
    if cmd == "version":
        print(__version__)
    elif cmd == "project":
        if sub == "add":
            name = projects.add(args.path)
            out.data({"name": name}) if out.as_json else out.line("cli.out.project_added", name=name)
        elif sub == "remove":
            projects.remove(args.project)
            out.data({"removed": args.project}) if out.as_json else out.line(
                "cli.out.project_removed", name=args.project)
        else:
            found = projects.list_projects()
            if out.as_json:
                out.data([{"name": n, "root": v["root"]} for n, v in found.items()])
            elif not found:
                out.line("cli.out.project_none")
            for n, v in found.items() if not out.as_json else ():
                out.line("cli.out.project_line", name=n, root=v["root"])
    elif cmd == "order":
        _order(args, sub, out)
    elif cmd == "attempt":
        _attempt(args, sub, out)
    elif cmd in ("choose", "undo"):
        _choose_undo(args, out)
    elif cmd == "queue":
        _queue(args, sub, out)
    elif cmd == "work":
        handled = worker.run(once=args.once, lang=out.lang)
        out.data({"processed": handled}) if out.as_json else out.line("cli.out.processed", count=handled)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = _prescan_lang(argv)
    parser = _build(lang)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse: usage errors exit 2, --help exits 0
        return exc.code if isinstance(exc.code, int) else 2
    lang = getattr(args, "lang", None) or lang
    out = _Out(lang, getattr(args, "json", False))
    try:
        return _run(args, out)
    except GvoiceError as exc:
        print(exc.message(lang), file=sys.stderr)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if os.environ.get("GVOICE_DEBUG") == "1":
            traceback.print_exc()
        print(i18n.t("cli.unexpected", lang, message="%s: %s" % (type(exc).__name__, exc)), file=sys.stderr)
    return 1
