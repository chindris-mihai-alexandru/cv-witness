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

    def test_treg_rows_use_application_link(self):
        # treg jobs-api rows carry application_link, not url; dedup must still work
        a = {"company": "Acme", "title": "Platform Engineer", "application_link": "https://jobs.example/1"}
        b = {"company": "Acme", "title": "Platform Engineer", "application_link": "https://other.example/2"}
        kept, dropped = eu.dedup_jobs([a, b])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped[0]["reason"], "same company+title (cross-source)")


    def test_treg_field_names_dedup_by_company_title(self):
        r1 = {"company_name": "Example Corp", "job_title": "Engineer",
              "url": "https://a.example/1", "description": "short"}
        r2 = {"company_name": "Example Corp", "job_title": "Engineer",
              "application_link": "https://b.example/2", "description": "much longer and richer description than the first row by a wide margin"}
        kept, dropped = eu.dedup_jobs([r1, r2])
        self.assertEqual(len(kept), 1)
        self.assertIn("much longer", kept[0]["description"])

    def test_treg_application_link_reindexed_after_swap(self):
        r1 = {"company": "A", "title": "Eng", "url": "https://a.example/1", "description": "short"}
        r2 = {"company": "A", "title": "Eng", "application_link": "https://b.example/2", "description": "much longer and richer description than the first row by a wide margin"}
        r3 = {"company": "B", "title": "Other", "application_link": "https://b.example/2", "description": "x"}
        kept, dropped = eu.dedup_jobs([r1, r2, r3])
        # r3 shares the winner's application_link; reindexing must catch it
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(dropped), 2)
        self.assertTrue(any("same URL" in d["reason"] for d in dropped))


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