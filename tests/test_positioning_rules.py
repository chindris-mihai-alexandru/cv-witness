"""Guard for candidate-side rules derived from upstream recruiter tooling."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PositioningRuleTests(unittest.TestCase):
    def setUp(self):
        self.ref = (ROOT / "references" / "recruiter-search-positioning.md").read_text(
            encoding="utf-8")
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_work_rights_and_location_rule(self):
        self.assertIn("work rights and location truthfully", self.ref)
        self.assertIn("no sponsorship required", self.ref)

    def test_repeat_application_rule(self):
        self.assertIn("one tailored application per company", self.ref)
        self.assertIn("possible spam signal", self.ref)

    def test_channel_continuity_rule(self):
        self.assertIn("reply on that application thread", self.ref)
        self.assertIn("original channel", self.skill)

    def test_no_employer_side_features_promoted(self):
        for term in ("hiring.list_applicants", "pipeline_move", "candidate_note_create"):
            self.assertNotIn(term, self.ref)


if __name__ == "__main__":
    unittest.main()
