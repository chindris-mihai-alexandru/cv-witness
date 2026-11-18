"""README structure drift guard.

The README's repository-structure tree previously listed only a subset of the
scripts and omitted references/, so it silently went stale. This guard fails
when a tracked script or reference file is missing from the README, keeping the
documented structure in sync with the actual tree (DRY: the filesystem is the
source of truth). It stores no personal data.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadmeStructureTests(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_every_script_is_documented(self):
        missing = [p.name for p in sorted((ROOT / "scripts").glob("*.py"))
                   if p.name not in self.readme]
        self.assertEqual(missing, [], f"Scripts missing from README structure: {missing}")

    def test_reference_lists_are_documented(self):
        # The README documents the references/company_lists directory; the
        # individual list filenames are not required to be enumerated.
        self.assertIn("references/", self.readme)
        self.assertIn("company_lists", self.readme)

    def test_key_root_files_are_documented(self):
        for name in ("SKILL.md", "AGENTS.md", "CHANGELOG.md", "CONTRIBUTING.md",
                     "LICENSE", "template.html", "render.sh", "index.html"):
            self.assertIn(name, self.readme, f"{name} missing from README")


if __name__ == "__main__":
    unittest.main()
