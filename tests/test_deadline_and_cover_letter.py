"""Deadline and cover-letter check tests (fictional dates and people only)."""
import datetime
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from email.message import Message
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_posting_liveness as liveness
import cover_letter_check as clc


class DeadlineTest(unittest.TestCase):
    TODAY = datetime.date(2026, 11, 21)

    def test_expired_yearless_deadline(self):
        body = "Cloud Engineer role. Apply today! The deadline for applying is November 20th."
        date, _ = liveness.find_deadline(body, today=self.TODAY)
        self.assertEqual(date, datetime.date(2026, 11, 20))
        verdict, detail = liveness.classify(200, body, "/careers/493",
                                            "/careers/493", "Engineer",
                                            today=self.TODAY)
        self.assertEqual(verdict, "expired")
        self.assertIn("PASSED", detail)

    def test_future_deadline_is_live(self):
        body = "Cloud Engineer role. The deadline for applying is November 30th, 2026."
        verdict, detail = liveness.classify(200, body, "/careers/493",
                                            "/careers/493", "Engineer",
                                            today=self.TODAY)
        self.assertEqual(verdict, "live")
        self.assertIn("open", detail)

    def test_january_deadline_in_november_is_next_year(self):
        date, _ = liveness.find_deadline("Apply by January 5th.", today=self.TODAY)
        self.assertEqual(date, datetime.date(2027, 1, 5))

    def test_no_deadline_phrase_unaffected(self):
        date, _ = liveness.find_deadline("Posted 20 November 2026.", today=self.TODAY)
        self.assertIsNone(date)

    def test_transient_http_is_suspicious_not_dead(self):
        for status in (429, 500, 502, 504):
            verdict, detail = liveness.classify(status, "Bad Gateway", "/job/1", "/job/1", "")
            self.assertEqual(verdict, "suspicious")
            self.assertIn("transient", detail)
        verdict, detail = liveness.classify(404, "Not found", "/job/1", "/job/1", "")
        self.assertEqual(verdict, "dead")

    def test_closure_question_and_filled_form_are_not_closure(self):
        body = "Applications closed? Don't see what you're looking for? Engineer roles open."
        self.assertIsNone(liveness.closure_detail(body))
        body = "Once the job application form has been filled out, submit it. Engineer role."
        self.assertIsNone(liveness.closure_detail(body))

    def test_filled_requisition_is_closure(self):
        body = "We are sorry, the job you are trying to apply for has been filled."
        self.assertIn("filled", liveness.closure_detail(body))

    def test_cli_rejects_non_http_url_without_network(self):
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            code = liveness.main(["not a url", "--expect", "Engineer"])
        self.assertEqual(code, 2)

    def test_cli_rejects_file_scheme_without_local_read(self):
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            code = liveness.main(["file:///etc/passwd", "--expect", "Engineer"])
        self.assertEqual(code, 2)

    def test_cli_reads_http_error_body_for_closure(self):
        error = HTTPError("https://jobs.example/1", 404, "Not Found", Message(),
                          io.BytesIO(b"<p>This job is no longer available.</p>"))
        out = io.StringIO()
        with mock.patch.object(liveness.urllib.request, "urlopen", side_effect=error), \
             redirect_stdout(out):
            code = liveness.main(["https://jobs.example/1", "--expect", "Engineer"])
        self.assertEqual(code, 1)
        self.assertIn("closure phrase", out.getvalue())


class CoverLetterTest(unittest.TestCase):
    BODY = ("Dear Team, I support cloud platforms. " * 42 +
            "I am based in Romania and can relocate. Kind regards, Example Person.")

    def test_clean_letter_passes(self):
        report = clc.check_letter(self.BODY, role="cloud platforms",
                                  company="", eu_citizen=True)
        self.assertTrue(report["passed"], report["flags"])

    def test_flags_placeholder_hype_and_permit_confusion(self):
        text = self.BODY + " I am passionate and still need a work permit. [FILL: x]"
        report = clc.check_letter(text, eu_citizen=True)
        joined = " ".join(report["flags"])
        self.assertIn("placeholder", joined)
        self.assertIn("hype", joined)
        self.assertIn("work permit", joined)

    def test_non_eu_skips_permit_check(self):
        text = self.BODY + " I need a work permit."
        self.assertTrue(clc.check_letter(text, eu_citizen=False)["passed"])

    def test_negated_permit_statement_is_not_flagged(self):
        text = self.BODY + " As an EU citizen I do not need a work permit in Denmark."
        self.assertTrue(clc.check_letter(text, eu_citizen=True)["passed"])

    def test_flags_dashes_and_stock_opening(self):
        text = self.BODY + " I am writing to apply — with care."
        flags = " ".join(clc.check_letter(text)["flags"])
        self.assertIn("em dash", flags)
        self.assertIn("hype wording", flags)


if __name__ == "__main__":
    unittest.main()
