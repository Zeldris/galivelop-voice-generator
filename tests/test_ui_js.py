"""Behaviour of the UI's JavaScript, run with ``node`` (no npm packages): each test writes a small ``.mjs`` in a
temporary directory, imports the real modules of ``gvoice/ui/`` by ``file://`` URL, and compares the JSON it prints."""
import json
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from gvoice import schema

UI = Path(__file__).resolve().parent.parent / "gvoice" / "ui"
FAKE_DOM_URL = (Path(__file__).resolve().parent / "ui_fake_dom.mjs").as_uri()  # DOM falso compartido
NODE = shutil.which("node")
MIN_NODE = 18  # ES modules, structuredClone, global fetch/URL


def node_major():
    out = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=20).stdout
    m = re.match(r"v(\d+)", out.strip())
    return int(m.group(1)) if m else 0

PATTERN_CASES = ["a", "0", "abc-def", "a-", "a--b", "-a", "A", "aB", "a/b", "a/b/c-1", "/a", "a/", "a//b", "a/-b", "a b",
                 "a_b", "voz/id-01", "ñ", "a/B", "", "-", "a.b", "../a", "a/../b", "1/2"]
SHEETS = [
    {}, {"gender": "male"}, {"age": "  "},
    {"age": "child"}, {"age": "12 years old"}, {"age": "teenager"}, {"age": "young"}, {"age": "young adult"},
    {"age": "young man"}, {"age": "adult"}, {"age": "middle-aged adult"}, {"age": "elderly"}, {"age": "30s"},
    {"age": "thirties"}, {"age": "25"}, {"age": "Adult"}, {"age": "child-like adult"}, {"age": "ageless"},
    {"age": "adult", "texture": "bright, gravelly"}, {"age": "adult", "tone": "Bright"},
    {"age": "adult", "pitch": "high-pitched"}, {"age": "adult", "pitch": "high pitched"},
    {"age": "adult", "extra": {"mood": "cute and light"}}, {"age": "adult", "texture": "brightness"},
    {"age": "adult", "texture": "small-ish"}, {"age": "adult", "emotion": "childlike"},
    {"age": "adult", "tone": "calm", "personality": "precise"}, {"extra": {"x": "small"}},
]


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
            f"const FAKE_DOM_URL = {json.dumps(FAKE_DOM_URL)};\n"
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

    def test_order_model_constants_match_python_sources(self):
        """The limits copied into order-model.js equal their sources (common/order schemas, orders.py)."""
        from gvoice import orders
        got = self.run_js("""
const m = await mod('js/order-model.js');
const keys = %s, segs = %s;
out({ MAX_COUNT: m.MAX_COUNT, MAX_SEED: m.MAX_SEED, MAX_KEY: m.MAX_KEY, MAX_TEST_TEXT: m.MAX_TEST_TEXT,
  MAX_LINE_TEXT: m.MAX_LINE_TEXT, SHEET_FIELDS: m.SHEET_FIELDS,
  key: keys.map((k) => m.KEY_PATTERN.test(k)), seg: segs.map((k) => m.SEGMENT_PATTERN.test(k)) });
""" % (json.dumps(PATTERN_CASES), json.dumps(PATTERN_CASES)))
        common = schema.load_schema("common")["$defs"]
        order_props = schema.load_schema("order")["properties"]
        self.assertEqual(got["MAX_SEED"], common["seed"]["maximum"])
        self.assertEqual(got["MAX_SEED"], orders.SEED_LIMIT - 1)
        self.assertEqual(got["MAX_KEY"], common["key"]["maxLength"])
        self.assertEqual(got["MAX_TEST_TEXT"], common["testText"]["maxLength"])
        self.assertEqual(got["MAX_LINE_TEXT"], order_props["text"]["maxLength"])
        with self.assertRaises(Exception) as cm:  # MAX_COUNT: 1..50 in orders.check_count, no schema
            orders.check_count(got["MAX_COUNT"] + 1)
        self.assertIn("count_invalid", str(getattr(cm.exception, "code", cm.exception)))
        orders.check_count(got["MAX_COUNT"])
        props = [k for k in schema.load_schema("design-sheet")["properties"] if k not in ("$schema", "extra")]
        self.assertEqual(got["SHEET_FIELDS"], props)
        for name, rx_js in (("key", got["key"]), ("seg", got["seg"])):
            rx = re.compile(common["key" if name == "key" else "name"]["pattern"])
            self.assertEqual(rx_js, [bool(rx.search(c)) for c in PATTERN_CASES], name)

    def test_mock_limits_match_python(self):
        """api-mock.js hard-codes count 1..50 (twice); it has no seed limit of its own (no source to compare)."""
        src = (UI / "mock" / "api-mock.js").read_text(encoding="utf-8")
        found = re.findall(r"count < 1 \|\| count > (\d+)", src)
        self.assertEqual(len(found), 2)
        got = self.run_js("const m = await mod('js/order-model.js'); out(m.MAX_COUNT);")
        self.assertEqual({int(n) for n in found}, {got})

    def test_mock_warnings_match_sheet_py(self):
        """warningsOf / BANNED / SUGGESTIONS of the mock give the same warnings as gvoice.sheet.warnings."""
        from gvoice import sheet
        got = self.run_js("""
const m = await mod('mock/api-mock.js');
const sheets = %s;
out({ banned: m.BANNED, suggestions: m.SUGGESTIONS, warnings: sheets.map((s) => m.warningsOf(s)) });
process.exit(0);
""" % json.dumps(SHEETS))
        self.assertEqual(got["banned"], list(sheet.BANNED_WORDS))
        self.assertEqual(got["suggestions"], ", ".join(sheet.SUGGESTIONS))
        for s, js in zip(SHEETS, got["warnings"]):
            py = [{"code": w.code, "params": w.params}
                  for w in sheet.warnings(s)]
            self.assertEqual(js, py, json.dumps(s))


    # ---- F5.3: ficha con avisos ----

    FAKE_DOM = """
const { installFakeDom, flush: flushAll, fakeTimers } = await import(FAKE_DOM_URL);
installFakeDom();
"""

    LOAD_LOCALE = """
import { readFileSync } from 'node:fs';
const { api, setTransport } = await mod('js/api.js');
const i18n = await mod('js/i18n.js');
const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
globalThis.document = { documentElement: { lang: '' } };
setTransport(async (method, url) => {
  const lang = new URL(url, 'http://x').pathname.split('/').pop();
  return { status: 200, json: JSON.parse(readFileSync(new URL(UI + '/../locales/' + lang + '.json').pathname, 'utf8')) };
});
"""

    WARNINGS = [
        {"code": "sheet.age_missing", "params": {}},
        {"code": "sheet.age_not_adult", "params": {"age": "child"}},
        {"code": "sheet.banned_word", "params": {"word": "bright", "field": "texture", "suggestions": "deep, resonant"}},
    ]

    def test_warning_items_give_an_icon_and_the_text_of_each_code_in_both_languages(self):
        got = self.run_js(self.LOAD_LOCALE + """
const { warningItems } = await mod('js/components/sheet-warnings.js');
const warnings = %s;
const r = {};
for (const lang of ['es', 'en']) { await i18n.load(lang); r[lang] = warningItems(warnings); }
r.unknown = warningItems([{ code: 'sheet.nope', params: {}, message: 'del servidor' }]);
r.none = warningItems(undefined);
out(r);
""" % json.dumps(self.WARNINGS))
        for lang in ("es", "en"):
            locale = json.loads((UI.parent / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
            self.assertEqual([i["code"] for i in got[lang]], [w["code"] for w in self.WARNINGS])
            self.assertEqual([i["icon"] for i in got[lang]], [w["code"] for w in self.WARNINGS])
            self.assertEqual(len({i["text"] for i in got[lang]}), 3)
            self.assertEqual(got[lang][0]["text"], locale["warning.sheet.age_missing"])
            self.assertIn('"child"', got[lang][1]["text"])
            self.assertIn("bright", got[lang][2]["text"])
            self.assertIn("deep, resonant", got[lang][2]["text"])
        self.assertNotEqual(got["es"][0]["text"], got["en"][0]["text"])
        self.assertEqual(got["unknown"], [{"code": "sheet.nope", "icon": "default", "text": "del servidor"}])
        self.assertEqual(got["none"], [])

    def test_sheet_panel_renders_each_warning_with_its_icon_and_text_on_screen(self):
        got = self.run_js(self.LOAD_LOCALE + self.FAKE_DOM + """
const { sheetPanel, sheetWarnings } = await mod('js/components/sheet-warnings.js');
await i18n.load('es');
const view = (node) => {
  const items = node.find((e) => e.tag === 'li');
  return {
    live: node.find((e) => e.tag === 'div' && e.attrs.role).map((d) => [d.attrs.role, d.attrs['aria-live'], d.find((e) => e.tag === 'ul').length]),
    ulRole: node.find((e) => e.tag === 'ul').map((u) => u.attrs.role || null),
    pre: node.find((e) => e.tag === 'pre').map((p) => [p.textContent, p.className]),
    items: items.map((li) => ({
      cls: li.className, code: li.dataset.code, liText: li.textContent,
      svgs: li.find((e) => e.tag === 'svg').map((s) => ({ hidden: s.attrs['aria-hidden'], viewBox: s.attrs.viewBox, parts: s.children.length, ns: s.ns })),
      text: li.find((e) => e.className === 'warn-text').map((e) => e.textContent).join(''),
    })),
  };
};
const r = {};
r.three = view(sheetWarnings({ instruction: 'age: child; texture: bright', warnings: %s }));
r.none = view(sheetWarnings({ instruction: 'age: adult', warnings: [] }));
const p = sheetPanel();
p.update({ instruction: 'a', warnings: %s });
p.update({ instruction: 'age: adult', warnings: [] });
r.repaint = view(p.node);
p.fail('no se pudo');
r.fail = p.node.find((e) => e.className.includes('sheet-fail')).map((e) => [e.textContent, e.hidden]);
r.failView = view(p.node);
// sin cambios: no se repinta (los nodos de la lista son los mismos)
const q = sheetPanel();
q.update({ instruction: 'x', warnings: %s });
const before = q.node.find((e) => e.tag === 'li');
q.update({ instruction: 'x', warnings: %s });
r.sameNodes = q.node.find((e) => e.tag === 'li').every((li, i) => li === before[i]);
q.update({ instruction: 'y', warnings: %s });
r.changedNodes = q.node.find((e) => e.tag === 'li').some((li, i) => li === before[i]);
out(r);
""" % ((json.dumps(self.WARNINGS),) * 5))
        locale = json.loads((UI.parent / "locales" / "es.json").read_text(encoding="utf-8"))
        three = got["three"]
        self.assertEqual(three["live"], [["status", "polite", 1]])  # la región viva envuelve el ul...
        self.assertEqual(three["ulRole"], [None])                    # ...y el ul conserva su semántica de lista
        self.assertEqual(three["pre"][0][0], "age: child; texture: bright")
        self.assertIn("mono", three["pre"][0][1])
        self.assertEqual([i["code"] for i in three["items"]], [w["code"] for w in self.WARNINGS])
        for item in three["items"]:
            self.assertEqual(len(item["svgs"]), 1, item["code"])  # un icono por aviso...
            svg = item["svgs"][0]
            self.assertEqual((svg["hidden"], svg["viewBox"], svg["ns"]), ("true", "0 0 24 24", "http://www.w3.org/2000/svg"))
            self.assertGreaterEqual(svg["parts"], 2)
            self.assertTrue(item["text"].strip(), item["code"])  # ...y su texto visible
        self.assertEqual(three["items"][0]["text"], locale["warning.sheet.age_missing"])
        self.assertIn('"child"', three["items"][1]["text"])
        self.assertIn("deep, resonant", three["items"][2]["text"])
        # sin avisos: un texto corto y ningún icono
        self.assertEqual(len(got["none"]["items"]), 1)
        self.assertEqual(got["none"]["items"][0]["liText"], "Sin avisos")
        self.assertEqual(got["none"]["items"][0]["svgs"], [])
        # repintar sustituye lo anterior, y fallar deja un aviso discreto sin tocar la lista
        self.assertEqual(len(got["repaint"]["items"]), 1)
        self.assertEqual(got["repaint"]["pre"][0][0], "age: adult")
        self.assertEqual(got["fail"], [["no se pudo", False]])
        # al fallar no queda la instrucción ni los avisos de la ficha anterior
        self.assertEqual(got["failView"]["pre"][0][0], "")
        self.assertEqual(got["failView"]["items"], [])
        self.assertTrue(got["sameNodes"])        # mismo resultado: no se repinta
        self.assertFalse(got["changedNodes"])    # resultado distinto: sí

    def test_sheet_panel_without_warnings_says_so(self):
        got = self.run_js(self.LOAD_LOCALE + self.FAKE_DOM + """
const { sheetWarnings } = await mod('js/components/sheet-warnings.js');
const r = {};
for (const lang of ['es', 'en']) {
  await i18n.load(lang);
  const node = sheetWarnings({ instruction: 'age: adult', warnings: [] });
  r[lang] = node.find((e) => e.tag === 'li').map((li) => li.textContent);
}
out(r);
""")
        self.assertEqual(got, {"es": ["Sin avisos"], "en": ["No warnings"]})

    def test_sheet_checker_skips_an_unchanged_sheet_and_retries_after_a_failure(self):
        got = self.run_js("""
const { createSheetChecker } = await mod('js/sheet-check.js');
const { sheetFromFields } = await mod('js/order-model.js');
const timers = new Map(); let nextId = 1;
const setTimer = (fn) => { const id = nextId++; timers.set(id, fn); return id; };
const clearTimer = (id) => timers.delete(id);
const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
const fire = async () => { const all = [...timers.values()]; timers.clear(); for (const f of all) f(); await flush(); };
const sent = []; let fail = true; const errors = [];
const checker = createSheetChecker({
  check: async (s) => { sent.push(s); if (fail) throw new Error('x'); return {}; },
  onResult: () => {}, onError: (e) => errors.push(e.message), setTimer, clearTimer,
});
checker.request({ age: 'a' }); await fire();            // primera: sale (y falla)
checker.request({ age: 'a' }); await fire();            // misma ficha tras el fallo: se reintenta
fail = false;
checker.request({ age: 'a' }); await fire();            // misma ficha que la última: no sale
checker.request({ age: 'a' }); checker.request({ age: 'a' }); await fire();
checker.request({ age: 'b' }); await fire();            // otra: sale
checker.cancel();
checker.request({ age: 'b' }); await fire();            // tras cancelar, sale de nuevo
// «extra» mal escrito: la ficha sin esas líneas se comprueba igual
const bad = sheetFromFields({ sheet: { age: 'adult' }, extra: 'sin dos puntos' });
out({ sent, errors, bad });
""")
        self.assertEqual(got["sent"], [{"age": "a"}, {"age": "a"}, {"age": "a"}, {"age": "b"}, {"age": "b"}])
        self.assertEqual(got["errors"], ["x", "x"])
        self.assertEqual(got["bad"]["sheet"], {"age": "adult"})  # sin `extra`, pero hay ficha que comprobar
        self.assertIsNotNone(got["bad"]["badLine"])

    def test_sheet_dialog_does_nothing_when_the_route_changed_while_loading(self):
        got = self.run_js(self.LOAD_LOCALE + self.FAKE_DOM + """
const { openSheetDialog } = await mod('js/components/sheet-dialog.js');
await i18n.load('es');
const appended = []; const toasts = [];
document.body.append = (n) => appended.push(n); // cuenta lo que se añade al cuerpo
const run = async (apiFn, alive) => {
  const before = appended.length;
  api.sheet = apiFn;
  const dlg = await openSheetDialog('p', 'k', { isAlive: () => alive });
  return { dlg: dlg === null, appended: appended.length - before };
};
const r = {};
r.deadOk = await run(async () => ({ instruction: 'a', warnings: [] }), false);
r.deadErr = await run(async () => { throw new Error('boom'); }, false);
const toast = await mod('js/components/toast.js');
out(r);
""")
        self.assertEqual(got["deadOk"], {"dlg": True, "appended": 0})
        self.assertEqual(got["deadErr"], {"dlg": True, "appended": 0})

    def test_sheet_checker_waits_and_drops_stale_responses(self):
        got = self.run_js("""
const { createSheetChecker, CHECK_DELAY_MS } = await mod('js/sheet-check.js');
const timers = new Map(); let nextId = 1;
const setTimer = (fn, ms) => { const id = nextId++; timers.set(id, { fn, ms }); return id; };
const clearTimer = (id) => timers.delete(id);
const flush = async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); };
const fire = async () => { const all = [...timers.values()]; timers.clear(); for (const t of all) t.fn(); await flush(); };
const pending = new Map(); // ficha → resolver
const results = []; const errors = [];
const checker = createSheetChecker({
  check: (s) => new Promise((res, rej) => pending.set(s.age, { res, rej })),
  onResult: (r) => results.push(r), onError: (e) => errors.push(e.message), setTimer, clearTimer,
});
const r = { delay: CHECK_DELAY_MS };
checker.request({ age: 'a' }); checker.request({ age: 'ab' });
r.debounced = timers.size; r.ms = [...timers.values()].map((t) => t.ms);   // dos pulsaciones, un solo temporizador
await fire();                                                             // sale la petición de «ab»
checker.request({ age: 'abc' });                                          // llega una más nueva mientras la anterior vuela
await fire();
pending.get('abc').res({ instruction: 'abc' });
await flush();
pending.get('ab').res({ instruction: 'ab' });                             // la vieja contesta tarde: se descarta
await flush();
r.results = results.map((x) => x.instruction);
checker.request({ age: 'x' }); await fire();
pending.get('x').rej(new Error('caído'));                                  // un fallo solo cuenta si es de la última
await flush();
r.errors = errors.slice();
checker.request({ age: 'y' }); await fire(); checker.cancel(); pending.get('y').res({ instruction: 'y' });
await flush();
r.afterCancel = results.map((x) => x.instruction);
out(r);
""")
        self.assertEqual(got["delay"], 300)
        self.assertEqual((got["debounced"], got["ms"]), (1, [300]))
        self.assertEqual(got["results"], ["abc"])
        self.assertEqual(got["errors"], ["caído"])
        self.assertEqual(got["afterCancel"], ["abc"])

    # ---- retro F5.3: async-guard.js y el DOM falso compartido ----

    def test_async_guard_latest_discards_old_responses_and_their_failures(self):
        got = self.run_js("""
const { latest, STALE } = await mod('js/async-guard.js');
const defer = () => { let res, rej; const p = new Promise((a, b) => { res = a; rej = b; }); return { p, res, rej }; };
const g = latest();
const a = defer(), b = defer();
const ra = g.run(a.p), rb = g.run(b.p);
b.res('nueva'); a.res('vieja');                    // la vieja contesta después de la nueva
const r = { newer: await rb, older: (await ra) === STALE };
const c = defer(), d = defer();
const rc = g.run(c.p).catch((e) => 'lanzó ' + e.message), rd = g.run(d.p);
c.rej(new Error('viejo')); d.res('ok');           // el fallo de una vieja no llega a nadie
r.oldFailure = (await rc) === STALE; r.afterOld = await rd;
const e = defer(); const re = g.run(e.p).catch((x) => 'lanzó ' + x.message);
e.rej(new Error('último'));                        // el de la última sí
r.lastFailure = await re;
const f = defer(); const rf = g.run(f.p); g.invalidate(); f.res('tarde');
r.invalidated = (await rf) === STALE;
out(r);
""")
        self.assertEqual(got, {"newer": "nueva", "older": True, "oldFailure": True, "afterOld": "ok",
                               "lastFailure": "lanzó último", "invalidated": True})

    def test_async_guard_busy_ignores_overlapping_calls_and_resets_after_a_throw(self):
        got = self.run_js("""
const { busy } = await mod('js/async-guard.js');
const defer = () => { let res; const p = new Promise((a) => { res = a; }); return { p, res }; };
const r = {};
let calls = 0; let gate = defer(); const changes = [];
const fn = busy(async (x) => { calls++; await gate.p; if (x === 'boom') throw new Error('boom'); return x; }, { onChange: (v) => changes.push(v) });
const first = fn('a'); const second = await fn('b');  // la segunda no hace nada mientras corre la primera
r.secondIgnored = second === undefined; r.activeWhileRunning = fn.active;
gate.res(); r.first = await first; r.calls = calls; r.activeAfter = fn.active;
gate = defer(); gate.res();
try { await fn('boom'); } catch (e) { r.threw = e.message; }
r.activeAfterThrow = fn.active;                        // la bandera se repone con `finally`
r.again = await fn('c');
r.changes = changes;
// `keep`: la bandera sigue puesta hasta `release()`
const held = busy(async () => 'dlg', { keep: (v) => v === 'dlg' });
await held(); r.heldActive = held.active; r.heldIgnored = (await held()) === undefined; held.release(); r.released = held.active;
const { lifetime } = await mod('js/async-guard.js');
const life = lifetime(); r.alive = life.alive(); life.end(); r.dead = life.alive();
out(r);
""")
        self.assertEqual(got["secondIgnored"], True)
        self.assertEqual((got["activeWhileRunning"], got["first"], got["calls"], got["activeAfter"]), (True, "a", 1, False))
        self.assertEqual((got["threw"], got["activeAfterThrow"], got["again"]), ("boom", False, "c"))
        self.assertEqual(got["changes"], [True, False, True, False, True, False])
        self.assertEqual((got["heldActive"], got["heldIgnored"], got["released"]), (True, True, False))
        self.assertEqual((got["alive"], got["dead"]), (True, False))

    def test_project_view_paints_nothing_after_cleanup_and_drops_old_filter_answers(self):
        got = self.run_js(self.LOAD_LOCALE + self.FAKE_DOM + """
const { projectView } = await mod('js/components/project-view.js');
await i18n.load('es');
const defer = () => { let res; const p = new Promise((a) => { res = a; }); return { p, res }; };
const order = (key) => ({ key, type: 'voice', testText: 'hola', attempts: [], chosen: null });
const rows = (v) => v.node.find((e) => e.className.includes('order-row')).map((e) => e.attrs['aria-label']);
api.project = async () => ({ root: '/x' });
const r = {};
// vista muerta: la respuesta llega después de `cleanup` y no pinta
let gate = defer(); api.orders = () => gate.p;
const dead = projectView({ project: 'p', query: {} });
await flushAll(); dead.cleanup(); gate.res([order('a')]); await flushAll();
r.deadRows = rows(dead); r.deadBusy = dead.node.find((e) => e.attrs['aria-busy'] !== undefined).map((e) => e.attrs['aria-busy']);
// viva: con dos peticiones seguidas solo vale la última
const gates = []; api.orders = () => { const g = defer(); gates.push(g); return g.p; };
const live = projectView({ project: 'p', query: {} });
await flushAll();
live.node.find((e) => e.attrs.id === 'f-type')[0].dispatchEvent('change');   // segunda petición
await flushAll();
gates[1].res([order('nuevo')]); await flushAll();
gates[0].res([order('viejo')]); await flushAll();
r.liveRows = rows(live);
out(r);
""")
        self.assertEqual(got["deadRows"], [])
        self.assertEqual(got["deadBusy"], ["true"])  # sigue «cargando»: nada lo repintó
        self.assertEqual(got["liveRows"], ["nuevo"])

    def test_new_order_voice_sheet_panel_follows_the_fields(self):
        got = self.run_js(self.LOAD_LOCALE + self.FAKE_DOM + """
const { openNewOrder } = await mod('js/components/new-order.js');
const { warningsOf } = await mod('mock/api-mock.js');
await i18n.load('es');
const timers = fakeTimers();
const checks = [];
api.project = async () => ({ config: { voices: {} } });
api.orders = async () => [];
api.checkSheet = async (s) => { checks.push(s); return { instruction: JSON.stringify(s), warnings: warningsOf(s) }; };
const dlg = await openNewOrder('p', {});
const codes = () => dlg.find((e) => e.tag === 'li' && e.dataset.code).map((li) => li.dataset.code);
const okShown = () => dlg.find((e) => e.className.includes('sheet-ok')).length;
const field = (id) => dlg.find((e) => e.attrs.id === id)[0];
const r = { open: dlg.open, inBody: dlg.isConnected };
await flushAll(); await timers.advance(300);
r.initial = codes();                                            // ficha vacía: ya avisa de la edad
field('no-sheet-age').type('child');
await timers.advance(299); r.beforeDelay = codes();             // aún no pasó la espera: nada cambia
await timers.advance(1); r.child = codes();
field('no-sheet-age').type('adult'); field('no-sheet-texture').type('bright');   // dos pulsaciones, una petición
await timers.advance(300); r.bright = codes(); r.callsSoFar = checks.length;
// una línea de «extra» mal escrita no rompe el panel: sigue actualizándose al cambiar la edad
field('no-extra').type('sin dos puntos');
field('no-sheet-texture').type('');
await timers.advance(300);
field('no-sheet-age').type('child');
await timers.advance(300);
r.withBadExtra = codes(); r.lastSheet = checks[checks.length - 1];
field('no-sheet-age').type('adult'); await timers.advance(300);
r.fixed = codes(); r.ok = okShown();
// cerrar cancela lo pendiente: nada se pide después
field('no-sheet-age').type('elderly'); const before = checks.length;
dlg.close(); await flushAll(); await timers.advance(1000);
r.afterClose = checks.length - before; r.removed = dlg.isConnected;
timers.restore();
out(r);
process.exit(0);
""")
        self.assertTrue(got["open"] and got["inBody"])
        self.assertEqual(got["initial"], ["sheet.age_missing"])
        self.assertEqual(got["beforeDelay"], ["sheet.age_missing"])
        self.assertEqual(got["child"], ["sheet.age_not_adult"])
        self.assertEqual(got["bright"], ["sheet.banned_word"])
        self.assertEqual(got["callsSoFar"], 3)  # inicial, «child», y una sola por las dos pulsaciones
        self.assertEqual(got["withBadExtra"], ["sheet.age_not_adult"])
        self.assertEqual(got["lastSheet"], {"age": "child"})  # la línea mal escrita queda fuera de la ficha
        self.assertEqual((got["fixed"], got["ok"]), ([], 1))
        self.assertEqual((got["afterClose"], got["removed"]), (0, False))

    def test_peaks_parity_between_simulator_and_python(self):
        """The simulator's peaksOf and gvoice.peaks must give the same peaks for the same Int16 samples."""
        import random
        from gvoice import peaks as pk
        rng = random.Random(7)
        cases = [
            [rng.randint(-32768, 32767) for _ in range(1000)],
            [rng.randint(-32768, 32767) for _ in range(1003)],          # L not divisible by n
            [0] * 7 + [-32768, 2048, 6144, 32767, 100, 1],              # L < n: empty buckets; half-way ties
            [2048 * k for k in range(-16, 16)] * 3,
        ]
        for n in (16, 400, 2000):
            for samples in cases:
                with self.subTest(n=n, length=len(samples)):
                    with tempfile.TemporaryDirectory() as tmp:
                        path = Path(tmp) / "a.wav"
                        with wave.open(str(path), "wb") as w:
                            w.setnchannels(1)
                            w.setsampwidth(2)
                            w.setframerate(24000)
                            w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
                        want = pk.peaks(path, n)["peaks"]
                    got = self.run_js(self.mock_script(f"""
const {{ peaksOf }} = await mod('mock/api-mock.js');
out(peaksOf(Int16Array.from({json.dumps(samples)}), {n}));
"""))
                    self.assertEqual(got, want)

    def test_api_mock_peaks_route_validates_n_like_python(self):
        got = self.run_js(self.mock_script("""
const list = (await call('GET', '/api/projects/example-world/orders')).json;
const o = (list.orders || list)[0];
const key = o.key;
const take = (await call('POST', `/api/projects/example-world/orders/${key}/attempts`, { count: 1 })).json;
const id = (take.attempts || take)[0].id;
const base = `/api/projects/example-world/orders/${key}/attempts/${id}/peaks`;
const r = {};
for (const q of ['', '?n=16', '?n=2000', '?n=15', '?n=2001', '?n=abc', '?n=', '?n=20.5']) {
  const x = await call('GET', base + q);
  r[q] = [x.status, x.code || x.json.peaks.length];
}
out(r);
"""))
        self.assertEqual(got, {"": [200, 400], "?n=16": [200, 16], "?n=2000": [200, 2000], "?n=15": [400, "api.bad_param"],
                               "?n=2001": [400, "api.bad_param"], "?n=abc": [400, "api.bad_param"],
                               "?n=": [400, "api.bad_param"], "?n=20.5": [400, "api.bad_param"]})

    def test_api_audio_url_without_transport_is_the_server_url(self):
        got = self.run_js("""
const store = new Map();
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const calls = [];
globalThis.fetch = async (...a) => { calls.push(a); throw new Error('no fetch expected'); };
const revoked = [];
globalThis.URL.revokeObjectURL = (u) => revoked.push(u);
const { api } = await mod('js/api.js');
const url = await api.audioUrl('mi mundo', 'narrator/x-1', 'a 1');
api.revokeAudioUrl(url); api.revokeAudioUrl('blob:abc'); api.revokeAudioUrl(null);
out({ url, calls: calls.length, revoked });
""")
        self.assertEqual(got["url"], "/api/projects/mi%20mundo/orders/narrator%2Fx-1/attempts/a%201/audio?lang=es")
        self.assertEqual(got["calls"], 0)
        self.assertEqual(got["revoked"], ["blob:abc"])

    def test_api_audio_url_with_transport_makes_an_object_url_and_raises_on_errors(self):
        got = self.run_js("""
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const made = [];
globalThis.URL.createObjectURL = (b) => { made.push(b.size); return 'blob:fake/' + made.length; };
const { api, setTransport, ApiError } = await mod('js/api.js');
const seen = [];
setTransport(async (method, url) => {
  seen.push([method, url]);
  if (url.includes('/missing/')) return { status: 404, json: { error: { code: 'api.not_found', message: 'nope' } } };
  return { status: 200, blob: new Blob(['abcd'], { type: 'audio/wav' }) };
});
const r = { url: await api.audioUrl('w', 'k', 'a1') };
try { await api.audioUrl('w', 'k', 'missing'); r.thrown = null; } catch (e) { r.thrown = [e instanceof ApiError, e.status, e.code]; }
r.seen = seen; r.made = made;
out(r);
""")
        self.assertEqual(got["url"], "blob:fake/1")
        self.assertEqual(got["made"], [4])
        self.assertEqual(got["seen"][0], ["GET", "/api/projects/w/orders/k/attempts/a1/audio?lang=es"])
        self.assertEqual(got["thrown"], [True, 404, "api.not_found"])

    def test_sheet_from_fields_ignores_empty_fields_and_reports_bad_extra(self):
        got = self.run_js("""
const m = await mod('js/order-model.js');
out([m.sheetFromFields({ sheet: { age: ' child ', texture: '', tone: 'calm' }, extra: 'breathing: audible' }),
     m.sheetFromFields({ sheet: {}, extra: 'sin dos puntos' }), m.sheetFromFields({})]);
""")
        self.assertEqual(got[0], {"sheet": {"age": "child", "tone": "calm", "extra": {"breathing": "audible"}}, "badLine": None})
        self.assertEqual(got[1]["sheet"], {})
        self.assertEqual(got[1]["badLine"], "sin dos puntos")
        self.assertEqual(got[2], {"sheet": {}, "badLine": None})


    # ---- F5.4: galería de tomas ----

    ORDER_ENV = FAKE_DOM + """
import { readFileSync } from 'node:fs';
const doc = globalThis.document;
const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)) };
globalThis.setInterval = () => 1;                       // la cola del simulador no avanza sola
globalThis.location = { origin: 'http://localhost', hash: '' };
const es = JSON.parse(readFileSync(new URL(UI + '/../locales/es.json').pathname, 'utf8'));
globalThis.fetch = async () => ({ json: async () => es });
const made = []; const revoked = [];
URL.createObjectURL = () => { const u = 'blob:t/' + (made.length + 1); made.push(u); return u; };
URL.revokeObjectURL = (u) => { revoked.push(u); };
const { api, setTransport, ApiError } = await mod('js/api.js');
const i18n = await mod('js/i18n.js');
const mock = await mod('mock/api-mock.js');
const seen = [];
setTransport(async (method, url, body) => { seen.push([method, url, body]); return mock.transport(method, url, body); });
await i18n.load('es');
doc.body.append(Object.assign(doc.createElement('div'), { attrs: { id: 'toasts' } }), Object.assign(doc.createElement('div'), { attrs: { id: 'alerts' } }));
const { orderView } = await mod('js/components/order-view.js');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, ms = 5000) => { const t0 = Date.now(); while (!fn()) { if (Date.now() - t0 > ms) throw new Error('timeout: ' + fn); await sleep(15); } };
const mount = async (key, query = {}) => {
  const view = orderView({ project: 'example-world', key, query });
  doc.body.append(view.node);
  await until(() => view.node.find((e) => e.tag === 'audio').length > 0 || view.node.textContent.includes('Este pedido aún no'));
  await until(() => view.node.find((e) => e.tag === 'audio').every((a) => a.src));
  return view;
};
const cards = (view) => view.node.find((e) => e.className.split(' ').includes('take-card'));
const cardOf = (view, id) => cards(view).find((c) => c.dataset.take === String(id));
const btn = (root, text) => root.find((e) => e.tag === 'button' && e.textContent.includes(text))[0];
const press = (key, target = doc.body) => target.dispatchEvent({ type: 'keydown', key });
const toasts = () => doc.getElementById('toasts').textContent;
const chosenIds = (view) => cards(view).filter((c) => c.classList.contains('is-chosen')).map((c) => c.dataset.take);
const audioOf = (view, id) => cardOf(view, id).find((e) => e.tag === 'audio')[0];
const shown = (view) => view.node.find((e) => e.className.includes('notice-warn') && e.textContent.includes('pone en cola sus huellas')).every((e) => !e.hidden);
const lastDraw = (card) => { const c = card.find((e) => e.tag === 'canvas')[0].getContext('2d').calls; return c.slice(c.map((x) => x[0]).lastIndexOf('clearRect')); };
"""

    def test_order_view_paints_voice_takes_with_state_prints_and_waveform(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator');
await until(() => lastDraw(cardOf(view, 2)).filter((c) => c[0] === 'fillRect').length > 2);
const text = (id) => cardOf(view, id).textContent;
const draw = lastDraw(cardOf(view, 2));
out({
  ids: cards(view).map((c) => c.dataset.take), chosen: chosenIds(view),
  head: view.node.children[0].textContent,
  chosenText: text(2).includes('Elegida'), chosenCheck: text(2).includes('✓'), otherChosenText: text(3).includes('Elegida'),
  discardedChip: text(1).includes('✗ Descartada'), candidateChip: text(2).includes('Candidata'),
  prints2: text(2).includes('0.6b-base: hecha') && text(2).includes('1.7b-base: hecha'), prints1: text(1).includes('0.6b-base: pendiente'),
  note: cardOf(view, 2).find((e) => e.tag === 'textarea')[0].value,
  peaksUrls: seen.filter((s) => s[1].includes('/peaks')).map((s) => s[1].split('?')[1]).slice(0, 3),
  bars: draw.filter((c) => c[0] === 'fillRect').length,
  choose: [1, 2, 3].map((id) => { const b = btn(cardOf(view, id), 'Elegir'); return [b.disabled, b.hidden]; }),
  panel: view.node.textContent.includes('Elegida: toma 2'), voiceNote: shown(view),
  undoDisabled: btn(view.node, 'Deshacer elección').disabled,
});
view.cleanup();
""")
        self.assertEqual(got["ids"], ["1", "2", "3"])
        self.assertEqual(got["chosen"], ["2"])
        self.assertIn("The law of the obelisks admits no exceptions.", got["head"])
        self.assertIn("narrator/intro-02", got["head"])  # frases desfasadas
        self.assertTrue(got["chosenText"] and got["chosenCheck"], "la elegida lleva visto y texto, no solo color")
        self.assertFalse(got["otherChosenText"])
        self.assertTrue(got["discardedChip"] and got["candidateChip"])
        self.assertTrue(got["prints2"] and got["prints1"])
        self.assertEqual(got["note"], "la mejor")
        self.assertEqual(got["peaksUrls"][0].split("&")[0], "n=75")  # 300 px de ancho / 4 px por barra
        self.assertEqual(got["bars"], 1 + 75)  # el fondo y una barra por cubo
        self.assertEqual(got["choose"], [[True, False], [True, True], [False, False]])  # descartada: apagado; elegida: oculto
        self.assertTrue(got["panel"] and got["voiceNote"])
        self.assertFalse(got["undoDisabled"])

    def test_order_view_line_shows_voice_and_stale_without_prints(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator/intro-02');
const fresh = await mount('narrator/intro-01');
out({ stale: view.node.textContent, fresh: fresh.node.textContent, voiceNote: shown(view) });
view.cleanup(); fresh.cleanup();
""")
        self.assertIn("Then the obelisks rose.", got["stale"])
        self.assertIn("voz narrator", got["stale"])
        self.assertIn("Desfasada", got["stale"])
        self.assertNotIn("Huellas", got["stale"])
        self.assertFalse(got["voiceNote"])
        self.assertNotIn("Desfasada", got["fresh"].split("Elección")[0])

    def test_choose_marks_the_take_with_text_and_queues_prints_then_undo_goes_back(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator');
btn(cardOf(view, 3), 'Elegir').click();
await until(() => chosenIds(view).join() === '3');
const r = {};
r.afterChoose = { chosen: chosenIds(view), text: cardOf(view, 3).textContent.includes('✓') && cardOf(view, 3).textContent.includes('Elegida'),
  old: cardOf(view, 2).textContent.includes('Elegida'), prints: cardOf(view, 3).textContent.includes('0.6b-base: en cola'),
  toast: toasts(), call: seen.filter((s) => s[1].includes('/choose')).map((s) => s[2]), panel: view.node.textContent.includes('Elegida: toma 3'),
  hint: view.node.textContent.includes('Vuelve a la toma 2') };
btn(view.node, 'Deshacer elección').click();
await until(() => chosenIds(view).join() === '2');
r.afterUndo = { chosen: chosenIds(view), toast: toasts(), calls: seen.filter((s) => s[1].includes('/undo')).length };
view.cleanup();
out(r);
""")
        a = got["afterChoose"]
        self.assertEqual(a["chosen"], ["3"])
        self.assertTrue(a["text"])
        self.assertFalse(a["old"])
        self.assertTrue(a["prints"], "elegir una toma de voz pone en cola sus huellas")
        self.assertIn("Toma 3 elegida", a["toast"])
        self.assertIn("huellas de la toma 3", a["toast"])
        self.assertEqual(a["call"], [{"attempt": 3}])
        self.assertTrue(a["panel"] and a["hint"])
        self.assertEqual(got["afterUndo"]["chosen"], ["2"])
        self.assertIn("vuelve la toma 2", got["afterUndo"]["toast"])
        self.assertEqual(got["afterUndo"]["calls"], 1)

    def test_server_409_shows_the_error_and_keeps_the_state(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator');
// un 409 de elegir (la toma cambió de estado en otro sitio): aviso con el mensaje del servidor y estado intacto
const real = api.choose;
api.choose = async () => { throw new ApiError(409, { error: { code: 'order.choose_discarded', message: 'el intento 3 está descartado y no se puede elegir' } }); };
btn(cardOf(view, 3), 'Elegir').click();
await until(() => toasts().includes('descartado'));
const r = { choose409: toasts(), chosen: chosenIds(view), alert: doc.getElementById('alerts').textContent };
api.choose = real; await sleep(500);   // la acción termina con la recarga del pedido
// deshacer hacia una toma descartada: 409 del simulador (order.undo_discarded)
btn(cardOf(view, 3), 'Elegir').click();
await until(() => chosenIds(view).join() === '3');
btn(cardOf(view, 2), 'Descartar').click();
await until(() => cardOf(view, 2).classList.contains('is-discarded'));
btn(view.node, 'Deshacer elección').click();
await until(() => toasts().includes('No se puede deshacer') || toasts().toLowerCase().includes('descartado y'));
r.undo409 = toasts(); r.chosenAfterUndo = chosenIds(view);
view.cleanup();
out(r);
""")
        self.assertIn("el intento 3 está descartado", got["choose409"])
        self.assertIn("el intento 3 está descartado", got["alert"])  # también en la región de alertas
        self.assertEqual(got["chosen"], ["2"])
        self.assertEqual(got["chosenAfterUndo"], ["3"])
        self.assertRegex(got["undo409"], "descartad")

    def test_keyboard_walks_plays_chooses_undoes_marks_and_ignores_text_fields(self):
        got = self.run_js(self.ORDER_ENV + """
const { initShortcuts } = await mod('js/components/shortcuts.js');
const view = await mount('narrator');
const r = {};
const tab = () => cards(view).map((c) => c.attrs.tabindex).join();
r.tab0 = tab();                                          // la elegida (2) es la actual
press('ArrowRight'); r.tab1 = tab(); r.focus3 = cardOf(view, 3).focused;
press('ArrowRight'); r.tabEnd = tab();                    // no pasa del final
press('ArrowLeft'); press('ArrowUp'); r.tabStart = tab();
press('ArrowDown'); press('ArrowDown'); r.back3 = tab();
press('p'); await until(() => !audioOf(view, 3).paused); r.playing3 = !audioOf(view, 3).paused;
press('ArrowLeft'); press(' '); await until(() => !audioOf(view, 2).paused);
r.exclusive = { two: !audioOf(view, 2).paused, three: audioOf(view, 3).paused };
press('Escape'); r.paused = audioOf(view, 2).paused;
// campos de texto: no disparan atajos
const note = cardOf(view, 2).find((e) => e.tag === 'textarea')[0];
note.dispatchEvent({ type: 'keydown', key: 'e' }); note.dispatchEvent({ type: 'keydown', key: 'ArrowRight' });
r.typing = { chosenCalls: seen.filter((s) => s[1].includes('/choose')).length, tab: tab() };
// Intro sobre un botón no reproduce
btn(cardOf(view, 2), 'Candidata'); press('Enter', btn(cardOf(view, 2), 'Reproducir')); r.enterOnButton = audioOf(view, 2).paused;
// elegir, marcar y deshacer con una tecla
press('ArrowRight'); press('e'); await until(() => chosenIds(view).join() === '3'); r.chose = chosenIds(view);
press('c'); await until(() => cardOf(view, 3).textContent.includes('Candidata') && cardOf(view, 3).find((e) => e.attrs['aria-pressed'] === 'true').length > 0);
r.candidate = cardOf(view, 3).textContent.includes('Candidata');
press('ArrowLeft'); press('ArrowLeft'); press('d'); await until(() => cardOf(view, 1).classList.contains('is-discarded') === false);
r.restored = !cardOf(view, 1).classList.contains('is-discarded');
press('u'); await until(() => chosenIds(view).join() === '2'); r.undone = chosenIds(view);
// sin atajos de una tecla: las letras no hacen nada, las flechas sí
store.set('gvoice.oneKey', 'off');
const before = seen.length; press('u'); press('e'); await sleep(50); r.letterCalls = seen.length - before;
press('ArrowRight'); r.arrowStill = tab();
store.delete('gvoice.oneKey');
// la ayuda: ? abre el diálogo y Esc lo cierra
initShortcuts(); press('?'); r.help = doc.body.find((e) => e.tag === 'dialog' && e.open).length;
doc.body.find((e) => e.tag === 'dialog')[0].dispatchEvent({ type: 'keydown', key: 'e' });
r.helpSwallows = seen.filter((s) => s[1].includes('/choose')).length;
view.cleanup();
out(r);
""", timeout=60)
        self.assertEqual(got["tab0"], "-1,0,-1")
        self.assertEqual((got["tab1"], got["focus3"]), ("-1,-1,0", 1))
        self.assertEqual(got["tabEnd"], "-1,-1,0")
        self.assertEqual(got["tabStart"], "0,-1,-1")
        self.assertEqual(got["back3"], "-1,-1,0")
        self.assertTrue(got["playing3"])
        self.assertEqual(got["exclusive"], {"two": True, "three": True})
        self.assertTrue(got["paused"])
        self.assertEqual(got["typing"], {"chosenCalls": 0, "tab": "-1,0,-1"})
        self.assertTrue(got["enterOnButton"])
        self.assertEqual(got["chose"], ["3"])
        self.assertTrue(got["candidate"])
        self.assertTrue(got["restored"])  # la 1 estaba descartada: «d» la recupera
        self.assertEqual(got["undone"], ["2"])
        self.assertEqual(got["letterCalls"], 0)
        self.assertEqual(got["arrowStill"], "-1,0,-1")  # de la 1 a la 2
        self.assertEqual(got["help"], 1)
        self.assertEqual(got["helpSwallows"], 1)  # la ayuda abierta no deja pasar «e» a la galería: sigue la única elección de antes

    def test_gamepad_buttons_walk_play_choose_and_undo(self):
        got = self.run_js(self.ORDER_ENV + """
const { padActions, startGamepad } = await mod('js/components/shortcuts.js');
const buttons = (n) => Array.from({ length: 17 }, (_, i) => ({ pressed: n.includes(i), value: n.includes(i) ? 1 : 0 }));
const r = { pure: [padActions([], buttons([0])), padActions([true], buttons([0])), padActions([], buttons([2, 3, 15, 12, 1]))].map((x) => x.actions) };
let pad = { connected: true, buttons: buttons([]) };
Object.defineProperty(globalThis, 'navigator', { value: { getGamepads: () => [null, pad] }, configurable: true });
const view = await mount('narrator');
const tab = () => cards(view).map((c) => c.attrs.tabindex).join();
const tap = async (n) => { pad = { connected: true, buttons: buttons(n) }; await sleep(160); pad = { connected: true, buttons: buttons([]) }; await sleep(160); };
await tap([15]); r.next = tab();                       // cruceta derecha
await tap([0]); await until(() => !audioOf(view, 3).paused); r.play = true;   // A
await tap([1]); r.pause = audioOf(view, 3).paused;    // B
await tap([2]); await until(() => chosenIds(view).join() === '3'); r.choose = chosenIds(view);   // X
await tap([3]); await until(() => chosenIds(view).join() === '2'); r.undo = chosenIds(view);     // Y
view.cleanup();
pad = { connected: true, buttons: buttons([15]) }; await sleep(250); r.afterCleanup = tab();
out(r);
""", timeout=60)
        self.assertEqual(got["pure"], [["toggle"], [], ["pause", "choose", "undo", "prev", "next"]])
        self.assertEqual(got["next"], "-1,-1,0")
        self.assertTrue(got["play"] and got["pause"])
        self.assertEqual(got["choose"], ["3"])
        self.assertEqual(got["undo"], ["2"])
        self.assertEqual(got["afterCleanup"], "-1,-1,0")  # tras limpiar, el mando ya no mueve nada

    def test_cleanup_revokes_audio_urls_and_leaves_no_listeners_or_late_paint(self):
        got = self.run_js(self.ORDER_ENV + """
const r = { base: doc.listenerCount() };
const view = await mount('narrator');
r.mounted = { listeners: doc.listenerCount(), made: made.length };
press('p'); await until(() => !audioOf(view, 2).paused);
const audio = audioOf(view, 2);
view.cleanup();
r.after = { listeners: doc.listenerCount(), revoked: [...revoked].sort(), made: [...made].sort(), paused: audio.paused };
// un audio que llega después de limpiar se revoca al llegar, y un pedido tardío no pinta
const gate = {}; const late = new Promise((res) => { gate.res = res; });
const realUrl = api.audioUrl; api.audioUrl = () => late;
const realOrder = api.order; const lateOrder = new Promise((res) => { gate.order = res; }); api.order = () => lateOrder;
const dead = orderView({ project: 'example-world', key: 'narrator', query: {} });
doc.body.append(dead.node);
const first = orderView({ project: 'example-world', key: 'orc', query: {} });
await sleep(20); dead.cleanup(); first.cleanup();
gate.order(await realOrder('example-world', 'narrator')); await sleep(300);
r.dead = { cards: dead.node.find((e) => e.className.split(' ').includes('take-card')).length, listeners: doc.listenerCount() };
// mismo caso con la vista viva pero con la URL en vuelo
api.order = realOrder;
const live = orderView({ project: 'example-world', key: 'orc', query: {} });
doc.body.append(live.node);
await until(() => live.node.find((e) => e.className.split(' ').includes('take-card')).length === 1);
const before = revoked.length;
live.cleanup(); gate.res('blob:late/1'); await sleep(50);
r.late = revoked.slice(before);
api.audioUrl = realUrl;
out(r);
""")
        self.assertEqual(got["base"], 0)
        self.assertEqual(got["mounted"]["made"], 3)
        self.assertEqual(got["mounted"]["listeners"], 1)  # solo el keydown de la vista
        self.assertEqual(got["after"]["listeners"], 0)
        self.assertEqual(got["after"]["revoked"], got["after"]["made"])
        self.assertTrue(got["after"]["paused"])
        self.assertEqual(got["dead"], {"cards": 0, "listeners": 0})
        self.assertEqual(got["late"], ["blob:late/1"])

    def test_waveform_seeks_by_click_and_keys_and_redraws_on_resize_and_theme(self):
        got = self.run_js(self.ORDER_ENV + """
const resizers = []; const mutators = [];
globalThis.ResizeObserver = class { constructor(fn) { this.fn = fn; this.off = false; resizers.push(this); } observe() {} disconnect() { this.off = true; } };
globalThis.MutationObserver = class { constructor(fn) { this.fn = fn; this.off = false; mutators.push(this); } observe(_n, o) { this.opts = o; } disconnect() { this.off = true; } };
const view = await mount('narrator');
await until(() => lastDraw(cardOf(view, 2)).filter((c) => c[0] === 'fillRect').length > 2);
const card = cardOf(view, 2);
const slider = card.find((e) => e.attrs.role === 'slider')[0];
const audio = audioOf(view, 2);
const draws = () => card.find((e) => e.tag === 'canvas')[0].getContext('2d').calls.filter((c) => c[0] === 'clearRect').length;
const r = { audioMs: 2600 + 2 * 450 };
slider.clientWidth = 400; slider.dispatchEvent({ type: 'click', clientX: 100 });
r.click = audio.currentTime;
let moved = false; slider.dispatchEvent({ type: 'keydown', key: 'ArrowRight' });   // ← →: la reproducción, no la toma
r.keyStep = audio.currentTime; r.tab = cards(view).map((c) => c.attrs.tabindex).join();
slider.dispatchEvent({ type: 'keydown', key: 'End' }); r.end = audio.currentTime;
slider.dispatchEvent({ type: 'keydown', key: 'Home' }); r.home = audio.currentTime;
r.now = slider.attrs['aria-valuenow'];
const draw = lastDraw(card);
audio.currentTime = r.audioMs / 2000; audio.dispatchEvent('timeupdate');
const half = lastDraw(card);
r.colors = { played: half.filter((c) => c[0] === 'set fillStyle').some((c) => c[1] === '#d9467a'), cursor: half.some((c) => c[0] === 'fillRect' && c[3] === 2) };
const n = draws(); resizers.forEach((o) => o.fn()); r.resize = draws() - n;
const m = draws(); mutators.forEach((o) => o.fn()); r.theme = draws() - m;
r.observes = mutators[0].opts.attributeFilter;
view.cleanup(); r.disconnected = [...resizers, ...mutators].every((o) => o.off);
out(r);
""")
        total = got["audioMs"] / 1000
        self.assertAlmostEqual(got["click"], total * 0.25, places=3)  # 100 de 400 px
        self.assertAlmostEqual(got["keyStep"], total * 0.30, places=3)
        self.assertEqual(got["tab"], "-1,0,-1")  # la flecha no cambió de toma
        self.assertAlmostEqual(got["end"], total, places=3)
        self.assertEqual(got["home"], 0)
        self.assertTrue(got["colors"]["played"] and got["colors"]["cursor"])
        self.assertGreaterEqual(got["resize"], 1)
        self.assertGreaterEqual(got["theme"], 1)
        self.assertEqual(got["observes"], ["data-theme"])
        self.assertTrue(got["disconnected"])

    def test_note_state_and_more_takes_actions(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator');
const r = {};
const box = cardOf(view, 3).find((e) => e.tag === 'textarea')[0];
r.saveDisabled = btn(cardOf(view, 3), 'Guardar nota').disabled;
box.type('mejor que la dos'); r.saveEnabled = !btn(cardOf(view, 3), 'Guardar nota').disabled;
btn(cardOf(view, 3), 'Guardar nota').click();
await until(() => seen.some((s) => s[1].includes('/attempts/3/note')));
await until(() => btn(cardOf(view, 3), 'Guardar nota').disabled);
r.noteCall = seen.filter((s) => s[1].includes('/note')).map((s) => s[2]);
r.noteToast = toasts();
btn(cardOf(view, 3), 'Candidata').click();
await until(() => cardOf(view, 3).textContent.includes('Candidata') && btn(cardOf(view, 3), 'Candidata').attrs['aria-pressed'] === 'true');
btn(cardOf(view, 3), 'Candidata').click();
await until(() => btn(cardOf(view, 3), 'Candidata').attrs['aria-pressed'] === 'false');
r.marks = seen.filter((s) => s[1].includes('/mark')).map((s) => s[2]);
r.discardOnChosen = btn(cardOf(view, 2), 'Descartar').disabled;
// más tomas
view.node.find((e) => e.attrs.id === 'more-count')[0].value = '2';
btn(view.node, 'Pedir más tomas').click();
await until(() => view.node.textContent.includes('Tomas en la cola: 2'));
r.more = { call: seen.filter((s) => s[0] === 'POST' && /\\/attempts\\?/.test(s[1])).map((s) => s[2]), toast: toasts() };
view.cleanup();
out(r);
""")
        self.assertTrue(got["saveDisabled"] and got["saveEnabled"])
        self.assertEqual(got["noteCall"], [{"text": "mejor que la dos"}])
        self.assertIn("Nota de la toma 3 guardada", got["noteToast"])
        self.assertEqual(got["marks"], [{"state": "candidate"}, {"state": "new"}])
        self.assertTrue(got["discardOnChosen"])
        self.assertEqual(got["more"]["call"], [{"count": 2}])
        self.assertIn("2 tomas en la cola", got["more"]["toast"])

    # ---- F5.4: arreglos de la revisión del bloque ----

    LOOSE = """
const mountLoose = async (key, query = {}) => {   // no espera al audio: para los tests que lo retienen o lo rompen a propósito
  const view = orderView({ project: 'example-world', key, query });
  doc.body.append(view.node);
  await until(() => cards(view).length > 0);
  return view;
};
"""

    def test_a_refresh_that_cancels_the_first_load_still_mounts_the_gallery_with_the_models(self):
        got = self.run_js(self.ORDER_ENV + """
const realOrder = api.order; let calls = 0;
api.order = (...a) => (++calls === 1 ? new Promise(() => {}) : realOrder(...a));   // el primer GET no vuelve
api.undo = async () => ({ new: null });
const view = orderView({ project: 'example-world', key: 'narrator', query: {} });
doc.body.append(view.node);
await sleep(20);
press('u');   // deshacer antes de que vuelva la primera carga: su refresh la cancela
await until(() => cards(view).length === 3 || view.node.textContent.includes('Cargando') === false);
await sleep(20);
out({ cards: cards(view).length, loading: view.node.textContent.includes('Cargando'), prints: cardOf(view, 2) ? cardOf(view, 2).textContent.includes('0.6b-base: hecha') : null });
view.cleanup();
""")
        self.assertEqual(got, {"cards": 3, "loading": False, "prints": True})

    def test_polling_goes_on_after_a_failed_order_or_queue_request_and_stops_with_the_view(self):
        got = self.run_js(self.ORDER_ENV + """
const realST = globalThis.setTimeout; const waits = [];
globalThis.setTimeout = (fn, ms, ...a) => { if (ms >= 3000) { if (ms !== 10000) waits.push(ms);   // 10000 = el aviso de error; el resto, sondeos
     return realST(fn, 5); } return realST(fn, ms, ...a); };   // los sondeos, sin esperar
const realOrder = api.order; let calls = 0; let queueCalls = 0;
api.order = (...a) => { calls++; return calls === 2 ? Promise.reject(new Error('boom')) : realOrder(...a); };
const open = [{ id: 9, kind: 'line', project: 'example-world', key: 'narrator', state: 'queued', seed: 1 }];
api.queue = async () => { queueCalls++; if (queueCalls === 3) throw new Error('queue down'); return open; };
const view = orderView({ project: 'example-world', key: 'narrator', query: {} });
doc.body.append(view.node);
await until(() => calls >= 5);
const r = { calls: calls >= 5, waits: waits.slice(0, 4), cards: cards(view).length };
view.cleanup();
const after = calls; await sleep(100);
r.stoppedWithView = calls === after;
out(r);
""")
        self.assertTrue(got["calls"], "el sondeo sigue tras un fallo del pedido y de la cola")
        self.assertEqual(got["waits"][0], 3000)
        self.assertEqual(got["waits"][1], 6000)  # tras un fallo, espera creciente
        self.assertEqual(got["cards"], 3)
        self.assertTrue(got["stoppedWithView"])

    def test_a_take_that_receives_its_audio_in_a_later_refresh_gets_its_waveform(self):
        got = self.run_js(self.ORDER_ENV + self.LOOSE + """
const real = api.order; let phase = 0;
api.order = async (...a) => { const o = structuredClone(await real(...a)); if (!phase) delete o.attempts[0].audioMs; return o; };
api.newTakes = async () => [];
const view = await mountLoose('narrator');
await until(() => audioOf(view, 2).src);
const peaks1 = () => seen.filter((s) => s[1].includes('/attempts/1/peaks')).length;
const r = { before: { src: audioOf(view, 1).src || null, peaks: peaks1() } };
phase = 1; press('g');
await until(() => audioOf(view, 1).src, 3000);
r.after = { src: audioOf(view, 1).src, peaks: peaks1() };
view.cleanup();
out(r);
""")
        self.assertEqual(got["before"], {"src": None, "peaks": 0})
        self.assertTrue(got["after"]["src"])
        self.assertEqual(got["after"]["peaks"], 1)

    def test_merge_sources_drops_the_same_press_arriving_by_key_and_by_pad(self):
        got = self.run_js("""
const { mergeSources } = await mod('js/components/shortcuts.js');
let t = 1000; const seen = [];
const m = mergeSources((a) => seen.push(a), { now: () => t });
m.key('toggle'); t += 100; m.pad('toggle');       // the same press, 100 ms later by the other source: dropped
t += 50; m.key('toggle');                          // the same source repeating (auto-repeat): kept
t += 100; m.pad('toggle');                         // 100 ms after the last key: dropped
t += 300; m.pad('toggle');                         // a new press: kept
t += 10; m.pad('choose');                          // another action: kept
out(seen);
""")
        self.assertEqual(got, ["toggle", "toggle", "toggle", "choose"])

    def test_a_pad_press_that_also_arrives_as_a_key_acts_once(self):
        got = self.run_js(self.ORDER_ENV + """
const buttons = (n) => Array.from({ length: 17 }, (_, i) => ({ pressed: n.includes(i), value: n.includes(i) ? 1 : 0 }));
let pad = { connected: true, buttons: buttons([]) };
Object.defineProperty(globalThis, 'navigator', { value: { getGamepads: () => [pad] }, configurable: true });
const view = await mount('narrator');
press('ArrowRight');                                   // la toma 3
pad = { connected: true, buttons: buttons([0]) };      // A: reproducir...
press('Enter', doc.body);                              // ...y Steam Input manda además Intro
await until(() => !audioOf(view, 3).paused);
await sleep(400);                                      // el sondeo del mando ve A; si no se deduplica, pausa
const r = { playing: !audioOf(view, 3).paused };
pad = { connected: true, buttons: buttons([]) };
view.cleanup();
out(r);
""", timeout=60)
        self.assertTrue(got["playing"])

    def test_the_gamepad_respects_text_fields_and_open_dialogs_like_the_keyboard(self):
        got = self.run_js(self.ORDER_ENV + """
const { openHelp } = await mod('js/components/shortcuts.js');
const buttons = (n) => Array.from({ length: 17 }, (_, i) => ({ pressed: n.includes(i), value: n.includes(i) ? 1 : 0 }));
let pad = { connected: true, buttons: buttons([]) };
Object.defineProperty(globalThis, 'navigator', { value: { getGamepads: () => [pad] }, configurable: true });
const view = await mount('narrator');
const tap = async (n) => { pad = { connected: true, buttons: buttons(n) }; await sleep(160); pad = { connected: true, buttons: buttons([]) }; await sleep(160); };
const chooses = () => seen.filter((s) => s[1].includes('/choose')).length;
await tap([15]);                                      // la toma 3
cardOf(view, 3).find((e) => e.tag === 'textarea')[0].focus();
await tap([2]); const r = { typing: chooses() };      // X con el foco en la nota
doc.activeElement = null;
openHelp(); await tap([2]); r.dialog = chooses();     // X con la ayuda abierta
doc.body.find((e) => e.tag === 'dialog')[0].close(); await sleep(20); doc.activeElement = null;
await tap([2]); await until(() => chosenIds(view).join() === '3'); r.free = chooses();
view.cleanup();
out(r);
""", timeout=60)
        self.assertEqual(got, {"typing": 0, "dialog": 0, "free": 1})

    def test_a_note_typed_while_saving_stays_dirty_and_is_not_overwritten(self):
        got = self.run_js(self.ORDER_ENV + """
let release; api.note = (_p, _k, id, text) => new Promise((res) => { release = () => res({ id, note: text }); });
const view = await mount('narrator');
const card = cardOf(view, 3); const box = card.find((e) => e.tag === 'textarea')[0];
box.type('a'); btn(card, 'Guardar nota').click();
await until(() => release);
box.type('ab');                                        // se teclea mientras se guarda
release(); await sleep(30);
const r = { value: box.value, saveDisabled: btn(card, 'Guardar nota').disabled };
btn(card, 'Candidata').click();                         // repinta la tarjeta (update)
await until(() => btn(cardOf(view, 3), 'Candidata').attrs['aria-pressed'] === 'true');
r.afterUpdate = box.value;
view.cleanup();
out(r);
""")
        self.assertEqual(got, {"value": "ab", "saveDisabled": False, "afterUpdate": "ab"})

    def test_keyboard_choose_follows_the_same_guards_as_the_button(self):
        got = self.run_js(self.ORDER_ENV + """
const view = await mount('narrator');
press('ArrowLeft');                                    // la toma 1, descartada: «Elegir» está desactivado
press('e'); await sleep(60);
const r = { chooseCalls: seen.filter((s) => s[1].includes('/choose')).length, chosen: chosenIds(view) };
view.cleanup();
out(r);
""")
        self.assertEqual(got, {"chooseCalls": 0, "chosen": ["2"]})

    def test_keyboard_marks_ignore_a_second_press_while_one_is_in_flight(self):
        got = self.run_js(self.ORDER_ENV + """
const marks = []; let release;
api.mark = (_p, _k, id, state) => { marks.push(state); return new Promise((res) => { release = () => res({ id, state }); }); };
const view = await mount('narrator');
press('ArrowRight');                                   // la toma 3 (nueva)
press('c'); press('c'); press('d');                    // C dos veces y D, con la primera en vuelo
await sleep(30);
const r = { inFlight: marks.slice() };
release(); await sleep(30);
press('c'); await sleep(30);                            // ya con el estado vuelto: la candidata se quita
r.after = marks.slice();
release(); await sleep(20);
view.cleanup();
out(r);
""")
        self.assertEqual(got["inFlight"], ["candidate"])
        self.assertEqual(got["after"], ["candidate", "new"])  # la respuesta ya aplicada: C quita la marca

    def test_a_mark_answer_lands_on_the_current_take_after_a_concurrent_refresh(self):
        got = self.run_js(self.ORDER_ENV + """
let release; api.mark = (_p, _k, id, state) => new Promise((res) => { release = () => res({ id, state }); });
api.undo = async () => ({ new: null });
const realOrder = api.order; let orders = 0; api.order = async (...a) => { const o = structuredClone(await realOrder(...a)); orders++; return o; };   // un pedido nuevo en cada GET, como el de la red
const realQueue = api.queue; let queues = 0; api.queue = async (...a) => { const q = await realQueue(...a); queues++; return q; };
const view = await mount('narrator');
btn(cardOf(view, 3), 'Candidata').click();
await until(() => release);
const [o0, q0] = [orders, queues];
press('u');                                            // un refresh trae un pedido nuevo mientras vuelve la marca
await until(() => orders > o0 && queues > q0); await sleep(30);   // ya pintado
release();
await sleep(60);
const r = { pressed: btn(cardOf(view, 3), 'Candidata').attrs['aria-pressed'], chip: cardOf(view, 3).textContent.includes('Candidata') };
view.cleanup();
out(r);
""")
        self.assertEqual(got["pressed"], "true")

    def test_a_failed_audio_url_can_be_retried_and_a_peaks_failure_does_not_hide_it(self):
        got = self.run_js(self.ORDER_ENV + self.LOOSE + """
const realUrl = api.audioUrl; let ok = false; let calls = 0;
api.audioUrl = async (...a) => { calls++; if (!ok) throw new Error('no url'); return realUrl(...a); };
api.peaks = async () => { throw new Error('no peaks'); };
const view = await mountLoose('narrator');
await sleep(60);
const status = () => cardOf(view, 2).find((e) => e.className.includes('take-status'))[0].textContent;
const r = { status: status() };
ok = true; btn(cardOf(view, 2), 'Reproducir').click();
await until(() => !audioOf(view, 2).paused, 3000);
r.retried = { src: Boolean(audioOf(view, 2).src), status: status(), calls: calls > 3 };
view.cleanup();
out(r);
""")
        self.assertIn("No se pudo cargar el audio", got["status"])
        self.assertNotIn("forma de onda", got["status"])
        self.assertTrue(got["retried"]["src"] and got["retried"]["calls"])
        self.assertEqual(got["retried"]["status"], "")

    def test_a_seek_before_the_first_play_is_applied_when_the_audio_loads(self):
        got = self.run_js(self.ORDER_ENV + self.LOOSE + """
const realUrl = api.audioUrl; const rel = {};
api.audioUrl = (p, k, id) => new Promise((res) => { rel[id] = async () => res(await realUrl(p, k, id)); });
const view = await mountLoose('narrator');
const audio = audioOf(view, 2);
let t = 0; let src = '';   // como un navegador: asignar `src` reinicia la posición; sin `src`, una posición no se guarda
Object.defineProperty(audio, 'src', { get: () => src, set: (v) => { src = v; t = 0; } });
Object.defineProperty(audio, 'currentTime', { get: () => t, set: (v) => { if (src) t = v; } });
const slider = cardOf(view, 2).find((e) => e.attrs.role === 'slider')[0];
slider.dispatchEvent({ type: 'click', clientX: 150 });   // la mitad de 300 px, antes de reproducir
const r = { shown: slider.attrs['aria-valuenow'] };
await until(() => rel[2]); await rel[2](); await until(() => audio.src);
audio.dispatchEvent('loadedmetadata');
r.applied = audio.currentTime; r.total = 2600 + 2 * 450;
view.cleanup();
out(r);
""")
        self.assertEqual(got["shown"], "50")
        self.assertAlmostEqual(got["applied"], got["total"] / 2000, places=3)

    def test_playback_progress_only_repaints_without_measuring_again(self):
        got = self.run_js(self.ORDER_ENV + """
let styles = 0;
globalThis.getComputedStyle = () => { styles++; return { getPropertyValue: () => '' }; };
const resizers = []; globalThis.ResizeObserver = class { constructor(fn) { this.fn = fn; resizers.push(this); } observe() {} disconnect() {} };
const view = await mount('narrator');
await until(() => [1, 2, 3].every((id) => lastDraw(cardOf(view, id)).filter((c) => c[0] === 'fillRect').length > 2));
await sleep(50);
const card = cardOf(view, 2); const audio = audioOf(view, 2);
const clears = () => card.find((e) => e.tag === 'canvas')[0].getContext('2d').calls.filter((c) => c[0] === 'clearRect').length;
const r = { styles0: styles }; const c0 = clears();
for (let i = 1; i <= 20; i++) { audio.currentTime = i / 10; audio.dispatchEvent('timeupdate'); }
r.styles = styles - r.styles0; r.repaints = clears() - c0;
resizers.forEach((o) => o.fn()); r.afterResize = styles - r.styles0;   // un cambio de tamaño sí recalcula
view.cleanup();
out(r);
""")
        self.assertEqual(got["styles"], 0)
        self.assertGreaterEqual(got["repaints"], 20)
        self.assertGreater(got["afterResize"], 0)

    def test_question_mark_help_respects_the_one_key_switch(self):
        got = self.run_js(self.ORDER_ENV + """
const { initShortcuts } = await mod('js/components/shortcuts.js');
initShortcuts();
const open = () => doc.body.find((e) => e.tag === 'dialog' && e.open).length;
store.set('gvoice.oneKey', 'off'); press('?'); const r = { off: open() };
store.delete('gvoice.oneKey'); press('?'); r.on = open();
out(r);
""")
        self.assertEqual(got, {"off": 0, "on": 1})

    def test_take_model_helpers(self):
        got = self.run_js("""
const m = await mod('js/take-model.js');
const { keyAction } = await mod('js/components/shortcuts.js');
const order = { chosen: 2, chosenHistory: [null, 1] };
const takes = [{ id: 1, state: 'discarded', audioMs: 10 }, { id: 2, state: 'candidate', audioMs: 10 }, { id: 3, state: 'new' }, { id: 4, state: 'new', audioMs: 5 }];
const entries = [{ kind: 'prints', take: 4, state: 'running' }, { kind: 'prints', take: 3, state: 'queued' }, { kind: 'line', state: 'queued' }];
out({
  states: takes.map((t) => m.takeState(order, t)), canChoose: takes.map((t) => m.canChoose(order, t)),
  undo: [m.undoTarget(order), m.undoTarget({ chosenHistory: [null] }), m.undoTarget({ chosenHistory: [] }), m.undoTarget({})],
  prints: m.printStates({ id: 4, prints: { a: {} } }, ['a', 'b'], entries), printsQueued: m.printStates({ id: 3 }, ['a'], entries),
  open: m.openEntries([{ project: 'p', key: 'k', state: 'queued' }, { project: 'p', key: 'k', state: 'done' }, { project: 'p', key: 'x', state: 'running' }], 'p', 'k').length,
  pending: m.pendingTakes(entries),
  buckets: [m.bucketsFor(0), m.bucketsFor(300), m.bucketsFor(20), m.bucketsFor(100000)],
  resample: [m.resample([0.1, 0.9, 0.2, 0.4], 2), m.resample([0.5], 3), m.resample([], 3)],
  rects: m.barRects([0, 0.5, 1], 12, 64), fraction: [m.fractionAt(150, { left: 50, width: 200 }), m.fractionAt(0, { left: 50, width: 200 }), m.fractionAt(999, { left: 50, width: 200 }), m.fractionAt(5, { left: 0, width: 0 })],
  keys: [keyAction({ key: 'ArrowRight' }), keyAction({ key: 'E' }), keyAction({ key: 'e' }, false), keyAction({ key: 'Enter' }, false), keyAction({ key: 'e', ctrlKey: true }), keyAction({ key: ' ' }), keyAction({ key: 'z' })],
});
""")
        self.assertEqual(got["states"], ["discarded", "chosen", "new", "new"])
        self.assertEqual(got["canChoose"], [False, False, False, True])  # descartada, ya elegida, sin audio, buena
        self.assertEqual(got["undo"], [1, None, None, None])
        self.assertEqual(got["prints"], [{"model": "a", "status": "done"}, {"model": "b", "status": "running"}])
        self.assertEqual(got["printsQueued"], [{"model": "a", "status": "queued"}])
        self.assertEqual((got["open"], got["pending"]), (1, 1))
        self.assertEqual(got["buckets"], [120, 75, 16, 2000])
        self.assertEqual(got["resample"], [[0.9, 0.4], [0.5, 0.5, 0.5], []])
        self.assertEqual(got["rects"], [{"x": 0, "y": 32, "w": 3, "h": 1}, {"x": 4, "y": 16, "w": 3, "h": 32}, {"x": 8, "y": 0, "w": 3, "h": 64}])
        self.assertEqual(got["fraction"], [0.5, 0, 1, 0])
        self.assertEqual(got["keys"], ["next", "choose", None, "toggle", None, "toggle", None])

    # ---- F5.5: comparación A/B ----

    def test_compare_model_picks_the_pair_and_the_switch_point(self):
        got = self.run_js("""
const { pickPair, switchPoint } = await mod('js/compare-model.js');
const t = (id, audioMs = 1000) => (audioMs === null ? { id } : { id, audioMs });
const order = (chosen, ...attempts) => ({ chosen, attempts });
const four = order(3, t(1), t(2, null), t(3), t(4));
out({
  noQuery: pickPair(four, {}), validQuery: pickPair(four, { a: '4', b: '1' }), onlyA: pickPair(four, { a: '4' }), onlyB: pickPair(four, { b: '4' }),
  invalid: pickPair(four, { a: '2', b: '99' }), notNumbers: pickPair(four, { a: 'x', b: '' }), same: pickPair(four, { a: '1', b: '1' }),
  noChosen: pickPair(order(null, t(5), t(6)), {}), chosenNoAudio: pickPair(order(2, t(1), t(2, null), t(3)), {}),
  chosenFirstAudioB: pickPair(order(1, t(1), t(2)), {}), undefQuery: pickPair(four), unsorted: pickPair(order(null, t(9), t(7)), {}),
  oneAudio: pickPair(order(1, t(1), t(2, null)), {}), none: pickPair(order(null), {}), noAttempts: pickPair({ chosen: null }, {}), nullOrder: pickPair(null, {}),
  sp: [switchPoint(1.25, 3), switchPoint(1.25, 1), switchPoint(1.25, 1.25), switchPoint(-2, 3), switchPoint(NaN, 3), switchPoint(2, NaN), switchPoint(2, undefined), switchPoint(0, 0)],
});
""")
        self.assertEqual(got["noQuery"], {"a": 3, "b": 1})            # a = la elegida (con audio); b = la primera otra
        self.assertEqual(got["validQuery"], {"a": 4, "b": 1})
        self.assertEqual(got["onlyA"], {"a": 4, "b": 1})
        self.assertEqual(got["onlyB"], {"a": 3, "b": 4})
        self.assertEqual(got["invalid"], {"a": 3, "b": 1})            # 2 no tiene audio, 99 no existe
        self.assertEqual(got["notNumbers"], {"a": 3, "b": 1})
        self.assertEqual(got["same"], {"a": 1, "b": 3})               # a == b: b se busca otra
        self.assertEqual(got["noChosen"], {"a": 5, "b": 6})
        self.assertEqual(got["chosenNoAudio"], {"a": 1, "b": 3})
        self.assertEqual(got["chosenFirstAudioB"], {"a": 1, "b": 2})
        self.assertEqual(got["undefQuery"], {"a": 3, "b": 1})
        self.assertEqual(got["unsorted"], {"a": 7, "b": 9})
        for k in ("oneAudio", "none", "noAttempts", "nullOrder"):
            self.assertIsNone(got[k], k)
        self.assertEqual(got["sp"], [{"pos": 1.25, "atEnd": False}, {"pos": 1, "atEnd": True}, {"pos": 1.25, "atEnd": True},
                                     {"pos": 0, "atEnd": False}, {"pos": 0, "atEnd": False}, {"pos": 2, "atEnd": False},
                                     {"pos": 2, "atEnd": False}, {"pos": 0, "atEnd": True}])

    def test_router_compare_route_with_a_key_that_has_slashes(self):
        got = self.run_js("""
const { parse, to } = await mod('js/router.js');
const key = 'narrator/intro-01';
const hash = to.compare('mi mundo', key, 3, 5);
out({ hash, parsed: parse(hash), bare: to.compare('p', key), onlyA: to.compare('p', key, 2), plain: parse('#/p/mundo/o/narrator%2Fintro-01'),
  typed: parse('#/p/mundo/o/k/ab'), wrongTail: parse('#/p/mundo/o/k/ab/x').name });
""")
        self.assertEqual(got["hash"], "#/p/mi%20mundo/o/narrator%2Fintro-01/ab?a=3&b=5")
        self.assertEqual(got["parsed"], {"name": "compare", "project": "mi mundo", "key": "narrator/intro-01", "query": {"a": "3", "b": "5"}})
        self.assertEqual((got["bare"], got["onlyA"]), ("#/p/p/o/narrator%2Fintro-01/ab", "#/p/p/o/narrator%2Fintro-01/ab?a=2"))
        self.assertEqual(got["plain"]["name"], "order")
        self.assertEqual((got["typed"]["name"], got["typed"]["query"]), ("compare", {}))
        self.assertEqual(got["wrongTail"], "order")  # lo que no es «ab» sigue siendo el pedido, como antes

    def test_swap_is_x_and_the_shoulder_buttons_and_is_in_the_help(self):
        got = self.run_js(self.FAKE_DOM + """
const { keyAction, padActions, SHORTCUTS } = await mod('js/components/shortcuts.js');
const buttons = (n) => Array.from({ length: 17 }, (_, i) => ({ pressed: n.includes(i), value: 0 }));
const labels = SHORTCUTS.map(([g, items]) => [g, items.filter(([, l]) => l === 'ui.shortcuts.swap').map(([k]) => k)]);
out({ x: keyAction({ key: 'x' }), X: keyAction({ key: 'X' }), noLetters: keyAction({ key: 'x' }, false), ctrl: keyAction({ key: 'x', ctrlKey: true }),
  arrows: keyAction({ key: 'ArrowRight' }, false), pad: [4, 5, 6].map((i) => padActions([], buttons([i])).actions), labels });
""")
        self.assertEqual((got["x"], got["X"], got["noLetters"], got["ctrl"]), ("swap", "swap", None, None))
        self.assertEqual(got["arrows"], "next")
        self.assertEqual(got["pad"], [["swap"], ["swap"], []])
        self.assertEqual(got["labels"], [["ui.shortcuts.group.global", []], ["ui.shortcuts.group.gallery", [["X"]]], ["ui.shortcuts.group.pad", [["LB", "RB"]]]])

    def test_queue_model_counts_pill_cancel_clear_visible_and_error(self):
        got = self.run_js("""
const m = await mod('js/queue-model.js');
const E = (id, state, extra = {}) => ({ id, state, kind: 'line', project: 'a', key: 'k', ...extra });
const es = [E(0, 'failed', { error: { code: 'engine.failed', params: { message: 'x' } } }), E(3, 'queued', { project: 'b' }), E(1, 'running'), E(2, 'queued'), E(4, 'done'), E(5, 'cancelled'), E(6, 'bogus')];
out({
  counts: m.counts(es), none: m.counts(null), pill: m.pillParts(es), idle: m.pillParts([E(9, 'done')]),
  cancel: es.map((e) => m.canCancel(e)), cancelNull: m.canCancel(null),
  clearAll: m.clearable(es).map((e) => e.id), clearB: m.clearable(es, 'b').map((e) => e.id),
  all: m.visible(es, 'all').map((e) => e.id), pending: m.visible(es, 'pending').map((e) => e.id),
  failed: m.visible(es, 'failed').map((e) => e.id), done: m.visible(es, 'done').map((e) => e.id),
  errText: m.errorOf(E(7, 'failed', { errorText: 'ya traducido', error: { code: 'x' } })),
  errKey: m.errorOf(es[0], (k, p) => k + ':' + p.message), errNone: m.errorOf(E(8, 'failed')), errNoKey: m.errorOf(E(8, 'failed', { error: { code: 'weird.code' } }), () => null), errNotFailed: m.errorOf(E(8, 'done', { errorText: 'x' })),
});
""")
        self.assertEqual(got["counts"], {"running": 1, "queued": 2, "done": 1, "failed": 1, "cancelled": 1})
        self.assertEqual(got["none"]["queued"], 0)
        self.assertEqual(got["pill"], {"running": 1, "queued": 2, "idle": False})
        self.assertTrue(got["idle"]["idle"])
        self.assertEqual(got["cancel"], [False, True, True, True, False, False, False])
        self.assertFalse(got["cancelNull"])
        self.assertEqual((got["clearAll"], got["clearB"]), ([3, 2], [3]))  # lo que corre no se vacía
        self.assertEqual(got["pending"], [1, 2, 3])
        self.assertEqual((got["failed"], got["done"]), ([0], [4]))
        self.assertEqual(got["all"][:3], [1, 2, 3])  # primero lo que corre, luego lo que espera por id
        self.assertEqual(got["all"][3:], [6, 5, 4, 0])  # y el resto, lo más nuevo antes
        self.assertIn("weird.code", got["errNoKey"])   # a code without text is still a reason
        self.assertEqual((got["errText"], got["errKey"], got["errNone"], got["errNotFailed"]), ("ya traducido", "error.engine.failed:x", None, None))

    def test_queue_model_error_falls_back_to_ui_error_code(self):
        got = self.run_js("""
const m = await mod('js/queue-model.js');
const e = { id: 1, state: 'failed', error: { code: 'weird.code' } };
out({ viaCode: m.errorOf(e, (k, p) => (k === 'ui.error.code' ? 'Error ' + p.code : null)), bare: m.errorOf(e, () => null) });
""")
        self.assertEqual(got["viaCode"], "Error weird.code")
        self.assertEqual(got["bare"], "error: weird.code")

    def test_describe_error_uses_api_message_or_ui_error_code(self):
        got = self.run_js("""
const { ApiError, OfflineError, describeError } = await mod('js/api.js');
const t = (k, p) => (k === 'ui.error.code' ? 'Error ' + p.code : k);
out({ bare: describeError(new ApiError(500, { error: { code: 'x.y' } }), t), said: describeError(new ApiError(400, { error: { code: 'x.y', message: 'dicho' } }), t), noBody: describeError(new ApiError(502, null), t) });
""")
        self.assertEqual(got["bare"], "Error x.y")
        self.assertEqual(got["said"], "dicho")
        self.assertEqual(got["noBody"], "Error api.unexpected")

    QUEUE_ENV = ORDER_ENV + """
const { initQueueBar, toggleQueue } = await mod('js/components/queue-bar.js');
const poll = await mod('js/queue-poll.js');
const stores = await mod('js/store.js');
doc.body.append(Object.assign(doc.createElement('div'), { attrs: { id: 'qpill' } }), Object.assign(doc.createElement('aside'), { attrs: { id: 'queue-drawer' }, hidden: true }));
const pillHost = doc.getElementById('qpill'); const drawer = doc.getElementById('queue-drawer');
initQueueBar(pillHost, drawer);
await poll.refreshNow();
const fid = (id) => drawer.find((e) => e.dataset && e.dataset.fid === id)[0];
"""

    def test_queue_bar_pill_drawer_cancel_and_clear(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
r.pill = pillHost.textContent; r.closed = drawer.hidden;
pillHost.find((e) => e.tag === 'button')[0].click();
r.open = !drawer.hidden;
r.entries = drawer.find((e) => e.className.includes('queue-entry')).map((e) => e.textContent);
r.cancelIds = drawer.find((e) => e.dataset && String(e.dataset.fid).startsWith('cancel-')).map((e) => e.dataset.fid);
r.noMove = drawer.find((e) => e.dataset && /^(up|down|top|pause)/.test(String(e.dataset.fid))).length;
r.clear = fid('clear-all').textContent; r.dangerClass = fid('clear-all').className.includes('btn-danger');
// cancelar la que espera (id 2)
fid('cancel-2').click(); await until(() => !drawer.find((e) => e.dataset && e.dataset.fid === 'cancel-2').length);
r.afterCancel = pillHost.textContent; r.seenCancel = seen.filter((s) => s[1].includes('/cancel')).map((s) => s[0] + ' ' + s[1].split('?')[0]);
// filtro de fallidas: su error traducido, con ✗
fid('filter-failed').click();
r.failed = drawer.find((e) => e.className.includes('queue-entry')).map((e) => e.textContent);
// vaciar: sin nada esperando ya no hay botón
r.clearGone = drawer.find((e) => e.dataset && e.dataset.fid === 'clear-all').length;
out(r);
""")
        self.assertEqual(got["pill"], "1 en marcha · 1 en cola")
        self.assertTrue(got["closed"] and got["open"])
        self.assertEqual(len(got["entries"]), 3)
        self.assertEqual(got["cancelIds"], ["cancel-1", "cancel-2"])
        self.assertEqual(got["noMove"], 0)
        self.assertIn("Vaciar cola (1)", got["clear"])
        self.assertTrue(got["dangerClass"])
        self.assertEqual(got["seenCancel"], ["POST /api/queue/2/cancel"])
        self.assertEqual(got["afterCancel"], "1 en marcha")
        self.assertEqual(len(got["failed"]), 1)
        self.assertIn("✗ ", got["failed"][0])
        self.assertIn("out of memory", got["failed"][0])
        self.assertEqual(got["clearGone"], 0)

    def test_queue_bar_clear_confirms_then_posts_and_cancel_declined_posts_nothing(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
pillHost.find((e) => e.tag === 'button')[0].click();
fid('clear-all').click();
await until(() => doc.body.find((e) => e.tag === 'dialog').length > 0);
const dlg = doc.body.find((e) => e.tag === 'dialog')[0];
const buttons = dlg.find((e) => e.tag === 'button');
r.message = dlg.textContent;
r.confirmDanger = buttons[0].className.includes('btn-danger');
buttons[1].click(); await sleep(30);                       // «Cancelar»: no se envía nada
r.postsAfterDecline = seen.filter((s) => s[1].split('?')[0].endsWith('/clear')).length;
fid('clear-all').click();
await until(() => doc.body.find((e) => e.tag === 'dialog').length > 0);
doc.body.find((e) => e.tag === 'dialog')[0].find((e) => e.tag === 'button')[0].click();
await until(() => seen.some((s) => s[1].split('?')[0].endsWith('/clear')));
await until(() => pillHost.textContent === '1 en marcha');
r.clear = seen.filter((s) => s[1].split('?')[0].endsWith('/clear')).map((s) => [s[0], s[1].split('?')[0], s[2]]);
r.toast = toasts();
out(r);
""")
        self.assertTrue(got["confirmDanger"])
        self.assertEqual(got["postsAfterDecline"], 0)
        self.assertEqual(got["clear"], [["POST", "/api/queue/clear", {}]])
        self.assertIn("1 entrada cancelada.", got["toast"])
        self.assertNotIn("1 entradas", got["toast"])
        self.assertIn("Se cancelará 1 entrada que espera. Lo que ya está en marcha sigue hasta terminar.", got["message"])

    def test_queue_bar_unknown_state_and_kind_show_raw_and_the_entry_is_a_group(self):
        got = self.run_js(self.QUEUE_ENV + """
stores.set('queue', [{ id: 50, state: 'zzstate', kind: 'zzkind', project: 'a', key: 'k', seed: null },
  { id: 51, state: 'failed', kind: 'line', project: 'a', key: 'k', error: { code: 'no.such.code' } }]);
toggleQueue(true);
const ents = drawer.find((e) => e.className.includes('queue-entry'));
out({ roles: ents.map((e) => e.attrs.role), text: ents.map((e) => e.textContent) });
""")
        unknown = next(x for x in got["text"] if "zzstate" in x)
        failed = next(x for x in got["text"] if "Fallida" in x)
        self.assertIn("zzkind", unknown)
        self.assertNotIn("ui.queue.", unknown)
        self.assertIn("no.such.code", failed)   # the failed entry has a reason
        self.assertEqual(got["roles"], ["group", "group"])

    def test_loading_and_bind_shortcuts_are_shared_and_the_help_lists_only_the_view_actions(self):
        got = self.run_js(self.ORDER_ENV + """
const sh = await mod('js/components/shortcuts.js');
const texts = () => doc.body.find((e) => e.tag === 'dialog')[0].find((e) => e.tag === 'dd').map((e) => e.textContent);
const r = { loading: sh.loading().textContent.trim().length > 0 };
const seenA = [];
const stop = sh.bindShortcuts((a) => seenA.push(a), { actions: ['toggle', 'swap'] });
press('p'); press('x'); press('u'); press('ArrowRight');   // u and the arrow are not this view's
r.acted = seenA.slice();
sh.openHelp(); r.helpSome = texts(); doc.body.find((e) => e.tag === 'dialog')[0].close(); await sleep(20);
stop();
press('p'); r.afterStop = seenA.length;
sh.openHelp(null, { actions: null }); r.helpAll = texts(); doc.body.find((e) => e.tag === 'dialog')[0].close();
out(r);
""")
        self.assertTrue(got["loading"])
        self.assertEqual(got["acted"], ["toggle", "swap"])
        self.assertEqual(got["afterStop"], 2)
        for gone in ("Deshacer elección", "Descartar"):
            self.assertFalse(any(gone in x for x in got["helpSome"]), gone)
        self.assertLess(len(got["helpSome"]), len(got["helpAll"]))
        self.assertGreater(len(got["helpSome"]), 3)   # the global rows stay

    def test_compare_view_help_does_not_list_actions_it_does_not_do(self):
        got = self.run_js(self.COMPARE_ENV + """
const { openHelp } = await mod('js/components/shortcuts.js');
const view = await mountCmp('narrator', { a: '2', b: '3' });
openHelp();
const dlg = doc.body.find((e) => e.tag === 'dialog')[0];
const dts = dlg.find((e) => e.tag === 'dt'); const dds = dlg.find((e) => e.tag === 'dd');
const rows = dts.map((dt, i) => [dt.find((e) => e.tag === 'kbd').map((k) => k.textContent).join(' '), dds[i].textContent]);
view.cleanup();
out(rows);
""")
        keys = [k for k, _ in got]
        for k in ("U", "C", "D", "G", "Y"):
            self.assertNotIn(k, keys)
        self.assertIn(["X", "Comparación A/B: cambiar de lado (←/→ pasan a A/B)"], got)   # the swap row, by its text
        self.assertIn(["LB RB", "Comparación A/B: cambiar de lado (←/→ pasan a A/B)"], got)

    def test_help_without_a_bound_view_lists_only_the_global_rows_and_closes_when_the_view_stops(self):
        got = self.run_js(self.COMPARE_ENV + """
const sh = await mod('js/components/shortcuts.js');
const rows = () => doc.body.find((e) => e.tag === 'dialog' && e.open)[0].find((e) => e.tag === 'dd').map((e) => e.textContent);
const r = {};
sh.openHelp(); r.none = rows(); sh.closeHelp();
const stop = sh.bindShortcuts(() => {}, { actions: ['next'] });
sh.openHelp(); r.dpad = rows(); sh.closeHelp();
sh.openHelp(); r.openBeforeStop = sh.helpOpen(); stop(); r.openAfterStop = sh.helpOpen();
sh.openHelp(); r.afterStop = rows(); sh.closeHelp();
const stopAll = sh.bindShortcuts(() => {});
sh.openHelp(); r.noFilter = rows().length; sh.closeHelp(); stopAll();
out(r);
""")
        self.assertEqual(len(got["none"]), 3)   # ?, Esc, Tab: no order, A/B or pad rows
        self.assertEqual(got["afterStop"], got["none"])
        self.assertIn("Cruceta: toma anterior o siguiente", got["dpad"])   # a view with only «next» still has the d-pad row
        self.assertEqual((got["openBeforeStop"], got["openAfterStop"]), (True, False))
        self.assertGreater(got["noFilter"], 10)

    def test_queue_open_blocks_the_keys_of_the_order_and_compare_views(self):
        got = self.run_js(self.COMPARE_ENV + """
const { initQueueBar, toggleQueue } = await mod('js/components/queue-bar.js');
doc.body.append(Object.assign(doc.createElement('div'), { attrs: { id: 'qpill' } }), Object.assign(doc.createElement('aside'), { attrs: { id: 'queue-drawer' }, hidden: true }));
initQueueBar(doc.getElementById('qpill'), doc.getElementById('queue-drawer'));
const r = {};
const order = await mount('narrator');
const focused = () => cards(order).map((c) => c.focused).join();
const f0 = focused(); const posts0 = seen.filter((s) => s[0] === 'POST').length;
toggleQueue(true);
press('ArrowRight'); press('g'); press('d'); press('p'); await sleep(30);
r.orderBlocked = focused() === f0 && seen.filter((s) => s[0] === 'POST').length === posts0 && audioOf(order, 2).paused;
toggleQueue(false);
press('ArrowRight'); r.orderFree = focused() !== f0;
order.cleanup();
const view = await mountCmp('narrator', { a: '2', b: '3' });
const active = () => sidesOf(view).map((s) => s.textContent.includes('Suena este lado') ? s.dataset.side : '').join('');
toggleQueue(true);
const before = active(); press('x'); press('ArrowRight'); await sleep(30);
r.compareBlocked = active() === before && audios(view).every((a) => a.paused);
toggleQueue(false);
press('x'); await until(() => active() !== before); r.compareFree = true;
out(r);
""")
        self.assertEqual(got, {"orderBlocked": True, "orderFree": True, "compareBlocked": True, "compareFree": True})

    def test_queue_bar_cancel_moves_the_focus_to_the_next_entry_or_to_close(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
pillHost.find((e) => e.tag === 'button')[0].click();
const fidOf = () => (doc.activeElement && doc.activeElement.dataset ? doc.activeElement.dataset.fid : null);
r.ids = drawer.find((e) => e.dataset && /^(cancel|go)-/.test(String(e.dataset.fid))).map((e) => e.dataset.fid);
fid('cancel-2').focus(); fid('cancel-2').click();
await until(() => !drawer.find((e) => e.dataset && e.dataset.fid === 'cancel-2').length);
r.afterWaiting = fidOf();                                  // desapareció: la siguiente entrada (la fallida, con su enlace)
fid('cancel-1').focus(); fid('cancel-1').click();
await until(() => fid('cancel-1').disabled && fidOf() !== 'cancel-1');
r.afterRunning = fidOf();                                  // queda deshabilitado: la siguiente entrada
fid('go-0').focus();
stores.set('queue', []);                                   // sin entradas: nada a lo que ir, y el foco que se pierde va a «cerrar»
r.empty = fidOf();
out(r);
""")
        self.assertEqual(got["ids"], ["cancel-1", "cancel-2", "go-0"])
        self.assertEqual(got["afterWaiting"], "go-0")
        self.assertEqual(got["afterRunning"], "go-2")  # la de antes ya cancelada, que ahora solo ofrece ir al pedido
        self.assertEqual(got["empty"], "close")

    def test_queue_bar_cancel_says_requested_for_a_running_entry_and_ignores_a_second_press(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
let release; const held = new Promise((res) => { release = res; });
setTransport(async (method, url, body) => { seen.push([method, url, body]); if (method === 'POST' && url.includes('/cancel')) await held; return mock.transport(method, url, body); });
pillHost.find((e) => e.tag === 'button')[0].click();
fid('cancel-1').click(); fid('cancel-1').click();            // doble pulsación mientras el POST va en curso
await sleep(30);
r.disabledWhileInFlight = fid('cancel-1').disabled;
r.postsWhileInFlight = seen.filter((s) => s[1].includes('/cancel')).length;
release();
await until(() => toasts().includes('Cancelación pedida'));
await sleep(30);
r.posts = seen.filter((s) => s[1].includes('/cancel')).length;
r.toast = toasts();
r.errors = doc.getElementById('alerts').textContent;
out(r);
""")
        self.assertTrue(got["disabledWhileInFlight"])
        self.assertEqual((got["postsWhileInFlight"], got["posts"]), (1, 1))
        self.assertIn("Cancelación pedida para la entrada 1.", got["toast"])
        self.assertNotIn("Entrada 1 cancelada.", got["toast"])
        self.assertEqual(got["errors"], "")

    def test_queue_bar_cancel_of_a_waiting_entry_says_cancelled_and_the_button_is_back_after_a_failure(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
pillHost.find((e) => e.tag === 'button')[0].click();
fid('cancel-2').click();
await until(() => toasts().includes('cancelada'));
r.toast = toasts();
out(r);
""")
        self.assertIn("Entrada 2 cancelada.", got["toast"])

    def test_queue_bar_follows_the_language_and_the_route(self):
        got = self.run_js(self.QUEUE_ENV + """
const r = {};
const router = await mod('js/router.js');
pillHost.find((e) => e.tag === 'button')[0].click();
r.es = pillHost.textContent;
const E = (id, project) => ({ id, kind: 'line', project, key: 'k' + id, state: 'queued', seed: 1, cancelRequested: false });
stores.set('queue', [E(1, 'example-world'), E(2, 'other')]);
const clearProject = () => drawer.find((e) => e.dataset && e.dataset.fid === 'clear-project').map((e) => e.textContent);
r.noRoute = clearProject();
location.hash = '#/p/other/orders'; router.navigate('#/p/other/orders');
r.routeOther = clearProject();
location.hash = '#/p/example-world/orders'; router.navigate('#/p/example-world/orders');
r.routeWorld = clearProject();
const en = JSON.parse(readFileSync(new URL(UI + '/../locales/en.json').pathname, 'utf8'));
globalThis.fetch = async () => ({ json: async () => en });
await i18n.load('en');
r.en = pillHost.textContent;
out(r);
""")
        self.assertEqual(got["es"], "1 en marcha · 1 en cola")
        self.assertEqual(got["noRoute"], [])
        self.assertEqual(got["routeOther"], ["Vaciar cola de other (1)"])
        self.assertEqual(got["routeWorld"], ["Vaciar cola de example-world (1)"])
        self.assertEqual(got["en"], "2 queued")

    def test_queue_bar_escape_goes_through_the_shortcuts_hook_and_help_closes_first(self):
        got = self.run_js(self.QUEUE_ENV + """
const { initShortcuts, openHelp, helpOpen } = await mod('js/components/shortcuts.js');
const { closeQueue, isQueueOpen } = await mod('js/components/queue-bar.js');
initShortcuts({ closeAll: closeQueue });
const r = {};
const pill = () => pillHost.find((e) => e.tag === 'button')[0];
pill().click();
const esc = () => doc.body.dispatchEvent({ type: 'keydown', key: 'Escape' });
openHelp(); esc();                                          // con la ayuda encima, solo se cierra la ayuda
r.afterHelpEsc = { help: helpOpen(), queue: isQueueOpen() };
fid('close').focus(); const ev = esc();                     // el foco dentro del cajón: vuelve a la píldora
r.afterEsc = { queue: isQueueOpen(), hidden: drawer.hidden, focusOnPill: doc.activeElement === pill(), prevented: ev.defaultPrevented };
pill().click(); doc.body.focus(); esc();                    // el foco fuera del cajón: no se le roba
r.outside = { queue: isQueueOpen(), focusOnPill: doc.activeElement === pill() };
out(r);
""")
        self.assertEqual(got["afterHelpEsc"], {"help": False, "queue": True})
        self.assertEqual(got["afterEsc"], {"queue": False, "hidden": True, "focusOnPill": True, "prevented": True})
        self.assertEqual(got["outside"], {"queue": False, "focusOnPill": False})

    COMPARE_ENV = ORDER_ENV + """
const { compareView } = await mod('js/components/compare-view.js');
const mountCmp = async (key, query = {}) => {
  const view = compareView({ project: 'example-world', key, query });
  doc.body.append(view.node);
  await until(() => view.node.find((e) => e.tag === 'audio').length === 2 && view.node.find((e) => e.tag === 'audio').every((a) => a.src));
  await sleep(20);
  return view;
};
const audios = (view) => view.node.find((e) => e.tag === 'audio');
const sidesOf = (view) => view.node.find((e) => e.className.split(' ').includes('compare-side'));
const state = (a, b) => ({ a: { paused: a.paused, t: a.currentTime }, b: { paused: b.paused, t: b.currentTime } });
const playBtn = (view) => view.node.find((e) => e.className.includes('compare-play'))[0];
const swapBtn = (view) => btn(view.node, 'Cambiar A↔B');
"""

    def test_compare_swap_keeps_the_point_and_the_play_state(self):
        got = self.run_js(self.COMPARE_ENV + """
const r = {};
// 1) sonando en A, A en 1,25 s: el cambio deja A en pausa y B sonando desde 1,25 s
let view = await mountCmp('narrator', { a: '2', b: '3' });
let [A, B] = audios(view);
r.layout = { sides: sidesOf(view).map((s) => s.dataset.side), titles: sidesOf(view).map((s) => s.find((e) => e.tag === 'h2')[0].textContent),
  selects: sidesOf(view).map((s) => s.find((e) => e.tag === 'select')[0].value), chosenSide: sidesOf(view).map((s) => s.classList.contains('is-chosen')),
  activeText: sidesOf(view).map((s) => s.textContent.includes('Suena este lado')), hash: location.hash };
playBtn(view).click(); await until(() => !A.paused);
A.currentTime = 1.25;
swapBtn(view).click(); await until(() => !B.paused);
r.playing = { ...state(A, B), label: playBtn(view).textContent, active: sidesOf(view).map((s) => s.textContent.includes('Suena este lado')), current: sidesOf(view).map((s) => s.attrs['aria-current'] || null) };
swapBtn(view).click(); await until(() => !A.paused);        // y de vuelta: A desde donde estaba B
r.back = state(A, B);
view.cleanup();
// 2) en pausa: el cambio deja B en el punto y en pausa
view = await mountCmp('narrator', { a: '2', b: '3' }); [A, B] = audios(view);
A.currentTime = 1.25; swapBtn(view).click(); await sleep(30);
r.paused = state(A, B);
// 3) B más corta que el punto: se queda al final y no suena; A se pausa
view.cleanup();
view = await mountCmp('narrator', { a: '2', b: '3' }); [A, B] = audios(view);
B.duration = 1.0;
playBtn(view).click(); await until(() => !A.paused);
A.currentTime = 1.25; swapBtn(view).click(); await sleep(30);
r.short = { ...state(A, B), hint: view.node.textContent.includes('La toma B es más corta') };
view.cleanup();
out(r);
""", timeout=60)
        self.assertEqual(got["layout"]["sides"], ["a", "b"])
        self.assertEqual(got["layout"]["titles"], ["A Toma 2", "B Toma 3"])
        self.assertEqual(got["layout"]["selects"], ["2", "3"])
        self.assertEqual(got["layout"]["chosenSide"], [True, False])
        self.assertEqual(got["layout"]["activeText"], [True, False])  # el lado activo lo dice con texto
        self.assertEqual(got["layout"]["hash"], "#/p/example-world/o/narrator/ab?a=2&b=3")
        self.assertEqual(got["playing"]["a"], {"paused": True, "t": 1.25})
        self.assertEqual(got["playing"]["b"], {"paused": False, "t": 1.25})
        self.assertEqual(got["playing"]["active"], [False, True])
        self.assertEqual(got["playing"]["current"], [None, "true"])
        self.assertIn("Pausar", got["playing"]["label"])
        self.assertEqual(got["back"]["a"]["paused"], False)
        self.assertEqual(got["back"]["b"]["paused"], True)
        self.assertEqual(got["paused"], {"a": {"paused": True, "t": 1.25}, "b": {"paused": True, "t": 1.25}})
        self.assertEqual(got["short"]["a"]["paused"], True)
        self.assertEqual(got["short"]["b"], {"paused": True, "t": 1.0})
        self.assertTrue(got["short"]["hint"])

    def test_compare_keys_and_buttons_do_the_same_swap(self):
        got = self.run_js(self.COMPARE_ENV + """
const r = {};
const view = await mountCmp('narrator', { a: '2', b: '3' });
const [A, B] = audios(view);
const active = () => sidesOf(view).map((s) => s.textContent.includes('Suena este lado') ? s.dataset.side : '').join('');
press(' '); await until(() => !A.paused);                   // reproducir
A.currentTime = 1.25;
press('ArrowRight'); await until(() => !B.paused); r.next = { ...state(A, B), active: active() };
press('ArrowRight'); r.nextAgain = { ...state(A, B), active: active() };            // ya en B: nada
B.currentTime = 2.5;
press('ArrowLeft'); await until(() => !A.paused); r.prev = { ...state(A, B), active: active() };
A.currentTime = 0.5;
press('x'); await until(() => !B.paused); r.x = { ...state(A, B), active: active() };
press('Escape'); r.escape = { ...state(A, B), active: active() };                    // pausa del lado activo
// lo mismo con las flechas arriba y abajo, y con el botón
press('ArrowUp'); r.up = active(); press('ArrowDown'); r.down = active();
swapBtn(view).click(); r.button = active();
// los campos de texto y las letras apagadas
const sel = sidesOf(view)[0].find((e) => e.tag === 'select')[0];
sel.dispatchEvent({ type: 'keydown', key: 'x' }); r.inSelect = active();
store.set('gvoice.oneKey', 'off'); press('x'); r.lettersOff = active(); press('ArrowRight'); r.arrowsOn = active();
store.delete('gvoice.oneKey');
// el mando: LB y RB, y no actúa con un campo o un diálogo
let pad = { connected: true, buttons: [] };
const buttons = (n) => Array.from({ length: 17 }, (_, i) => ({ pressed: n.includes(i), value: 0 }));
view.cleanup();
Object.defineProperty(globalThis, 'navigator', { value: { getGamepads: () => [pad] }, configurable: true });
const view2 = await mountCmp('narrator', { a: '2', b: '3' });
const active2 = () => sidesOf(view2).map((s) => s.textContent.includes('Suena este lado') ? s.dataset.side : '').join('');
const tap = async (n) => { pad = { connected: true, buttons: buttons(n) }; await sleep(160); pad = { connected: true, buttons: buttons([]) }; await sleep(160); };
await tap([5]); r.rb = active2(); await tap([4]); r.lb = active2();
view2.cleanup();
await tap([5]); r.afterCleanup = active2();
out(r);
""", timeout=60)
        self.assertEqual(got["next"], {"a": {"paused": True, "t": 1.25}, "b": {"paused": False, "t": 1.25}, "active": "b"})
        self.assertEqual(got["nextAgain"]["active"], "b")
        self.assertEqual(got["prev"], {"a": {"paused": False, "t": 2.5}, "b": {"paused": True, "t": 2.5}, "active": "a"})
        self.assertEqual(got["x"], {"a": {"paused": True, "t": 0.5}, "b": {"paused": False, "t": 0.5}, "active": "b"})
        self.assertEqual(got["escape"]["b"]["paused"], True)
        self.assertEqual((got["up"], got["down"], got["button"]), ("a", "b", "a"))
        self.assertEqual(got["inSelect"], "a")                 # un campo no dispara atajos
        self.assertEqual(got["lettersOff"], "a")               # sin atajos de una tecla, x no hace nada
        self.assertEqual(got["arrowsOn"], "b")
        self.assertEqual((got["rb"], got["lb"]), ("b", "a"))
        self.assertEqual(got["afterCleanup"], "a")

    def test_compare_wave_click_moves_both_audios_and_a_shorter_one_stays_at_its_end(self):
        got = self.run_js(self.COMPARE_ENV + """
const view = await mountCmp('narrator', { a: '2', b: '3' });
const [A, B] = audios(view);
B.duration = 1.0; A.duration = 3.5;
const waves = view.node.find((e) => e.attrs.role === 'slider');
waves[0].dispatchEvent({ type: 'click', clientX: 150 });    // mitad de A (3,5 s) = 1,75 s
const r = { click: state(A, B), hint: view.node.textContent.includes('La toma B es más corta') };
waves[0].dispatchEvent({ type: 'keydown', key: 'ArrowLeft' });      // 5 % menos: otra posición en los dos
r.key = state(A, B);
B.duration = 4.0;
waves[1].dispatchEvent({ type: 'click', clientX: 75 });     // un cuarto de B (4 s) = 1 s
r.fromB = state(A, B);
r.times = view.node.find((e) => e.className.includes('take-time')).map((e) => e.textContent);
view.cleanup();
out(r);
""")
        self.assertEqual(got["click"], {"a": {"paused": True, "t": 1.75}, "b": {"paused": True, "t": 1.0}})
        self.assertTrue(got["hint"])
        self.assertAlmostEqual(got["key"]["a"]["t"], 1.575)
        self.assertEqual(got["key"]["b"]["t"], 1.0)
        self.assertEqual((got["fromB"]["a"]["t"], got["fromB"]["b"]["t"]), (1.0, 1.0))
        self.assertEqual(got["times"], ["0:01 / 0:04", "0:01 / 0:04"])

    def test_compare_changes_a_side_take_updates_the_hash_and_chooses_one_at_a_time(self):
        got = self.run_js(self.COMPARE_ENV + """
const r = {};
const view = await mountCmp('narrator', { a: '2', b: '3' });
const selOf = (n) => sidesOf(view)[n].find((e) => e.tag === 'select')[0];
const optsOf = (n) => selOf(n).find((e) => e.tag === 'option').map((o) => [o.value, o.disabled]);
r.opts = optsOf(0);
const oldA = audios(view)[0]; const madeBefore = made.length; const revokedBefore = revoked.length;
selOf(0).value = '3'; selOf(0).dispatchEvent('change');      // la toma del otro lado: no se acepta
r.sameAsOther = { hash: location.hash, value: selOf(0).value, kept: audios(view)[0] === oldA };
selOf(0).value = '1'; selOf(0).dispatchEvent('change');
await until(() => audios(view)[0].src && made.length === madeBefore + 1);
r.changed = { hash: location.hash, value: selOf(0).value, replaced: audios(view)[0] !== oldA, revoked: revoked.length - revokedBefore, title: sidesOf(view)[0].find((e) => e.tag === 'h2')[0].textContent,
  chosenA: sidesOf(view)[0].classList.contains('is-chosen'), opts: optsOf(1) };
// elegir: A (toma 1) está descartada, B (3) se puede elegir
const chooseA = btn(view.node, 'Elegir A'); const chooseB = btn(view.node, 'Elegir B');
r.before = { a: chooseA.disabled, b: chooseB.disabled };
chooseA.click(); await sleep(30); r.noCall = seen.filter((s) => s[1].includes('/choose')).length;
chooseB.click(); chooseB.click();
await until(() => btn(view.node, 'Elegir B').disabled);
r.after = { calls: seen.filter((s) => s[1].includes('/choose')).map((s) => s[2]), a: btn(view.node, 'Elegir A').disabled, b: btn(view.node, 'Elegir B').disabled,
  chosen: sidesOf(view).map((s) => s.classList.contains('is-chosen')), toast: toasts().includes('toma 3') };
// la tecla «e» elige el lado activo (A: la 1, descartada: nada)
press('e'); await sleep(30); r.keyChoose = seen.filter((s) => s[1].includes('/choose')).length;
view.cleanup();
const cleaned = { listeners: doc.listenerCount(), revokedAll: made.every((u) => revoked.includes(u)) };
r.cleaned = cleaned;
out(r);
""", timeout=60)
        self.assertEqual(got["opts"], [["1", False], ["2", False], ["3", True]])
        self.assertEqual(got["sameAsOther"], {"hash": "#/p/example-world/o/narrator/ab?a=2&b=3", "value": "2", "kept": True})
        self.assertEqual(got["changed"]["hash"], "#/p/example-world/o/narrator/ab?a=1&b=3")
        self.assertEqual((got["changed"]["value"], got["changed"]["replaced"], got["changed"]["revoked"]), ("1", True, 1))
        self.assertEqual(got["changed"]["title"], "A Toma 1")
        self.assertFalse(got["changed"]["chosenA"])
        self.assertEqual(got["changed"]["opts"], [["1", True], ["2", False], ["3", False]])
        self.assertEqual(got["before"], {"a": True, "b": False})
        self.assertEqual(got["noCall"], 0)
        self.assertEqual(got["after"]["calls"], [{"attempt": 3}])  # dos clics seguidos: una sola petición
        self.assertEqual((got["after"]["a"], got["after"]["b"]), (True, True))  # A sigue descartada; B ya es la elegida
        self.assertEqual(got["after"]["chosen"], [False, True])
        self.assertTrue(got["after"]["toast"])
        self.assertEqual(got["keyChoose"], 1)
        self.assertEqual(got["cleaned"], {"listeners": 0, "revokedAll": True})

    def test_compare_needs_two_takes_with_audio_and_order_view_links_to_it(self):
        got = self.run_js(self.COMPARE_ENV + """
const r = {};
const one = compareView({ project: 'example-world', key: 'orc', query: {} });
doc.body.append(one.node);
await until(() => one.node.textContent.includes('al menos dos tomas'));
r.one = { audios: audios(one).length, links: one.node.find((e) => e.tag === 'a').map((a) => a.attrs.href), live: doc.listenerCount() };
one.cleanup(); r.one.after = doc.listenerCount();
const missing = compareView({ project: 'example-world', key: 'nope', query: {} });
doc.body.append(missing.node);
await until(() => missing.node.find((e) => e.attrs.role === 'alert').length > 0);
r.missing = missing.node.find((e) => e.tag === 'a').length; missing.cleanup();
// el pedido: «Comparar A/B» con la toma enfocada y la elegida; con una sola toma, apagado y con su pista
const view = await mount('narrator');
const cmp = () => btn(view.node, 'Comparar A/B');
r.order = { disabled: cmp().disabled };
cmp().click(); r.hash = location.hash;
press('ArrowRight'); cmp().click(); r.hashRight = location.hash;
const before = seen.length; const tabBefore = cards(view).map((c) => c.attrs.tabindex).join();
press('x'); await sleep(20);
r.swapInOrder = { calls: seen.length - before, tab: cards(view).map((c) => c.attrs.tabindex).join() === tabBefore, paused: audios(view).every((a) => a.paused) };
view.cleanup();
const orc = await mount('orc');
r.orc = { disabled: btn(orc.node, 'Comparar A/B').disabled, hint: orc.node.textContent.includes('al menos dos tomas con audio') };
orc.cleanup();
out(r);
""", timeout=60)
        self.assertEqual(got["one"], {"audios": 0, "links": ["#/p/example-world/o/orc"], "live": 1, "after": 0})
        self.assertEqual(got["missing"], 1)
        self.assertFalse(got["order"]["disabled"])
        self.assertEqual(got["hash"], "#/p/example-world/o/narrator/ab?a=2&b=1")   # la enfocada (la elegida) contra otra con audio
        self.assertEqual(got["hashRight"], "#/p/example-world/o/narrator/ab?a=3&b=2")  # la enfocada contra la elegida
        self.assertEqual(got["swapInOrder"], {"calls": 0, "tab": True, "paused": True})
        self.assertEqual(got["orc"], {"disabled": True, "hint": True})

    def test_compare_a_late_pause_after_cleanup_does_not_throw(self):
        got = self.run_js(self.COMPARE_ENV + """
const view = await mountCmp('narrator', { a: '2', b: '3' });
const [A, B] = audios(view);
view.cleanup();
const errs = [];
for (const [el, ev] of [[A, 'pause'], [B, 'ended'], [A, 'play']]) { try { el.dispatchEvent(ev); } catch (e) { errs.push(String(e)); } }
out({ errs });
""")
        self.assertEqual(got["errs"], [])

    def test_compare_the_latest_position_wins_over_a_pending_one(self):
        got = self.run_js(self.COMPARE_ENV + """
const view = await mountCmp('narrator', { a: '2', b: '3' });
const realUrl = api.audioUrl; const rel = {};
api.audioUrl = (p, k, id) => new Promise((res) => { rel[id] = async () => res(await realUrl(p, k, id)); });
const [oldA, B] = audios(view);
oldA.currentTime = 1.5;
const sel = sidesOf(view)[0].find((e) => e.tag === 'select')[0];
sel.value = '1'; sel.dispatchEvent('change');
const A = audios(view)[0];
let t = 0; let src = '';   // like a browser: no position without `src`, and a new `src` restarts it
Object.defineProperty(A, 'src', { get: () => src, set: (v) => { src = v; t = 0; } });
Object.defineProperty(A, 'currentTime', { get: () => t, set: (v) => { if (src) t = v; } });
await until(() => rel[1]); await rel[1](); await until(() => A.src);
B.duration = 4.0;
view.node.find((e) => e.attrs.role === 'slider')[1].dispatchEvent({ type: 'click', clientX: 75 });   // 1 s in B
A.dispatchEvent('loadedmetadata');
out({ t: A.currentTime });
view.cleanup();
""", timeout=60)
        self.assertEqual(got["t"], 1.0)

    def test_compare_play_asked_on_a_side_that_is_switched_away_before_its_source_arrives(self):
        got = self.run_js(self.COMPARE_ENV + """
const realUrl = api.audioUrl; const rel = {};
api.audioUrl = (p, k, id) => new Promise((res) => { rel[id] = async () => res(await realUrl(p, k, id)); });
const view = compareView({ project: 'example-world', key: 'narrator', query: { a: '2', b: '3' } });
doc.body.append(view.node);
await until(() => rel[2] && rel[3]);
await rel[3](); await until(() => audios(view)[1].src);
const [A, B] = audios(view);
playBtn(view).click();                 // A asked to play, without source yet
swapBtn(view).click();                 // the play intent goes to B
await until(() => !B.paused);
const r = { b: !B.paused, a: A.paused };
await rel[2](); await until(() => A.src); await sleep(40);
r.after = { a: A.paused, b: B.paused };
view.cleanup();
out(r);
""", timeout=60)
        self.assertEqual(got["b"], True)
        self.assertEqual(got["a"], True)
        self.assertEqual(got["after"], {"a": True, "b": False})

    def test_compare_changing_a_take_clips_the_position_and_drops_the_old_hint(self):
        got = self.run_js(self.COMPARE_ENV + """
const r = {};
const view = await mountCmp('narrator', { a: '2', b: '3' });
const selOf = (n) => sidesOf(view)[n].find((e) => e.tag === 'select')[0];
const hintOn = () => view.node.textContent.includes('La toma B es más corta');
audios(view)[0].currentTime = 99;
selOf(1).value = '1'; selOf(1).dispatchEvent('change');
await until(() => audios(view)[1].src);
audios(view)[1].dispatchEvent('loadedmetadata');
r.clipped = { t: audios(view)[1].currentTime, hint: hintOn() };
audios(view)[0].currentTime = 0.5;
selOf(1).value = '3'; selOf(1).dispatchEvent('change');
await until(() => audios(view)[1].src); audios(view)[1].dispatchEvent('loadedmetadata');
r.moved = { t: audios(view)[1].currentTime, hint: hintOn() };
// the active side playing, changed to a take shorter than its position: it stays at the end and does not play
audios(view)[0].currentTime = 0.5; playBtn(view).click(); await until(() => !audios(view)[0].paused);
audios(view)[0].currentTime = 99;
selOf(0).value = '1'; selOf(0).dispatchEvent('change');
await until(() => audios(view)[0].src); await sleep(40); audios(view)[0].dispatchEvent('loadedmetadata');
r.active = { paused: audios(view)[0].paused, t: audios(view)[0].currentTime, hint: view.node.textContent.includes('La toma A es más corta') };
view.cleanup();
out(r);
""", timeout=60)
        self.assertAlmostEqual(got["clipped"]["t"], 3.05)
        self.assertTrue(got["clipped"]["hint"])
        self.assertEqual(got["moved"], {"t": 0.5, "hint": False})
        self.assertEqual(got["active"]["paused"], True)
        self.assertAlmostEqual(got["active"]["t"], 3.05)
        self.assertTrue(got["active"]["hint"])

    def test_compare_ignores_the_keys_it_does_not_use(self):
        got = self.run_js(self.COMPARE_ENV + """
const view = await mountCmp('narrator', { a: '2', b: '3' });
const prevented = {};
for (const k of ['u', 'c', 'd', 'g', 'x', 'e']) { if (press(k).defaultPrevented) prevented[k] = true; }
view.cleanup();
out({ prevented: Object.keys(prevented).sort() });
""")
        self.assertEqual(got["prevented"], ["e", "x"])


if __name__ == "__main__":
    unittest.main()
