"""Real browser/Poppler checks with fictional documents only."""
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import cv_checks as checks
from scripts import render_cv

ROOT = Path(__file__).resolve().parents[1]


def export_tools_available():
    try:
        render_cv.browser_path()
        return bool(shutil.which("pdfinfo") and shutil.which("pdftotext"))
    except checks.CheckError:
        return False


TOOLS_AVAILABLE = export_tools_available()
if os.environ.get("CV_WITNESS_REQUIRE_PDF_TESTS") == "1" and not TOOLS_AVAILABLE:
    raise RuntimeError("CI requires actual Chromium and Poppler; export tests must not silently skip.")


@unittest.skipUnless(TOOLS_AVAILABLE, "Chromium and Poppler are needed for real PDF tests")
class RealPDFTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cv-witness-pdf-test-")
        self.root = Path(self.temporary.name).resolve()
        self.options = {"no_sandbox": os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1"}
        self.source = """<!doctype html><html lang="en"><meta charset="utf-8">
<style>@page { size: A4; margin: 16mm; } body { font: 11pt Arial, sans-serif; }</style>
<body><h1>Alex Morgan (fictional)</h1><h2>Professional Summary</h2>
<p>I build small reporting tools and explain their tradeoffs in practical notes.</p>
<h2>Professional Experience</h2><p>Sample Studio (fictional), 2024</p>
<p>Ștefan checked the café inventory and wrote a clear release note.</p></body></html>"""

    def tearDown(self):
        self.temporary.cleanup()

    def render(self, source=None, name="candidate.pdf", **options):
        return render_cv.render_html(source or self.source, self.root / name, **self.options, **options)

    def test_actual_a4_and_letter_geometry_live_text_unicode(self):
        for paper in ("a4", "letter"):
            with self.subTest(paper=paper):
                report = self.render(name=paper + ".pdf", paper=paper,
                                     expected_text=["Alex Morgan", "Professional Experience", "Ștefan", "café"])
                self.assertTrue(report["passed"])
                self.assertEqual(report["pages"], 1)
                if os.name == "posix":
                    self.assertEqual((self.root / (paper + ".pdf")).stat().st_mode & 0o777, 0o600)

    def test_strict_posting_failure_never_publishes_candidate(self):
        posting = self.root / "posting.txt"
        posting.write_text("You will build small reporting tools and explain their tradeoffs.", encoding="utf-8")
        with self.assertRaises(checks.CheckFailure) as failure:
            self.render(posting=posting)
        self.assertFalse((self.root / "candidate.pdf").exists())
        self.assertIn("posting_phrase_overlap", [p["code"] for p in failure.exception.report["problems"]])
        self.assertNotIn("build small reporting tools", json.dumps(failure.exception.report))
        report = self.render(posting=posting, overlap_policy="review")
        self.assertTrue(report["passed"])
        self.assertGreater(report["posting_review"]["shared_runs"], 0)

    def test_failed_expected_text_cannot_replace_existing_output(self):
        self.render()
        output = self.root / "candidate.pdf"
        before = output.read_bytes()
        with self.assertRaises(checks.CheckFailure):
            self.render(replace=True, expected_text=["UNSUPPORTED_PRIVATE_CREDENTIAL"])
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".cv-witness-*")), [])

    def test_page_limit_fails_instead_of_dropping_content(self):
        source = self.source.replace("</body>", '<div style="break-before:page">Second fictional page</div></body>')
        with self.assertRaises(checks.CheckFailure):
            self.render(source)
        self.assertFalse((self.root / "candidate.pdf").exists())
        report = self.render(source, max_pages=2)
        self.assertEqual(report["pages"], 2)
        self.assertIn("Second fictional page", checks.read_text(self.root / "candidate.pdf"))

    def test_marker_in_html_fails_before_render(self):
        with self.assertRaises(checks.CheckError):
            self.render(self.source.replace("Alex Morgan", "{{NAME}}"))
        self.assertFalse((self.root / "candidate.pdf").exists())

    def test_existing_synthetic_template_remains_usable(self):
        template = (ROOT / "template.html").read_text(encoding="utf-8")
        fields = json.loads((ROOT / "examples/sample-cv.json").read_text())["fields"]
        filled = re.sub(r"\{\{([A-Z0-9_]+)\}\}", lambda m: html.escape(fields[m[1]], quote=True), template)
        for paper in ("a4", "letter"):
            with self.subTest(paper=paper):
                report = self.render(filled, name="legacy-" + paper + ".pdf", paper=paper, max_pages=2,
                                     expected_text=["Alex Morgan", "Education", "Languages"])
                self.assertTrue(report["passed"])

    def test_cli_strict_failure_exit_and_redacted_metrics(self):
        self.render()
        posting = self.root / "posting.md"
        posting.write_text("build small reporting tools and explain their tradeoffs", encoding="utf-8")
        for script, arguments in (
            ("jd_overlap.py", [str(self.root / "candidate.pdf"), str(posting), "--strict", "--json"]),
            ("check_cv.py", [str(self.root / "candidate.pdf"), "--posting", str(posting)]),
        ):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 1, result.stderr)
                report = json.loads(result.stdout)
                self.assertFalse(report["passed"])
                self.assertNotIn("build small reporting tools", result.stdout + result.stderr)

    def test_shell_entrypoint_works_from_another_directory_with_spaced_paths(self):
        source = self.root / "fictional input.html"
        output = self.root / "fictional output.pdf"
        source.write_text(self.source, encoding="utf-8")
        options = ["--no-sandbox"] if self.options["no_sandbox"] else []
        result = subprocess.run(["/bin/sh", str(ROOT / "render.sh"), str(source), str(output), "letter", *options], capture_output=True, text=True, timeout=100, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["paper"], "letter")
        self.assertTrue(output.is_file())
        again = subprocess.run(["/bin/sh", str(ROOT / "render.sh"), str(source), str(output), "letter"], capture_output=True, text=True, timeout=10, cwd=self.root)
        self.assertEqual(again.returncode, 2)
        self.assertNotIn("Alex Morgan", again.stdout + again.stderr)


if __name__ == "__main__":
    unittest.main()
