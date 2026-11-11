#!/usr/bin/env python3
"""Query European job sources for CV-tailoring intelligence.

YC's WAAS catalog is US-heavy. For EU roles, the top sources **as of
2026-11** are the free, keyless national/aggregator APIs. Dead or gated
platforms are excluded on purpose: Honeypot shut down Jan 2025, talent.io was
restructured and weakened, EURES is partner-API-only (its terms explicitly
forbid screen scraping), and Indeed/Stepstone have no public API.

Tier 1 (no credentials, works today):
  1. Arbeitnow  - keyless JSON API aggregating EU/Germany jobs from ATS
     platforms (Greenhouse, SmartRecruiters, Join, Teamtailor, Recruitee,
     Comeet). `remote` and `visa_sponsorship` fields. ~50 req rate limit;
     ~300 jobs/page, newest first. Terms require a link back; can revoke.
     Endpoint: https://www.arbeitnow.com/api/job-board-api
  2. Bundesagentur für Arbeit (Jobsuche) - Germany's national employment
     service. Free JSON API, static X-API-Key header accepted (the public
     header value), no signup. Covers on-site German roles the remote boards
     miss. Endpoint: https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs
  3. Official ATS public APIs - Greenhouse (boards-api.greenhouse.io),
     Lever (api.lever.co, incl. jobs.eu.lever.co boards) and Ashby
     (api.ashbyhq.com). No key; one employer's board per call.

Tier 2 (free key required): Adzuna (developer.adzuna.com) - 19 markets incl.
de/fr/nl/be/at/ch/es/it/pl + gb/us. Self-serve REST; descriptions truncated.
Set ADZUNA_APP_ID / ADZUNA_API_KEY in the environment or pass --key-file.
Free tier is for personal research; commercial/publication use is paid.

Normalised output rows: company, title, location, url, description
(possibly truncated), salary fields when present. JSON on stdout; never
paste full posting text into a transcript unless asked.

Usage:
  python3 scripts/eu_network.py check
  python3 scripts/eu_network.py arbeitnow --query "backend engineer" --limit 5
  python3 scripts/eu_network.py bundesagentur --query "Python" --where "Berlin" --limit 5
  python3 scripts/eu_network.py adzuna --country de --query "backend engineer" --limit 5
  python3 scripts/eu_network.py ats --provider greenhouse --company n26 --limit 10
  python3 scripts/eu_network.py ats --provider greenhouse --enterprise --query "engineer"
  python3 scripts/eu_network.py ats --provider lever --company zalando --limit 10
  python3 scripts/eu_network.py ats --provider ashby --company electric --limit 10

Exit codes: 0 ok, 1 runtime/API error, 2 missing credentials/CLI prerequisites.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

# Official public ATS endpoints (no auth required)
ATS_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{company}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true",
}

# Verified-this-session European enterprise boards (2026-11-11: each slug
# returned live postings via its official feed). Startup intel comes from the
# YC CLI / WAAS; these cover the big-co side of the EU market.
ENTERPRISE_BOARDS = {
    "greenhouse": ["celonis", "n26", "contentful", "trustpilot"],
    "lever": ["spotify", "farfetch"],
    "ashby": [],
}


class EuNetworkError(Exception):
    pass


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "cv-witness/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode(errors="replace"))
    except urllib.error.HTTPError as e:
        raise EuNetworkError(f"HTTP {e.code} from {url}: {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise EuNetworkError(f"network error for {url}: {e.reason}") from e


def _strip_html(text: str) -> str:
    """Crude HTML→text for ATS posting bodies (Greenhouse content is HTML)."""
    text = html.unescape(text)          # first: &lt;h2&gt; -> <h2> (double-escaped JSON)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</?(?:p|div|h[1-6]|ul|ol|strong|em|b|i|li|span)[^>]*>", " ", text, flags=re.I)
    text = html.unescape(text)          # again: &amp; -> & after tag stripping
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


# --- Adzuna ---------------------------------------------------------------

def _load_adzuna_keys(key_file: str | None) -> tuple[str, str]:
    app_id = os.environ.get("ADZUNA_APP_ID")
    key = os.environ.get("ADZUNA_API_KEY")
    if key_file and os.path.isfile(key_file):
        import stat
        mode = os.stat(key_file).st_mode & 0o777
        if mode & 0o077:
            print(f"warning: {key_file} is not 0600 (mode {oct(mode)}); chmod it", file=sys.stderr)
        lines = [l.strip() for l in open(key_file).read().splitlines() if "=" in l]
        for line in lines:
            k, _, v = line.partition("=")
            if k.strip() == "ADZUNA_APP_ID":
                app_id = v.strip()
            elif k.strip() == "ADZUNA_API_KEY":
                key = v.strip()
    if not app_id or not key:
        raise EuNetworkError(
            "Adzuna credentials missing. Register a free key at "
            "https://developer.adzuna.com, then export ADZUNA_APP_ID and "
            "ADZUNA_API_KEY (or pass --key-file)."
        )
    return app_id, key


def adzuna_search(country: str, query: str, limit: int, key_file: str | None,
                  where: str = "") -> list[dict]:
    app_id, key = _load_adzuna_keys(key_file)
    params = {
        "app_id": app_id, "app_key": key,
        "what": query, "results_per_page": str(limit),
        "content-type": "application/json",
    }
    if where:
        params["where"] = where
    url = ADZUNA_BASE.format(country=country, page=1) + "?" + urllib.parse.urlencode(params)
    data = _get(url)
    rows = []
    for r in data.get("results", []):
        loc = r.get("location") or {}
        rows.append({
            "source": "adzuna", "country": country,
            "company": (r.get("company") or {}).get("display_name", ""),
            "title": r.get("title", ""),
            "location": ", ".join(loc.get("area") or []),
            "url": r.get("redirect_url", ""),
            "description": r.get("description", ""),
            "salary_min": r.get("salary_min"), "salary_max": r.get("salary_max"),
            "contract_type": r.get("contract_type"),
            "category": (r.get("category") or {}).get("label", ""),
        })
    return rows


# --- Arbeitnow (keyless, EU/Germany focus) ----------------------------------

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def arbeitnow_search(query: str, limit: int, page: int = 1) -> list[dict]:
    params = {"page": str(page)}
    data = _get(ARBEITNOW_URL + "?" + urllib.parse.urlencode(params))
    rows = []
    for j in (data.get("data") or []):
        tags = j.get("tags") or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        description = _strip_html(j.get("description") or "")[:4000]
        haystack = " ".join(filter(None, [
            str(j.get("title", "")), str(j.get("company_name", "")),
            *[str(t) for t in tags], description,
        ])).lower()
        if query and query.lower() not in haystack:
            # The endpoint is paginated newest-first, not keyword-searchable;
            # fetch up to `page` pages and filter client-side.
            continue
        rows.append({
            "source": "arbeitnow",
            "company": j.get("company_name", ""),
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("url", ""),
            "description": description,
            "salary_min": None, "salary_max": None,
            "contract_type": ", ".join(j.get("job_types") or [])
            if isinstance(j.get("job_types"), list) else str(j.get("job_types") or ""),
            "category": ", ".join(tags),
            "remote": bool(j.get("remote")),
            "visa_sponsorship": bool(j.get("visa_sponsorship")),
        })
    return rows


# --- Bundesagentur für Arbeit (Jobsuche, Germany national board) -------------

BA_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
BA_STATIC_KEY = "jobboerse-jobsuche"  # public header value documented by the service


def bundesagentur_search(query: str, where: str = "", limit: int = 10) -> list[dict]:
    params = {"was": query, "page": "1", "size": str(min(limit, 20))}
    if where:
        params["wo"] = where
    url = BA_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "X-API-Key": BA_STATIC_KEY,
                                               "User-Agent": "cv-witness/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode(errors="replace"))
    except urllib.error.HTTPError as e:
        raise EuNetworkError(f"Bundesagentur HTTP {e.code}: {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise EuNetworkError(f"Bundesagentur network error: {e.reason}") from e
    rows = []
    for j in (data.get("ergebnisliste") or []):
        locations = []
        for loc in (j.get("stellenlokationen") or []):
            addr = loc.get("adresse") or {}
            parts = [addr.get("ort"), addr.get("region")]
            city = ", ".join(filter(None, parts)) or addr.get("plz", "")
            locations.append(city)
        rows.append({
            "source": "bundesagentur",
            "company": j.get("firma", ""),
            "title": j.get("stellenangebotsTitel", ""),
            "location": "; ".join(filter(None, locations)) or "Germany",
            "url": "https://www.arbeitsagentur.de/jobsuche/suche?was={}".format(
                urllib.parse.quote(query)),
            "description": (j.get("stellenbeschreibung") or (
                j.get("hauptberuf") or ""))[:4000],
            "salary_min": None, "salary_max": None,
            "contract_type": "Vollzeit" if j.get("arbeitszeitVollzeit") else "",
            "category": j.get("hauptberuf", ""),
        })
    return rows


# --- ATS public feeds ------------------------------------------------------

def _companies_arg(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]


def _greenhouse_rows(company: str) -> list[dict]:
    data = _get(ATS_ENDPOINTS["greenhouse"].format(company=company))
    rows = []
    for j in (data.get("jobs") or []):
        loc = (j.get("location") or {}).get("name", "")
        rows.append({
            "source": "greenhouse", "company": company,
            "title": j.get("title", ""),
            "location": loc,
            "url": j.get("absolute_url", ""),
            "description": _strip_html(j.get("content") or "")[:4000],
            "salary_min": None, "salary_max": None,
            "contract_type": "", "category": "",
        })
    return rows


def _lever_rows(company: str) -> list[dict]:
    data = _get(ATS_ENDPOINTS["lever"].format(company=company))
    rows = []
    for j in (data if isinstance(data, list) else []):
        cats = j.get("categories") or {}
        rows.append({
            "source": "lever", "company": company,
            "title": j.get("text", ""),
            "location": cats.get("location", ""),
            "url": j.get("hostedUrl", ""),
            "description": (j.get("descriptionPlain") or j.get("description") or "")[:4000],
            "salary_min": None, "salary_max": None,
            "contract_type": cats.get("commitment", ""),
            "category": cats.get("team", ""),
        })
    return rows


def _ashby_rows(company: str) -> list[dict]:
    data = _get(ATS_ENDPOINTS["ashby"].format(company=company))
    rows = []
    for j in (data.get("jobs") or []):
        rows.append({
            "source": "ashby", "company": company,
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "url": j.get("applyUrl", ""),
            "description": _strip_html(j.get("descriptionHtml") or "")[:4000],
            "salary_min": j.get("compensation", {}).get("value", {}).get("minValue"),
            "salary_max": j.get("compensation", {}).get("value", {}).get("maxValue"),
            "contract_type": j.get("employmentType", ""),
            "category": j.get("department", ""),
        })
    return rows


# --- CLI -------------------------------------------------------------------

def cmd_check(args: argparse.Namespace | None = None) -> int:
    """Check prerequisites. Arbeitnow/Bundesagentur/ATS need no credentials."""
    problems = []
    if not (os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_API_KEY")):
        problems.append("Adzuna: ADZUNA_APP_ID/ADZUNA_API_KEY not set (optional tier-2)")
    print("\n".join(problems) if problems else "ok")
    return 2 if problems else 0


def cmd_arbeitnow(args: argparse.Namespace) -> int:
    try:
        rows = arbeitnow_search(args.query, args.limit, args.page)
    except EuNetworkError as e:
        print(f"arbeitnow: {e}", file=sys.stderr)
        return 1
    out = {"source": "arbeitnow", "count": len(rows), "jobs": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_bundesagentur(args: argparse.Namespace) -> int:
    try:
        rows = bundesagentur_search(args.query, args.where, args.limit)
    except EuNetworkError as e:
        print(f"bundesagentur: {e}", file=sys.stderr)
        return 1
    out = {"source": "bundesagentur", "count": len(rows), "jobs": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_adzuna(args: argparse.Namespace) -> int:
    try:
        rows = adzuna_search(args.country, args.query, args.limit, args.key_file, args.where)
    except EuNetworkError as e:
        print(f"adzuna: {e}", file=sys.stderr)
        return 1 if "credentials" not in str(e) else 2
    out = {"source": "adzuna", "count": len(rows), "jobs": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_ats(args: argparse.Namespace) -> int:
    handler = {"greenhouse": _greenhouse_rows, "lever": _lever_rows, "ashby": _ashby_rows}.get(args.provider)
    if handler is None:
        print(f"unknown provider {args.provider!r}; choose greenhouse|lever|ashby", file=sys.stderr)
        return 2
    if args.enterprise:
        companies = ENTERPRISE_BOARDS.get(args.provider, [])
        if not companies:
            print(f"no verified enterprise boards for provider {args.provider!r} "
                  f"(try --company <slug>)", file=sys.stderr)
            return 2
    else:
        companies = _companies_arg(args.company)
        if not companies:
            print("provide --company <slug> (or --enterprise for the shortlist)", file=sys.stderr)
            return 2
    all_rows = []
    errors = []
    for c in companies:
        try:
            for row in handler(c):
                if args.query and args.query.lower() not in row["title"].lower():
                    continue
                all_rows.append(row)
        except EuNetworkError as e:
            errors.append(f"{c}: {e}")
    out = {"source": args.provider, "count": len(all_rows), "jobs": all_rows}
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        for row in all_rows[: args.limit]:
            print(f"• {row['company']} — {row['title'][:70]} | {row['location'][:50]}")
            print(f"    {row['url']}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    return 1 if (not all_rows and errors) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="European job-source intel for CV tailoring")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="check prerequisites (Arbeitnow/Bundesagentur/ATS need none)").set_defaults(func=cmd_check)
    p = sub.add_parser("arbeitnow", help="Arbeitnow keyless EU/Germany jobs (paginated, client-filtered)")
    p.add_argument("--query", default="", help="title/company/tags substring; empty = all")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--page", type=int, default=1)
    p.set_defaults(func=cmd_arbeitnow)

    p = sub.add_parser("bundesagentur", help="Germany national job board (keyless, X-API-Key header)")
    p.add_argument("--query", required=True, help="search term for 'was'")
    p.add_argument("--where", default="", help="location for 'wo'")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_bundesagentur)

    p = sub.add_parser("adzuna", help="Adzuna market search (needs free API key)")
    p.add_argument("--country", required=True, help="2-letter code: de, fr, nl, be, at, ch, es, it, pl, gb, ...")
    p.add_argument("--query", required=True)
    p.add_argument("--where", default="", help="optional location term")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--key-file", default=None)
    p.set_defaults(func=cmd_adzuna)

    p = sub.add_parser("ats", help="official ATS public feed (no key): greenhouse|lever|ashby")
    p.add_argument("--provider", choices=["greenhouse", "lever", "ashby"], required=True)
    p.add_argument("--company", default="", help="board slug or comma-separated list, or --enterprise")
    p.add_argument("--enterprise", action="store_true",
                   help="query the verified EU enterprise shortlist instead of --company")
    p.add_argument("--query", default="", help="substring filter on title (case-insensitive)")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ats)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
