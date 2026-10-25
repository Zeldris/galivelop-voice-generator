import copy
import json
import unittest
from pathlib import Path

from gvoice import schema as S

ROOT = Path(__file__).resolve().parent.parent

EXAMPLES = {
    "project-config": "examples/galivelop-voices.json",
    "design-sheet": "examples/design-sheet.json",
    "effect-chain": "examples/effect-chain.json",
    "pack": "examples/pack.json",
    "voice": "examples/voice.json",
    "machine-profile": "gvoice/machine_profiles/steam-deck.json",
}
ORDERS = ("examples/order-voice.json", "examples/order-line.json")


def read(rel):
    with open(ROOT / rel, encoding="utf-8") as fh:
        return json.load(fh)


def errs(instance, name):
    return sorted((e.path, e.code) for e in S.validate(instance, S.load_schema(name)))


class ValidExamples(unittest.TestCase):
    def test_every_schema_has_a_valid_example(self):
        schemas = {p.name[: -len(".schema.json")] for p in (ROOT / "gvoice" / "schemas").glob("*.schema.json")}
        self.assertEqual(schemas, set(EXAMPLES) | {"order", "common"})
        for name, rel in EXAMPLES.items():
            self.assertEqual(errs(read(rel), name), [], rel)
        for rel in ORDERS:
            self.assertEqual(errs(read(rel), "order"), [], rel)

    def test_example_schema_refs_point_to_existing_files(self):
        for rel in list(EXAMPLES.values()) + list(ORDERS):
            ref = read(rel).get("$schema")
            if ref:
                self.assertTrue((ROOT / Path(rel).parent / ref).exists(), rel)

    def test_shared_defs_live_only_in_common(self):
        common = set(S.load_schema("common")["$defs"])
        self.assertTrue({"key", "name", "relativePath", "baseModel", "seed", "testText", "device"} <= common)
        for path in (ROOT / "gvoice" / "schemas").glob("*.schema.json"):
            name = path.name[: -len(".schema.json")]
            if name == "common":
                continue
            copies = common & set(S.load_schema(name).get("$defs", {}))
            self.assertEqual(copies, set(), name)
            self.assertNotIn("designSheet", S.load_schema(name).get("$defs", {}), name)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('"0.6b-base"', text, name)  # model ids only in common (and examples)
            self.assertNotIn("(?![/~])", text, name)  # the relative-path pattern lives in common

    def test_voice_example_matches_the_project_example(self):
        voice, project = read(EXAMPLES["voice"]), read(EXAMPLES["project-config"])
        self.assertEqual(voice.get("effects"), project["voices"][voice["key"]].get("effects"))
        self.assertNotIn("formatVersion", voice)
        self.assertEqual(voice["device"], "Vulkan0")
        for print_ in voice["prints"].values():
            self.assertIn("device", print_)

    def test_design_sheet_has_the_twelve_keys(self):
        props = set(S.load_schema("design-sheet")["properties"])
        self.assertEqual(props - {"$schema", "extra"}, {
            "gender", "age", "pitch", "speed", "volume", "clarity", "fluency", "accent",
            "texture", "emotion", "tone", "personality"})

    def test_effect_vocabulary_is_closed(self):
        enum = S.load_schema("effect-chain")["$defs"]["step"]["properties"]["type"]["enum"]
        self.assertEqual(sorted(enum), sorted(
            ["highpass", "lowpass", "equalizer", "gain", "saturation", "reverb", "chorus", "pitch"]))


class BrokenExamples(unittest.TestCase):
    def broken(self, rel, name, mutate, expected):
        data = copy.deepcopy(read(rel))
        mutate(data)
        self.assertEqual(errs(data, name), expected)

    def test_project_config(self):
        rel = EXAMPLES["project-config"]
        self.broken(rel, "project-config", lambda d: d["voices"].update({"Bad_Key": {}}),
                    [("/voices/Bad_Key", "propertyNames")])
        self.broken(rel, "project-config", lambda d: d.update(printModels=["9b-base"]),
                    [("/printModels/0", "enum")])
        self.broken(rel, "project-config", lambda d: d["delivery"].update(dir="../out"),
                    [("/delivery/dir", "pattern")])
        self.broken(rel, "project-config", lambda d: d.update(voices={}),
                    [("/voices", "minProperties")])
        self.broken(rel, "project-config", lambda d: d.pop("name"), [("", "required")])
        self.broken(rel, "project-config", lambda d: d.update(minVersion="1.0"),
                    [("/minVersion", "pattern")])

    def test_order(self):
        v, ln = ORDERS
        self.broken(v, "order", lambda d: d.update(type="sound"), [("/type", "enum")])
        self.broken(v, "order", lambda d: d.update(seed=-1), [("/seed", "minimum")])
        self.broken(v, "order", lambda d: d["designSheet"].update(volume=3),
                    [("/designSheet/volume", "type")])
        self.broken(v, "order", lambda d: d["designSheet"].update(mood="x"),
                    [("/designSheet/mood", "additionalProperties")])
        self.broken(ln, "order", lambda d: d.update(key="a/../b"), [("/key", "pattern")])
        self.broken(ln, "order", lambda d: d.update(text=""), [("/text", "minLength")])
        self.broken(ln, "order", lambda d: d.pop("type"), [("", "required")])
        for bad, code in ((0, "minimum"), (21, "maximum"), ("2", "type"), (1.5, "type")):
            self.broken(ln, "order", lambda d: d.update(count=bad), [("/count", code)])
            self.broken(v, "order", lambda d: d.update(count=bad), [("/count", code)])
        self.broken(ln, "order", lambda d: d.update(model="9b-base"), [("/model", "enum")])
        self.broken(v, "order", lambda d: d.update(model="1.7b-base"), [("/model", "false")])

    def test_machine_profile(self):
        rel = EXAMPLES["machine-profile"]
        self.broken(rel, "machine-profile", lambda d: d["engine"].update(fallbackDevice="gpu"),
                    [("/engine/fallbackDevice", "enum")])
        self.broken(rel, "machine-profile", lambda d: d["models"].update(design="0.6b-base"),
                    [("/models/design", "enum")])
        self.broken(rel, "machine-profile", lambda d: d.pop("timeoutS"), [("", "required")])
        self.broken(rel, "machine-profile", lambda d: d.update(timeoutS=0),
                    [("/timeoutS", "minimum")])

    def test_design_sheet(self):
        rel = EXAMPLES["design-sheet"]
        self.broken(rel, "design-sheet", lambda d: d.update(age=30), [("/age", "type")])
        self.broken(rel, "design-sheet", lambda d: d.update(mood="x"),
                    [("/mood", "additionalProperties")])
        self.broken(rel, "design-sheet", lambda d: d["extra"].update(a=1),
                    [("/extra/a", "type")])

    def test_effect_chain(self):
        rel = EXAMPLES["effect-chain"]
        self.broken(rel, "effect-chain", lambda d: d["steps"][0].update(type="flanger"),
                    [("/steps/0/type", "enum")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][2].update(semitones=40),
                    [("/steps/2/semitones", "maximum")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][0].update(freqHz=5),
                    [("/steps/0/freqHz", "minimum")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][4].update(impulse="/abs.wav"),
                    [("/steps/4/impulse", "pattern")])
        self.broken(rel, "effect-chain", lambda d: d.update(steps=[]), [("/steps", "minItems")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][1].update(q=1),
                    [("/steps/1/q", "additionalProperties")])

    def test_pack(self):
        rel = EXAMPLES["pack"]
        self.broken(rel, "pack", lambda d: d["models"][0].update(sha256="abc"),
                    [("/models/0/sha256", "pattern")])
        self.broken(rel, "pack", lambda d: d["engine"].update(commit="main"),
                    [("/engine/commit", "pattern")])
        self.broken(rel, "pack", lambda d: d.pop("formatVersion"), [("", "required")])
        self.broken(rel, "pack", lambda d: d.update(formatVersion=0),
                    [("/formatVersion", "minimum")])

    def test_voice(self):
        rel = EXAMPLES["voice"]
        self.broken(rel, "voice", lambda d: d["reference"].pop("text"),
                    [("/reference", "required")])
        self.broken(rel, "voice", lambda d: d["reference"].update(audio="../x.wav"),
                    [("/reference/audio", "pattern")])
        self.broken(rel, "voice", lambda d: d["prints"]["0.6b-base"].pop("rvq"),
                    [("/prints/0.6b-base", "required")])
        self.broken(rel, "voice", lambda d: d["prints"].update({"Bad": d["prints"]["0.6b-base"]}),
                    [("/prints/Bad", "propertyNames")])
        self.broken(rel, "voice", lambda d: d.update(key="Narrator"), [("/key", "pattern")])

    def test_order_type_decides_the_fields(self):
        v, ln = ORDERS
        self.broken(ln, "order", lambda d: d.pop("text"), [("", "required")])
        self.broken(ln, "order", lambda d: d.pop("voice"), [("", "required")])
        self.broken(ln, "order", lambda d: d.update(testText="hi"), [("/testText", "false")])
        self.broken(ln, "order", lambda d: d.update(designSheet={}), [("/designSheet", "false")])
        self.broken(v, "order", lambda d: d.update(text="hi"), [("/text", "false")])
        self.broken(v, "order", lambda d: d.update(voice="narrator"), [("/voice", "false")])
        self.broken(v, "order", lambda d: d.pop("testText"), [("", "required")])
        self.broken(v, "order", lambda d: d.pop("designSheet"), [("", "required")])
        self.broken(v, "order", lambda d: d.pop("type"), [("", "required")])

    def test_order_missing_field_names_it(self):
        data = copy.deepcopy(read(ORDERS[1]))
        del data["text"]
        err = S.validate(data, S.load_schema("order"))[0]
        self.assertEqual(err.params["name"], "text")

    def test_seed_is_an_unsigned_32_bit_integer(self):
        v = ORDERS[0]
        self.broken(v, "order", lambda d: d.update(seed=2 ** 32 - 1), [])
        self.broken(v, "order", lambda d: d.update(seed=2 ** 32), [("/seed", "maximum")])
        self.broken(v, "order", lambda d: d.update(seed=2 ** 80), [("/seed", "maximum")])
        self.broken(v, "order", lambda d: d.update(seed=1e300), [("/seed", "maximum")])
        self.broken(v, "order", lambda d: d.update(seed=1.5), [("/seed", "type")])
        self.broken(EXAMPLES["voice"], "voice", lambda d: d.update(seed=2 ** 80),
                    [("/seed", "maximum")])

    def test_effect_steps_require_their_own_parameters(self):
        rel = EXAMPLES["effect-chain"]
        self.broken(rel, "effect-chain", lambda d: d["steps"][4].pop("impulse"),
                    [("/steps/4", "required")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][2].pop("semitones"),
                    [("/steps/2", "required")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][0].pop("freqHz"),
                    [("/steps/0", "required")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][6].pop("freqHz"),
                    [("/steps/6", "required")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][0].update(semitones=3),
                    [("/steps/0/semitones", "additionalProperties")])
        self.broken(rel, "effect-chain", lambda d: d["steps"][7].update(impulse="a.wav"),
                    [("/steps/7/impulse", "additionalProperties")])

    def test_effect_step_error_message_names_the_parameter(self):
        data = copy.deepcopy(read(EXAMPLES["effect-chain"]))
        data["steps"][4].pop("impulse")
        err = S.validate(data, S.load_schema("effect-chain"))[0]
        self.assertEqual((err.path, err.params["name"]), ("/steps/4", "impulse"))

    def test_voice_device_and_prints(self):
        rel = EXAMPLES["voice"]
        self.broken(rel, "voice", lambda d: d.pop("device"), [("", "required")])
        self.broken(rel, "voice", lambda d: d.update(device="gpu"), [("/device", "pattern")])
        self.broken(rel, "voice", lambda d: d["prints"]["0.6b-base"].pop("device"),
                    [("/prints/0.6b-base", "required")])
        self.broken(rel, "voice", lambda d: d.update(formatVersion=1),
                    [("/formatVersion", "additionalProperties")])

    def test_prints_with_unknown_model(self):
        data = copy.deepcopy(read(EXAMPLES["voice"]))
        data["prints"]["9b-base"] = data["prints"]["0.6b-base"]
        errors = S.validate(data, S.load_schema("voice"))
        self.assertEqual([(e.path, e.code, e.params["name"]) for e in errors],
                         [("/prints/9b-base", "propertyNames", "9b-base")])

    def test_pack_models_and_device(self):
        rel = EXAMPLES["pack"]
        self.broken(rel, "pack", lambda d: d["models"][0].update(id="9b-base"),
                    [("/models/0/id", "enum")])
        self.broken(rel, "pack", lambda d: d.update(device="Vulkan0"), [])
        self.broken(rel, "pack", lambda d: d.update(device="x"), [("/device", "pattern")])

    def test_machine_profile_requires_the_abort_threshold(self):
        data = copy.deepcopy(read(EXAMPLES["machine-profile"]))
        del data["watchMemoryMb"]
        err = S.validate(data, S.load_schema("machine-profile"))[0]
        self.assertEqual((err.path, err.code, err.params["name"]), ("", "required", "watchMemoryMb"))


if __name__ == "__main__":
    unittest.main()
