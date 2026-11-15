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
class FakeNode { constructor() { this.children = []; this.parent = null; }
  append(...c) { for (const x of c) this.appendChild(typeof x === 'string' ? new FakeText(x) : x); }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parent = null; return c; }
  get firstChild() { return this.children[0] || null; }
  get textContent() { return this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { this.children = [new FakeText(String(v))]; }
}
class FakeText extends FakeNode { constructor(s) { super(); this.text = s; } get textContent() { return this.text; } set textContent(v) { this.text = String(v); } }
class FakeEl extends FakeNode {
  constructor(tag) { super(); this.tag = tag; this.attrs = {}; this.className = ''; this.dataset = {}; this.hidden = false; this.listeners = {}; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  addEventListener(k, fn) { this.listeners[k] = fn; }
  find(pred, acc = []) { for (const c of this.children) if (c instanceof FakeEl) { if (pred(c)) acc.push(c); c.find(pred, acc); } return acc; }
}
globalThis.Node = FakeNode;
globalThis.document = {
  documentElement: { lang: '' },
  createElement: (tag) => new FakeEl(tag),
  createElementNS: (ns, tag) => { const e = new FakeEl(tag); e.ns = ns; return e; },
  createTextNode: (s) => new FakeText(s),
};
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
globalThis.document.body = { append: (n) => appended.push(n) };
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


if __name__ == "__main__":
    unittest.main()
