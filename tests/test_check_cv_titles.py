"""Tests for the advisory title-drift check."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_cv_titles as titles  # noqa: E402


MASTER = """## Contact
- Name: Jane Example

## Experience - Example Studio (Jan 2020 - Dec 2024; one employer)

Role 2: Senior Software Engineer (Jan 2022 - Dec 2024)
- Built a service.

Role 1: Software Engineer (Jan 2020 - Dec 2021)
- Built an API.

## Projects
- Other section
"""


def fields(role: str, dates: str = "Jan 2022 - Dec 2024") -> dict:
    return {
        "COMPANY": "Example Studio",
        "ROLES_BLOCK": (
            f'<div class="role-line"><span class="title">{role}</span>'
            f'<span class="dates">{dates}</span></div>'
            '<div class="role-sub"><ul><li>Built a service.</li></ul></div>'
        ),
    }


class TitleDriftTest(unittest.TestCase):
    def test_exact_title_is_accepted(self):
        result = titles.compare(fields("Senior Software Engineer"), MASTER)
        self.assertEqual(result["exact"], ["Senior Software Engineer"])
        self.assertEqual(result["mismatches"], [])

    def test_title_inflation_is_reported(self):
        result = titles.compare(fields("Lead Software Engineer"), MASTER)
        self.assertEqual(result["mismatches"], [{
            "tailored": "Lead Software Engineer",
            "approved": "Senior Software Engineer",
            "dates": "Jan 2022 - Dec 2024",
        }])

    def test_unmatched_role_is_not_a_mismatch(self):
        result = titles.compare(fields("Software Engineer", "Jan 2025 - Present"), MASTER)
        self.assertEqual(result["exact"], [])
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["unmatched"][0]["role"], "Software Engineer")

    def test_master_without_experience_entries_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Experience"):
            titles.compare(fields("Senior Software Engineer"), "## Projects\n- Nothing\n")

    def test_role_without_dates_fails_closed(self):
        bad = {
            "COMPANY": "Example Studio",
            "ROLES_BLOCK": '<div class="role-line"><span class="title">Engineer</span></div>',
        }
        with self.assertRaisesRegex(ValueError, "missing title or dates"):
            titles.compare(bad, MASTER)


if __name__ == "__main__":
    unittest.main()
