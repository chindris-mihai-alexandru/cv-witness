"""Candidate-side Bookface action helpers (fictional tool schemas only)."""
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bookface_mcp_auth as bf


class FakeHTTPError(Exception):
    def __init__(self, code, body, challenge=None):
        self.code = code
        self.headers = {"WWW-Authenticate": challenge} if challenge else {}
        self._body = body.encode()

    def read(self):
        return self._body


class CandidateActionTest(unittest.TestCase):
    def test_empty_enum_falls_back_to_yc_cli(self):
        tools = [{"name": "waas_candidate", "inputSchema": {
            "properties": {"action": {"enum": []}}}}]
        summary = bf.candidate_action_summary(tools)
        self.assertEqual(summary["actions"], [])
        self.assertEqual(summary["job_discovery"], [])

    def test_discovery_and_profile_actions_are_split(self):
        tools = [{"name": "waas_candidate", "inputSchema": {
            "properties": {"action": {"enum": [
                "search_jobs", "company_jobs", "update_profile", "apply_to_job",
                "unrelated"
            ]}}}}]
        summary = bf.candidate_action_summary(tools)
        self.assertEqual(summary["job_discovery"], ["search_jobs", "company_jobs"])
        self.assertEqual(summary["profile_or_apply"], ["update_profile", "apply_to_job"])

    def test_employer_tools_are_ignored(self):
        tools = [{"name": "hiring_list_applicants", "inputSchema": {
            "properties": {"action": {"enum": ["apply_to_job"]}}}}]
        summary = bf.candidate_action_summary(tools)
        self.assertEqual(summary["actions"], [])

    def test_oauth_challenge_is_rendered_without_token(self):
        err = FakeHTTPError(
            401, '{"error":"invalid_token"}',
            'Bearer resource_metadata="https://api.ycombinator.com/'
            '.well-known/oauth-protected-resource", scope="mcp:access"')
        text = bf._http_error_detail(err)
        self.assertIn("HTTP 401", text)
        self.assertIn("mcp:access", text)
        self.assertIn("invalid_token", text)
        self.assertNotIn("Authorization", text)


if __name__ == "__main__":
    unittest.main()
