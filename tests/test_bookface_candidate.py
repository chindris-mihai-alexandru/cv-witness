"""Candidate-side Bookface action helpers (fictional tool schemas only)."""
import json
import os
import stat
import sys
import tempfile
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

    def test_no_candidate_tool_in_hosted_tools_list(self):
        tools = [{"name": "search"}, {"name": "load_skill"}, {"name": "company"}]
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
        tools = [
            {"name": "hiring_list_applicants", "inputSchema": {
                "properties": {"action": {"enum": ["apply_to_job"]}}}},
            {"name": "hiring.get_candidates", "inputSchema": {
                "properties": {"action": {"enum": ["apply_to_job"]}}}},
            {"name": "candidate_batch", "inputSchema": {
                "properties": {"action": {"enum": ["apply_to_job"]}}}},
        ]
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


class TokenCleanupTest(unittest.TestCase):
    def test_write_token_file_is_atomic_and_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / ".cv-witness" / "token.json")
            bf._write_token_file(path, {"refresh_token": "fictional"})
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(Path(path).parent).st_mode), 0o700)
            self.assertFalse(list(Path(path).parent.glob(".bookface-token-*")))

    def test_code_file_is_created_once_owner_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "callback.json")
            bf._write_code_file(path, {"code": "fictional"})
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                bf._write_code_file(path, {"code": "second"})

    def test_forget_removes_token_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "token.json")
            Path(path).write_text("{}", encoding="utf-8")
            self.assertEqual(bf.cmd_forget(path), 0)
            self.assertFalse(Path(path).exists())
            self.assertEqual(bf.cmd_forget(path), 0)


class SkillDocTest(unittest.TestCase):
    def test_skill_documents_verified_dead_ends(self):
        skill = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(
            encoding="utf-8")
        for phrase in (
            "Unknown or unavailable action: search_jobs",
            "insufficient_scope",
            "mcp:access",
            "8 tools",
            "finding-a-startup-job",
            "yc tools run search",
        ):
            self.assertIn(phrase, skill)


if __name__ == "__main__":
    unittest.main()
