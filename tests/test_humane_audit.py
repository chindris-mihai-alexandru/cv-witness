"""Tests for the humane wording audit (advisory lexical review aid, not a verdict)."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import humane_audit


class HumaneAuditTests(unittest.TestCase):
    def test_flags_hype_buzzword(self):
        f = humane_audit.scan("Spearheaded a world-class, results-driven platform.")
        self.assertTrue(f)
        self.assertIn("hype/buzzword", f[0]["hits"])

    def test_flags_superlative_without_evidence(self):
        f = humane_audit.scan("Delivered an exceptional, unparalleled result.")
        self.assertTrue(f)
        self.assertIn("superlative (needs evidence)", f[0]["hits"])

    def test_flags_self_flattery(self):
        f = humane_audit.scan("A passionate, dedicated team player.")
        self.assertTrue(f)
        self.assertIn("self-flattery", f[0]["hits"])

    def test_plain_factual_bullet_is_not_flagged(self):
        f = humane_audit.scan("Built a Python FastAPI backend with source-cited RAG search.")
        self.assertEqual(f, [])

    def test_matching_is_case_insensitive(self):
        self.assertTrue(humane_audit.scan("WORLD-CLASS synergy"))

    def test_empty_text_has_no_findings(self):
        self.assertEqual(humane_audit.scan(""), [])

    def test_advisory_exit_zero_even_with_flags(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.txt"
            p.write_text("A passionate guru spearheading world-class synergy.")
            self.assertEqual(humane_audit.main([str(p)]), 0)

    def test_advisory_exit_zero_when_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.txt"
            p.write_text("Built a service and added tests.")
            self.assertEqual(humane_audit.main([str(p)]), 0)

    def test_extract_text_plain(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.txt"
            p.write_text("Built a service.")
            self.assertIn("Built a service.", humane_audit.extract_text(p))

    def test_extract_text_strips_html(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "draft.html"
            p.write_text("<ul><li>Built a service.</li></ul>")
            self.assertIn("Built a service.", humane_audit.extract_text(p))


if __name__ == "__main__":
    unittest.main()