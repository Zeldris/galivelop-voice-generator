"""The vendored `grun` is intact and is the pinned one (R3; `grun.vendor.verify`)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grun import vendor  # noqa: E402

# Fingerprint of the vendored copy (source galivelop-runtime@6099663b2c51, grun 0.1.0.dev0).
# Re-vendor with `python -m grun vendor --dest .` and update this line together with the copy.
PINNED = "3fcde460a379af83e42f3682ecec05910ff61f962831c3f795e40f3b43ba7900"


class VendoredGrunTest(unittest.TestCase):
    def test_copy_matches_pinned_fingerprint(self):
        self.assertEqual(vendor.verify(ROOT / "grun", pinned=PINNED), [])

    def test_wrong_pin_is_reported(self):
        problems = vendor.verify(ROOT / "grun", pinned="0" * 64)
        self.assertEqual([p["code"] for p in problems], ["vendor.pinned"])


if __name__ == "__main__":
    unittest.main()
