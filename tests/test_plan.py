"""`docs/plan.md`: los ids de la tabla de decisiones son únicos y consecutivos (retro 2026-11-17, P3: hubo dos D18)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_ROW = re.compile(r"^\| D(\d+) \|", re.M)


def decision_problem(text):
    """El motivo por el que los ids `| D<n> |` de `text` no van de D1 a Dn sin huecos ni repetidos, o None."""
    ids = [int(n) for n in _ROW.findall(text)]
    if not ids:
        return "no hay filas «| D<n> |»"
    repeated = sorted({n for n in ids if ids.count(n) > 1})
    if repeated:
        return "ids repetidos: " + ", ".join("D%d" % n for n in repeated)
    if ids != list(range(1, len(ids) + 1)):
        return "los ids no van de D1 a D%d en orden: %s" % (len(ids), " ".join("D%d" % n for n in ids))
    return None


class DecisionIds(unittest.TestCase):
    def test_plan_ids_are_unique_and_consecutive(self):
        problem = decision_problem((ROOT / "docs" / "plan.md").read_text(encoding="utf-8"))
        self.assertIsNone(problem, problem)

    def test_repeated_id_is_reported(self):
        self.assertEqual(decision_problem("| D1 | a |\n| D2 | b |\n| D2 | c |\n"), "ids repetidos: D2")

    def test_gap_or_disorder_is_reported(self):
        self.assertIn("no van de D1 a D2", decision_problem("| D1 | a |\n| D3 | b |\n"))
        self.assertIn("no van de D1 a D2", decision_problem("| D2 | a |\n| D1 | b |\n"))


if __name__ == "__main__":
    unittest.main()
