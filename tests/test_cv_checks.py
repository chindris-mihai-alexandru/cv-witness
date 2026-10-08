"""Synthetic export validation and phrase-review tests."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import cv_checks as checks
from scripts import jd_overlap
from scripts import render_cv


class PhraseTests(unittest.TestCase):
    def test_long_run_is_not_capped_at_six_words(self):
        text = "one two three four five six seven eight nine ten"
        runs = checks.shared_runs(text, text)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["words"], 10)

    def test_three_words_do_not_fail_strict_threshold(self):
        self.assertEqual(checks.shared_runs("build tools with care", "build tools with patience"), [])

    def test_unicode_normalization_keeps_non_ascii_words(self):
        runs = checks.shared_runs("Ștefan a écrit des notes claires", "Stefan a ecrit des notes claires")
        self.assertEqual(runs[0]["words"], 6)

    def test_default_report_does_not_print_private_phrase(self):
        text = "synthetic confidential words stay private"
        self.assertNotIn(text, json.dumps(checks.overlap_report(text, text)))
        self.assertIn(text, json.dumps(checks.overlap_report(text, text, True)))

    def test_repetitive_input_has_a_work_limit(self):
        with patch.object(checks, "MAX_PAIRS", 20):
            with self.assertRaises(checks.CheckError):
                checks.shared_runs("word " * 100, "word " * 100)

    def test_empty_inputs_fail_closed(self):
        with self.assertRaises(checks.CheckError):
            checks.shared_runs("hello", "")

    def test_cli_strict_failure_review_success_and_phrase_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cv = root / "cv.txt"
            posting = root / "posting.md"
            text = "synthetic private matching phrase here"
            cv.write_text(text)
            posting.write_text(text)
            for options, expected in ((["--strict"], 1), ([], 0), (["--show-phrases", "--strict"], 1)):
                with self.subTest(options=options):
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        result = jd_overlap.main([str(cv), str(posting), "--json", *options])
                    self.assertEqual(result, expected)
                    report = json.loads(stream.getvalue())
                    self.assertEqual("phrase" in report["runs"][0], "--show-phrases" in options)
                    self.assertNotIn("originality certificate", report)

    def test_bad_utf8_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.md"
            path.write_bytes(b"\xff")
            with self.assertRaises(checks.CheckError):
                checks.read_text(path)

    def test_tool_output_is_bounded_before_capture_finishes(self):
        with patch.object(checks, "MAX_BYTES", 1024):
            with self.assertRaises(checks.CheckError):
                checks.run_tool([sys.executable, "-c", "import sys; sys.stdout.write('x'*1000000)"])

    def test_tool_timeout_and_stderr_never_echo_private_text(self):
        with self.assertRaises(checks.CheckError):
            checks.run_tool([sys.executable, "-c", "import time; time.sleep(5)"], timeout=.05)
        try:
            checks.run_tool([sys.executable, "-c", "import sys; print('PRIVATE_TOOL_TEXT',file=sys.stderr); sys.exit(1)"])
        except checks.CheckError as error:
            self.assertNotIn("PRIVATE_TOOL_TEXT", str(error))
        else:
            self.fail("Expected a tool failure")


class PDFCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.temp.name) / "synthetic.pdf"
        self.pdf.write_bytes(b"%PDF-synthetic")
        self.info = "Pages: 1\nEncrypted: no\n"
        self.box = "Page    1 size: 594.96 x 841.92 pts (A4)\n"
        self.text = "Alex Morgan\nProfessional Experience\nBuilt a small garden planner.\n\f"

    def tearDown(self):
        self.temp.cleanup()

    def validate(self, **kwargs):
        with patch.object(checks, "run_tool", side_effect=[self.info, self.box]), patch.object(checks, "read_text", return_value=self.text):
            return checks.validate_pdf(self.pdf, **kwargs)

    def test_good_live_text_and_geometry_pass(self):
        self.assertTrue(self.validate(expected_text=["Alex Morgan", "Professional Experience"])["passed"])

    def test_missing_expected_text_is_redacted(self):
        report = self.validate(expected_text=["PRIVATE_MISSING_CREDENTIAL"])
        self.assertFalse(report["passed"])
        self.assertNotIn("PRIVATE_MISSING_CREDENTIAL", json.dumps(report))
        self.assertIn({"code": "missing_expected_text", "item": 1}, report["problems"])

    def test_wrong_paper_fails(self):
        report = self.validate(paper="letter")
        self.assertIn("paper_geometry", [item["code"] for item in report["problems"]])

    def test_blank_second_page_and_page_limit_fail(self):
        self.info = "Pages: 2\nEncrypted: no\n"
        self.box += "Page    2 size: 594.96 x 841.92 pts (A4)\n"
        self.text += "\f"
        report = self.validate()
        self.assertIn("page_limit", [item["code"] for item in report["problems"]])
        self.assertIn("empty_or_image_only_page", [item["code"] for item in report["problems"]])

    def test_markers_replacement_glyph_and_encryption_fail(self):
        self.text = "[FILL: fictional missing detail] \ufffd \f"
        self.info = "Pages: 1\nEncrypted: yes (print:yes)\n"
        report = self.validate()
        self.assertEqual(set(item["code"] for item in report["problems"]), {"unresolved_marker", "invalid_extracted_glyph", "encrypted_pdf"})

    def test_source_markers_are_checked_even_if_not_extracted(self):
        self.assertIn("unresolved_source_marker", [item["code"] for item in self.validate(source_html="<title>{{NAME}}</title>")["problems"]])

    def test_explicit_page_limit_contract_is_validated(self):
        for limit in (0, 31, True):
            with self.subTest(limit=limit):
                with self.assertRaises(checks.CheckError):
                    checks.validate_pdf(self.pdf, max_pages=limit)


class RendererContractTests(unittest.TestCase):
    def test_page_size_override_works_for_a4_and_letter_without_source_changes(self):
        source = "<style>@page { margin: 12mm; size : letter; }</style>"
        self.assertIn("size: A4;", render_cv.page_css(source, "a4"))
        self.assertIn("size: letter;", render_cv.page_css(source, "letter"))
        self.assertIn("size : letter", source)

    def test_missing_and_ambiguous_page_css_fail(self):
        for source in ("<style>body {}</style>", "@page{size:A4}@page{size:letter}", "@page{margin:12mm}", "@page{size:A4;size:letter}"):
            with self.subTest(source=source):
                with self.assertRaises(checks.CheckError):
                    render_cv.page_css(source, "a4")

    def test_html_sources_reject_unresolved_and_external_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.html"
            for content in ("<style>@page{size:A4;}</style>{{NAME}}", "<script>fake()</script>", '<img src="https://example.com/image">'):
                with self.subTest(content=content):
                    source.write_text(content)
                    with self.assertRaises(checks.CheckError):
                        render_cv.checked_source(source, "a4")

    def test_direct_renderer_cannot_bypass_self_contained_source_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "candidate.pdf"
            for content in ('@page{size:A4}<script>fake()</script>', '@page{size:A4}<img src="https://example.com/private">'):
                with self.subTest(content=content), patch.object(render_cv, "browser_path") as browser:
                    with self.assertRaises(checks.CheckError):
                        render_cv.render_html(content, output)
                    browser.assert_not_called()
                    self.assertFalse(output.exists())

    def test_symlinked_output_parent_fails_before_browser_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "target").mkdir()
            (root / "linked").symlink_to(root / "target", target_is_directory=True)
            with self.assertRaises(checks.CheckError), patch.object(render_cv, "browser_path") as browser:
                render_cv.render_html("@page{size:A4} Fictional prose", root / "linked" / "candidate.pdf")
            browser.assert_not_called()
            self.assertFalse((root / "target" / "candidate.pdf").exists())

    def test_invalid_page_limit_fails_before_browser_runs(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(render_cv, "browser_path") as browser:
            with self.assertRaises(checks.CheckError):
                render_cv.render_html("@page{size:A4} Fictional prose", Path(temporary).resolve() / "candidate.pdf", max_pages=0)
            browser.assert_not_called()

    def test_explicit_browser_environment_does_not_silently_fallback(self):
        with patch.dict("os.environ", {"CV_WITNESS_BROWSER": "/nonexistent/cv-witness-browser"}):
            with self.assertRaises(checks.CheckError):
                render_cv.browser_path()

    def test_completed_pdf_does_not_wait_for_a_lingering_browser_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "candidate.pdf"
            code = "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-synthetic\\n%%EOF\\n'); time.sleep(30)"
            render_cv.run_browser([sys.executable, "-c", code, str(output)], output, timeout=3)
            self.assertIsNotNone(render_cv.complete_pdf(output))

    def test_incomplete_pdf_is_not_accepted_when_process_lingers(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "candidate.pdf"
            code = "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-incomplete'); time.sleep(30)"
            with self.assertRaises(checks.CheckError):
                render_cv.run_browser([sys.executable, "-c", code, str(output)], output, timeout=.2)
            self.assertIsNone(render_cv.complete_pdf(output))

    def test_failed_browser_with_a_pdf_still_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "candidate.pdf"
            code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'%PDF-synthetic\\n%%EOF\\n'); sys.exit(1)"
            with self.assertRaises(checks.CheckError):
                render_cv.run_browser([sys.executable, "-c", code, str(output)], output, timeout=3)


if __name__ == "__main__":
    unittest.main()
