"""Tests for the ATS validation, knockout check and bullet audit scripts."""
import json
from pathlib import Path
import shutil
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

    def test_explicit_range_beats_company_tenure(self):
        # The "over 22 years of experience" is the FIRM's tenure, not the role floor.
        posting = ("Example Capital is a multi-billion firm with over 22 years of experience. "
                   "Requires 4-6 years of hands-on infrastructure operations experience.")
        # A stated range means AT LEAST its lower bound (4), not its ceiling.
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 4)

    def test_range_takes_lower_bound(self):
        # "2 to 6 years" requires at least 2; 6 is the ceiling, not the floor.
        # Reporting the ceiling would overstate the requirement (honest gap
        # analysis must report the posting's real floor).
        posting = "We need someone with 2 to 6 years of post-graduation experience."
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 2)

    def test_company_tenure_alone_is_not_a_requirement(self):
        posting = "Established with over 22 years of experience, our firm is hiring a junior engineer."
        self.assertNotIn("min_years", knockout_check.extract_signals(posting))

    def test_decade_numbers_kept_for_explicit_senior_roles(self):
        posting = "A senior staff role for someone with 20+ years of experience."
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 20)

    def test_takes_the_largest_stated_minimum(self):
        posting = "2+ years of experience; senior roles need 6 years of experience."
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 6)

    def test_noun_list_between_years_and_experience(self):
        # Microsoft's "Technical Support Advisor" wording: the number and
        # "experience" are separated by a list of job functions.
        posting = ("Bachelor's Degree in IT AND 3+ years system development, network "
                   "operations, software support, IT, consulting or technical "
                   "troubleshooting experience OR 4+ years of the above")
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 3)

    def test_or_alternatives_use_the_lower_floor(self):
        # "3+ years X OR 4+ years Y" is satisfiable by either branch, so the
        # honest floor is 3, not 4.
        posting = "3+ years of experience OR 4+ years of equivalent experience"
        self.assertEqual(knockout_check.extract_signals(posting).get("min_years"), 3)

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

    def test_middle_dot_header_city_with_work_mode(self):
        # Teamtailor headers: "Platform Services · Rotterdam · Hybrid". The city
        # sits between middle dots mid-line, not as a "City, Country" pair.
        posting = ("Azure & Citrix Platform Engineer\n"
                   "Platform Services · Rotterdam · Hybrid\n"
                   "Build secure, reliable cloud solutions.")
        signals = knockout_check.extract_signals(posting)
        self.assertEqual(signals.get("location"), "Rotterdam, NL")
        self.assertIn("Rotterdam, NL", signals.get("locations", []))

    def test_alternatives_list_is_not_a_location(self):
        # "primarily in Azure, Citrix or infrastructure engineering" is a list of
        # alternatives, not a work location; the real city still wins.
        posting = ("Platform Engineer\n"
                   "Whether your expertise lies primarily in Azure, Citrix or "
                   "infrastructure engineering, you will grow.\n"
                   "Platform Services · Rotterdam · Hybrid")
        signals = knockout_check.extract_signals(posting)
        self.assertNotIn("Azure, Citrix", signals.get("locations", []))
        self.assertEqual(signals.get("location"), "Rotterdam, NL")

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

    def test_work_authorization_is_unclear_without_a_candidate_profile(self):
        # No citizenship/residency fact: the checker must not guess a pass.
        status, _ = knockout_check.check_signal("work_auth", "authorized to work in CH",
                                                "authorized to work in CH")
        self.assertEqual(status, "UNCLEAR")

    def test_work_authorization_passes_under_eu_free_movement(self):
        # A Romanian citizen may work in Denmark without sponsorship.
        status, detail = knockout_check.check_signal(
            "work_auth", "right to work in Denmark",
            "Romania", {"citizen": "RO", "work_auth_countries": ["denmark"], "sponsorship": False})
        self.assertEqual(status, "PASS")
        self.assertIn("free movement", detail)

    def test_work_authorization_fails_for_uk_without_sponsorship(self):
        status, detail = knockout_check.check_signal(
            "work_auth", "right to work in the United Kingdom",
            "Romania", {"citizen": "RO", "work_auth_countries": ["united kingdom"], "sponsorship": False})
        self.assertEqual(status, "FAIL")
        self.assertIn("no sponsorship", detail)

    def test_work_authorization_one_viable_country_is_enough(self):
        # "Denmark or the United Kingdom": the Danish option carries the role.
        status, _ = knockout_check.check_signal(
            "work_auth", "right to work in Denmark or the United Kingdom",
            "Romania", {"citizen": "RO",
                        "work_auth_countries": ["denmark", "united kingdom"],
                        "sponsorship": False})
        self.assertEqual(status, "PASS")

    def test_clearance_is_a_hard_fail_without_an_active_clearance(self):
        status, detail = knockout_check.check_signal(
            "clearance", "active security clearance", "no clearance", {"citizen": "RO"})
        self.assertEqual(status, "FAIL")
        self.assertIn("employer-sponsored", detail)

    def test_clearance_passes_when_the_candidate_holds_one(self):
        status, _ = knockout_check.check_signal(
            "clearance", "active security clearance", "no clearance",
            {"citizen": "RO", "holds_clearance": True})
        self.assertEqual(status, "PASS")

    def test_extracts_every_location_from_a_locations_header(self):
        posting = "Cloud Platform Engineer\nlocations: Aalborg, Copenhagen, Antwerp\nFull time"
        signals = knockout_check.extract_signals(posting)
        self.assertEqual(signals.get("locations"), ["Aalborg", "Copenhagen", "Antwerp"])

    def test_locations_pass_for_an_eu_citizen(self):
        status, detail = knockout_check.check_signal(
            "locations", ["Aalborg", "Copenhagen", "Antwerp"], "Romania", {"citizen": "RO"})
        self.assertEqual(status, "PASS")
        self.assertIn("Aalborg", detail)

    def test_extracts_clearance_requirement(self):
        signals = knockout_check.extract_signals(
            "This position requires the successful candidate to have an active security clearance.")
        self.assertEqual(signals.get("clearance"), "active security clearance")

    def test_city_names_resolve_to_countries(self):
        self.assertEqual(knockout_check.country_iso2("Aalborg"), "DK")
        self.assertEqual(knockout_check.country_iso2("Copenhagen"), "DK")
        self.assertEqual(knockout_check.country_iso2("Antwerp"), "BE")
        self.assertEqual(knockout_check.country_iso2("Gloucester"), "GB")
        self.assertIsNone(knockout_check.country_iso2("Springfield"))


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


class BulletContractTests(unittest.TestCase):
    """The house rule: exactly three bullets per role and per project block."""

    def test_counts_bullets_per_kind(self):
        html = ('<ul class="role-sub"><li>a</li><li>b</li><li>c</li></ul>'
                '<ul class="project"><li>x</li><li>y</li><li>z</li></ul>')
        self.assertEqual(bullet_audit.count_block_bullets(html, "role-sub"),
                         [{"kind": "role-sub", "index": 1, "bullets": 3}])
        self.assertEqual(bullet_audit.count_block_bullets(html, "project"),
                         [{"kind": "project", "index": 1, "bullets": 3}])

    def test_three_bullet_contract_passes_with_exactly_three(self):
        html = ('<ul class="role-sub"><li>a</li><li>b</li><li>c</li></ul>'
                '<ul class="project"><li>x</li><li>y</li><li>z</li></ul>')
        self.assertEqual(bullet_audit.check_three_bullet_contract(html), [])

    def test_contract_flags_a_two_bullet_role(self):
        html = ('<ul class="role-sub"><li>a</li><li>b</li></ul>'
                '<ul class="project"><li>x</li><li>y</li><li>z</li></ul>')
        violations = bullet_audit.check_three_bullet_contract(html)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["kind"], "role-sub")
        self.assertEqual(violations[0]["bullets"], 2)

    def test_contract_flags_every_short_or_long_block(self):
        html = ('<ul class="role-sub"><li>a</li></ul>'
                '<ul class="role-sub"><li>a</li><li>b</li><li>c</li><li>d</li></ul>'
                '<ul class="project"><li>x</li><li>y</li></ul>')
        violations = bullet_audit.check_three_bullet_contract(html)
        self.assertEqual(len(violations), 3)

    def test_contract_ignores_unrelated_lists(self):
        html = ('<ul class="skills"><li>Python</li></ul>'
                '<ul class="role-sub"><li>a</li><li>b</li><li>c</li></ul>')
        self.assertEqual(bullet_audit.check_three_bullet_contract(html), [])

    def test_contract_supports_div_wrapped_lists(self):
        html = ('<div class="role-sub"><ul><li>a</li><li>b</li><li>c</li></ul></div>'
                '<div class="project"><ul><li>x</li><li>y</li><li>z</li></ul></div>')
        self.assertEqual(len(bullet_audit.count_block_bullets(html, "role-sub")), 1)
        self.assertEqual(bullet_audit.check_three_bullet_contract(html), [])

    def test_source_html_bullets_are_not_merged(self):
        html = ('<ul class="role-sub"><li>Built a Python API with FastAPI.</li>'
                '<li>Automated tests with 30 checks.</li>'
                '<li>Monitored uptime above 99% with AppDynamics.</li></ul>')
        bullets = bullet_audit.bullets_from_source_html(html)
        self.assertEqual(len(bullets), 3)
        self.assertTrue(bullets[0].startswith("Built"))
        self.assertNotIn("Automated tests", bullets[0])

    def test_min_and_max_can_be_relaxed(self):
        html = '<ul class="role-sub"><li>a</li><li>b</li></ul>'
        self.assertEqual(bullet_audit.check_three_bullet_contract(html, 2, 3), [])


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

    def test_heading_aliases_are_recognized(self):
        text = ("ZUSAMMENFASSUNG\nbody\nKENNTNISSE\nbody\n"
                "BERUFSERFAHRUNG\nbody\nAUSBILDUNG\nbody\n")
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

    def test_language_names_are_not_location_claims(self):
        # "French and German (elementary)" is a LANGUAGES section entry, not a
        # claimed residence; must not trigger the phone-prefix mismatch flag.
        cv = ("Jane Example\nRomania · +40 712 345 678\n\n"
              "PROFESSIONAL SUMMARY\nExperience\n\n"
              "LANGUAGES\nRomanian (native) · English (full professional)\n"
              "French and German (elementary)")
        issues = ats_validate.check_fraud_signals(cv)
        self.assertFalse(any("Location claims" in i for i in issues))

    def test_real_location_mismatch_still_flagged(self):
        # A claimed residence that does not match the phone prefix is still caught.
        cv = ("Jane Example\nFrance · +1 212 555 0178\n\n"
              "PROFESSIONAL SUMMARY\nExperience")
        issues = ats_validate.check_fraud_signals(cv)
        self.assertTrue(any("Location claims" in i for i in issues))


class DegreeTests(unittest.TestCase):
    def test_bsc_education_keyword_is_recognized(self):
        text = ("PROFESSIONAL SUMMARY\nPython Docker CI/CD\n\n"
                "EDUCATION\nB.Sc. Computer Science\n")
        self.assertEqual(ats_validate.check_ats_fields(text), [])

    def test_education_keyword_still_required(self):
        text = "PROFESSIONAL SUMMARY\nPython Docker CI/CD\n"
        issues = ats_validate.check_ats_fields(text)
        self.assertTrue(any("education" in i.lower() for i in issues))


class PDFHygieneTests(unittest.TestCase):
    def test_flags_oversized_pdf(self):
        from unittest.mock import patch
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(b"%PDF-1.4\n" + b"x" * 200)
            handle.flush()
            with patch.object(ats_validate, "MAX_GREENHOUSE_PARSE_BYTES", 100):
                issues = ats_validate.check_pdf_hygiene(handle.name)
        self.assertTrue(any("2.5 MB" in i for i in issues))

    def test_sample_pdf_has_embedded_fonts(self):
        root = Path(__file__).resolve().parents[1]
        if not shutil.which("pdffonts"):
            self.skipTest("pdffonts not available")
        self.assertEqual(ats_validate.check_pdf_hygiene(str(root / "assets/sample-cv.pdf")), [])


if __name__ == "__main__":
    unittest.main()
