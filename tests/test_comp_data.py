"""Tests for the EU compensation providers (scripts/comp_data.py).

Network calls are stubbed: the provider layer must be testable offline and must
degrade to None when a source is unreachable, never raise.
"""
import sys
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import comp_data


EUPTD_PAGE = """
<html><body>
<p>Typical advertised range &euro;93,178&ndash;&euro;173,519 per year</p>
<p>Based on 16 advertised ranges Employers 8 (largest 31%)</p>
<p>Full span observed: &euro;40,000&ndash;&euro;243,525.</p>
<p>Data as of 2026-08-31</p>
</body></html>
"""


class RoleNormalisationTests(unittest.TestCase):
    def test_exact_role_slug_wins(self):
        self.assertEqual(comp_data.normalise_role("Data Scientist"), "data-scientist")

    def test_aliases_map_to_the_closest_role(self):
        self.assertEqual(comp_data.normalise_role("Cloud Platform Engineer"), "devops-engineer")
        self.assertEqual(comp_data.normalise_role("SRE"), "devops-engineer")
        self.assertEqual(comp_data.normalise_role("Machine Learning Engineer"), "machine-learning-engineer")
        self.assertEqual(comp_data.normalise_role("Customer Support Specialist"), "customer-support")

    def test_unknown_title_falls_back_to_software_engineer(self):
        self.assertEqual(comp_data.normalise_role("Quantum Basket Weaver"), "software-engineer")


class EuptdParsingTests(unittest.TestCase):
    def test_parses_band_sample_and_as_of(self):
        parsed = comp_data._parse_band(comp_data._text_from_html(EUPTD_PAGE))
        if parsed is None:
            self.fail("band was not parsed from the fixture")
        self.assertEqual(parsed["band"], "€93178–€173519")
        self.assertEqual(parsed["sample_size"], 16)
        self.assertEqual(parsed["employers"], 8)
        self.assertEqual(parsed["as_of"], "2026-08-31")

    def test_returns_none_when_no_band_is_published(self):
        self.assertIsNone(comp_data._parse_band("no salary data here"))

    def test_role_lookup_uses_the_normalised_slug(self):
        with mock.patch.object(comp_data, "_get", return_value=EUPTD_PAGE) as get:
            result = comp_data.euptd_role("Cloud Platform Engineer")
        get.assert_called_once_with(f"{comp_data.EUPTD_BASE}/devops-engineer/")
        self.assertEqual(result["provider"], "euptd")
        self.assertEqual(result["scope"], "Europe")

    def test_unreachable_source_returns_none(self):
        with mock.patch.object(comp_data, "_get", return_value=None):
            self.assertIsNone(comp_data.euptd_role("DevOps Engineer"))

    def test_country_lookup_rejects_a_non_two_letter_code(self):
        self.assertIsNone(comp_data.euptd_country("Danmark"))
        self.assertIsNone(comp_data.euptd_country("D"))

    def test_country_pages_are_sparse(self):
        # Only countries with enough disclosed data publish a page; a 404 is a
        # normal, reported gap rather than an error.
        with mock.patch.object(comp_data, "_get", return_value=None):
            self.assertIsNone(comp_data.euptd_country("DK"))


class WageApiTests(unittest.TestCase):
    def test_requires_a_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(comp_data.wageapi_salary("engineer", "DE"))

    def test_queries_the_eu_endpoint_with_the_key(self):
        with mock.patch.dict("os.environ", {"WAGEAPI_KEY": "test-key"}):
            with mock.patch.object(comp_data, "_get", return_value='{"percentiles": {}}') as get:
                result = comp_data.wageapi_salary("software engineer", "DE")
        self.assertEqual(result, {"provider": "wageapi", "raw": {"percentiles": {}}})
        url = get.call_args[0][0]
        self.assertIn("wageapi.com", url)
        self.assertIn("X-API-Key", get.call_args[1]["headers"])


class CatalogTests(unittest.TestCase):
    def test_catalog_documents_the_eu_first_stack(self):
        names = [p["name"] for p in comp_data.provider_catalog()]
        self.assertIn("euptd", names)
        self.assertIn("wageapi", names)
        self.assertIn("figures", names)
        self.assertIn("ravio", names)

    def test_levels_fyi_is_marked_us_centric(self):
        levels = next(p for p in comp_data.provider_catalog() if p["name"] == "levels.fyi")
        self.assertIn("US", levels["scope"])


if __name__ == "__main__":
    unittest.main()
