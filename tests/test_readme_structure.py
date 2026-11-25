"""Documentation structure drift guard.

The exhaustive script tree previously lived in README.md and silently went
stale. The README now carries a short orientation, while
docs/repository-map.md is the canonical grouped inventory. This guard fails
when a tracked script or root file is missing from the map, keeping the
documentation in sync with the actual tree (DRY: the filesystem is the source
of truth). It stores no personal data.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationStructureTests(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.map = (ROOT / "docs" / "repository-map.md").read_text(encoding="utf-8")

    def test_readme_links_to_canonical_map(self):
        self.assertIn("[repository map](docs/repository-map.md)", self.readme)

    def test_every_script_is_documented_in_the_map(self):
        missing = [p.name for p in sorted((ROOT / "scripts").glob("*.py"))
                   if p.name not in self.map]
        self.assertEqual(missing, [], f"Scripts missing from map: {missing}")

    def test_reference_lists_are_documented(self):
        self.assertIn("references/", self.map)
        self.assertIn("company_lists", self.map)

    def test_key_root_files_are_documented(self):
        for name in ("SKILL.md", "AGENTS.md", "CHANGELOG.md", "CONTRIBUTING.md",
                     "LICENSE", "template.html", "render.sh", "index.html"):
            self.assertIn(name, self.map, f"{name} missing from map")


if __name__ == "__main__":
    unittest.main()
