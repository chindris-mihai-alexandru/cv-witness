import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from linkedin_export_import import build_snapshot  # noqa: E402


class LinkedInExportImportTest(unittest.TestCase):
    def make_dir(self, root: Path) -> None:
        (root / "Profile.csv").write_text(
            "First Name,Last Name,Headline,Summary,Current Company,Websites,Birth Date,Maiden Name\n"
            "Ada,Lovelace,Platform Engineer,Builds systems,Analytical Engines,https://example.com,1815-12-10,Byron\n",
            encoding="utf-8")
        (root / "Positions.csv").write_text(
            "Company Name,Title,Location,Start Date,End Date,Description\n"
            "Analytical Engines,Application Support Specialist,London,Jan 2021,Present,Supported engines\n",
            encoding="utf-8")
        (root / "Skills.csv").write_text("Name\nPython\n", encoding="utf-8")

    def test_directory_snapshot_excludes_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_dir(Path(tmp))
            snapshot = build_snapshot(Path(tmp))
        self.assertEqual(snapshot["profile"]["first_name"], "Ada")
        self.assertNotIn("birthdate", snapshot["profile"])
        self.assertNotIn("maidenname", snapshot["profile"])
        self.assertEqual(snapshot["positions"][0]["title"], "Application Support Specialist")
        self.assertEqual(snapshot["positions"][0]["_row"], 2)
        self.assertEqual(snapshot["_meta"]["counts"]["skills"], 1)
        self.assertTrue(any("excluded sensitive fields" in warning
                            for warning in snapshot["_meta"]["warnings"]))

    def test_zip_snapshot_reads_nested_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "export"
            source.mkdir()
            self.make_dir(source)
            archive = Path(tmp) / "export.zip"
            with zipfile.ZipFile(archive, "w") as zip_file:
                for csv_file in source.glob("*.csv"):
                    zip_file.write(csv_file, f"export/{csv_file.name}")
            snapshot = build_snapshot(archive)
        self.assertEqual(snapshot["profile"]["last_name"], "Lovelace")
        self.assertIn("export/Profile.csv", snapshot["_meta"]["files_seen"])

    def test_ignores_unrecognized_csv_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Random.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            snapshot = build_snapshot(root)
        self.assertEqual(snapshot["profile"], {})
        self.assertTrue(any("recognized export files not found" in warning
                            for warning in snapshot["_meta"]["warnings"]))

    def test_rejects_non_zip_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not-a-zip.zip"
            bad.write_text("plain text", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_snapshot(bad)


if __name__ == "__main__":
    unittest.main()
