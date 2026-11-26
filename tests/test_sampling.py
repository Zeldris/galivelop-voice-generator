import copy
import json
import unittest

from gvoice import engine, models, orders, queue, sampling, schema as S, worker
from tests.test_cli import CliBase, PROJECT, VOICE as CLI_VOICE
from tests.test_engine import NEVER
from tests.test_orders import make_wav
from tests.test_worker import WorkerBase

CATALOG = {"temperature": 0.9, "topK": 50, "topP": 1.0, "repetitionPenalty": 1.05, "greedy": False,
           "subTalker": {"temperature": 0.9, "topK": 50, "topP": 1.0}}


def errors(instance, name):
    return [(e.path, e.code) for e in S.validate(instance, S.load_schema(name))]


class SamplingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.sch = {"$ref": "common.schema.json#/$defs/sampling"}

    def codes(self, value):
        return [(e.path, e.code) for e in S.validate(value, self.sch)]

    def test_valid_and_empty(self):
        self.assertEqual(self.codes({}), [])
        self.assertEqual(self.codes(CATALOG), [])
        self.assertEqual(self.codes({"topP": 1, "temperature": 2, "repetitionPenalty": 1, "topK": 1000}), [])

    def test_ranges_each_with_its_reason(self):
        cases = {("temperature", 0): "exclusiveMinimum", ("temperature", 2.1): "maximum",
                 ("topK", 0): "minimum", ("topK", 1001): "maximum", ("topK", 1.5): "type",
                 ("topP", 0): "exclusiveMinimum", ("topP", 1.01): "maximum",
                 ("repetitionPenalty", 0.99): "minimum", ("repetitionPenalty", 2.01): "maximum",
                 ("greedy", 1): "type"}
        for (name, value), code in cases.items():
            self.assertEqual(self.codes({name: value}), [("/" + name, code)], (name, value))
        for name, value, code in (("temperature", 0, "exclusiveMinimum"), ("topK", 0, "minimum"),
                                  ("topP", 5, "maximum")):
            self.assertEqual(self.codes({"subTalker": {name: value}}), [("/subTalker/" + name, code)])

    def test_no_extra_properties_also_inside_sub_talker(self):
        self.assertEqual(self.codes({"speed": 1}), [("/speed", "additionalProperties")])
        self.assertEqual(self.codes({"subTalker": {"greedy": True}}),
                         [("/subTalker/greedy", "additionalProperties")])

    def test_used_by_order_config_voice_and_catalog(self):
        ref = {"$ref": "common.schema.json#/$defs/sampling"}
        for name in ("order", "project-config", "voice", "engine-catalog"):
            self.assertEqual(S.load_schema(name)["properties"]["sampling"]["$ref"], ref["$ref"], name)
        self.assertEqual(models.load("qwentts")["sampling"], CATALOG)

    def test_exclusive_minimum_message(self):
        err = S.validate(0, {"type": "number", "exclusiveMinimum": 0})
        self.assertEqual([e.code for e in err], ["exclusiveMinimum"])
        self.assertIn("greater than 0", S.format_error(err[0], "en"))

    def test_order_sampling_with_voice_and_line_but_not_with_a_sample(self):
        voice = {"key": "v", "type": "voice", "testText": "t", "designSheet": {}, "sampling": {"topK": 5}}
        sheet_errors = [e for e in errors(voice, "order") if "sampling" in e[0]]
        self.assertEqual(sheet_errors, [])
        line = {"key": "l", "type": "line", "voice": "v", "text": "t", "sampling": {"topK": 0}}
        self.assertEqual(errors(line, "order"), [("/sampling/topK", "minimum")])
        sample = {"key": "v", "type": "voice", "locale": "es-ES", "sampling": {"topK": 5},
                  "sample": {"audio": "/a.wav", "text": "t", "source": "s", "license": "l"}}
        found = S.validate(sample, S.load_schema("order"))
        self.assertEqual([(e.path, e.code) for e in found], [("/sampling", "false")])
        self.assertIn("sampling", S.format_error(found[0], "en"))
        del sample["sampling"]
        self.assertEqual(errors(sample, "order"), [])

    def test_project_config_sampling(self):
        with open("examples/galivelop-voices.json", encoding="utf-8") as fh:
            config = json.load(fh)
        config["sampling"] = {"temperature": 0.5}
        self.assertEqual(errors(config, "project-config"), [])
        config["sampling"] = {"temperature": 3}
        self.assertEqual(errors(config, "project-config"), [("/sampling/temperature", "maximum")])


class ResolveTests(unittest.TestCase):
    def test_catalog_alone_is_complete(self):
        self.assertEqual(sampling.resolve(), CATALOG)
        self.assertEqual(sampling.resolve({}, {}), CATALOG)

    def test_layers_field_by_field_order_over_config_over_catalog(self):
        config = {"temperature": 0.5, "topK": 20, "subTalker": {"temperature": 0.4, "topK": 10}}
        order = {"temperature": 0.7, "greedy": True, "subTalker": {"topK": 5}}
        self.assertEqual(sampling.resolve(order, config), {
            "temperature": 0.7, "topK": 20, "topP": 1.0, "repetitionPenalty": 1.05, "greedy": True,
            "subTalker": {"temperature": 0.4, "topK": 5, "topP": 1.0}})

    def test_inputs_are_not_modified_and_result_is_a_copy(self):
        order, config = {"subTalker": {"topK": 5}}, {"subTalker": {"topP": 0.5}}
        before = copy.deepcopy((order, config))
        out = sampling.resolve(order, config)
        out["subTalker"]["topK"] = 99
        self.assertEqual((order, config), before)
        self.assertEqual(sampling.defaults(), CATALOG)

    def test_merge_without_layers(self):
        self.assertEqual(sampling.merge(None, {"topK": 3}, None), {"topK": 3})


class TakeSamplingTests(WorkerBase):
    def test_specs_carry_the_effective_sampling_per_layer(self):
        self.write_config(sampling={"topK": 20, "subTalker": {"temperature": 0.4}})
        orders.submit(self.p, self.voice(sampling={"temperature": 0.7}))
        specs = orders.attempt_specs(self.p, "narrator", 2)
        want = dict(CATALOG, temperature=0.7, topK=20, subTalker=dict(CATALOG["subTalker"], temperature=0.4))
        self.assertEqual([s["sampling"] for s in specs], [want, want])
        self.assertIsNot(specs[0]["sampling"], specs[1]["sampling"])

    def test_resubmit_replaces_or_clears_the_order_sampling(self):
        orders.submit(self.p, self.voice(sampling={"topK": 7}))
        self.assertEqual(orders.get(self.p, "narrator")["sampling"], {"topK": 7})
        orders.submit(self.p, self.voice())
        self.assertNotIn("sampling", orders.get(self.p, "narrator"))
        self.assertEqual(orders.attempt_specs(self.p, "narrator")[0]["sampling"], CATALOG)

    def test_a_line_does_not_inherit_the_sampling_of_its_voice(self):
        orders.submit(self.p, self.voice(sampling={"temperature": 0.3}))
        orders.choose(self.p, "narrator", self.take())
        plain = self.line()
        del plain["sampling"]  # the example line has one of its own
        orders.submit(self.p, plain)
        self.assertEqual(orders.attempt_specs(self.p, "narrator/intro-01")[0]["sampling"], CATALOG)
        orders.submit(self.p, self.line(sampling={"topP": 0.9}))
        self.assertEqual(orders.attempt_specs(self.p, "narrator/intro-01")[0]["sampling"], dict(CATALOG, topP=0.9))

    def test_worker_passes_it_to_the_job_and_stores_it_next_to_the_seed(self):
        orders.submit(self.p, self.voice(sampling={"temperature": 0.7, "greedy": True}))
        entry, = queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator", seed=7))
        self.assertEqual(entry["sampling"]["temperature"], 0.7)
        seen = []

        class Spy(engine.FakeEngine):
            def design(self, job, should_cancel):
                seen.append(job)
                return super().design(job, should_cancel)

        self.run_worker(engine=Spy())
        want = dict(CATALOG, temperature=0.7, greedy=True)
        self.assertEqual([j.sampling for j in seen], [want])
        take = self.attempt("narrator", 1)
        self.assertEqual((take["seed"], take["sampling"]), (7, want))

    def test_a_queued_entry_keeps_the_sampling_it_was_queued_with(self):
        orders.submit(self.p, self.voice(sampling={"topK": 7}))
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator"))
        orders.submit(self.p, self.voice(sampling={"topK": 9}))  # changed before the worker runs
        self.run_worker()
        self.assertEqual(self.attempt("narrator", 1)["sampling"]["topK"], 7)

    def test_entry_from_before_0_4_1_gets_the_effective_sampling_when_run(self):
        orders.submit(self.p, self.voice())
        queue.enqueue(self.p, "narrator", orders.attempt_specs(self.p, "narrator"))

        def drop(data):
            for entry in data["entries"]:
                entry.pop("sampling")

        queue._txn(drop)
        self.run_worker()
        self.assertEqual(self.attempt("narrator", 1)["sampling"], CATALOG)

    def test_line_take_stores_its_own_effective_sampling(self):
        self.voice_done()
        orders.submit(self.p, self.line(sampling={"topK": 11}))
        queue.new_takes(self.p, "narrator/intro-01")
        self.run_worker()
        self.assertEqual(self.attempt("narrator/intro-01", 1)["sampling"], dict(CATALOG, topK=11))

    def test_sample_take_has_no_sampling(self):
        order = {"type": "voice", "key": "narrator", "locale": "es-ES", "sample": {
            "audio": make_wav(self.tmp / "a.wav"), "text": "Amanece.", "source": "own", "license": "CC0-1.0"}}
        record, _ = queue.submit_order(self.p, order)
        self.assertEqual(record["attempts"][0]["source"], "sample")
        self.assertNotIn("sampling", record["attempts"][0])
        self.assertNotIn("sampling", record)


class FakeEngineSamplingTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def audio(self, name, **kw):
        job = engine.DesignJob(instruction="Gender: male.", text="Hello there.", seed=5,
                               output=str(self.tmp / name), **kw)
        engine.FakeEngine().design(job, NEVER)
        return (self.tmp / name).read_bytes()

    def test_same_sampling_same_bytes_other_sampling_other_audio(self):
        a = self.audio("a.wav", sampling=dict(CATALOG))
        self.assertEqual(a, self.audio("b.wav", sampling=copy.deepcopy(CATALOG)))
        self.assertNotEqual(a, self.audio("c.wav", sampling=dict(CATALOG, temperature=0.8)))
        self.assertNotEqual(a, self.audio("d.wav", sampling=dict(CATALOG, subTalker={"temperature": 0.9, "topK": 49,
                                                                                    "topP": 1.0})))
        self.assertNotEqual(a, self.audio("e.wav", sampling=dict(CATALOG, greedy=True)))

    def test_line_depends_on_sampling_too(self):
        fake = engine.FakeEngine()
        pj = engine.PrintJob(reference=str(self.tmp / "r.wav"), text="t", model="0.6b-base",
                             spk=str(self.tmp / "p.spk"), rvq=str(self.tmp / "p.rvq"))
        (self.tmp / "r.wav").write_bytes(b"RIFFx")
        fake.voiceprint(pj, NEVER)

        def line(name, **kw):
            job = engine.LineJob(spk=pj.spk, rvq=pj.rvq, text="A line.", seed=1, output=str(self.tmp / name), **kw)
            fake.line(job, NEVER)
            return (self.tmp / name).read_bytes()

        a = line("a.wav", sampling=dict(CATALOG))
        self.assertEqual(a, line("b.wav", sampling=dict(CATALOG)))
        self.assertNotEqual(a, line("c.wav", sampling=dict(CATALOG, topP=0.9)))


class ShowTakeSamplingTests(CliBase):
    def test_order_show_prints_the_sampling_of_a_take(self):
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", CLI_VOICE, sampling={"temperature": 0.7}))
        self.ok("work")
        text = self.ok("order", "show", PROJECT, "narrator")
        self.assertIn("sampling: temp 0.7, top-k 50, top-p 1.0, rep-pen 1.05; sub: temp 0.9, top-k 50, top-p 1.0",
                      text)
        self.assertNotIn("greedy", text)
        es = self.ok("--lang", "es", "order", "show", PROJECT, "narrator")
        self.assertIn("muestreo: temp 0.7", es)
        self.assertEqual(self.js("order", "show", PROJECT, "narrator")["attempts"][0]["sampling"]["temperature"], 0.7)


if __name__ == "__main__":
    unittest.main()
