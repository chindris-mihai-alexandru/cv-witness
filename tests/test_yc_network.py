"""Tests for the YC network intel script (yc_network.py).

The tests mock subprocess output — they do not require a yc login or network
access, so the full suite runs in CI without credentials.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import yc_network


def _fake_csv(rows):
    """Build a csv_results string like the yc tool emits."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


JOBS_CSV = _fake_csv([
    {"id": "1", "link": "[Acme](https://www.ycombinator.com/companies/acme/jobs/1-x)",
     "company_name": "Acme", "job_type": "fulltime", "remote": "yes",
     "locations_for_search": "US, CA, US, San Francisco, CA, US",
     "min_experience": "3", "skills": "Python, PostgreSQL",
     "role": "eng", "eng_type": "be"},
    {"id": "2", "link": "[Beta](https://www.ycombinator.com/companies/beta/jobs/2-y)",
     "company_name": "Beta", "job_type": "fulltime", "remote": "no",
     "locations_for_search": "GB, England, GB, London, England, GB",
     "min_experience": "0", "skills": "Go; Kubernetes | Docker",
     "role": "eng", "eng_type": "be"},
])


def _fake_response(csv_text, total_count=2):
    proc = mock.Mock()
    proc.returncode = 0
    proc.stdout = json.dumps({"result": {"status": "success", "total_count": total_count,
                                         "count": len(csv_text.splitlines()) - 1 if csv_text else 0,
                                         "csv_results": csv_text}})
    proc.stderr = ""
    return proc


class YcAvailabilityTests(unittest.TestCase):
    def test_check_reports_missing_cli(self):
        with mock.patch.object(yc_network.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                yc_network.cmd_check(None)
        self.assertEqual(ctx.exception.code, 2)

    def test_check_reports_unauthenticated(self):
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "Not logged in."
        proc.stderr = ""
        with mock.patch.object(yc_network.shutil, "which", return_value="/usr/local/bin/yc"), \
             mock.patch.object(yc_network, "_yc", return_value=proc), \
             mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(yc_network.cmd_check(None), 2)

    def test_check_ok_when_authed(self):
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "mihai-chindris"
        proc.stderr = ""
        with mock.patch.object(yc_network, "_yc", return_value=proc), \
             mock.patch("sys.stdout"):
            self.assertEqual(yc_network.cmd_check(None), 0)


class YcSearchTests(unittest.TestCase):
    def test_split_skills_handles_commas_semicolons_and_pipes(self):
        self.assertEqual(yc_network.re_split_skills("Python, PostgreSQL; Go | Docker"),
                         ["Python", "PostgreSQL", "Go", "Docker"])

    def test_split_skills_empty(self):
        self.assertEqual(yc_network.re_split_skills(""), [])
        self.assertEqual(yc_network.re_split_skills(None), [])

    def test_rows_parse(self):
        data = {"result": {"csv_results": JOBS_CSV}}
        rows = yc_network._rows(data)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["company_name"], "Acme")
        self.assertEqual(rows[1]["company_name"], "Beta")

    def test_rows_empty(self):
        self.assertEqual(yc_network._rows({"result": {}}), [])

    def test_jobs_summary_shape(self):
        proc = _fake_response(JOBS_CSV)
        with mock.patch.object(yc_network, "_yc", return_value=proc), mock.patch("sys.stdout"):
            out = {}
            import io
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                args = mock.Mock(query="backend", limit=2, json=False, filters=None)
                yc_network.cmd_jobs(args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["total_count"], 2)
        self.assertEqual(out["count"], 2)
        self.assertEqual(len(out["jobs"]), 2)
        self.assertEqual(out["jobs"][0]["company"], "Acme")
        self.assertNotIn("link", out["jobs"][0])  # summary mode omits link
        self.assertNotIn("skills", out["jobs"][0])  # summary mode omits skills

    def test_jobs_json_mode_adds_link_and_skills(self):
        proc = _fake_response(JOBS_CSV)
        with mock.patch.object(yc_network, "_yc", return_value=proc):
            import io
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                args = mock.Mock(query="backend", limit=2, json=True, filters=None)
                yc_network.cmd_jobs(args)
            out = json.loads(buf.getvalue())
        self.assertIn("link", out["jobs"][0])
        self.assertEqual(out["jobs"][0]["skills"], "Python, PostgreSQL")

    def test_skills_aggregation(self):
        proc = _fake_response(JOBS_CSV)
        with mock.patch.object(yc_network, "_yc", return_value=proc), mock.patch("sys.stdout"):
            import io
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                args = mock.Mock(query="backend", limit=2, filters=None)
                yc_network.cmd_skills(args)
            out = json.loads(buf.getvalue())
        self.assertEqual(out["postings_seen"], 2)
        freq = dict(out["skill_frequency"])
        self.assertEqual(freq["Python"], 1)
        self.assertEqual(freq["Go"], 1)
        self.assertEqual(dict(out["min_experience_years"])["3"], 1)
        self.assertEqual(dict(out["min_experience_years"])["0"], 1)

    def test_unknown_filters_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            yc_network._parse_filters('{"bogus_filter":"x"}')
        self.assertEqual(ctx.exception.code, 2)

    def test_valid_filters_parsed(self):
        f = yc_network._parse_filters('{"remote":"yes","eng_type":"be"}')
        self.assertEqual(f, {"remote": "yes", "eng_type": "be"})

    def test_none_filters(self):
        self.assertIsNone(yc_network._parse_filters(None))


class YcSubprocessTests(unittest.TestCase):
    def test_calls_yc_with_search_input(self):
        """_run_search builds the exact yc tools run command."""
        with mock.patch.object(yc_network, "_yc", return_value=_fake_response("")) as m:
            yc_network._run_search("jobs", "python", 5, ["min_experience"], {"remote": "yes"})
        args = m.call_args[0][0]
        self.assertEqual(args[:3], ["tools", "run", "search"])
        self.assertIn("--input", args)
        payload = json.loads(args[args.index("--input") + 1])
        self.assertEqual(payload["entity"], "jobs")
        self.assertEqual(payload["query"], "python")
        self.assertEqual(payload["extra_fields"], "min_experience")
        self.assertEqual(payload["filters"], {"remote": "yes"})

    def test_missing_cli_exits_2(self):
        with mock.patch.object(yc_network.shutil, "which", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                yc_network._yc(["me"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
