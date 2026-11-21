"""Advisory exact-term coverage tests (fictional data only)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import jd_coverage as jc


class CoverageTest(unittest.TestCase):
    CV = ("Example Person\nEXPERIENCE\nBuilt PowerShell automation for Azure DevOps.\n"
          "Handled incident troubleshooting and monitoring with AppDynamics.\n")

    def test_exact_and_case_insensitive(self):
        rows = jc.coverage(self.CV, ["PowerShell", "powershell", "Azure DevOps"])
        self.assertTrue(all(r["present"] for r in rows))
        self.assertEqual(rows[1]["occurrences"], rows[0]["occurrences"])

    def test_multiword_and_whitespace_normalized(self):
        rows = jc.coverage("Handled  incident   troubleshooting\n",
                           ["incident troubleshooting"])
        self.assertTrue(rows[0]["present"])

    def test_missing_term_reported_not_invented(self):
        rows = jc.coverage(self.CV, ["Azure Virtual Desktop"])
        self.assertFalse(rows[0]["present"])
        self.assertEqual(rows[0]["occurrences"], 0)

    def test_terms_file_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as handle:
            handle.write("# required terms\nPowerShell\n\nAzure SQL\n")
            path = handle.name
        try:
            rows = jc.coverage(self.CV, [line.strip() for line in
                                         open(path, encoding="utf-8")
                                         if line.strip() and not line.lstrip().startswith("#")])
            self.assertEqual([r["present"] for r in rows], [True, False])
        finally:
            os.unlink(path)

    def test_empty_term_ignored(self):
        rows = jc.coverage(self.CV, ["   "])
        self.assertFalse(rows[0]["present"])


if __name__ == "__main__":
    unittest.main()
