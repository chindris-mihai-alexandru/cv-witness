"""Repeatable template contracts and real, fictional lane/paper exports."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import build_cv as builder
from scripts import cv_checks as checks
from scripts import render_cv

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "examples/structured-cv.json").read_text(encoding="utf-8"))


def pdf_tools():
    try:
        render_cv.browser_path()
        return bool(shutil.which("pdfinfo") and shutil.which("pdftotext"))
    except checks.CheckError:
        return False


class BuilderTests(unittest.TestCase):
    def test_four_roles_and_all_supplied_sections_are_preserved(self):
        data = fixture()
        source, expected, order = builder.build_html(data)
        for role in data["experience"][0]["roles"]:
            self.assertIn(role["title"], source)
            self.assertIn(role["dates"], expected)
            self.assertIn(role["bullets"][0], expected)
        self.assertEqual(len(data["experience"][0]["roles"]), 4)
        self.assertNotIn("Certifications", source)
        self.assertEqual(order, [key for key in builder.LANES["engineering"] if data.get(key)])

    def test_lanes_change_order_not_wording(self):
        data = fixture()
        content = []
        for lane in builder.LANES:
            source, expected, order = builder.build_html(data, lane)
            headings = re.findall(r'<section id="([^"]+)">', source)
            self.assertEqual(headings, order)
            content.append(set(expected))
        self.assertTrue(all(values == content[0] for values in content))

    def test_every_optional_section_can_be_omitted(self):
        for omitted in builder.SECTIONS:
            with self.subTest(omitted=omitted):
                data = fixture()
                data.pop(omitted, None)
                source, _, order = builder.build_html(data)
                self.assertNotIn(omitted, order)
                self.assertNotIn('<section id="' + omitted + '">', source)

    def test_only_education_is_valid_without_fake_experience(self):
        source, expected, order = builder.build_html({
            "schema_version": 1, "header": {"name": "Alex Morgan"},
            "education": ["Sample College (fictional), 2024"]
        })
        self.assertEqual(order, ["education"])
        self.assertNotIn("Professional Experience", source)
        self.assertIn("Sample College (fictional), 2024", expected)

    def test_section_order_cannot_drop_duplicate_or_invent_sections(self):
        data = fixture()
        for order in (["summary"], ["summary", "summary"], ["unknown"], "summary"):
            with self.subTest(order=order), self.assertRaises(checks.CheckError):
                builder.build_html(data, section_order=order)
        active = [key for key in builder.SECTIONS if data.get(key)]
        self.assertEqual(builder.build_html(data, section_order=list(reversed(active)))[2], list(reversed(active)))

    def test_unknown_fields_fail_instead_of_silent_loss(self):
        for path in ("document", "header", "role"):
            with self.subTest(path=path):
                data = fixture()
                target = data if path == "document" else data["header"] if path == "header" else data["experience"][0]["roles"][0]
                target["unknown_field"] = "This must never silently disappear."
                with self.assertRaises(checks.CheckError):
                    builder.build_html(data)

    def test_invalid_types_empty_required_values_and_versions_fail(self):
        modifications = [
            lambda d: d.update(schema_version=True),
            lambda d: d.update(experience="not a list"),
            lambda d: d["header"].update(name=""),
            lambda d: d["experience"][0].update(roles=[]),
            lambda d: d["experience"][0]["roles"][0].update(bullets=[]),
            lambda d: d.update(summary=None),
            lambda d: d.update(languages=[{"unsupported": "object"}]),
        ]
        for modify in modifications:
            data = fixture()
            modify(data)
            with self.subTest(modify=modify), self.assertRaises(checks.CheckError):
                builder.build_html(data)

    def test_unresolved_markers_and_invalid_unicode_fail(self):
        for value in ("[FILL: name]", "{{NAME}}", "Alex\x00Morgan", "Alex\ud800"):
            data = fixture()
            data["header"]["name"] = value
            with self.subTest(value=repr(value)), self.assertRaises(checks.CheckError):
                builder.build_html(data)

    def test_text_markup_is_escaped_and_link_schemes_are_validated(self):
        data = fixture()
        data["summary"] = "I explain <tradeoffs> & keep notes in plain language."
        source, expected, _ = builder.build_html(data)
        self.assertIn("&lt;tradeoffs&gt; &amp;", source)
        self.assertIn(data["summary"], expected)
        for url in ("javascript:alert(1)", "file:///private/source", "https://user:password@example.com", "//example.com", "https://example.com/private note"):
            with self.subTest(url=url):
                data["header"]["contacts"][0]["url"] = url
                with self.assertRaises(checks.CheckError):
                    builder.build_html(data)

    def test_duplicate_json_keys_and_malformed_files_fail_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for content in ('{"schema_version":1,"schema_version":2}', '{"private":"SECRET_INPUT"'):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(checks.CheckError) as failure:
                    builder.load_document(path)
                self.assertNotIn("SECRET_INPUT", str(failure.exception))

    def test_data_is_not_changed_by_building(self):
        data = fixture()
        original = copy.deepcopy(data)
        builder.build_html(data)
        self.assertEqual(data, original)


TOOLS_AVAILABLE = pdf_tools()
if os.environ.get("CV_WITNESS_REQUIRE_PDF_TESTS") == "1" and not TOOLS_AVAILABLE:
    raise RuntimeError("Template CI requires Chromium and Poppler.")


@unittest.skipUnless(TOOLS_AVAILABLE, "Chromium and Poppler required for lane PDF tests")
class LanePDFTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cv-witness-lane-test-")
        self.root = Path(self.temporary.name).resolve()
        self.options = {"no_sandbox": os.environ.get("CV_WITNESS_CI_NO_SANDBOX") == "1"}

    def tearDown(self):
        self.temporary.cleanup()

    def test_every_lane_and_paper_keeps_text_and_section_order(self):
        for lane in builder.LANES:
            for paper in ("a4", "letter"):
                with self.subTest(lane=lane, paper=paper):
                    source, expected, order = builder.build_html(fixture(), lane)
                    output = self.root / (lane + "-" + paper + ".pdf")
                    report = render_cv.render_html(source, output, paper, max_pages=2, expected_text=expected, **self.options)
                    self.assertTrue(report["passed"])
                    extracted = checks.normalized_text(checks.read_text(output))
                    offsets = [extracted.index(checks.normalized_text(builder.HEADINGS[key])) for key in order]
                    self.assertEqual(offsets, sorted(offsets))

    def test_six_roles_long_content_crosses_pages_without_trimming(self):
        data = fixture()
        roles = data["experience"][0]["roles"]
        for number in range(6):
            role = copy.deepcopy(roles[0])
            role["title"] = "Fictional role " + str(number + 1)
            role["bullets"] = [
                f"Record {number + 1}.{index + 1}: " + "I checked the input, explained the result and documented a useful next step. " * 3
                for index in range(4)
            ]
            if number == 0:
                roles.clear()
            roles.append(role)
        source, expected, _ = builder.build_html(data)
        output = self.root / "long.pdf"
        with self.assertRaises(checks.CheckFailure):
            render_cv.render_html(source, output, max_pages=1, expected_text=expected, **self.options)
        self.assertFalse(output.exists())
        report = render_cv.render_html(source, output, max_pages=6, expected_text=expected, **self.options)
        self.assertGreater(report["pages"], 1)
        extracted = checks.read_text(output)
        for number in range(6):
            self.assertIn("Fictional role " + str(number + 1), extracted)
        self.assertIn("Record 6.4", extracted)

    def test_builder_cli_works_from_elsewhere_and_uses_the_shared_gate(self):
        path = self.root / "approved.json"
        path.write_text(json.dumps(fixture(), ensure_ascii=False), encoding="utf-8")
        output = self.root / "checked.pdf"
        command = [sys.executable, str(ROOT / "scripts/build_cv.py"), str(path), str(output),
                   "--lane", "research", "--paper", "letter", "--max-pages", "2"]
        if self.options["no_sandbox"]:
            command.append("--no-sandbox")
        result = subprocess.run(command, capture_output=True, text=True, timeout=100, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["lane"], "research")
        self.assertNotIn("Alex Morgan", result.stdout)
        self.assertTrue(output.exists())

    def test_technical_wording_is_data_not_a_css_resource(self):
        data = fixture()
        data["summary"] = "I documented url() examples, @import behavior and a src= attribute for other developers."
        source, expected, _ = builder.build_html(data)
        report = render_cv.render_html(source, self.root / "wording.pdf", max_pages=2,
                                       expected_text=expected, **self.options)
        self.assertTrue(report["passed"])
        self.assertIn(checks.normalized_text(data["summary"]), checks.normalized_text(checks.read_text(self.root / "wording.pdf")))

    def test_long_url_wraps_without_losing_its_expected_text(self):
        data = fixture()
        data["projects"][0]["url"] = "https://example.com/" + "long-source-identifier" * 12
        source, expected, _ = builder.build_html(data)
        report = render_cv.render_html(source, self.root / "long-url.pdf", max_pages=3,
                                       expected_text=expected, **self.options)
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
