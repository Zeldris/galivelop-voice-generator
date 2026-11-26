import json
import unittest

from gvoice import i18n, listening, orders, projects, schema as S
from gvoice.errors import GvoiceError
from tests.test_cli import CONFIG, PROJECT, VOICE, CliBase


def errors_of(config):
    return [(e.path, e.code) for e in S.validate(config, S.load_schema("project-config"))]


class CriteriaTests(unittest.TestCase):
    def test_defaults_ids_and_eliminatory(self):
        self.assertEqual([(c["id"], c["eliminatory"]) for c in listening.criteria()],
                         [("theta", True), ("accent", True), ("clean", True), ("tone", False), ("stable", False)])
        for lang in ("es", "en"):
            for c in listening.criteria():
                self.assertNotIn("listening.criterion", listening.label(c, lang))

    def test_label_of_the_project_is_shown_as_is_and_falls_back_to_the_translation(self):
        self.assertEqual(listening.label({"id": "x", "label": "Mi criterio", "eliminatory": False}, "es"), "Mi criterio")
        self.assertEqual(listening.label({"id": "theta", "eliminatory": True}, "en"),
                         i18n.t("listening.criterion.theta", "en"))
        self.assertEqual(listening.label({"id": "nolabel", "eliminatory": False}, "en"), "nolabel")

    def test_schema_accepts_and_rejects(self):
        config = json.loads(CONFIG)
        config["listening"] = {"criteria": [{"id": "theta", "eliminatory": True},
                                            {"id": "breath_2", "label": "Respira", "eliminatory": False}]}
        self.assertEqual(errors_of(config), [])
        config["listening"]["criteria"][1]["id"] = "Breath"
        self.assertEqual(errors_of(config), [("/listening/criteria/1/id", "pattern")])
        config["listening"]["criteria"] = [{"id": "a", "eliminatory": True, "zzz": 1}]
        self.assertEqual(errors_of(config), [("/listening/criteria/0/zzz", "additionalProperties")])


class ListeningBase(CliBase):
    def setUp(self):
        super().setUp()
        self.add_project()
        self.ok("order", "submit", PROJECT, self.write_order("v.json", VOICE))
        self.ok("work")
        self.cfg = self.root / "galivelop-voices.json"

    def configure(self, criteria):
        config = json.loads(CONFIG)
        config["listening"] = {"criteria": criteria}
        self.cfg.write_text(json.dumps(config))

    def take(self, n=1):
        return orders.get(PROJECT, "narrator")["attempts"][n - 1]


class ProjectCriteriaTests(ListeningBase):
    def test_project_list_replaces_the_defaults(self):
        self.configure([{"id": "calm", "label": "Tranquila", "eliminatory": True},
                        {"id": "theta", "eliminatory": False}])
        found = listening.criteria(PROJECT)
        self.assertEqual([(c["id"], c["eliminatory"]) for c in found], [("calm", True), ("theta", False)])
        view = listening.view(PROJECT, self.take(), "en")
        self.assertEqual([r["label"] for r in view], ["Tranquila", i18n.t("listening.criterion.theta", "en")])

    def test_a_repeated_id_is_rejected_with_its_reason(self):
        self.configure([{"id": "calm", "eliminatory": True}, {"id": "calm", "eliminatory": False}])
        with self.assertRaises(GvoiceError) as ctx:
            projects.load_config(self.root)
        self.assertEqual((ctx.exception.code, ctx.exception.params), ("project.listening_duplicate", {"id": "calm"}))
        self.assertIn("calm", ctx.exception.message("en"))


class RateTests(ListeningBase):
    def test_mark_clear_and_note(self):
        orders.rate(PROJECT, "narrator", 1, yes=["theta", "tone"], no=["clean"], note="suena a Madrid")
        card = self.take()["listening"]
        self.assertEqual((card["marks"], card["note"]), ({"theta": "yes", "tone": "yes", "clean": "no"}, "suena a Madrid"))
        self.assertRegex(card["at"], r"^\d{4}-\d\d-\d\dT")
        orders.rate(PROJECT, "narrator", 1, clear=["tone"], no=["theta"])
        card = self.take()["listening"]
        self.assertEqual((card["marks"], card["note"]), ({"theta": "no", "clean": "no"}, "suena a Madrid"))
        orders.rate(PROJECT, "narrator", 1, clear_note=True)
        self.assertEqual(self.take()["listening"]["note"], "")
        orders.rate(PROJECT, "narrator", 1, clear=["theta", "clean"])
        self.assertNotIn("listening", self.take())

    def test_unknown_criterion_and_unknown_take(self):
        with self.assertRaises(GvoiceError) as ctx:
            orders.rate(PROJECT, "narrator", 1, yes=["nope"])
        self.assertEqual(ctx.exception.code, "listening.criterion_unknown")
        self.assertNotIn("listening", self.take())
        with self.assertRaises(GvoiceError) as ctx:
            orders.rate(PROJECT, "narrator", 9, yes=["theta"])
        self.assertEqual(ctx.exception.code, "order.attempt_unknown")
        with self.assertRaises(GvoiceError) as ctx:
            orders.rate(PROJECT, "nothing", 1, yes=["theta"])
        self.assertEqual(ctx.exception.code, "order.unknown")

    def test_a_criterion_of_the_project_is_accepted_and_a_default_one_is_not(self):
        self.configure([{"id": "calm", "eliminatory": False}])
        orders.rate(PROJECT, "narrator", 1, yes=["calm"])
        with self.assertRaises(GvoiceError) as ctx:
            orders.rate(PROJECT, "narrator", 1, yes=["theta"])
        self.assertEqual(ctx.exception.code, "listening.criterion_unknown")


class ChooseTests(ListeningBase):
    def test_a_no_on_an_eliminatory_criterion_warns_and_still_chooses(self):
        orders.rate(PROJECT, "narrator", 1, no=["theta", "accent"], yes=["clean"])
        result = orders.choose(PROJECT, "narrator", 1)
        self.assertEqual(result["new"], 1)
        self.assertEqual(result["warnings"], [{"code": "listening.eliminatory_failed", "params": {"ids": "theta, accent"}}])
        self.assertEqual(orders.get(PROJECT, "narrator")["chosen"], 1)

    def test_no_warning_without_an_eliminatory_no(self):
        orders.rate(PROJECT, "narrator", 1, no=["tone"], yes=["theta"])
        self.assertEqual(orders.choose(PROJECT, "narrator", 1), {"old": None, "new": 1})

    def test_cli_prints_the_translated_warning(self):
        self.ok("take", "rate", PROJECT, "narrator", "1", "--no", "theta")
        out = self.ok("choose", PROJECT, "narrator", "1")
        self.assertIn("Chose take 1", out)
        self.assertIn("warning: The take has a \"no\" on eliminatory criteria", out)
        self.assertIn("(theta)", out)
        self.assertEqual(self.js("choose", PROJECT, "narrator", "1")["warnings"][0]["params"], {"ids": "theta"})


class CliTests(ListeningBase):
    def test_rate_without_options_shows_the_sheet(self):
        out = self.ok("take", "rate", PROJECT, "narrator", "1")
        self.assertIn("Listening sheet of take 1:", out)
        self.assertIn("[not heard] theta: Distinguishes θ", out)
        self.assertIn("(eliminatory)", out)
        self.assertEqual(sum("(eliminatory)" in line for line in out.splitlines()), 3)

    def test_rate_marks_and_shows(self):
        out = self.ok("take", "rate", PROJECT, "narrator", "1", "--yes", "theta", "--yes", "accent", "--no", "clean",
                      "--note", "casi")
        self.assertIn("listening sheet saved", out)
        self.assertIn("[yes] theta", out)
        self.assertIn("[no] clean", out)
        self.assertIn("[not heard] tone", out)
        self.assertIn("note: casi", out)
        out = self.ok("--lang", "es", "take", "rate", PROJECT, "narrator", "1", "--clear", "theta", "--clear-note")
        self.assertIn("[sin oír] theta", out)
        self.assertNotIn("nota:", out)

    def test_rate_errors(self):
        code, out, err = self.run_cli("take", "rate", PROJECT, "narrator", "1", "--yes", "nope")
        self.assertEqual(code, 1)
        self.assertIn("not a listening criterion", err)
        code, out, err = self.run_cli("take", "rate", PROJECT, "narrator", "7")
        self.assertEqual(code, 1)
        self.assertIn("no attempt 7", err)

    def test_order_show_summary_and_json(self):
        self.ok("take", "rate", PROJECT, "narrator", "1", "--yes", "theta", "--yes", "accent", "--yes", "tone",
                "--no", "clean")
        out = self.ok("order", "show", PROJECT, "narrator")
        self.assertIn("listening: 3/5 yes, 1 no (clean)", out)
        data = self.js("order", "show", PROJECT, "narrator")
        self.assertEqual(data["attempts"][0]["listening"]["marks"]["clean"], "no")
        rated = self.js("take", "rate", PROJECT, "narrator", "1")
        self.assertEqual([r["mark"] for r in rated["criteria"]], ["yes", "yes", "no", "yes", None])

    def test_a_sample_take_can_be_rated(self):
        self.assertEqual(
            self.take()["id"], 1)
        path = self.tmp / "data"
        order = next(path.glob("projects/*/orders/narrator/@/order.json"))
        data = json.loads(order.read_text())
        data["attempts"][0]["source"] = "sample"
        order.write_text(json.dumps(data))
        orders.rate(PROJECT, "narrator", 1, yes=["theta"])
        self.assertEqual(self.take()["listening"]["marks"], {"theta": "yes"})


if __name__ == "__main__":
    unittest.main()
