"""Tests for cross-source job dedup (eu_network.dedup_jobs / `dedup` command).

The same role syndicated across Arbeitnow/Greenhouse/Adzuna must be enriched once,
not once per source. Dedup keeps the richer row and reports dropped duplicates with
a reason so nothing is silently lost.
"""
import json
import os
import subprocess
import sys
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import eu_network as eu


def row(company="Acme", title="Platform Engineer", url="", location="", description="", **kw):
    return {"company": company, "title": title, "url": url, "location": location,
            "description": description, **kw}


class DedupJobsTest(unittest.TestCase):
    def test_empty(self):
        kept, dropped = eu.dedup_jobs([])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, [])

    def test_same_url_normalized(self):
        rows = [row(url="https://boards.example.com/jobs/1?utm_source=x#frag"),
                row(url="https://boards.example.com/jobs/1/")]
        kept, dropped = eu.dedup_jobs(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["reason"], "same URL")

    def test_cross_source_company_title(self):
        rows = [row(company="Acme", title="Platform Engineer", url="https://a.example/1"),
                row(company="acme", title="platform  engineer", url="https://b.example/2")]
        kept, dropped = eu.dedup_jobs(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped[0]["reason"], "same company+title (cross-source)")

    def test_distinct_roles_kept(self):
        rows = [row(company="Acme", title="Platform Engineer", url="https://a/1"),
                row(company="Acme", title="Data Engineer", url="https://a/2"),
                row(company="Other", title="Platform Engineer", url="https://b/3")]
        kept, dropped = eu.dedup_jobs(rows)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])

    def test_keeps_richer_row(self):
        thin = row(url="https://a/1")
        rich = row(url="https://a/1", location="Rotterdam", description="x" * 200, salary_min=70000)
        kept, dropped = eu.dedup_jobs([thin, rich])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["location"], "Rotterdam")
        self.assertEqual(dropped[0]["row"]["description"], "")

    def test_missing_url_falls_back_to_company_title(self):
        rows = [row(company="Acme", title="Platform Engineer", url=""),
                row(company="Acme", title="Platform Engineer", url="")]
        kept, dropped = eu.dedup_jobs(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 1)

    def test_dropped_carries_duplicate_of(self):
        rows = [row(url="https://a/1"), row(url="https://a/1")]
        _, dropped = eu.dedup_jobs(rows)
        self.assertIn("duplicate_of", dropped[0])
        self.assertTrue(dropped[0]["duplicate_of"])


class DedupCommandTest(unittest.TestCase):
    def _run(self, payload):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "eu_network.py"), "dedup"],
                              input=json.dumps(payload), capture_output=True, text=True)

    def test_stdin_list(self):
        r = self._run([row(url="https://a/1"), row(url="https://a/1")])
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["dropped_count"], 1)

    def test_stdin_jobs_object(self):
        r = self._run({"jobs": [row(company="A", title="T", url="https://a/1"),
                                row(company="B", title="U", url="https://b/2")]})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["count"], 2)

    def test_bad_input(self):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "eu_network.py"), "dedup"],
                           input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()