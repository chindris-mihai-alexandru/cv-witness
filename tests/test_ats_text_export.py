"""Tests for the parser-safe plain-text CV export."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ATSTextExportTest(unittest.TestCase):
    def test_synthetic_fields_export_is_single_column_and_ordered(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import ats_text_export
        fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
        text = ats_text_export.plain_text(fields)
        headings = ["PROFESSIONAL SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE",
                    "PROJECTS", "CERTIFICATIONS", "EDUCATION", "LANGUAGES"]
        positions = [text.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Alex Morgan", text)
        self.assertIn("alex@example.com", text)
        self.assertIn("B.Sc. Computer Science", text)
        self.assertIn("Software Engineer - Jan 2023 - Present", text)
        self.assertIn("Report Desk - fictional reporting project; Python, FastAPI, SQLite - 2024", text)
        self.assertNotIn("<p>", text)
        self.assertNotIn("{{", text)
        self.assertTrue(all(not line.startswith("  ") for line in text.splitlines()))

    def test_missing_optional_sections_are_omitted(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import ats_text_export
        text = ats_text_export.plain_text({"NAME": "Jane Example", "EMAIL": "jane@example.com"})
        self.assertNotIn("EDUCATION", text)
        self.assertNotIn("SKILLS", text)
        self.assertIn("Jane Example", text)


if __name__ == "__main__":
    unittest.main()
