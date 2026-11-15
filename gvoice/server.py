"""Local web server of the interface (F5.1): the static files of ``gvoice/ui`` and nothing else yet.

Copiado de gimg@46248251 (D7) (`gimg/server.py`: `_static`, CSP, no-cache, `Host` check); adaptado a gvoice. The API
(F4) is not here: every route of `api_contract.ROUTES` answers 501 ``api.not_implemented``, except
``GET /api/locales/{lang}``, which the interface needs for its texts. Anything else under ``/api`` is 404.

Run it with ``python3 -m gvoice ui`` (or ``python3 -m gvoice.server``) and open http://127.0.0.1:8765/ (add ``?mock=1`` to
use the in-browser simulator instead of the API). It listens on 127.0.0.1 by default and refuses requests whose
``Host`` is not the one it listens on (DNS rebinding)."""
from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import api_contract, i18n, paths
from .errors import GvoiceError

UI_DIR = Path(__file__).resolve().parent / "ui"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"
DEFAULT_PORT = 8765

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".json": "application/json; charset=utf-8",
}
# media-src: the player (F5.4) plays takes from the API (`'self'`) and the simulator's generated audio (`blob:`)
STATIC_CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; script-src 'self'; "
              "style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin", "Cross-Origin-Opener-Policy": "same-origin",
}
STATUS = {"api.not_implemented": 501, "api.not_found": 404, "api.method_not_allowed": 405, "api.bad_host": 403}


class Reply:
    def __init__(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        self.status, self.body, self.content_type, self.headers = status, body, content_type, headers or {}


def error_reply(code: str, lang: str, **params) -> Reply:
    """``{"error": {"code", "params", "message"}}``: the shape `api.js` turns into an `ApiError`."""
    message = GvoiceError(code, **params).message(lang)
    body = {"error": {"code": code, "params": params, "message": message}}
    return Reply(STATUS[code], json.dumps(body, ensure_ascii=False).encode("utf-8"))


def static_reply(segments) -> "Reply | None":
    """``/`` -> ui/index.html; ``/ui/<path>`` -> files of ``gvoice/ui`` with a known extension. None = 404."""
    if not segments:
        rel = "index.html"
    elif segments[0] == "ui" and len(segments) > 1:
        rel = "/".join(segments[1:])
    else:
        return None
    ctype = STATIC_TYPES.get(os.path.splitext(rel)[1].lower())
    if ctype is None:
        return None
    try:
        target = paths.inside(UI_DIR, rel)
        if not target.is_file():
            return None
        data = target.read_bytes()
    except (GvoiceError, OSError):
        return None
    return Reply(200, data, ctype, {"Content-Security-Policy": STATIC_CSP, "Cache-Control": "no-cache"})


def _lang(query: str) -> str:
    for pair in query.split("&"):
        name, _, value = pair.partition("=")
        if name == "lang" and value in i18n.available():
            return value
    return i18n.default_lang()


def handle(method: str, target: str) -> Reply:
    """The reply to one request line; pure, so the tests can call it without a socket."""
    split = urlsplit(target)
    lang = _lang(split.query)
    segments = [unquote(s) for s in split.path.split("/") if s]  # split first: %2F stays inside its segment
    if segments[:1] == ["api"]:
        route, params = api_contract.match(method, segments)
        if route is None:
            return error_reply("api.not_found", lang, path=split.path)
        if route == "method":
            return error_reply("api.method_not_allowed", lang, method=method)
        if route[1] == "/api/locales/{lang}":
            if params["lang"] not in i18n.available():
                return error_reply("api.not_found", lang, path=split.path)
            data = (LOCALES_DIR / (params["lang"] + ".json")).read_bytes()
            return Reply(200, data, headers={"Cache-Control": "no-cache"})
        return error_reply("api.not_implemented", lang)
    if method in ("GET", "HEAD"):
        reply = static_reply(segments)
        if reply is not None:
            return reply
    return error_reply("api.not_found", lang, path=split.path)


class Handler(BaseHTTPRequestHandler):
    server_version = "gvoice"
    sys_version = ""
    timeout = 30

    def log_message(self, fmt, *args):  # quiet, like gimg
        if os.environ.get("GVOICE_DEBUG") == "1":
            super().log_message(fmt, *args)

    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:%d" % port, "localhost:%d" % port, "[::1]:%d" % port}
        bound = self.server.server_address[0]
        if bound not in ("0.0.0.0", "::", ""):
            hosts.add("%s:%d" % (bound.lower(), port))
        host = self.headers.get("Host")
        return host is not None and host.lower() in hosts

    def _serve(self):
        if getattr(self.server, "check_host", True) and not self._host_ok():
            reply = error_reply("api.bad_host", i18n.default_lang())
        else:
            reply = handle(self.command, self.path)
        self.send_response(reply.status)
        for name, value in BASE_HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Type", reply.content_type)
        self.send_header("Content-Length", str(len(reply.body)))
        if "Cache-Control" not in reply.headers:
            self.send_header("Cache-Control", "no-store")
        for name, value in reply.headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(reply.body)
        self.close_connection = True

    do_GET = do_POST = do_PUT = do_HEAD = do_DELETE = do_OPTIONS = do_PATCH = _serve


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    @property
    def port(self) -> int:
        return self.server_address[1]


def make_server(port: int = 0, host: str = "127.0.0.1") -> Server:
    """Bind `host`:`port` (0 = any free port) without serving yet; see `start_thread`."""
    return Server((host, port), Handler)


def start_thread(server: Server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    return thread


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1", lang: str | None = None) -> int:
    server = make_server(port, host)
    print(i18n.t("cli.out.ui_listening", lang, host=host, port=server.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m gvoice.server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    return serve(args.port, args.host)


if __name__ == "__main__":
    raise SystemExit(main())
