"""Ollama eviction (D-7) and the local-host check (invariant 11).

Adapted from gimg@HEAD gimg/engine_sdcpp.py (``ollama_loaded``, ``ollama_unload`` and the wait), without gimg."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.error  # noqa: F401  (HTTPError on a refused redirect)
import urllib.request

from . import machine_lock
from .errors import GrunError

URL_ENV = "GRUN_OLLAMA_URL"
DEFAULT_URL = "http://localhost:11434"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
MODES = ("unload", "abort", "ignore")
MAX_BYTES = 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect (invariant 11): the 3xx is raised as an `HTTPError`, a failure like any other."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# never through a proxy, never to another host by redirect
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def check_local(url) -> str:
    """The URL without a trailing ``/``, if it is http(s) on a local host; else `GrunError`."""
    try:
        parts = urllib.parse.urlsplit(url if isinstance(url, str) else "")
        host = parts.hostname or ""
    except ValueError:
        parts, host = None, ""
    if parts is None or parts.scheme not in ("http", "https"):
        raise GrunError("engine.ollama_url", url=str(url))
    if host.lower() not in LOCAL_HOSTS:
        raise GrunError("net.non_local_host", host=host)
    return url.rstrip("/")


def _request(url, path, body=None, timeout=10.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url + path, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=timeout) as resp:
        return resp.read(MAX_BYTES + 1)


def loaded(url, timeout: float = 2.0) -> list:
    """Names of the models Ollama has in memory (``size > 0``); any network or JSON error is ``[]``."""
    try:
        raw = _request(url, "/api/ps", timeout=timeout)
        if len(raw) > MAX_BYTES:
            return []
        models = json.loads(raw.decode("utf-8")).get("models")
        names = []
        for item in models if isinstance(models, list) else ():
            size = item.get("size")
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0:
                names.append(name)
        return names
    except Exception:  # network (OSError, HTTPException), bad JSON or an odd shape: nothing is loaded
        return []


def unload(url, name, timeout: float = 10.0) -> None:
    """Ask Ollama to drop model `name` (generate and embed endpoints); errors are ignored."""
    for path, body in (("/api/generate", {"model": name, "keep_alive": 0}),
                       ("/api/embed", {"model": name, "input": "", "keep_alive": 0})):
        try:
            _request(url, path, body, timeout)
        except Exception:
            pass


def evict(machine, should_cancel=None, *, wait_s: float = 15.0, poll_s: float = 1.0) -> list:
    """Free the memory Ollama holds, by ``machine["engine"]["ollama"]``: ``unload`` (default), ``abort`` or
    ``ignore``. Returns the models unloaded. Models that stay loaded: ``engine.ollama_loaded``. The wait polls
    `should_cancel` (true raises `machine_lock.WaitCancelled`)."""
    engine = machine.get("engine") or {}
    mode = engine.get("ollama", "unload")
    url = check_local(os.environ.get(URL_ENV) or engine.get("ollamaUrl") or DEFAULT_URL)
    if mode == "ignore":
        return []
    names = loaded(url)
    if not names:
        return []
    if mode == "abort":
        raise GrunError("engine.ollama_loaded", models=", ".join(names))
    for name in names:
        unload(url, name)
    deadline = time.monotonic() + wait_s
    while True:
        if should_cancel is not None and should_cancel():
            raise machine_lock.WaitCancelled()
        left = loaded(url)
        if not left:
            return names
        if time.monotonic() >= deadline:
            raise GrunError("engine.ollama_loaded", models=", ".join(left))
        time.sleep(poll_s)
