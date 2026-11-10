"""Tests for the ATS validation, knockout check and bullet audit scripts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import ats_validate
from scripts import bullet_audit
from scripts import knockout_check


# --- knockout_check --------------------------------------------------------

class KnockoutSignalTests(unittest.TestCase):
    def test_extracts_years_of_experience(self):
        posting = "We need 4+ years of professional experience with Kubernetes."
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 4)

    def test_takes_the_largest_stated_minimum(self):
        posting = "2+ years of experience; senior roles need 6 years of experience."
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 6)

    def test_education_floor_is_the_lower_degree_when_offered_as_alternatives(self):
        posting = ("a Master's degree with 2 to 6 years of post-graduation "
                   "professional experience; or a PhD with no more than 3 years")
        self.assertEqual(knockout_check.extract_signals(posting).get("education"), "Master's")

    def test_extracts_named_place_over_work_mode(self):
        posting = "Software Engineer\nGeneva, Switzerland\nFull-time\nFully Onsite"
        signals = knockout_check.extract_signals(posting)
        self.assertEqual(signals.get("location"), "Geneva, Switzerland")

    def test_place_regex_does_not_swallow_the_next_line(self):
        posting = "Role\nGeneva, Switzerland\nFull-time\nCompensation: CHF 6,000"
        signals = knockout_check.extract_signals(posting)
        self.assertEqual(signals.get("location"), "Geneva, Switzerland")

    def test_passes_when_cv_meets_the_year_floor(self):
        status, _ = knockout_check.check_signal("min_years", 4, "5 years of experience")
        self.assertEqual(status, "PASS")

    def test_fails_when_cv_is_below_the_year_floor(self):
        status, _ = knockout_check.check_signal("min_years", 6, "3 years of experience")
        self.assertEqual(status, "FAIL")

    def test_is_unclear_when_no_years_are_stated(self):
        status, _ = knockout_check.check_signal("min_years", 4, "experienced engineer")
        self.assertEqual(status, "UNCLEAR")

    def test_education_passes_at_or_above_the_floor(self):
        status, _ = knockout_check.check_signal("education", "Master's",
                                                "M.S. in Software Engineering, 2026")
        self.assertEqual(status, "PASS")

    def test_education_fails_below_the_floor(self):
        status, _ = knockout_check.check_signal("education", "Master's",
                                                "B.A. in Economic Informatics, 2020")
        self.assertEqual(status, "FAIL")

    def test_work_authorization_is_never_auto_passed(self):
        status, _ = knockout_check.check_signal("work_auth", "authorized to work in CH",
                                                "authorized to work in CH")
        self.assertEqual(status, "UNCLEAR")


# --- bullet_audit ----------------------------------------------------------

class BulletExtractionTests(unittest.TestCase):
    def test_joins_wrapped_bullet_lines(self):
        cv = ("PROFESSIONAL EXPERIENCE\n"
              "   Built a backend service,\n"
              "   deployed it on Kubernetes.\n")
        bullets = bullet_audit.find_bullets(cv)
        self.assertEqual(len(bullets), 1)
        self.assertIn("Built a backend service, deployed it on Kubernetes.", bullets[0])

    def test_ignores_headings_and_flush_left_body_text(self):
        cv = ("PROFESSIONAL SUMMARY\n"
              "Software engineer with four years of experience.\n"
              "PROFESSIONAL EXPERIENCE\n"
              "   Built a backend service.\n")
        bullets = bullet_audit.find_bullets(cv)
        self.assertEqual(len(bullets), 1)

    def test_certifications_are_out_of_scope(self):
        cv = ("CERTIFICATIONS\n"
              "   AWS Certified AI Practitioner, Sep 2026\n"
              "PROFESSIONAL EXPERIENCE\n"
              "   Built a backend service.\n")
        bullets = bullet_audit.find_bullets(cv)
        self.assertEqual(len(bullets), 1)


class BulletElementTests(unittest.TestCase):
    def test_detects_action_metric_and_tool(self):
        result = bullet_audit.audit_bullet(
            "Built a Python FastAPI backend serving 12,000 requests per day"
        )
        self.assertTrue(result["action"])
        self.assertTrue(result["metric"])
        self.assertTrue(result["tool"])
        self.assertEqual(result["missing"], [])

    def test_flags_a_duty_statement(self):
        result = bullet_audit.audit_bullet(
            "Responsible for various tasks across the platform"
        )
        self.assertIn("action", result["missing"])
        self.assertIn("metric", result["missing"])

    def test_flags_a_bullet_without_a_number(self):
        result = bullet_audit.audit_bullet(
            "Developed REST API endpoints with OAuth2 certificate authentication"
        )
        self.assertTrue(result["action"])
        self.assertIn("metric", result["missing"])

    def test_detects_duty_language(self):
        result = bullet_audit.audit_bullet("Assisted the team with daily duties")
        self.assertTrue(result["duty_language"])


# --- ats_validate ----------------------------------------------------------

class ContactFieldTests(unittest.TestCase):
    def test_passes_when_email_and_phone_are_present(self):
        issues = ats_validate.check_contact_fields(
            "Jane Example\njane@example.com\n+1 555 123 4567\n"
        )
        self.assertEqual(issues, [])

    def test_flags_a_missing_email(self):
        issues = ats_validate.check_contact_fields("Jane Example\n+1 555 123 4567\n")
        self.assertTrue(any("email" in i.lower() for i in issues))

    def test_flags_a_missing_phone(self):
        issues = ats_validate.check_contact_fields("Jane Example\njane@example.com\n")
        self.assertTrue(any("phone" in i.lower() for i in issues))


class SectionHeadingTests(unittest.TestCase):
    def test_standard_headings_are_all_recognized(self):
        text = ("PROFESSIONAL SUMMARY\nbody\nSKILLS\nbody\n"
                "PROFESSIONAL EXPERIENCE\nbody\nEDUCATION\nbody\n")
        self.assertEqual(ats_validate.check_section_headings(text), [])

    def test_flags_a_missing_heading(self):
        issues = ats_validate.check_section_headings("PROFESSIONAL SUMMARY\nbody\n")
        self.assertTrue(any("EXPERIENCE" in i for i in issues))


class DateTests(unittest.TestCase):
    def test_recognizes_month_year_and_iso(self):
        self.assertEqual(ats_validate.check_dates("Started Jan 2023"), [])
        self.assertEqual(ats_validate.check_dates("Started 2023-01"), [])

    def test_flags_a_cv_with_no_dates(self):
        issues = ats_validate.check_dates("No dates in this document at all")
        self.assertTrue(issues)


class FraudSignalTests(unittest.TestCase):
    def test_flags_a_broken_linkedin_url(self):
        issues = ats_validate.check_fraud_signals("linkedin.com/in/c")
        self.assertTrue(any("LinkedIn" in i for i in issues))

    def test_accepts_a_plausible_linkedin_url(self):
        self.assertEqual(ats_validate.check_fraud_signals("linkedin.com/in/jane-example"), [])


if __name__ == "__main__":
    unittest.main()
