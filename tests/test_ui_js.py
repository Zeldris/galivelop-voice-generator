"""Behaviour of the UI's JavaScript, run with ``node`` (no npm packages): each test writes a small ``.mjs`` in a
temporary directory, imports the real modules of ``gvoice/ui/`` by ``file://`` URL, and compares the JSON it prints."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "gvoice" / "ui"
NODE = shutil.which("node")
MIN_NODE = 18  # ES modules, structuredClone, global fetch/URL


def node_major():
    out = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=20).stdout
    m = re.match(r"v(\d+)", out.strip())
    return int(m.group(1)) if m else 0


class UiJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NODE is None:
            raise unittest.SkipTest("node no está: los tests del JS se saltan")
        if node_major() < MIN_NODE:
            raise unittest.SkipTest(f"node < {MIN_NODE}: los tests del JS se saltan")

    def run_js(self, body, timeout=30):
        """Run ``body`` as an ES module with ``mod(path)`` importing from gvoice/ui; return the JSON it ``out(...)``s."""
        script = (
            f"const UI = {json.dumps(UI.as_uri())};\n"
            "const mod = (p) => import(UI + '/' + p);\n"
            "const out = (v) => process.stdout.write(JSON.stringify(v));\n" + body
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.mjs"
            path.write_text(script, encoding="utf-8")
            r = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=timeout)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_router_parse_and_roundtrip(self):
        got = self.run_js("""
const { parse, to } = await mod('js/router.js');
const bad = (() => { try { return parse('#/p/%E0%A4'); } catch (e) { return 'threw: ' + e.message; } })();
const key = 'narrator/intro-01';
out({
  root: parse('#/'), proj: parse('#/p/mundo'), orders: parse('#/p/mundo/orders'), other: parse('#/p/mundo/otro'),
  order: parse('#/p/mundo/o/narrator%2Fintro-01?a=3'), bad,
  rtProject: parse(to.project('mi mundo/x')), rtOrder: parse(to.order('mi mundo', key, 3)),
  rtOrderPlain: parse(to.order('mundo', key)), hashes: [to.projects(), to.project('mundo'), to.order('mundo', key, 3)],
});
""")
        self.assertEqual(got["root"]["name"], "projects")
        for k in ("proj", "orders"):
            self.assertEqual((got[k]["name"], got[k]["project"], got[k]["tab"]), ("project", "mundo", "orders"), k)
        self.assertEqual(got["other"]["name"], "notfound")
        self.assertEqual((got["order"]["name"], got["order"]["project"], got["order"]["key"], got["order"]["query"]),
                         ("order", "mundo", "narrator/intro-01", {"a": "3"}))
        self.assertEqual(got["bad"]["name"], "notfound")  # a malformed hash is not an exception
        self.assertEqual((got["rtProject"]["name"], got["rtProject"]["project"]), ("project", "mi mundo/x"))
        self.assertEqual((got["rtOrder"]["project"], got["rtOrder"]["key"], got["rtOrder"]["query"]),
                         ("mi mundo", "narrator/intro-01", {"a": "3"}))
        self.assertEqual((got["rtOrderPlain"]["key"], got["rtOrderPlain"]["query"]), ("narrator/intro-01", {}))
        self.assertEqual(got["hashes"], ["#/", "#/p/mundo/orders", "#/p/mundo/o/narrator%2Fintro-01?a=3"])

    def test_i18n_load_failure_keeps_previous_state(self):
        got = self.run_js("""
const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
globalThis.document = { documentElement: { lang: '' } };
const { api, setTransport, getLang } = await mod('js/api.js');
const i18n = await mod('js/i18n.js');
const dicts = { es: { 'ui.hi': 'Hola {name}' }, en: { 'ui.hi': 'Hello {name}' } };
let down = false;
setTransport(async (method, url) => {
  const lang = new URL(url, 'http://x').pathname.split('/').pop();
  if (down) return { status: 503, json: { error: { code: 'api.unexpected', message: 'down' } } };
  return { status: 200, json: dicts[lang] };
});
const r = {};
await i18n.load('en');
r.after = [i18n.t('ui.hi', { name: 'Ana' }), i18n.lang(), store.get('gvoice.lang'), document.documentElement.lang, i18n.t('ui.missing')];
down = true;
try { await i18n.load('es'); r.thrown = false; } catch (e) { r.thrown = true; r.err = e.message; }
r.failed = [i18n.t('ui.hi', { name: 'Ana' }), i18n.lang(), store.get('gvoice.lang'), document.documentElement.lang, getLang()];
out(r);
""")
        self.assertEqual(got["after"], ["Hello Ana", "en", "en", "en", "ui.missing"])
        self.assertTrue(got["thrown"])
        self.assertEqual(got["err"], "down")
        self.assertEqual(got["failed"], ["Hello Ana", "en", "en", "en", "en"])

    def mock_script(self, body):
        return """
let tick = null;
globalThis.setInterval = (fn) => { tick = fn; return 1; };
globalThis.location = { origin: 'http://localhost' };
globalThis.fetch = async () => ({ json: async () => ({}) });
const { transport } = await mod('mock/api-mock.js');
const call = async (m, p, b) => { const r = await transport(m, p, b); return { status: r.status, code: r.json && r.json.error && r.json.error.code, json: r.json }; };
""" + body

    def test_api_mock_transport_errors_and_count(self):
        got = self.run_js(self.mock_script("""
const order = { key: 'narrator/x-1', type: 'line', voice: 'narrator', text: 'Hi' };
const strip = (r) => ({ status: r.status, code: r.code });
out({
  method: strip(await call('DELETE', '/api/projects')),
  missing: strip(await call('GET', '/api/nope')),
  zero: strip(await call('POST', '/api/projects/example-world/orders', { order, count: 0 })),
  zeroAttempts: strip(await call('POST', '/api/projects/example-world/orders/narrator/attempts', { count: 0 })),
  noCount: strip(await call('POST', '/api/projects/example-world/orders', { order })),
});
"""))
        self.assertEqual(got["method"], {"status": 405, "code": "api.method_not_allowed"})
        self.assertEqual(got["missing"], {"status": 404, "code": "api.not_found"})
        self.assertEqual(got["zero"], {"status": 400, "code": "api.bad_param"})
        self.assertEqual(got["zeroAttempts"], {"status": 400, "code": "api.bad_param"})
        self.assertEqual(got["noCount"], {"status": 200})  # no error code (undefined is dropped by JSON)

    def test_api_mock_cancel_running_entry_creates_no_take(self):
        got = self.run_js(self.mock_script("""
const entry = async () => (await call('GET', '/api/queue')).json.find((e) => e.id === 1);
const takes = async () => (await call('GET', '/api/projects/example-world/orders/narrator%2Fintro-02')).json.attempts.length;
const before = { entry: await entry(), takes: await takes() };
const cancel = await call('POST', '/api/queue/1/cancel');
const requested = await entry();
tick();
const after = await entry();
out({ before, cancelStatus: cancel.status, requested, after, takes: await takes(), tickSet: typeof tick });
"""))
        self.assertEqual(got["tickSet"], "function")
        self.assertEqual(got["before"]["entry"]["state"], "running")
        self.assertEqual(got["cancelStatus"], 200)
        self.assertEqual((got["requested"]["state"], got["requested"]["cancelRequested"]), ("running", True))
        self.assertEqual(got["after"]["state"], "cancelled")
        self.assertIsNone(got["after"]["attemptId"])
        self.assertEqual(got["takes"], got["before"]["takes"])

    def test_theme_defaults_to_light(self):
        got = self.run_js("""
const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
globalThis.document = { documentElement: { dataset: {} } };
const select = { value: '', addEventListener(ev, fn) { this.fn = fn; } };
const { initTheme } = await mod('js/components/theme.js');
initTheme(select);
const first = { theme: document.documentElement.dataset.theme, value: select.value };
select.value = 'dark'; select.fn();
out({ first, dark: document.documentElement.dataset.theme, saved: store.get('gvoice.theme') });
""")
        self.assertEqual(got["first"], {"theme": "light", "value": "light"})
        self.assertEqual((got["dark"], got["saved"]), ("dark", "dark"))


if __name__ == "__main__":
    unittest.main()
