"""Tests for the dependency-free Resume Metadata Standard writer."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rms_metadata as rms  # noqa: E402


class RMSMetadataTest(unittest.TestCase):
    def test_template_is_complete_and_synthetic(self):
        template = rms.template_payload()
        self.assertEqual(len(template), 1274)
        self.assertEqual(template["rms_schema_details"], rms.SCHEMA_URL)
        self.assertEqual(template["rms_experience_count"], "0")
        self.assertEqual(template["rms_contact_fullName"], rms.NA)
        self.assertEqual(template["rms_experience_15_role"], rms.NA)

    def test_payload_from_fields_maps_synthetic_sample(self):
        fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
        payload = rms.payload_from_fields(fields)
        self.assertEqual(payload["rms_contact_fullName"], "Alex Morgan")
        self.assertEqual(payload["rms_experience_count"], "3")
        self.assertEqual(payload["rms_education_count"], "2")
        self.assertEqual(payload["rms_project_count"], "2")
        self.assertEqual(payload["rms_skill_count"], "4")
        self.assertIn("Built a Python service", payload["rms_experience_0_description"])

    def test_explicit_metadata_rejects_unknown_keys(self):
        with self.assertRaisesRegex(ValueError, "Unknown RMS keys"):
            rms.payload_from_fields({"RMS": {"rms_not_a_field": "x"}})

    def test_date_parts_are_utc_milliseconds(self):
        value, timestamp, date_format = rms._date_parts("Jan 2023")
        self.assertEqual(value, "Jan 2023")
        self.assertEqual(timestamp, "1672531200000")
        self.assertEqual(date_format, "MMM YYYY")
        value, timestamp, date_format = rms._date_parts("Present")
        self.assertEqual(value, "Present")
        self.assertEqual(timestamp, rms.NA)

    def test_validate_payload_catches_schema_errors(self):
        payload = {
            "rms_schema_details": rms.SCHEMA_URL,
            "rms_experience_count": "1",
            "rms_experience_1_role": "Out of range",
            "rms_experience_0_dateBeginTS": "yesterday",
            "rms_experience_0_isCurrent": "maybe",
            "rms_experience_0_dateBeginFormat": "tomorrow",
        }
        errors = rms.validate_payload(payload)
        joined = " ".join(errors)
        self.assertIn("index outside", joined)
        self.assertIn("timestamp", joined)
        self.assertIn("true, false", joined)
        self.assertIn("date format", joined)

    def test_duplicate_injection_is_rejected(self):
        source = ROOT / "assets/sample-cv.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-witness-rms-") as temporary:
            directory = Path(temporary)
            first = directory / "first.pdf"
            fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
            payload = rms.payload_from_fields(fields)
            rms.inject_xmp(source, first, payload)
            with self.assertRaisesRegex(ValueError, "already has an XMP packet"):
                rms.inject_xmp(first, directory / "second.pdf", payload)

    def test_unsupported_pdf_structures_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cv-witness-rms-") as temporary:
            directory = Path(temporary)
            xref_stream = directory / "xref-stream.pdf"
            xref_stream.write_bytes(
                b"%PDF-1.5\n5 0 obj\n<< /Type /XRef >>\nendobj\nstartxref\n9\n%%EOF\n")
            with self.assertRaisesRegex(ValueError, "xref streams"):
                rms.inject_xmp(xref_stream, directory / "out.pdf", {"rms_summary": "x"})

            body = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            xref_offset = len(body)
            encrypted = directory / "encrypted.pdf"
            encrypted.write_bytes(
                body + f"xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 1 /Root 1 0 R /Encrypt 2 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
            with self.assertRaisesRegex(ValueError, "Encrypted"):
                rms.inject_xmp(encrypted, directory / "out.pdf", {"rms_summary": "x"})

    def test_xmp_round_trip_escapes_special_characters(self):
        payload = {"rms_summary": 'A & B < C "quote" >\nsecond line'}
        packet = rms.build_xmp(payload)
        self.assertIn(b"&amp;", packet)
        self.assertIn(b"rms_v2.0.1", packet)
        read = rms.read_xmp(packet)
        self.assertEqual(read["rms_summary"], payload["rms_summary"])
        self.assertEqual(read["producer"], "rms_v2.0.1")

    def test_read_xmp_rejects_packetless_pdf(self):
        with self.assertRaisesRegex(ValueError, "No XMP packet"):
            rms.read_xmp(b"%PDF-1.4\nno metadata\n")

    def test_injection_preserves_visible_pdf_bytes(self):
        source = ROOT / "assets/sample-cv.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-witness-rms-") as temporary:
            target = Path(temporary) / "with-rms.pdf"
            fields = json.loads((ROOT / "examples/sample-cv.json").read_text(encoding="utf-8"))["fields"]
            result = rms.inject_xmp(source, target, rms.payload_from_fields(fields))
            original = source.read_bytes()
            output = target.read_bytes()
            self.assertEqual(result["status"], "ok")
            self.assertTrue(output.startswith(original))
            self.assertIn(b"/Prev", output)
            metadata = rms.read_xmp(output)
            self.assertEqual(metadata["producer"], "rms_v2.0.1")
            self.assertEqual(metadata["rms_experience_count"], "3")

            if shutil.which("pdftotext"):
                before = subprocess.run(
                    ["pdftotext", "-layout", str(source), "-"],
                    check=True, capture_output=True).stdout
                after = subprocess.run(
                    ["pdftotext", "-layout", str(target), "-"],
                    check=True, capture_output=True).stdout
                self.assertEqual(before, after)

    def test_cli_verify_prints_counts_without_pii(self):
        source = ROOT / "assets/sample-cv.pdf"
        with tempfile.TemporaryDirectory(prefix="cv-witness-rms-") as temporary:
            target = Path(temporary) / "with-rms.pdf"
            fields = ROOT / "examples/sample-cv.json"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/rms_metadata.py"),
                 "--pdf", str(source), "--fields", str(fields), "--output", str(target)],
                check=True, capture_output=True, text=True)
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/rms_metadata.py"),
                 "--pdf", str(target), "--verify"],
                check=True, capture_output=True, text=True)
            self.assertIn('"experience_count": "3"', result.stdout)
            self.assertNotIn("Alex Morgan", result.stdout)
            self.assertNotIn("example.com", result.stdout)

    def test_print_template_is_pii_free(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/rms_metadata.py"), "--print-template"],
            check=True, capture_output=True, text=True)
        template = json.loads(result.stdout)
        self.assertEqual(len(template), 1274)
        self.assertEqual(template["rms_contact_email"], rms.NA)


if __name__ == "__main__":
    unittest.main()
