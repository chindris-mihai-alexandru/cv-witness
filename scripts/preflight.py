#!/usr/bin/env python3
"""Live market pre-flight: pull real postings and check them against a CV.

The skill's pre-flight checklist says to check a CV against a posting before
tailoring. This script removes the manual step: it aggregates live postings
from every configured source and runs the existing knockout checker against
each one, so a FAIL surfaces before any tailoring work is invested.

Sources (all optional, all degraded gracefully):
  - YC / Work at a Startup via the `yc` CLI (see scripts/yc_network.py);
    run `yc login` once.
  - European ATS public feeds (greenhouse / lever / ashby) with --ats;
    no credentials required.
  - Adzuna with --country and ADZUNA_APP_ID/ADZUNA_API_KEY (see
    scripts/eu_network.py).

Design: reuse, do not duplicate. This script imports knockout_check's signal
extraction and evidence matching, and yc_network/eu_network for fetches. It
adds no new parsing logic of its own.

Usage:
  python3 scripts/preflight.py --cv CV.pdf --role "backend engineer"
  python3 scripts/preflight.py --cv CV.pdf --role "kubernetes" \
      --ats greenhouse:n26,lever:zalando --adzuna-country de --where "Berlin"
  python3 scripts/preflight.py --cv CV.pdf --role "backend" --max-postings 200

Exit codes:
  0 - checked; no FAIL across all postings that yielded signals
  1 - at least one FAIL (a tailoring gap surfaced)
  2 - input/config error
  Other - no postings at all (nothing to check; report, do not fail the gate)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eu_network import adzuna_search, EuNetworkError  # noqa: E402
from eu_network import _greenhouse_rows, _lever_rows, _ashby_rows  # noqa: E402
from eu_network import arbeitnow_search, bundesagentur_search  # noqa: E402
import knockout_check  # noqa: E402


def fetch_yc_postings(role: str, limit: int) -> list[dict]:
    """Live WAAS postings via the yc CLI. Returns [] and a note when unusable."""
    if not shutil.which("yc"):
        return []
    proc = subprocess.run(
        ["yc", "tools", "run", "search", "--input", json.dumps({
            "entity": "jobs", "query": role, "limit": limit,
            "extra_fields": "description,min_experience,skills,role,company_name",
        })],
        capture_output=True, text=True, timeout=240,
    )
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    res = data.get("result", data)
    import csv, io
    rows = list(csv.DictReader(io.StringIO(res.get("csv_results", ""))))
    out = []
    for r in rows:
        out.append({
            "source": "yc", "company": r.get("company_name", ""),
            "title": r.get("role", "") or r.get("title", ""),
            "location": r.get("locations_for_search", ""),
            "text": "\n".join(filter(None, [r.get("title", ""), r.get("description", ""),
                                            f"min experience: {r.get('min_experience', '')}" if r.get("min_experience") else ""])),
            "url": r.get("link", ""), "skills": r.get("skills", ""),
        })
    return out


def fetch_ats_postings(specs: list[str]) -> list[dict]:
    """specs like 'greenhouse:n26' or 'lever:zalando,deliveryhero'."""
    fetch = {"greenhouse": _greenhouse_rows, "lever": _lever_rows, "ashby": _ashby_rows}
    out = []
    for spec in specs:
        provider, _, companies = spec.partition(":")
        handler = fetch.get(provider)
        if not handler:
            continue
        for company in companies.split(","):
            try:
                for row in handler(company):
                    out.append({
                        "source": provider, "company": company,
                        "title": row["title"], "location": row["location"],
                        "text": "\n".join(filter(None, [row["title"], row["description"]])),
                        "url": row["url"], "skills": "",
                    })
            except EuNetworkError:
                continue
    return out


def fetch_adzuna_postings(country: str, role: str, limit: int) -> list[dict]:
    out = []
    try:
        for row in adzuna_search(country, role, limit, None):
            out.append({
                "source": "adzuna", "company": row["company"],
                "title": row["title"], "location": row["location"],
                "text": "\n".join(filter(None, [row["title"], row["description"]])),
                "url": row["url"], "skills": "",
            })
    except EuNetworkError as e:
        print(f"[preflight] adzuna skipped: {e}", file=sys.stderr)
    return out


def fetch_arbeitnow_postings(role: str, limit: int) -> list[dict]:
    out = []
    try:
        for row in arbeitnow_search(role, limit, 1):
            out.append({
                "source": "arbeitnow", "company": row["company"],
                "title": row["title"], "location": row["location"],
                "text": "\n".join(filter(None, [row["title"], row["description"]])),
                "url": row["url"], "skills": "",
            })
    except EuNetworkError as e:
        print(f"[preflight] arbeitnow skipped: {e}", file=sys.stderr)
    return out


def fetch_bundesagentur_postings(role: str, where: str, limit: int) -> list[dict]:
    out = []
    try:
        for row in bundesagentur_search(role, where, limit):
            out.append({
                "source": "bundesagentur", "company": row["company"],
                "title": row["title"], "location": row["location"],
                "text": "\n".join(filter(None, [row["title"], row["description"]])),
                "url": row["url"], "skills": "",
            })
    except EuNetworkError as e:
        print(f"[preflight] bundesagentur skipped: {e}", file=sys.stderr)
    return out


def check_posting(posting: dict, cv: str) -> dict | None:
    """Run knockout signals for one posting. None when nothing extractable."""
    signals = knockout_check.extract_signals(posting["text"])
    if not signals:
        return None
    results = []
    for name, value in signals.items():
        status, detail = knockout_check.check_signal(name, value, cv)
        results.append({"signal": name, "requirement": value, "status": status, "detail": detail})
    return {"posting": posting, "signals": signals, "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description="Live market pre-flight against a CV")
    ap.add_argument("--cv", required=True, help="CV file (PDF or text)")
    ap.add_argument("--role", required=True, help="role query used to pull postings")
    ap.add_argument("--ats", default="", help="comma-separated provider:company specs (greenhouse:n26)")
    ap.add_argument("--adzuna-country", default="", help="2-letter country for Adzuna (de, fr, ...)")
    ap.add_argument("--where", default="", help="location term for Bundesagentur (Berlin, ...)")
    ap.add_argument("--max-postings", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        cv = knockout_check.read_text(args.cv)
    except knockout_check.KnockoutError as e:
        print(f"preflight: {e}", file=sys.stderr)
        return 2

    postings = []
    postings += fetch_yc_postings(args.role, args.max_postings // 2)
    ats_specs = [s.strip() for s in args.ats.split(",") if s.strip()]
    postings += fetch_ats_postings(ats_specs)
    if args.adzuna_country:
        postings += fetch_adzuna_postings(args.adzuna_country, args.role, args.max_postings // 4)
    postings += fetch_arbeitnow_postings(args.role, args.max_postings // 4)
    postings += fetch_bundesagentur_postings(args.role, args.where, args.max_postings // 4)

    if not postings:
        print(json.dumps({"checked": 0, "note": "no postings available from any source"}))
        return 3

    all_checks = []
    for p in postings:
        c = check_posting(p, cv)
        if c:
            all_checks.append(c)

    fails = [c for c in all_checks if any(r["status"] == "FAIL" for r in c["results"])]
    unclear = [c for c in all_checks if any(r["status"] == "UNCLEAR" for r in c["results"]) and c not in fails]

    if args.json:
        print(json.dumps({
            "checked": len(postings), "with_signals": len(all_checks),
            "fails": len(fails), "unclear": len(unclear),
            "summary": [
                {"company": c["posting"]["company"], "title": c["posting"]["title"],
                 "source": c["posting"]["source"],
                 "worst": "FAIL" if any(r["status"] == "FAIL" for r in c["results"])
                         else ("UNCLEAR" if any(r["status"] == "UNCLEAR" for r in c["results"]) else "PASS"),
                 "results": c["results"]}
                for c in all_checks
            ],
        }, indent=2, ensure_ascii=False))
        return 1 if fails else 0

    print(f"=== LIVE PRE-FLIGHT: {len(postings)} postings checked ===")
    for c in all_checks:
        worst = "FAIL" if any(r["status"] == "FAIL" for r in c["results"]) else "UNCLEAR" if any(r["status"] == "UNCLEAR" for r in c["results"]) else "PASS"
        print(f"\n[{worst}] {c['posting']['source']}:{c['posting']['company']} - {c['posting']['title']}")
        for r in c["results"]:
            print(f"    {r['status']:<8} {r['signal']}: {r['detail']}")
    print(f"\n{fails and 'FAILURES FOUND - check the flagged signals before tailoring' or 'No hard failures detected.'}")

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
