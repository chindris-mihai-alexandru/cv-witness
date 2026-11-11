"""Tests for the European job-source adapter (eu_network.py) and preflight.py.

The tests mock network calls — no keys, no credentials, runs in CI.
"""
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import eu_network
from scripts import preflight
from scripts import knockout_check


# --- eu_network: HTML stripping --------------------------------------------

class StripHtmlTests(unittest.TestCase):
    def test_unescapes_then_strips(self):
        # Greenhouse emits double-escaped HTML in JSON
        raw = "&lt;h2&gt;&lt;strong&gt;About&lt;/strong&gt;&lt;/h2&gt;\n&lt;p&gt;Body &amp; more&lt;/p&gt;"
        out = eu_network._strip_html(raw)
        self.assertEqual(out, "About \n Body & more")

    def test_list_items_become_lines(self):
        raw = "<ul><li>one</li><li>two</li></ul>"
        out = eu_network._strip_html(raw)
        self.assertIn("- one", out)
        self.assertIn("- two", out)
        self.assertIn("one", out.split("-")[1])  # items follow the markers

    def test_plain_text_passthrough(self):
        self.assertEqual(eu_network._strip_html("hello world"), "hello world")


# --- eu_network: Arbeitnow -------------------------------------------------

ARBEITNOW_PAYLOAD = {
    "data": [
        {"slug": "backend-python-1", "company_name": "Acme GmbH", "title": "Backend Engineer (Python)",
         "description": "<p>Build APIs in Python</p>", "remote": "True",
         "url": "https://www.arbeitnow.com/jobs/companies/acme/backend-python-1",
         "tags": "[\"Python\", \"Cloud\"]", "job_types": "[\"Full-time\"]", "location": "Berlin",
         "created_at": "1794349838"},
        {"slug": "sales-2", "company_name": "Beta", "title": "Sales Manager",
         "description": "<p>Close deals</p>", "remote": "False",
         "url": "https://www.arbeitnow.com/jobs/companies/beta/sales-2",
         "tags": "[]", "job_types": "[]", "location": "Munich", "created_at": "1794340000"},
    ]
}


class ArbeitnowTests(unittest.TestCase):
    def test_query_filter_and_normalization(self):
        with mock.patch.object(eu_network, "_get", return_value=ARBEITNOW_PAYLOAD):
            rows = eu_network.arbeitnow_search("Python", 5, 1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["company"], "Acme GmbH")
        self.assertEqual(row["title"], "Backend Engineer (Python)")
        self.assertEqual(row["remote"], True)
        self.assertEqual(row["category"], "Python, Cloud")
        self.assertNotIn("<p>", row["description"])

    def test_stringified_tags_parsed(self):
        with mock.patch.object(eu_network, "_get", return_value=ARBEITNOW_PAYLOAD):
            rows = eu_network.arbeitnow_search("", 5, 1)
        self.assertEqual(len(rows), 2)

    def test_no_match_returns_empty(self):
        with mock.patch.object(eu_network, "_get", return_value=ARBEITNOW_PAYLOAD):
            rows = eu_network.arbeitnow_search("Rust", 5, 1)
        self.assertEqual(rows, [])


# --- eu_network: Bundesagentur ---------------------------------------------

BA_PAYLOAD = {
    "ergebnisliste": [
        {"stellenangebotsTitel": "Python Developer", "firma": "Tech Berlin GmbH",
         "stellenlokationen": [{"adresse": {"ort": "Berlin", "region": "BERLIN", "plz": "10247"},
                                "breite": 1.0, "laenge": 2.0}],
         "arbeitszeitVollzeit": True, "hauptberuf": "Informatiker/in"},
    ],
    "maxErgebnisse": 1,
}


class BundesagenturTests(unittest.TestCase):
    def test_normalizes_german_fields(self):
        payload = json.dumps(BA_PAYLOAD).encode()
        ctx = mock.MagicMock()
        ctx.read.return_value = payload
        ctx.__enter__.return_value = ctx
        with mock.patch("urllib.request.urlopen", return_value=ctx):
            rows = eu_network.bundesagentur_search("Python", "Berlin", 5)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Python Developer")
        self.assertEqual(row["company"], "Tech Berlin GmbH")
        self.assertIn("Berlin", row["location"])
        self.assertEqual(row["contract_type"], "Vollzeit")

    def test_http_error_raises(self):
        import email.message
        err = urllib.error.HTTPError("url", 500, "boom",
                                     email.message.Message(),
                                     __import__("io").BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(eu_network.EuNetworkError):
                eu_network.bundesagentur_search("Python", "", 5)


# --- eu_network: Adzuna key handling ---------------------------------------

class AdzunaKeyTests(unittest.TestCase):
    def test_missing_keys_raise(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(eu_network.EuNetworkError):
                eu_network._load_adzuna_keys(None)

    def test_keys_from_env(self):
        with mock.patch.dict("os.environ", {"ADZUNA_APP_ID": "a", "ADZUNA_API_KEY": "k"}, clear=True):
            self.assertEqual(eu_network._load_adzuna_keys(None), ("a", "k"))


class AtsCliTests(unittest.TestCase):
    """--enterprise mode: shortlist resolution and query filtering."""

    def test_enterprise_uses_verified_shortlist(self):
        row = {"source": "greenhouse", "company": "celonis", "title": "Backend Engineer",
               "location": "Munich", "url": "x", "description": "d",
               "salary_min": None, "salary_max": None, "contract_type": "", "category": ""}
        args = mock.Mock(provider="greenhouse", company="", enterprise=True,
                         query="", limit=10, json=False)
        with mock.patch.object(eu_network, "_greenhouse_rows", return_value=[row]) as m, \
             mock.patch("sys.stdout"):
            code = eu_network.cmd_ats(args)
        self.assertEqual(code, 0)
        # one handler call per shortlist company, in order
        called = [mc.args[0] for mc in m.call_args_list]
        self.assertEqual(called, eu_network.ENTERPRISE_BOARDS["greenhouse"])

    def test_enterprise_query_filters_titles(self):
        rows = [
            {"source": "greenhouse", "company": "n26", "title": "Backend Engineer",
             "location": "", "url": "", "description": "", "salary_min": None,
             "salary_max": None, "contract_type": "", "category": ""},
            {"source": "greenhouse", "company": "n26", "title": "Sales Manager",
             "location": "", "url": "", "description": "", "salary_min": None,
             "salary_max": None, "contract_type": "", "category": ""},
        ]
        args = mock.Mock(provider="greenhouse", company="", enterprise=True,
                         query="engineer", limit=10, json=False)
        with mock.patch.object(eu_network, "_greenhouse_rows", return_value=rows), \
             mock.patch("sys.stdout"):
            eu_network.cmd_ats(args)
            # capture stdout via a buf
            import io
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                eu_network.cmd_ats(args)
            out = buf.getvalue()
        self.assertIn("Backend Engineer", out)
        self.assertNotIn("Sales Manager", out)

    def test_enterprise_without_boards_errors(self):
        args = mock.Mock(provider="ashby", company="", enterprise=True,
                         query="", limit=10, json=False)
        with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
            code = eu_network.cmd_ats(args)
        self.assertEqual(code, 2)

    def test_neither_company_nor_enterprise_errors(self):
        args = mock.Mock(provider="greenhouse", company="", enterprise=False,
                         query="", limit=10, json=False)
        with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
            code = eu_network.cmd_ats(args)
        self.assertEqual(code, 2)


# --- knockout_check: location filtering ------------------------------------

class LocationFilterTests(unittest.TestCase):
    def test_department_acronym_pair_rejected(self):
        posting = "The MLRO France team handles AFC Ops, KYC Ops and SAR, RFI reporting."
        signals = knockout_check.extract_signals(posting)
        self.assertNotIn("location", signals)

    def test_city_country_still_detected(self):
        posting = "Software Engineer\nGeneva, Switzerland\nFull-time"
        self.assertEqual(knockout_check.extract_signals(posting).get("location"), "Geneva, Switzerland")

    def test_hyphenated_job_descriptor_not_a_location(self):
        # "Full-time, Non-Investment" is a job-type line, not a place; the real
        # location on the previous line is what should survive.
        posting = ("Infrastructure Engineer\nGeneva, Switzerland; GVA (Geneva) - Non-Investment\n"
                   "Full-time, Non-Investment")
        signals = knockout_check.extract_signals(posting)
        self.assertEqual(signals.get("location"), "Geneva, Switzerland")

    def test_berlin_germany_detected(self):
        self.assertEqual(
            knockout_check.extract_signals("Backend Engineer Berlin, Germany (hybrid)").get("location"),
            "Berlin, Germany")

    def test_leading_article_stripped_but_hague_kept(self):
        self.assertEqual(knockout_check._first_place("The Munich, Germany office"), "Munich, Germany")
        self.assertEqual(knockout_check._first_place("The Hague, Netherlands"), "The Hague, Netherlands")


# --- preflight: wiring ------------------------------------------------------

class PreflightTests(unittest.TestCase):
    def test_check_posting_uses_knockout_signals(self):
        posting = {"source": "test", "company": "X", "title": "Y",
                   "text": "Senior Engineer, Berlin, Germany. 5+ years experience, Master's degree."}
        cv = "Senior Engineer at Siemens, Berlin\n2021 - present\nMaster's degree"
        out = preflight.check_posting(posting, cv)
        self.assertIsNotNone(out)
        statuses = {r["signal"]: r["status"] for r in out["results"]}
        self.assertIn("min_years", statuses)
        self.assertIn("location", statuses)

    def test_check_posting_none_when_no_signals(self):
        posting = {"source": "test", "company": "X", "title": "Y", "text": "no signals here"}
        self.assertIsNone(preflight.check_posting(posting, "irrelevant cv text"))

    def test_fetch_eu_postings_degrades_gracefully(self):
        """A failing Bundesagentur call must not crash the preflight."""
        # Use preflight's own EuNetworkError class: preflight.py imports
        # eu_network via a sys.path insert, which can be a different module
        # object than the test's package import — the classes differ, and the
        # except clause only catches its own.
        with mock.patch.object(preflight, "bundesagentur_search",
                               side_effect=preflight.EuNetworkError("down")):
            rows = preflight.fetch_bundesagentur_postings("Python", "", 5)
        self.assertEqual(rows, [])

    def test_run_with_no_sources_exits_3(self):
        import io
        with mock.patch.object(preflight, "fetch_yc_postings", return_value=[]), \
             mock.patch.object(preflight, "fetch_ats_postings", return_value=[]), \
             mock.patch.object(preflight, "fetch_arbeitnow_postings", return_value=[]), \
             mock.patch.object(preflight, "fetch_bundesagentur_postings", return_value=[]), \
             mock.patch.object(preflight.knockout_check, "read_text", return_value="cv text"), \
             mock.patch("sys.argv", ["preflight", "--cv", "cv.pdf", "--role", "x"]):
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                code = preflight.main()
            self.assertEqual(code, 3)
            self.assertIn("no postings", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
