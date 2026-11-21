"""Tests for public_footprint.py: HF footprint reader + PR merge verification.

Fixtures are fictional (example.* domains / made-up repo ids). No real token,
name, email or private foundation content appears here (test_no_personal_data.py).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import public_footprint as pf


class FakeRunner:
    """Return canned CLI output keyed by command tail."""
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, cmd, timeout=45):
        key = cmd[1] if len(cmd) > 1 else ""
        r = self.responses.get(key)
        if r is None:
            return False, None, "unexpected command"
        return r


class HFFootprintTest(unittest.TestCase):
    def setUp(self):
        self.real = pf._run

    def tearDown(self):
        pf._run = self.real

    def test_reads_all_four_sections(self):
        payload = {
            "models": [{"id": "example/model", "likes": 0}],
            "datasets": [{"id": "example/data", "downloads_all_time": 12}],
            "spaces": [],
            "collections": [{"title": "Demo"}],
        }
        pf._run = lambda cmd, timeout=45: (True, payload.get(cmd[1], []), None)
        r = pf.hf_footprint("example-user", hf_bin="hf")
        self.assertEqual(r["author"], "example-user")
        self.assertEqual(r["models"], payload["models"])
        self.assertEqual(r["datasets"], payload["datasets"])
        self.assertEqual(r["collections"], payload["collections"])
        self.assertEqual(r["errors"], [])

    def test_cli_error_is_reported_not_crashed(self):
        pf._run = lambda cmd, timeout=45: (False, None, "hf not installed")
        r = pf.hf_footprint("example-user", hf_bin="hf")
        self.assertEqual(len(r["errors"]), 4)
        self.assertIn("hf not installed", r["errors"][0])

    def test_non_json_output_flagged(self):
        pf._run = lambda cmd, timeout=45: (True, "plain text", None)
        r = pf.hf_footprint("example-user", hf_bin="hf")
        self.assertTrue(any("non-JSON" in e for e in r["errors"]))

    def test_low_numbers_not_inflated(self):
        pf._run = lambda cmd, timeout=45: (True, [{"id": "example/m", "downloads": 0, "likes": 0}], None)
        r = pf.hf_footprint("example-user", hf_bin="hf")
        self.assertEqual(r["models"][0]["downloads"], 0)
        self.assertEqual(r["models"][0]["likes"], 0)


class VerifyPRTest(unittest.TestCase):
    def setUp(self):
        self.real = pf._run

    def tearDown(self):
        pf._run = self.real

    def test_merged_requires_state_and_merged_at(self):
        pf._run = lambda cmd, timeout=45: (True, {"state": "MERGED", "mergedAt": "2026-01-01T00:00:00Z",
                                                "number": 1, "title": "T"}, None)
        r = pf.verify_pr("https://github.com/example/repo/pull/1")
        self.assertTrue(r["merged"])
        self.assertEqual(r["state"], "MERGED")

    def test_closed_unmerged_is_not_merged(self):
        pf._run = lambda cmd, timeout=45: (True, {"state": "CLOSED", "mergedAt": None,
                                                "number": 2, "title": "T"}, None)
        r = pf.verify_pr("https://github.com/example/repo/pull/2")
        self.assertFalse(r["merged"])
        self.assertIsNone(r["merged_at"])

    def test_merged_state_without_date_is_not_merged(self):
        pf._run = lambda cmd, timeout=45: (True, {"state": "MERGED", "mergedAt": None}, None)
        self.assertFalse(pf.verify_pr("https://github.com/example/repo/pull/3")["merged"])

    def test_cli_failure_returns_error(self):
        pf._run = lambda cmd, timeout=45: (False, None, "gh not logged in")
        r = pf.verify_pr("https://github.com/example/repo/pull/4")
        self.assertFalse(r["merged"])
        self.assertIn("gh not logged in", r["error"])


if __name__ == "__main__":
    unittest.main()