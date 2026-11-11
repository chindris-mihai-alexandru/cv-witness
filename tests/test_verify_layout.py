"""Tests for the tool-agnostic layout gate (verify_layout.py).

verify_layout runs cv_checks.validate_pdf + cv_layout.check_layout over an
already-rendered PDF. The non-CLI parts are covered by their own tests; these
cover the CLI: input validation, check-failure passthrough, layout hookup.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_layout


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
    def test_default_expected_headings(self):
        """With no --expected, the seven standard headings are used."""
        def fake_validate(path, paper, max_pages, expected, posting,
                          source_html=None, ordered_text=(),
                          strict_ordered_text=False):
            self.assertEqual(tuple(expected), (
                "Professional Summary", "Skills", "Professional Experience",
                "Projects", "Education", "Certifications", "Languages"))
            return {"passed": True, "problems": []}

        with mock.patch.object(verify_layout.Path, "is_file", return_value=True), \
             mock.patch.object(verify_layout.Path, "stat") as st, \
             mock.patch.object(verify_layout, "validate_pdf",
                               side_effect=fake_validate), \
             mock.patch.object(verify_layout.subprocess, "run") as run, \
             mock.patch("sys.stdout"):
            st.return_value.st_size = 1000
            run.return_value = mock.Mock(returncode=1, stdout="")
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
