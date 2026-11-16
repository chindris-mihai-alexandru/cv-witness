"""Tests for the company context gate (scripts/company_context.py)."""
import json
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import company_context


def _write(text: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return handle.name


ATREIDES = """
Cloud Support Engineer (remote)
Atreides
Deliver: Copenhagen, Denmark; Gloucester, United Kingdom
Eligibility: You must have the right to work in the Denmark or the United Kingdom.
Please note that we do not provide visa sponsorship.
Security Clearance: This position requires the successful candidate to have an
active security clearance.
"""

CENTRICA = """
Cloud Platform Engineer
Centrica Energy
locations: Aalborg, Copenhagen, Antwerp
time type: Full time
You have hands-on experience with some of: Linux, AWS, Kubernetes, Terraform, Git.
Your English is good, written and spoken.
A degree in computer science. Equivalent practical experience is just as good.
"""

CV = "Alex Morgan\nRomania\nIT Operations & Support Engineer, Example Corp, Nov 2022 - Apr 2025\n"


class CuratedListTests(unittest.TestCase):
    def test_european_remote_list_loads(self):
        table = company_context.load_european_remote()
        self.assertGreater(len(table), 200)

    def test_remote_dna_list_loads(self):
        names = company_context.load_remote_dna()
        self.assertGreater(len(names), 150)

    def test_match_tolerates_a_parenthetical_suffix(self):
        table = company_context.load_european_remote()
        self.assertIn("automattic", table)
        self.assertIsNotNone(company_context.match_company("Automattic (fully remote)", table))

    def test_unknown_company_does_not_match(self):
        table = company_context.load_european_remote()
        self.assertIsNone(company_context.match_company("Not A Real Company XYZ", table))


class VerdictTests(unittest.TestCase):
    def test_clearance_gate_stops(self):
        context = company_context.build_context(
            _write(ATREIDES), _write(CV), "Atreides", "RO", sponsorship=False,
            holds_clearance=False, funding=False, layoffs_csv=None)
        self.assertEqual(context["verdict"], "STOP")
        self.assertTrue(any(g["signal"] == "clearance" and g["status"] == "FAIL"
                            for g in context["gates"]))

    def test_eu_role_proceeds(self):
        context = company_context.build_context(
            _write(CENTRICA), _write(CV), "Centrica Energy", "RO", sponsorship=True,
            holds_clearance=False, funding=False, layoffs_csv=None)
        self.assertEqual(context["verdict"], "PROCEED")
        self.assertTrue(context["relocation"]["eu_free_movement"])

    def test_uk_only_role_is_not_free_movement(self):
        posting = "Support Engineer\nLondon, United Kingdom\nright to work in the United Kingdom; no sponsorship"
        context = company_context.build_context(
            _write(posting), _write(CV), "Acme UK", "RO", sponsorship=False,
            holds_clearance=False, funding=False, layoffs_csv=None)
        self.assertFalse(context["relocation"]["eu_free_movement"])

    def test_layoff_records_are_optional_and_filtered(self):
        csv_path = _write("Company,Location,total_laid_off,date,percentage_laid_off,Industry,Source,stage,funds_raised,country,List_of_Employees_Laid_Off\n"
                          "Acme,Berlin,500,2026-03-01,0.2,Software,news,Series B,10000000,Germany,\n"
                          "Other,Paris,10,2026-02-01,0.01,Software,news,Seed,1000000,France,\n")
        hits = company_context.layoff_records(csv_path, "Acme")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["company"], "Acme")
        self.assertEqual(hits[0]["total_laid_off"], "500")


def _envelope(text: str) -> dict:
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": text}]}}


def _hirelog_transport(text: str):
    return lambda payload: _envelope(text)


class HirelogTrustTests(unittest.TestCase):
    """The Hirelog seam is injected, so the verdict logic runs offline."""

    def _build(self, transport, company="Centrica Energy", posting_url=None):
        return company_context.build_context(
            _write(CENTRICA), _write(CV), company, "RO", sponsorship=True,
            holds_clearance=False, funding=False, layoffs_csv=None,
            hirelog=True, posting_url=posting_url, trust_transport=transport)

    def test_hirelog_is_off_by_default_so_tests_stay_offline(self):
        context = company_context.build_context(
            _write(CENTRICA), _write(CV), "Centrica Energy", "RO", sponsorship=True,
            holds_clearance=False, funding=False, layoffs_csv=None)
        self.assertIsNone(context["trust"]["hirelog"])
        self.assertIsNone(context["trust"]["hirelog_posting"])

    def test_no_notes_keeps_the_verdict(self):
        transport = _hirelog_transport('{"found": false, "hint": "No notes yet."}')
        context = self._build(transport)
        self.assertEqual(context["verdict"], "PROCEED")
        self.assertFalse(context["trust"]["hirelog"]["found"])

    def test_unverified_red_flag_escalates_to_confirm(self):
        note = {"kind": "red_flag", "status": "unverified",
                "text_en": "Aggregator repost behind a remote label.",
                "trust": {"score": 0.77, "confirms": 0, "disputes": 0}}
        transport = _hirelog_transport(json.dumps({"found": True, "notes": [note]}))
        context = self._build(transport)
        self.assertEqual(context["verdict"], "CONFIRM")
        self.assertTrue(any("unverified" in reason for reason in context["reasons"]))

    def test_corroborated_red_flag_stops(self):
        note = {"kind": "red_flag", "status": "corroborated",
                "text_en": "Pay-to-apply confirmed by three agents.",
                "trust": {"score": 3.1, "confirms": 3, "disputes": 0}}
        transport = _hirelog_transport(json.dumps({"found": True, "notes": [note]}))
        context = self._build(transport)
        self.assertEqual(context["verdict"], "STOP")
        self.assertTrue(any("red flag" in reason for reason in context["reasons"]))

    def test_posting_red_flag_is_read_too(self):
        note = {"kind": "red_flag", "status": "unverified",
                "text_en": "Form knockout on location.",
                "trust": {"score": 0.8, "confirms": 0, "disputes": 0}}
        transport = _hirelog_transport(json.dumps({"notes": [note]}))
        context = self._build(transport, posting_url="https://example.com/job")
        self.assertEqual(context["verdict"], "CONFIRM")
        self.assertEqual(len(context["trust"]["hirelog_posting"]["notes"]), 1)

    def test_unreachable_hirelog_does_not_change_the_verdict(self):
        context = self._build(lambda payload: None)
        self.assertEqual(context["verdict"], "PROCEED")
        self.assertIsNone(context["trust"]["hirelog"])


class RelocationLanguageTests(unittest.TestCase):
    def test_posting_english_requirement_overrides_country_heuristic(self):
        posting = ("Product Support Engineer\nHungary - Budapest\n"
                   "Fluent in English, both written and verbal\n")
        context = company_context.build_context(
            _write(posting), _write(CV), "Veeva", "RO", sponsorship=True,
            holds_clearance=False, funding=False, layoffs_csv=None)
        self.assertEqual(context["relocation"]["countries"], ["HU"])
        self.assertTrue(context["relocation"]["english_friendly"])

    def test_no_english_signal_stays_false_for_hungary(self):
        context = company_context.build_context(
            _write("Engineer\nBudapest, Hungary\nGerman required"), _write(CV),
            "Acme", "RO", sponsorship=True, holds_clearance=False,
            funding=False, layoffs_csv=None)
        self.assertFalse(context["relocation"]["english_friendly"])


if __name__ == "__main__":
    unittest.main()
