"""Public gallery and preflight budget tests with fictional fixtures only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import preflight  # noqa: E402


class GalleryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("CV_WITNESS_REQUIRE_PDF_TESTS") == "1",
                         "real PDF gallery test needs Chromium and Poppler")
    def test_gallery_renders_six_fictional_lanes_in_both_papers(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "render_template_gallery.py"),
                 "--output-dir", directory],
                capture_output=True, text=True, timeout=600)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 12)
            self.assertTrue(all(line["passed"] for line in lines))
            self.assertEqual({line["paper"] for line in lines}, {"a4", "letter"})
            self.assertEqual(len({line["lane"] for line in lines}), 6)
            for path in Path(directory).glob("*.pdf"):
                text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"],
                                               text=True)
                self.assertIn("Alex Morgan", text)
                self.assertNotIn("foundation.md", text)


class PreflightBudgetTests(unittest.TestCase):
    def test_max_postings_is_a_global_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            cv = Path(directory) / "cv.txt"
            cv.write_text("Alex Morgan\nPython\n", encoding="utf-8")
            argv = ["preflight", "--cv", str(cv), "--role", "engineer", "--max-postings", "3", "--json"]
            postings = [{"url": f"https://jobs.example/{i}", "text": f"Engineer {i}",
                         "title": "Engineer"} for i in range(12)]
            out = StringIO()
            with mock.patch.object(preflight, "fetch_yc_postings", return_value=postings[:6]), \
                 mock.patch.object(preflight, "fetch_ats_postings", return_value=postings[6:]), \
                 mock.patch.object(preflight, "fetch_adzuna_postings", return_value=[]), \
                 mock.patch.object(preflight, "fetch_arbeitnow_postings", return_value=[]), \
                 mock.patch.object(preflight, "fetch_bundesagentur_postings", return_value=[]), \
                 mock.patch.object(sys, "argv", argv), \
                 redirect_stdout(out):
                code = preflight.main()
            self.assertEqual(code, 0)
            report = json.loads(out.getvalue())
            self.assertEqual(report["checked"], 3)


if __name__ == "__main__":
    unittest.main()
