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
        self.assertEqual(schemas, set(EXAMPLES) | {"order"})
        for name, rel in EXAMPLES.items():
            self.assertEqual(errs(read(rel), name), [], rel)
        for rel in ORDERS:
            self.assertEqual(errs(read(rel), "order"), [], rel)

    def test_example_schema_refs_point_to_existing_files(self):
        for rel in list(EXAMPLES.values()) + list(ORDERS):
            ref = read(rel).get("$schema")
            if ref:
                self.assertTrue((ROOT / Path(rel).parent / ref).exists(), rel)

    def test_shared_defs_are_identical_across_schemas(self):
        seen = {}
        for path in (ROOT / "gvoice" / "schemas").glob("*.schema.json"):
            for key, d in S.load_schema(path.name[: -len(".schema.json")]).get("$defs", {}).items():
                seen.setdefault(key, []).append((path.name, d))
        for key in ("name", "key", "relativePath", "baseModel", "designSheet", "seed"):
            self.assertGreater(len(seen[key]), 1, key)
        for key, copies in seen.items():
            if key in ("step",):
                continue
            for fname, d in copies[1:]:
                self.assertEqual(d, copies[0][1], "%s: %s vs %s" % (key, fname, copies[0][0]))

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


if __name__ == "__main__":
    unittest.main()
