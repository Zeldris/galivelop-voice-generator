"""Behaviour of the UI's JavaScript, run with ``node`` (no npm packages): each test writes a small ``.mjs`` in a
temporary directory, imports the real modules of ``gvoice/ui/`` by ``file://`` URL, and compares the JSON it prints."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from gvoice import schema

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


    def test_router_project_query_roundtrip(self):
        got = self.run_js("""
const { parse, to } = await mod('js/router.js');
const h = to.project('mi mundo', 'orders', { type: 'voice', chosen: '', other: undefined });
out({ h, back: parse(h), plain: to.project('mundo'), both: to.project('mundo', 'orders', { type: 'line', chosen: 'false' }) });
""")
        self.assertEqual(got["h"], "#/p/mi%20mundo/orders?type=voice")
        self.assertEqual((got["back"]["name"], got["back"]["project"], got["back"]["query"]), ("project", "mi mundo", {"type": "voice"}))
        self.assertEqual(got["plain"], "#/p/mundo/orders")
        self.assertEqual(got["both"], "#/p/mundo/orders?type=line&chosen=false")

    def test_filters_roundtrip_with_the_url(self):
        got = self.run_js("""
const { filtersFromQuery, filtersToQuery } = await mod('js/order-model.js');
const { parse, to } = await mod('js/router.js');
const cases = [{}, { type: 'voice' }, { chosen: 'true' }, { type: 'line', chosen: 'false' }];
const trips = cases.map((c) => filtersToQuery(filtersFromQuery(parse(to.project('p', 'orders', c)).query)));
out({
  trips, empty: filtersFromQuery({}), full: filtersFromQuery({ type: 'line', chosen: 'false' }),
  junk: filtersFromQuery({ type: 'sound', chosen: 'maybe' }), noEmpty: filtersToQuery({ type: '', chosen: '' }),
  junkOut: filtersToQuery({ type: 'x', chosen: 'y' }),
});
""")
        self.assertEqual(got["trips"], [{}, {"type": "voice"}, {"chosen": "true"}, {"type": "line", "chosen": "false"}])
        self.assertEqual(got["empty"], {"type": "", "chosen": ""})
        self.assertEqual(got["full"], {"type": "line", "chosen": "false"})
        self.assertEqual(got["junk"], {"type": "", "chosen": ""})  # a value outside the list is "all", never sent to the API
        self.assertEqual((got["noEmpty"], got["junkOut"]), ({}, {}))

    def test_order_summary(self):
        got = self.run_js("""
const { orderSummary } = await mod('js/order-model.js');
out({
  voice: orderSummary({ key: 'orc', type: 'voice', testText: 'Blood.', attempts: [{ id: 1 }, { id: 2 }], chosen: null }),
  line: orderSummary({ key: 'narrator/a', type: 'line', voice: 'narrator', text: 'Hi', attempts: [{ id: 1 }], chosen: 1 }),
  count: orderSummary({ key: 'x', type: 'voice', attemptCount: 4 }),
  none: orderSummary({ key: 'y', type: 'line', voice: 'v' }),
});
""")
        self.assertEqual(got["voice"], {"key": "orc", "type": "voice", "voice": "", "text": "Blood.", "takes": 2, "chosen": False, "chosenId": None})
        self.assertEqual(got["line"], {"key": "narrator/a", "type": "line", "voice": "narrator", "text": "Hi", "takes": 1, "chosen": True, "chosenId": 1})
        self.assertEqual((got["count"]["takes"], got["count"]["chosen"]), (4, False))
        self.assertEqual((got["none"]["takes"], got["none"]["text"]), (0, ""))

    def build(self, fields):
        """Run the real buildOrder on ``fields`` (a dict of form values) and return {body, errors}."""
        return self.run_js(f"const {{ buildOrder }} = await mod('js/order-model.js'); out(buildOrder({json.dumps(fields)}));")

    def assert_valid_order(self, body):
        errors = schema.validate(body["order"], schema.load_schema("order"))
        self.assertEqual(errors, [], errors)

    VOICE = {"type": "voice", "key": "narrator", "testText": "The law admits no exceptions.", "seed": "1234", "count": "3",
             "sheet": {"gender": "male", "age": " middle-aged adult ", "pitch": "", "tone": "authoritative"},
             "extra": "breathing: audible between sentences\n\n"}

    def test_build_voice_order_meets_the_schema(self):
        got = self.build(self.VOICE)
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["body"]["count"], 3)
        self.assertEqual(got["body"]["order"], {
            "type": "voice", "key": "narrator", "testText": "The law admits no exceptions.", "seed": 1234,
            "designSheet": {"gender": "male", "age": "middle-aged adult", "tone": "authoritative", "extra": {"breathing": "audible between sentences"}}})
        self.assert_valid_order(got["body"])
        # without seed or extra attributes: no `seed` and no `extra`, and still valid (an empty sheet is allowed)
        minimal = self.build({"type": "voice", "key": "orc/boss", "testText": "Blood.", "seed": "", "count": ""})
        self.assertEqual(minimal["body"]["order"], {"type": "voice", "key": "orc/boss", "testText": "Blood.", "designSheet": {}})
        self.assertEqual(minimal["body"]["count"], 1)
        self.assert_valid_order(minimal["body"])

    def test_build_line_order_meets_the_schema(self):
        got = self.build({"type": "line", "voice": "narrator", "lineId": "intro-01", "text": " Long ago. ", "seed": "7", "count": "2"})
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["body"], {"order": {"type": "line", "key": "narrator/intro-01", "voice": "narrator", "text": "Long ago.", "seed": 7}, "count": 2})
        self.assert_valid_order(got["body"])

    def test_build_rejects_missing_required_fields_with_their_reason(self):
        voice = self.build({"type": "voice", "key": " ", "testText": "", "count": "1"})
        self.assertIsNone(voice["body"])
        self.assertEqual([(e["field"], e["code"]) for e in voice["errors"]], [("key", "required"), ("testText", "required")])
        line = self.build({"type": "line", "voice": "", "lineId": "", "text": "  ", "count": "1"})
        self.assertIsNone(line["body"])
        self.assertEqual([(e["field"], e["code"]) for e in line["errors"]],
                         [("voice", "required"), ("lineId", "required"), ("text", "required")])
        self.assertEqual(self.build({"type": "sound"})["errors"], [{"field": "type", "code": "required"}])

    def test_build_rejects_keys_that_break_the_pattern(self):
        for bad in ("Narrator", "-x", "a b", "a//b", "/a", "a/", "../x", "ñu"):
            got = self.build({"type": "voice", "key": bad, "testText": "x"})
            self.assertEqual([(e["field"], e["code"]) for e in got["errors"]], [("key", "pattern")], bad)
        for bad in ("Intro", "a/b", "x y", "_x"):
            got = self.build({"type": "line", "voice": "narrator", "lineId": bad, "text": "x"})
            self.assertEqual([(e["field"], e["code"]) for e in got["errors"]], [("lineId", "pattern")], bad)
        got = self.build({"type": "line", "voice": "Narrator", "lineId": "a", "text": "x"})
        self.assertEqual([(e["field"], e["code"]) for e in got["errors"]], [("voice", "pattern")])
        # what the client accepts, the schema accepts; a key of 100 characters is the last valid one
        ok = self.build({"type": "voice", "key": "a" * 100, "testText": "x"})
        self.assertEqual(ok["errors"], [])
        self.assert_valid_order(ok["body"])
        long = self.build({"type": "voice", "key": "a" * 101, "testText": "x"})
        self.assertEqual(long["errors"], [{"field": "key", "code": "too_long", "params": {"max": 100}}])
        self.assertTrue(schema.validate({"type": "voice", "key": "a" * 101, "testText": "x", "designSheet": {}}, schema.load_schema("order")))
        long_line = self.build({"type": "line", "voice": "a" * 60, "lineId": "b" * 60, "text": "x"})
        self.assertEqual(long_line["errors"], [{"field": "lineId", "code": "too_long", "params": {"max": 100}}])

    def codes(self, fields, existing=None):
        got = self.run_js(f"const {{ buildOrder }} = await mod('js/order-model.js'); out(buildOrder({json.dumps(fields)}, {json.dumps(existing)} === null ? null : new Set({json.dumps(existing)})));")
        return got, [(e["field"], e["code"]) for e in got["errors"]]

    def test_line_voice_is_a_key_with_slashes(self):
        got = self.build({"type": "line", "voice": "npc/guard", "lineId": "hi-1", "text": "Halt."})
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["body"]["order"]["key"], "npc/guard/hi-1")
        self.assert_valid_order(got["body"])
        self.assertEqual(self.codes({"type": "line", "voice": "npc//guard", "lineId": "a", "text": "x"})[1], [("voice", "pattern")])
        self.assertEqual(self.codes({"type": "line", "voice": "npc/guard", "lineId": "a/b", "text": "x"})[1], [("lineId", "pattern")])

    def test_build_rejects_an_existing_key(self):
        voice = {"type": "voice", "key": "narrator", "testText": "x"}
        self.assertEqual(self.codes(voice, ["narrator", "orc"])[1], [("key", "key_exists")])
        self.assertEqual(self.codes(voice, ["orc"])[1], [])
        self.assertEqual(self.codes(voice)[1], [])  # sin claves cargadas, no se comprueba
        line = {"type": "line", "voice": "narrator", "lineId": "intro-01", "text": "x"}
        self.assertEqual(self.codes(line, ["narrator", "narrator/intro-01"])[1], [("lineId", "key_exists")])
        self.assertEqual(self.codes(line, ["narrator"])[1], [])

    def test_build_checks_the_seed_range_with_the_count(self):
        base = {"type": "voice", "key": "v", "testText": "x"}
        got, codes = self.codes({**base, "seed": "4294967295", "count": "3"})
        self.assertEqual(codes, [("seed", "seed_range")])
        self.assertEqual(got["errors"][0]["params"], {"max": 4294967295, "count": 3})
        self.assertEqual(self.codes({**base, "seed": "4294967295", "count": "1"})[1], [])
        self.assertEqual(self.codes({**base, "seed": "4294967293", "count": "3"})[1], [])
        self.assertEqual(self.codes({**base, "seed": "4294967294", "count": "3"})[1], [("seed", "seed_range")])
        self.assertEqual(self.codes({**base, "seed": "4294967295", "count": "51"})[1], [("count", "count")])

    def test_build_reports_non_numeric_number_inputs(self):
        base = {"type": "voice", "key": "v", "testText": "x", "seed": "", "count": ""}
        self.assertEqual(self.codes({**base, "seedBad": True})[1], [("seed", "seed")])
        self.assertEqual(self.codes({**base, "countBad": True})[1], [("count", "count")])
        self.assertEqual(self.codes({**base, "seedBad": False, "countBad": False})[1], [])

    def test_orders_of_reads_both_response_shapes(self):
        got = self.run_js("""const { ordersOf } = await mod('js/order-model.js');
out([ordersOf([{ key: 'a' }]), ordersOf({ orders: [{ key: 'b' }] }), ordersOf(null), ordersOf({}), ordersOf({ orders: 3 })]);""")
        self.assertEqual(got, [[{"key": "a"}], [{"key": "b"}], [], [], []])

    def test_api_mock_count_limit_is_the_real_one(self):
        got = self.run_js(self.mock_script("""
const order = { key: 'narrator/x-1', type: 'line', voice: 'narrator', text: 'Hi' };
const strip = (r) => ({ status: r.status, code: r.code, n: Array.isArray(r.json && r.json.entries) ? r.json.entries.length : null });
out({
  ok: strip(await call('POST', '/api/projects/example-world/orders', { order, count: 50 })),
  over: strip(await call('POST', '/api/projects/example-world/orders', { order, count: 51 })),
  attempts: strip(await call('POST', '/api/projects/example-world/orders/narrator/attempts', { count: 51 })),
});
"""))
        self.assertEqual(got["ok"]["status"], 200)
        self.assertEqual(got["ok"]["n"], 50)
        self.assertEqual((got["over"]["status"], got["over"]["code"]), (400, "api.bad_param"))
        self.assertEqual((got["attempts"]["status"], got["attempts"]["code"]), (400, "api.bad_param"))

    def test_build_rejects_bad_seed_count_extra_and_long_text(self):
        def reasons(**f):
            base = {"type": "voice", "key": "v", "testText": "x"}
            return [(e["field"], e["code"]) for e in self.build({**base, **f})["errors"]]
        self.assertEqual(reasons(seed="-1"), [("seed", "seed")])
        self.assertEqual(reasons(seed="1.5"), [("seed", "seed")])
        self.assertEqual(reasons(seed="4294967296"), [("seed", "seed")])
        self.assertEqual(reasons(seed="4294967295"), [])
        self.assertEqual(reasons(seed="0"), [])
        self.assertEqual(reasons(count="0"), [("count", "count")])
        self.assertEqual(reasons(count="51"), [("count", "count")])
        self.assertEqual(reasons(count="abc"), [("count", "count")])
        self.assertEqual(reasons(count="50"), [])
        bad = self.build({"type": "voice", "key": "v", "testText": "x", "extra": "ok: yes\nno colon here"})
        self.assertEqual(bad["errors"], [{"field": "extra", "code": "extra", "params": {"line": "no colon here"}}])
        self.assertEqual(reasons(extra="name:"), [("extra", "extra")])
        self.assertEqual(reasons(testText="x" * 1001), [("testText", "too_long")])
        self.assertEqual([(e["field"], e["code"]) for e in self.build({"type": "line", "voice": "v", "lineId": "a", "text": "x" * 4001})["errors"]], [("text", "too_long")])
        # all the problems at once, in form order
        many = self.build({"type": "voice", "key": "", "testText": "", "seed": "x", "count": "0"})
        self.assertEqual([e["field"] for e in many["errors"]], ["key", "testText", "seed", "count"])

    def test_api_mock_filters_orders_by_type_and_chosen(self):
        got = self.run_js(self.mock_script("""
const keys = async (q) => { const r = await call('GET', '/api/projects/example-world/orders' + q); return { status: r.status, keys: Array.isArray(r.json) ? r.json.map((o) => o.key) : null, code: r.code }; };
out({
  all: await keys(''), voice: await keys('?type=voice'), line: await keys('?type=line'),
  chosen: await keys('?chosen=true'), unchosen: await keys('?chosen=false'), both: await keys('?type=voice&chosen=false'),
  badType: await keys('?type=sound'), badChosen: await keys('?chosen=maybe'),
});
"""))
        self.assertEqual(got["all"]["keys"], ["narrator", "narrator/intro-01", "narrator/intro-02", "orc"])
        self.assertEqual(got["voice"]["keys"], ["narrator", "orc"])
        self.assertEqual(got["line"]["keys"], ["narrator/intro-01", "narrator/intro-02"])
        self.assertEqual(got["chosen"]["keys"], ["narrator", "narrator/intro-01", "narrator/intro-02"])
        self.assertEqual(got["unchosen"]["keys"], ["orc"])
        self.assertEqual(got["both"]["keys"], ["orc"])
        self.assertEqual((got["badType"]["status"], got["badType"]["code"]), (400, "api.bad_param"))
        self.assertEqual((got["badChosen"]["status"], got["badChosen"]["code"]), (400, "api.bad_param"))

    def test_api_mock_accepts_the_built_orders_and_lists_them(self):
        got = self.run_js(self.mock_script("""
const { buildOrder } = await mod('js/order-model.js');
const send = async (fields) => { const { body } = buildOrder(fields); const r = await call('POST', '/api/projects/example-world/orders', body); return { status: r.status, code: r.code, entries: r.json.entries && r.json.entries.length }; };
const voice = await send({ type: 'voice', key: 'wizard', testText: 'Fly.', sheet: { age: 'elderly man' }, count: '2' });
const line = await send({ type: 'line', voice: 'narrator', lineId: 'outro', text: 'The end.', count: '1' });
const orphan = await send({ type: 'line', voice: 'wizard', lineId: 'a', text: 'x', count: '1' });
const list = await call('GET', '/api/projects/example-world/orders?chosen=false');
out({ voice, line, orphan, unchosen: list.json.map((o) => o.key) });
"""))
        self.assertEqual(got["voice"], {"status": 200, "entries": 2})
        self.assertEqual(got["line"], {"status": 200, "entries": 1})
        # a line of a voice with no chosen take is refused by the API, with its reason
        self.assertEqual((got["orphan"]["status"], got["orphan"]["code"]), (409, "order.voice_not_fixed"))
        self.assertEqual(got["unchosen"], ["narrator/outro", "orc", "wizard"])


if __name__ == "__main__":
    unittest.main()
