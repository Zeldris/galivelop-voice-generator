"""The route contract of the local HTTP API (F5.1): what the web interface calls and what F4 has to serve.

Copiado de gimg@46248251 (D7) en estilo y prefijo (`gimg/server.py`: rutas `/api/...`, la clave de un pedido en un
solo segmento); adaptado a gvoice (D9, D10): sin perfiles, plantillas, composición ni marca; con el audio de la toma,
sus picos de forma de onda y la ficha de diseño con avisos.

`ROUTES` is a tuple of ``(method, pattern, summary)``. A pattern segment ``{name}`` matches one URL segment, decoded
(``{key}`` is an order key such as ``narrator/intro-01``, sent as ``narrator%2Fintro-01``). The query string is not part
of the pattern. ``tests/test_ui.py`` checks that ``gvoice/ui/js/api.js`` and the simulator use exactly these routes;
F4 implements them, and until then `gvoice.server` answers 501 on every one of them except ``GET /api/locales/{lang}``.
Documented in ``docs/api.md``."""
from __future__ import annotations

ROUTES = (
    ("GET", "/api/health", "Service state: version, worker alive, queue counts"),
    ("GET", "/api/locales/{lang}", "All interface texts of a language (gvoice/locales/<lang>.json)"),
    # projects (gvoice project add|remove|list)
    ("GET", "/api/projects", "List the registered projects"),
    ("POST", "/api/projects", "Register a project from a folder path (body: path)"),
    ("GET", "/api/projects/{p}", "One project: root and its galivelop-voices.json config"),
    ("POST", "/api/projects/{p}/remove", "Unregister a project (its files stay)"),
    # orders (gvoice order submit|list|show)
    ("GET", "/api/projects/{p}/orders", "List orders; query: type=voice|line, chosen=true|false"),
    ("POST", "/api/projects/{p}/orders", "Submit an order and queue its takes (body: order, count; a voice from a sample queues none and ignores count)"),
    ("GET", "/api/projects/{p}/orders/{key}", "One order with its takes, chosen take and stale marks"),
    ("GET", "/api/projects/{p}/orders/{key}/sheet", "Design sheet of a voice: instruction text and warnings"),
    ("POST", "/api/sheet/check", "Check a design sheet without storing it (body: designSheet)"),
    # takes (gvoice attempt new|mark|note, choose, undo)
    ("POST", "/api/projects/{p}/orders/{key}/attempts", "Queue more takes (body: count, seed)"),
    ("POST", "/api/projects/{p}/orders/{key}/attempts/{id}/mark", "Mark a take new|candidate|discarded (body: state)"),
    ("POST", "/api/projects/{p}/orders/{key}/attempts/{id}/note", "Set the note of a take (body: text)"),
    ("GET", "/api/projects/{p}/orders/{key}/attempts/{id}/audio", "The WAV audio of a take"),
    ("GET", "/api/projects/{p}/orders/{key}/attempts/{id}/peaks", "Waveform peaks of a take; query: n=<points>"),
    ("POST", "/api/projects/{p}/orders/{key}/choose", "Choose a take (a voice also queues its prints) (body: attempt)"),
    ("POST", "/api/projects/{p}/orders/{key}/undo", "Go back to the previously chosen take"),
    # queue (gvoice queue list|cancel)
    ("GET", "/api/queue", "List queue entries; query: state=queued|running|done|failed|cancelled"),
    ("POST", "/api/queue/{id}/cancel", "Cancel a queued or running entry"),
    ("POST", "/api/queue/clear", "Cancel every queued entry, of one project if given (body: project)"),
    # models (gvoice models list|verify|fetch)
    ("GET", "/api/models", "Model files and their state; query: engine"),
    ("POST", "/api/models/verify", "Check size and hash of model files (body: engine, ids)"),
    ("POST", "/api/models/fetch", "Download missing model files (body: engine, ids)"),
)


def _parts(pattern: str) -> tuple:
    return tuple(pattern.strip("/").split("/"))


def match(method: str, segments) -> tuple:
    """Find the route for `method` and the URL `segments` (already decoded).

    Returns ``(route, params)``; ``route`` is ``None`` when no pattern has that shape and ``"method"`` when one has
    it but for other methods."""
    segments = tuple(segments)
    shape_found = False
    for entry in ROUTES:
        parts = _parts(entry[1])
        if len(parts) != len(segments):
            continue
        params = {}
        for part, seg in zip(parts, segments):
            if part.startswith("{"):
                if seg == "":
                    break
                params[part[1:-1]] = seg
            elif part != seg:
                break
        else:
            shape_found = True
            if entry[0] == method:
                return entry, params
    return ("method" if shape_found else None), {}
