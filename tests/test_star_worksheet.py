"""Tests for the STAR+R worksheet generator."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import star_worksheet as worksheet  # noqa: E402


class STARWorksheetTest(unittest.TestCase):
    def test_worksheet_is_anchored_to_approved_bullets(self):
        fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
        text = worksheet.worksheet(fields)
        self.assertIn("# STAR+R interview worksheet", text)
        self.assertIn("Built a Python service", text)
        self.assertIn("**S (Situation):** [fill from verified evidence]", text)
        self.assertIn("**Reflection:**", text)
        self.assertIn("Do not invent metrics", text)
        self.assertGreater(text.count("## "), 5)

    def test_empty_fields_do_not_invent_stories(self):
        text = worksheet.worksheet({"NAME": "Jane Example"})
        self.assertIn("No approved bullets", text)
        self.assertEqual(text.count("## "), 0)

    def test_cli_prints_only_path_and_count(self):
        with tempfile.TemporaryDirectory(prefix="cv-witness-star-") as temporary:
            target = Path(temporary) / "stories.md"
            result = __import__("subprocess").run(
                [sys.executable, str(ROOT / "scripts/star_worksheet.py"),
                 "--fields", str(ROOT / "examples/sample-cv.json"),
                 "--output", str(target)],
                check=True, capture_output=True, text=True)
            self.assertIn("Wrote STAR+R worksheet", result.stdout)
            self.assertNotIn("Alex Morgan", result.stdout)
            self.assertIn("Built a Python service", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
