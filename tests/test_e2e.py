"""The whole cycle through the CLI (F1.6): project, voice, takes, prints, line, new reference, stale line, undo."""
import json

from gvoice import orders
from tests.test_cli import CliBase, LINE, PROJECT, VOICE

PRINT_MODELS = ("0.6b-base", "1.7b-base")  # printModels of examples/galivelop-voices.json


class EndToEnd(CliBase):
    def prints_on_disk(self, key, take):
        attempt = next(a for a in orders.get(PROJECT, key)["attempts"] if a["id"] == take)
        found = []
        for model in PRINT_MODELS:
            spk, rvq = orders.print_paths(PROJECT, key, attempt, model)
            if spk.is_file() and rvq.is_file():
                found.append(model)
        return found, sorted(attempt["prints"])

    def line_stale(self):
        return self.js("order", "show", PROJECT, "narrator/intro-01")["stale"]

    def test_full_cycle(self):
        # project
        self.assertIn(PROJECT, self.ok("project", "add", str(self.root)))

        # voice: order, work, choose; the prints job makes one print per printModel
        sub = self.js("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.assertEqual([e["kind"] for e in sub["entries"]], ["voice"])
        self.assertEqual(self.js("work"), {"processed": 1})
        self.assertEqual(self.prints_on_disk("narrator", 1), ([], []))
        chosen = self.js("choose", PROJECT, "narrator", "1")
        self.assertEqual((chosen["old"], chosen["new"]), (None, 1))
        self.assertEqual([e["kind"] for e in chosen["entries"]], ["prints"])
        self.assertIn("prints  example-world/narrator  take 1", self.ok("queue", "list", "--state", "queued"))
        self.assertEqual(self.js("work"), {"processed": 1})
        self.assertEqual(self.prints_on_disk("narrator", 1), (list(PRINT_MODELS), list(PRINT_MODELS)))
        self.assertIn("voice prints: 0.6b-base, 1.7b-base", self.ok("order", "show", PROJECT, "narrator"))

        # line: order, work, choose; made with take 1, so it is not stale
        sub = self.js("order", "submit", PROJECT, self.write_order("l.json", LINE))
        self.assertEqual([e["kind"] for e in sub["entries"]], ["line"])
        self.assertEqual(self.js("work"), {"processed": 1})
        self.assertEqual(self.js("choose", PROJECT, "narrator/intro-01", "1")["entries"], [])
        shown = self.js("order", "show", PROJECT, "narrator/intro-01")
        self.assertEqual((shown["attempts"][0]["reference"], shown["chosen"], shown["stale"]), (1, 1, False))
        self.assertNotIn("stale", self.ok("order", "list", PROJECT, "--type", "line"))
        self.assertFalse(self.line_stale())

        # another take of the voice, chosen: the line is stale (and nothing regenerates it)
        self.assertEqual(len(self.js("attempt", "new", PROJECT, "narrator", "--seed", "99")["entries"]), 1)
        self.assertEqual(self.js("work"), {"processed": 1})
        chosen = self.js("choose", PROJECT, "narrator", "2")
        self.assertEqual((chosen["old"], chosen["new"], len(chosen["entries"])), (1, 2, 1))
        self.assertEqual(self.js("work"), {"processed": 1})
        self.assertEqual(self.prints_on_disk("narrator", 2), (list(PRINT_MODELS), list(PRINT_MODELS)))
        self.assertTrue(self.line_stale())
        listed = self.js("order", "list", PROJECT)
        by_key = {o["key"]: o for o in listed}
        self.assertTrue(by_key["narrator/intro-01"]["stale"])
        self.assertEqual(by_key["narrator"]["staleLines"], ["narrator/intro-01"])
        self.assertIn("narrator/intro-01 [line]  chosen: 1  takes: 1 [stale: made with an old reference]",
                      self.ok("order", "list", PROJECT))
        self.assertIn("Stale lines: narrator/intro-01", self.ok("order", "show", PROJECT, "narrator"))
        self.assertIn("stale", self.ok("order", "show", PROJECT, "narrator/intro-01"))
        self.assertIn("desfasada", self.ok("--lang", "es", "order", "show", PROJECT, "narrator/intro-01"))
        self.assertEqual(self.js("queue", "list", "--state", "queued"), [])

        # undo: back to take 1, whose prints exist already (no job), and the line is no longer stale
        undone = self.js("undo", PROJECT, "narrator")
        self.assertEqual((undone["old"], undone["new"], undone["entries"]), (2, 1, []))
        self.assertFalse(self.line_stale())
        self.assertEqual(self.js("order", "show", PROJECT, "narrator")["staleLines"], [])
        self.assertNotIn("stale", self.ok("order", "list", PROJECT))
