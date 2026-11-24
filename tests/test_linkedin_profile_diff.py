import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from linkedin_profile_diff import analyze, render_preview  # noqa: E402


MASTER = """# Foundation Resume

## Experience - Example Corp (Jan 2021 - Present, London)

Role 1: Application Support Specialist (Jan 2021 - Present)
- Supported users.

## Projects

- Alpha Platform - built a system.

## Skills

- Engineering: Python
## Languages

- English (professional working proficiency)
## Certifications

- Example Certified
"""


class LinkedInProfileDiffTest(unittest.TestCase):
    def snapshot(self):
        return {
            "_meta": {"warnings": ["test warning"]},
            "profile": {"first_name": "Ada", "headline": "Platform Engineer",
                        "summary": "Builds systems"},
            "positions": [
                {"title": "IT Operations & Support Engineer", "company": "Example Corp",
                 "start_date": "Jan 2021", "end_date": "Present", "_source": "Positions.csv",
                 "_row": 2},
                {"title": "Unknown Role", "company": "Other Corp",
                 "start_date": "Feb 2022", "end_date": "Mar 2023", "_source": "Positions.csv",
                 "_row": 3},
            ],
            "projects": [{"name": "Alpha Platform", "_source": "Projects.csv", "_row": 2}],
            "skills": [{"name": "Python", "_source": "Skills.csv", "_row": 2}],
            "languages": [{"name": "English", "_source": "Languages.csv", "_row": 2}],
            "education": [],
        }

    def test_alias_and_exact_matches(self):
        aliases = {"roles": {"IT Operations & Support Engineer": "Application Support Specialist"}}
        report = analyze(self.snapshot(), MASTER, "", aliases)
        statuses = [row["status"] for row in report["positions"]]
        self.assertIn("alias", statuses)
        self.assertIn("unmatched", statuses)
        self.assertEqual(report["projects"][0]["status"], "present_in_source")
        self.assertEqual(report["skills"][0]["status"], "present_in_source")
        self.assertIn("test warning", report["warnings"])

    def test_preview_is_read_only_draft(self):
        report = analyze(self.snapshot(), MASTER, "")
        preview = render_preview(report)
        self.assertIn("No changes were applied to LinkedIn", preview)
        self.assertIn("- [ ]", preview)
        self.assertNotIn("approval_envelope", preview)

    def test_draft_wording_comes_from_fields_only(self):
        fields = {"ROLE": "Cloud Engineer", "SUMMARY": "Plain summary",
                  "SKILLS_BLOCK": "<p><em>Cloud:</em> Azure, Terraform</p>"}
        report = analyze(self.snapshot(), MASTER, "", None, fields)
        self.assertEqual(report["proposed_linkedin_draft"]["headline"], "Cloud Engineer")
        self.assertIn("Azure", report["proposed_linkedin_draft"]["skills"])


if __name__ == "__main__":
    unittest.main()
