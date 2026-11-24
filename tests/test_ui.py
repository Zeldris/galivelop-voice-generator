"""F5.1: the static interface (CSP, imports, texts, tokens), the route contract against `api.js` and the simulator,
and the static server."""
import http.client
import json
import re
import socket
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from gvoice import api_contract, i18n, server
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "gvoice" / "ui"
HEADER = "Copiado de gimg@46248251"
NEW_MARK = "Nuevo en gvoice (no copiado de gimg)"


def read(rel):
    return (UI / rel).read_text(encoding="utf-8")


def shape(pattern):
    """A pattern with its parameter names erased: ``/api/x/{p}`` -> ``/api/x/{}``."""
    return re.sub(r"\{\w+\}", "{}", pattern)


CONTRACT = {(m, shape(p)) for m, p, _ in api_contract.ROUTES}


class Static(unittest.TestCase):
    def test_index_has_no_inline_code(self):
        html = read("index.html")
        self.assertNotRegex(html, r"<script(?![^>]*\bsrc=)")
        self.assertNotRegex(html, r"<style")
        self.assertNotRegex(html, r"\sstyle=")
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertIn('<script type="module" src="/ui/js/app.js">', html)

    def test_js_has_no_innerhtml_or_eval(self):
        for f in (UI / "js").rglob("*.js"):
            src = re.sub(r"/\*.*?\*/|^\s*//.*$", "", f.read_text(encoding="utf-8"), flags=re.S | re.M)
            for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"):
                self.assertNotIn(bad, src, f"{f.name}: {bad}")

    def test_relative_imports_exist(self):
        for f in list((UI / "js").rglob("*.js")) + [UI / "mock" / "api-mock.js"]:
            for spec in re.findall(r"(?:from|import)\s*\(?\s*['\"]([^'\"]+)['\"]", f.read_text(encoding="utf-8")):
                if spec.startswith("/ui/"):
                    target = UI / spec[len("/ui/"):]
                elif spec.startswith("."):
                    target = (f.parent / spec).resolve()
                else:
                    self.fail(f"{f.name}: import not local: {spec}")
                self.assertTrue(target.is_file(), f"{f.name} imports {spec}, which does not exist")

    def test_html_and_css_assets_exist(self):
        html = read("index.html")
        for ref in re.findall(r'(?:href|src)="(/ui/[^"]+)"', html):
            self.assertTrue((UI / ref[4:]).is_file(), ref)
        for css in (UI / "css").glob("*.css"):
            for ref in re.findall(r"url\(['\"]?(/ui/[^'\")]+)", css.read_text(encoding="utf-8")):
                self.assertTrue((UI / ref[4:]).is_file(), f"{css.name}: {ref}")

    def test_copied_files_carry_the_header(self):
        files = [UI / "index.html", UI / "fonts" / "README.md", UI / "mock" / "api-mock.js"]
        files += list((UI / "css").glob("*.css")) + list((UI / "js").rglob("*.js"))
        for f in files:
            first = f.read_text(encoding="utf-8").split("\n\n")[0][:600]
            self.assertTrue(HEADER in first or NEW_MARK in first.split("\n")[0], f"{f.name}: sin cabecera de procedencia")
            self.assertFalse(HEADER in first and NEW_MARK in first, f"{f.name}: copiado y nuevo a la vez")

    def test_ui_keys_used_exist_in_both_languages(self):
        es = json.loads((ROOT / "gvoice/locales/es.json").read_text(encoding="utf-8"))
        en = json.loads((ROOT / "gvoice/locales/en.json").read_text(encoding="utf-8"))
        ui_es = {k for k in es if k.startswith("ui.")}
        self.assertEqual(ui_es, {k for k in en if k.startswith("ui.")})
        used = set()
        for f in list((UI / "js").rglob("*.js")) + [UI / "index.html"]:
            used |= set(re.findall(r"['\"`](ui\.[a-zA-Z0-9_.]+)['\"`]", f.read_text(encoding="utf-8")))
        missing = sorted(k for k in used if k not in ui_es)
        self.assertEqual(missing, [])
        for k in ui_es:  # same placeholders on both sides
            self.assertEqual(set(re.findall(r"\{(\w+)\}", es[k])), set(re.findall(r"\{(\w+)\}", en[k])), k)

    def test_mock_error_codes_have_texts(self):
        es = json.loads((ROOT / "gvoice/locales/es.json").read_text(encoding="utf-8"))
        en = json.loads((ROOT / "gvoice/locales/en.json").read_text(encoding="utf-8"))
        src = read("mock/api-mock.js")
        codes = set(re.findall(r"fail\((?:c\.)?lang, \d+, '([\w.]+)'", src))
        codes |= set(re.findall(r"error: \{ code: '([\w.]+)'", src))
        self.assertTrue(codes)
        for code in codes:
            self.assertIn("error." + code, es, code)
            self.assertIn("error." + code, en, code)
        for code in re.findall(r"'(sheet\.[a-z_]+)'", src):
            self.assertIn("warning." + code, es, code)

    def test_js_behaviours_checked_by_text(self):
        # router, theme, mock transport and i18n load are covered by behaviour in tests/test_ui_js.py (node)
        router, app = (read(f) for f in ("js/router.js", "js/app.js"))
        self.assertNotIn("pedidos", router)  # D9: the URL segment is English
        self.assertLess(app.index("onOffline("), app.index("i18n.load("))  # the band hears a boot that finds the API down

    def test_cloned_voices_have_no_sheet_and_no_new_takes(self):
        # (a node test cannot mount these views): the guards for a voice from a clip are in the source
        self.assertIn("o.cloned) return link", read("js/components/project-view.js"))
        order_view = read("js/components/order-view.js")
        self.assertIn("moreCard.hidden = cloned", order_view)
        self.assertIn("if (isCloned(order)) return;", order_view)
        for view in ("project-view", "order-view", "compare-view"):
            self.assertNotIn(".testText", read(f"js/components/{view}.js").replace("ui.order.testText", ""))
        mock = read("mock/api-mock.js")
        self.assertIn("clip: {", mock)
        self.assertEqual(mock.count("'order.clip_no_design'"), 2)  # sheet and more takes


def luminance(hexcolor):
    h = hexcolor.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    chan = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        chan.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blocks():
    """The three token blocks of tokens.css: light, dark by media query, dark by ``[data-theme=dark]``."""
    css = read("css/tokens.css")
    out = {}
    root = re.search(r":root\s*\{([^}]*)\}", css)
    media = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root[^{]*\{([^}]*)\}", css)
    attr = re.search(r"\[data-theme=['\"]?dark['\"]?\]\s*\{([^}]*)\}", css)
    for name, m in (("light", root), ("dark-media", media), ("dark-attr", attr)):
        if m:
            out[name] = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", m.group(1)))
    return out


class Tokens(unittest.TestCase):
    def test_voice_accent_in_every_block(self):
        b = blocks()
        self.assertEqual(set(b), {"light", "dark-media", "dark-attr"})
        for name, tokens in b.items():
            self.assertEqual(tokens["--accent"].lower(), "#d9467a", name)
            for k in ("--accent-text", "--accent-fill", "--accent-soft", "--focus"):
                self.assertIn(k, tokens, f"{name} {k}")
        self.assertEqual(b["dark-media"], b["dark-attr"] | {k: v for k, v in b["dark-media"].items() if k not in b["dark-attr"]})

    def test_accent_contrast(self):
        for name, t in blocks().items():
            self.assertGreaterEqual(contrast(t["--on-accent"] if "--on-accent" in t else "#ffffff", t["--accent-fill"]), 4.5, name + " button")
            if "--surface" in t:
                self.assertGreaterEqual(contrast(t["--accent-text"], t["--surface"]), 4.5, name + " text on surface")
            self.assertGreaterEqual(contrast(t["--focus"], t.get("--surface", "#ffffff")), 3.0, name + " focus ring")


def calls_of_api_js():
    """``(method, shape)`` of every named call in api.js, resolved through the ``paths`` table."""
    src = read("js/api.js")
    table = {}
    block = src[src.index("export const paths"):src.index("export const api")]
    for m in re.finditer(r"^  (\w+): \([^)]*\) => ([`'][^\n]*?[`'])(?:,)?$", block, re.M):
        table[m.group(1)] = m.group(2)
    # multi-line `orders` and the one with a query: take the template with the path
    table["orders"] = "`/api/projects/${enc(p)}/orders`"

    def resolve(expr):
        expr = expr.strip().strip("`'")
        expr = re.sub(r"\$\{paths\.(\w+)\([^)]*\)\}", lambda m: resolve(table[m.group(1)]), expr)
        expr = re.sub(r"\$\{\w+ \?.*$", "", expr)  # optional query string
        expr = re.sub(r"\$\{enc\([^)]*\)\}", "{}", expr)
        expr = re.sub(r"\$\{[^}]*\}", "", expr)
        return expr.strip("`'")

    out = set()
    for method, name in re.findall(r"\b(get|post)\(paths\.(\w+)\(", src[src.index("export const api"):]):
        out.add((method.upper(), resolve(table[name])))
    out.add(("GET", resolve(table["audio"])))  # the audio is never fetched by api.js: the player's <audio src> is
    return out


class Contract(unittest.TestCase):
    def test_routes_are_well_formed_and_unique(self):
        seen = set()
        for method, pattern, summary in api_contract.ROUTES:
            self.assertIn(method, ("GET", "POST"))
            self.assertTrue(pattern.startswith("/api/"))
            self.assertTrue(summary)
            self.assertNotIn((method, shape(pattern)), seen)
            seen.add((method, shape(pattern)))

    def test_api_js_uses_exactly_the_contract(self):
        self.assertEqual(calls_of_api_js(), CONTRACT)

    def test_mock_serves_exactly_the_contract(self):
        found = {(m, shape(p)) for m, p in re.findall(r"^route\('(GET|POST)', '([^']+)'", read("mock/api-mock.js"), re.M)}
        self.assertEqual(found, CONTRACT)

    def test_docs_list_every_route(self):
        doc = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
        for method, pattern, _ in api_contract.ROUTES:
            self.assertIn(f"`{method} {pattern}`", doc)

    def test_match(self):
        route, params = api_contract.match("GET", ["api", "projects", "w", "orders", "narrator/intro-01"])
        self.assertEqual(route[1], "/api/projects/{p}/orders/{key}")
        self.assertEqual(params, {"p": "w", "key": "narrator/intro-01"})
        self.assertEqual(api_contract.match("DELETE", ["api", "queue"])[0], "method")
        self.assertIsNone(api_contract.match("GET", ["api", "nope"])[0])
        self.assertIsNone(api_contract.match("GET", ["api", "projects", "", "orders"])[0])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.make_server(0)
        server.start_thread(cls.srv)
        cls.base = f"http://127.0.0.1:{cls.srv.port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path, method="GET", data=None):
        req = urllib.request.Request(self.base + path, method=method, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_index_with_csp_and_no_cache(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"<script", body)
        csp = headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_every_ui_file_is_served_with_its_type(self):
        for f in UI.rglob("*"):
            ext = f.suffix.lower()
            if f.is_file() and ext in server.STATIC_TYPES:
                status, headers, body = self.get("/ui/" + f.relative_to(UI).as_posix())
                self.assertEqual(status, 200, f)
                self.assertEqual(headers["Content-Type"], server.STATIC_TYPES[ext])
                self.assertEqual(body, f.read_bytes())

    def test_cannot_leave_the_folder(self):
        for path in ("/ui/../server.py", "/ui/%2e%2e/server.py", "/ui/..%2Fserver.py", "/ui/js/../../cli.py",
                     "/ui//etc/passwd", "/ui/css", "/ui/js/app.js.bak"):
            status, _, body = self.get(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"def main", body)

    def test_only_get_serves_static(self):
        self.assertEqual(self.get("/", method="POST", data=b"{}")[0], 404)

    def test_api_routes_answer_501_with_the_error_shape(self):
        for method, pattern, _ in api_contract.ROUTES:
            if pattern == "/api/locales/{lang}":
                continue
            path = re.sub(r"\{key\}", "narrator%2Fintro-01", re.sub(r"\{\w+\}", "x", pattern))
            status, _, body = self.get(path, method=method, data=b"{}" if method == "POST" else None)
            self.assertEqual(status, 501, f"{method} {path}")
            err = json.loads(body)["error"]
            self.assertEqual(err["code"], "api.not_implemented")
            self.assertTrue(err["message"])

    def test_cloned_voice_routes_never_answer_500(self):
        # the API is still F4: sheet and new takes of a voice from a clip (they will be 409 order.clip_no_design) are 501
        for method, path in (("GET", "/api/projects/w/orders/lector/sheet"),
                             ("POST", "/api/projects/w/orders/lector/attempts"),
                             ("GET", "/api/projects/w/orders/lector/attempts/1/audio")):
            status, _, body = self.get(path, method=method, data=b"{}" if method == "POST" else None)
            self.assertEqual(status, 501, path)
            self.assertEqual(json.loads(body)["error"]["code"], "api.not_implemented")

    def test_wrong_method_and_unknown_path(self):
        status, _, body = self.get("/api/queue", method="POST", data=b"{}")
        self.assertEqual((status, json.loads(body)["error"]["code"]), (405, "api.method_not_allowed"))
        status, _, body = self.get("/api/nope")
        self.assertEqual((status, json.loads(body)["error"]["code"]), (404, "api.not_found"))

    def test_locales_are_served_in_full(self):
        for lang in i18n.available():
            status, _, body = self.get("/api/locales/" + lang)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), json.loads((ROOT / f"gvoice/locales/{lang}.json").read_text(encoding="utf-8")))
        self.assertEqual(self.get("/api/locales/xx")[0], 404)

    def test_error_message_follows_the_requested_language(self):
        es = json.loads(self.get("/api/queue?lang=es")[2])["error"]["message"]
        en = json.loads(self.get("/api/queue?lang=en")[2])["error"]["message"]
        self.assertNotEqual(es, en)

    def test_foreign_host_is_refused(self):
        req = urllib.request.Request(self.base + "/", headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)
        self.assertEqual(json.loads(cm.exception.read())["error"]["code"], "api.bad_host")

    def test_empty_segment_is_not_found_and_one_trailing_slash_is_tolerated(self):
        for path in ("/api/projects//orders", "/api//queue", "/api/projects/x//"):
            status, _, body = self.get(path)
            self.assertEqual((status, json.loads(body)["error"]["code"]), (404, "api.not_found"), path)
        status, _, body = self.get("/api/queue/")
        self.assertEqual((status, json.loads(body)["error"]["code"]), (501, "api.not_implemented"))

    def post_raw(self, length_header, payload=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        try:
            conn.putrequest("POST", "/api/queue/clear")
            conn.putheader("Content-Length", length_header)
            conn.endheaders()
            if payload:
                conn.send(payload)
            res = conn.getresponse()
            return res.status, json.loads(res.read())
        finally:
            conn.close()

    def test_big_body_is_refused_with_413_and_no_reset(self):
        payload = b"x" * (2 << 20)
        for _ in range(5):
            status, body = self.post_raw(str(len(payload)), payload)
            self.assertEqual(status, 413)
            self.assertEqual(body["error"]["code"], "api.body_too_large")
            self.assertEqual(body["error"]["params"]["limit"], server.MAX_BODY)

    def test_small_body_gets_the_normal_reply(self):
        for _ in range(3):
            status, body = self.post_raw("2", b"{}")
            self.assertEqual((status, body["error"]["code"]), (501, "api.not_implemented"))

    def test_bad_content_length_is_400(self):
        for value in ("abc", "-5", "1.5"):
            status, body = self.post_raw(value)
            self.assertEqual((status, body["error"]["code"], body["error"]["params"]["name"]),
                             (400, "api.bad_param", "Content-Length"), value)


class LocalHost(unittest.TestCase):
    def test_only_loopback_is_accepted(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            self.assertEqual(server.check_host(host), host)
        for host in ("0.0.0.0", "::", "", "192.168.1.5", "example.com"):
            with self.assertRaises(GvoiceError) as cm:
                server.make_server(0, host)
            self.assertEqual(cm.exception.code, "cli.ui_host_not_local", host)
            self.assertIn(host, cm.exception.message("en")) if host else None

    def test_cli_refuses_a_foreign_host_without_binding(self):
        for lang in ("es", "en"):
            proc = subprocess.run([sys.executable, "-m", "gvoice", "ui", "--host", "0.0.0.0", "--port", "0", "--lang", lang],
                                  cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stderr.strip(), GvoiceError("cli.ui_host_not_local", host="0.0.0.0").message(lang))
            self.assertEqual(proc.stdout, "")

    def test_server_main_refuses_a_foreign_host(self):
        proc = subprocess.run([sys.executable, "-m", "gvoice.server", "--host", "::", "--port", "0"],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr.strip(), GvoiceError("cli.ui_host_not_local", host="::").message())

    def test_url_host_brackets_ipv6(self):
        self.assertEqual(server.url_host("::1"), "[::1]")
        self.assertEqual(server.url_host("localhost"), "localhost")

    def test_ipv6_loopback_is_served(self):
        try:
            srv = server.make_server(0, "::1")
        except OSError:
            self.skipTest("no IPv6 loopback")
        server.start_thread(srv)
        try:
            with urllib.request.urlopen(f"http://[::1]:{srv.port}/") as r:
                self.assertEqual(r.status, 200)
            req = urllib.request.Request(f"http://[::1]:{srv.port}/", headers={"Host": f"[::1]:{srv.port}"})
            with urllib.request.urlopen(req) as r:
                self.assertEqual(r.status, 200)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
