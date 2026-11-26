"""Tests for the tool-agnostic layout gate (verify_layout.py).

verify_layout runs cv_checks.validate_pdf + cv_layout.check_layout over an
already-rendered PDF. The non-CLI parts are covered by their own tests; these
cover the CLI: input validation, check-failure passthrough, layout hookup.
"""
import json
import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_layout
cv_layout = importlib.import_module("cv_layout")


class PageFillTests(unittest.TestCase):
    def test_underfilled_page_is_flagged(self):
        pages = [{"width": 595, "height": 842, "rows": [
            {"y0": 42.0, "y1": 50.0, "text": "a"},
            {"y0": 60.0, "y1": 70.0, "text": "b"},
        ]}]
        problems = cv_layout.check_page_fill(pages)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "layout_bottom_whitespace")
        self.assertEqual(problems[0]["page"], 1)
        self.assertEqual(problems[0]["top_pt"], 42.0)
        self.assertEqual(problems[0]["bottom_pt"], 772.0)

    def test_balanced_page_passes(self):
        pages = [{"width": 595, "height": 842, "rows": [
            {"y0": 42.9, "y1": 50.0, "text": "a"},
            {"y0": 790.0, "y1": 799.5, "text": "b"},
        ]}]
        self.assertEqual(cv_layout.check_page_fill(pages), [])

    def test_tolerance_boundary_is_allowed(self):
        pages = [{"width": 595, "height": 842, "rows": [
            {"y0": 42.0, "y1": 50.0, "text": "a"},
            {"y0": 770.0, "y1": 780.0, "text": "b"},
        ]}]
        self.assertEqual(cv_layout.check_page_fill(pages), [])

    def test_empty_page_is_ignored(self):
        self.assertEqual(cv_layout.check_page_fill([{"width": 595, "height": 842, "rows": []}]), [])

    def test_section_headings_excludes_candidate_name(self):
        values = ["Mihai Example", "Professional Summary", "Skills", "Projects", "Education"]
        self.assertEqual(cv_layout.section_headings(values),
                         ["Professional Summary", "Skills", "Projects", "Education"])

    def test_baseline_comparison_reports_metrics_only(self):
        reference = {"left_margin_pt": 42.0, "right_edge_pt": 558.0, "top_pt": 42.9,
                     "line_pitch_pt": 12.0, "heading_gap_pt": 15.0}
        candidate = dict(reference, left_margin_pt=48.0)
        problems = cv_layout.compare_baseline(candidate, reference)
        self.assertEqual(problems, [{"code": "baseline_deviation", "metric": "left_margin_pt",
                                     "delta_pt": 6.0, "allowed_pt": 2.5}])

    def test_right_aligned_dates_are_inferred_from_float_right_parts(self):
        pages = [{"width": 595, "height": 842, "rows": [
            {"x0": 42, "x1": 500, "parts": [
                {"x0": 42, "x1": 200, "text": "engineer"},
                {"x0": 420, "x1": 500, "text": "may 2026 - present"}]},
            {"x0": 42, "x1": 500, "parts": [
                {"x0": 42, "x1": 500, "text": "diploma 2024"}]},
        ]}]
        self.assertEqual(cv_layout.right_aligned_dates(pages), ["may 2026 - present"])


class VerifyLayoutCliTests(unittest.TestCase):
    @mock.patch("sys.argv", ["verify_layout", "/nonexistent-verify-layout.pdf"])
    def test_missing_file_returns_2(self):
        code = verify_layout.main()
        self.assertEqual(code, 2)

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf"])
    def test_over_size_pdf_rejected(self):
        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch("sys.stderr") as err:
            st.return_value.st_size = verify_layout.MAX_BYTES + 1
            code = verify_layout.main()
        self.assertEqual(code, 2)

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf"])
    def test_default_expected_headings_are_mandatory_only(self):
        """Optional sections may be omitted; only mandatory headings are default."""
        def fake_validate(path, paper, max_pages, expected, posting,
                          source_html=None, ordered_text=(),
                          strict_ordered_text=False):
            self.assertEqual(tuple(expected), verify_layout.MANDATORY_HEADINGS)
            return {"passed": True, "problems": []}

        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run") as run, \
             mock.patch("sys.stdout"):
            st.return_value.st_size = 1000
            run.return_value = mock.Mock(
                returncode=0,
                stdout='<page width="595" height="110">'
                       '<line xMin="42" yMin="42" xMax="100" yMax="50"><word xMin="42" yMin="42" xMax="100" yMax="50">Professional Summary</word></line>'
                       '<line xMin="42" yMin="55" xMax="100" yMax="63"><word xMin="42" yMin="55" xMax="100" yMax="63">Skills</word></line>'
                       '<line xMin="42" yMin="68" xMax="100" yMax="76"><word xMin="42" yMin="68" xMax="100" yMax="76">Professional Experience</word></line>'
                       '<line xMin="42" yMin="81" xMax="100" yMax="89"><word xMin="42" yMin="81" xMax="100" yMax="89">Education</word></line>'
                       '<line xMin="42" yMin="94" xMax="100" yMax="99"><word xMin="42" yMin="94" xMax="100" yMax="99">Body</word></line>'
                       '</page>')
            code = verify_layout.main()
        self.assertEqual(code, 0)

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf"])
    def test_page_limit_failure_returns_1(self):
        def fake_validate(*args_item, **kwargs):
            return {"passed": False,
                    "problems": [{"code": "page_limit", "actual": 2, "maximum": 1}]}
        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run") as run, \
             mock.patch("sys.stdout"):
            st.return_value.st_size = 1000
            run.return_value = mock.Mock(returncode=1, stdout="")
            code = verify_layout.main()
        self.assertEqual(code, 1)

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf", "--json"])
    def test_pdftotext_failure_fails_closed(self):
        def fake_validate(*args_item, **kwargs):
            return {"passed": True, "problems": []}
        out = StringIO()
        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run",
                               return_value=mock.Mock(returncode=1, stdout="")), \
             mock.patch("sys.stdout", out):
            st.return_value.st_size = 1000
            code = verify_layout.main()
        self.assertEqual(code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["layout_problems"][0]["code"], "layout_check_unavailable")

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf", "--json"])
    def test_bottom_whitespace_problem_fails_cli(self):
        def fake_validate(*args_item, **kwargs):
            return {"passed": True, "problems": []}
        bbox = ('<page width="595" height="842">'
                '<line xMin="42" yMin="42" xMax="100" yMax="50"><word xMin="42" yMin="42" xMax="100" yMax="50">A</word></line>'
                '<line xMin="42" yMin="60" xMax="100" yMax="70"><word xMin="42" yMin="60" xMax="100" yMax="70">B</word></line>'
                '</page>')
        run = mock.Mock(returncode=0, stdout=bbox)
        out = StringIO()
        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run", return_value=run), \
             mock.patch("sys.stdout", out):
            st.return_value.st_size = 1000
            code = verify_layout.main()
        self.assertEqual(code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["layout_problems"][0]["code"], "layout_bottom_whitespace")

    @mock.patch("sys.argv", ["verify_layout", "cv.pdf", "--json"])
    def test_layout_problems_append_to_report(self):
        def fake_validate(*args_item, **kwargs):
            return {"passed": True, "problems": []}
        run = mock.Mock(returncode=0)
        run.return_value.stdout = "<page width='595' height='842'></page>"
        out = StringIO()
        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run", return_value=run), \
             mock.patch.object(verify_layout, "parse_pages", return_value=[]), \
             mock.patch.object(verify_layout, "check_layout",
                               return_value=[{"code": "bullet_edge", "detail": "x"}]), \
             mock.patch("sys.stdout", out):
            st.return_value.st_size = 1000
            code = verify_layout.main()
        self.assertEqual(code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["layout_problems"][0]["code"], "bullet_edge")


if __name__ == "__main__":
    unittest.main()
