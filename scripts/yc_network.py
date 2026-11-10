#!/usr/bin/env python3
"""Query the YC / Work-at-a-Startup network for CV-tailoring intelligence.

Wraps the official `yc` CLI (install:
https://bookface.ycombinator.com/cli/install.sh, auth: `yc login`). Gives
cv-witness two capabilities the gated MCP `waas_candidate` actions do not:

  * jobs / postings: real WAAS postings with min_experience, skills,
    description, role, remote, visa, location — the requirement vocabulary
    that knockout_check.py and fit_score.py consume.
  * companies: YC companies with hiring signals for market-aware tailoring.

Why `yc` CLI instead of the MCP endpoint directly: `yc` keeps its own
refreshable OAuth session (never printed, rate-limited with Retry-After
handling) and is the stable supported surface. Verified 2026-11: the MCP
endpoint's waas_candidate action list is empty for candidate accounts, while
`yc search --type jobs` (and search.jobs via `yc tools run`) are not gated.

Search tool reference (verified via `yc tools describe search.jobs`):
  role: eng, operations, sales, marketing, product
  eng_type: fs, be, ml, fe, devops
  remote: no, yes, only
  job_type: fulltime, intern, contract, cofounder
  min_experience: numeric years (facet)
  us_visa_required: yes, none, possible
  extra_fields: min_experience, skills, description, role, eng_type,
    us_visa_required, company_team_size, has_salary, has_equity,
    company_waas_stage, company_website, company_description,
    company_hiring_description, created_at, locations_for_search

Output is JSON on stdout. Never emit the yc token; never paste full posting
text into a transcript unless the caller asked for it.

Usage:
  python3 scripts/yc_network.py check
  python3 scripts/yc_network.py jobs --query "backend engineer" --limit 5
  python3 scripts/yc_network.py postings --query "backend" \
      --filters '{"remote":"yes","eng_type":"be","min_experience":"0:3"}' \
      --extra-fields min_experience,skills,description,role --limit 5
  python3 scripts/yc_network.py companies --query "developer tools" --limit 10
  python3 scripts/yc_network.py skills --query "backend" --limit 40 \
      # aggregate skills + min_experience distribution for market calibration

Exit codes: 0 ok, 1 runtime/API error, 2 CLI missing / not authenticated.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from collections import Counter

JOB_EXTRA_FIELDS = [
    "min_experience", "skills", "description", "role", "eng_type",
    "us_visa_required", "company_team_size", "has_salary", "has_equity",
    "company_waas_stage", "company_website", "company_description",
    "company_hiring_description", "created_at", "locations_for_search",
]

KNOWN_FILTERS = {
    "role", "eng_type", "remote", "job_type", "min_experience",
    "us_visa_required", "company_team_size", "company_waas_stage",
    "locations_for_search", "has_salary", "has_equity", "company_parent_sector",
}


def _yc(args: list[str], timeout: int = 240) -> subprocess.CompletedProcess:
    if not shutil.which("yc"):
        print("yc CLI not found. Install: curl -fsSL https://bookface.ycombinator.com/cli/install.sh | bash",
              file=sys.stderr)
        sys.exit(2)
    try:
        return subprocess.run(["yc", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print("yc call timed out", file=sys.stderr)
        sys.exit(1)


def _parse_json(proc: subprocess.CompletedProcess) -> dict:
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip()
        if "Not logged in" in msg:
            print("yc not authenticated. Run: yc login", file=sys.stderr)
            sys.exit(2)
        print(f"yc failed ({proc.returncode}): {msg[:400]}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("yc returned non-JSON output", file=sys.stderr)
        sys.exit(1)


def _rows(data: dict) -> list[dict]:
    res = data.get("result", data)
    if not res.get("csv_results"):
        return []
    return list(csv.DictReader(io.StringIO(res["csv_results"])))


def cmd_check(args: argparse.Namespace | None = None) -> int:
    proc = _yc(["me"], timeout=60)
    blob = proc.stdout + proc.stderr
    if "Not logged in" in blob:
        print("not-authenticated", file=sys.stderr)
        return 2
    if proc.returncode != 0:
        print("yc me failed", file=sys.stderr)
        return 1
    print("ok")
    return 0


def _run_search(entity: str, query: str, limit: int, extra_fields: list[str] | None,
                filters: dict | None) -> dict:
    params: dict = {"entity": entity, "limit": limit}
    if query:
        params["query"] = query
    if extra_fields:
        params["extra_fields"] = ",".join(extra_fields)
    if filters:
        params["filters"] = filters
    proc = _yc(["tools", "run", "search", "--input", json.dumps(params)])
    return _parse_json(proc)


def cmd_jobs(args: argparse.Namespace) -> int:
    data = _run_search("jobs", args.query, args.limit, None, args.filters)
    res = data.get("result", data)
    rows = _rows(data)
    out = {"total_count": res.get("total_count"), "count": len(rows)}
    items = []
    for row in rows:
        item = {"company": row.get("company_name"), "role": row.get("role"),
                "remote": row.get("remote"), "locations": row.get("locations_for_search"),
                "job_type": row.get("job_type"), "min_experience": row.get("min_experience")}
        if args.json:
            item["link"] = row.get("link")
            item["skills"] = row.get("skills")
        items.append(item)
    out["jobs"] = items
    print(json.dumps(out, indent=2))
    return 0


def cmd_postings(args: argparse.Namespace) -> int:
    fields = args.extra_fields.split(",") if args.extra_fields else JOB_EXTRA_FIELDS
    data = _run_search("jobs", args.query, args.limit, fields, args.filters)
    res = data.get("result", data)
    rows = _rows(data)
    out = {"total_count": res.get("total_count"), "count": len(rows),
           "rows": rows}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    """Aggregate skills + min_experience across postings: market calibration."""
    fields = ["skills", "min_experience", "role", "eng_type"]
    data = _run_search("jobs", args.query, args.limit, fields, args.filters)
    rows = _rows(data)
    skill_counts: Counter = Counter()
    exp_hist: Counter = Counter()
    roles: Counter = Counter()
    for row in rows:
        for s in re_split_skills(row.get("skills", "")):
            skill_counts[s] += 1
        exp = row.get("min_experience") or "?"
        exp_hist[exp] += 1
        if row.get("role"):
            roles[row["role"]] += 1
    print(json.dumps({
        "queried": args.query, "postings_seen": len(rows),
        "skill_frequency": skill_counts.most_common(25),
        "min_experience_years": sorted(exp_hist.items(), key=lambda kv: (kv[0] != "?", str(kv[0]))),
        "role_split": dict(roles),
    }, indent=2))
    return 0


def re_split_skills(skills: str | None) -> list[str]:
    """Split a skills cell on commas / semicolons / pipes; strip empties."""
    if not skills:
        return []
    import re
    parts = re.split(r"[,;|]+", skills)
    return [p.strip() for p in parts if p.strip()]


def cmd_companies(args: argparse.Namespace) -> int:
    data = _run_search("companies", args.query, args.limit,
                       ["one_liner", "batch", "status", "isHiring"], args.filters)
    res = data.get("result", data)
    rows = _rows(data)
    out = {"total_count": res.get("total_count"), "count": len(rows)}
    items = []
    for row in rows:
        items.append({
            "name": row.get("name") or row.get("company_name"),
            "batch": row.get("batch"), "status": row.get("status"),
            "hiring": row.get("isHiring"), "one_liner": row.get("one_liner"),
        })
    out["companies"] = items
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def _parse_filters(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        filters = json.loads(text)
    except json.JSONDecodeError:
        print("--filters must be JSON, e.g. '{\"remote\":\"yes\",\"eng_type\":\"be\"}'", file=sys.stderr)
        sys.exit(2)
    unknown = set(filters) - KNOWN_FILTERS
    if unknown:
        print(f"unknown filter(s): {sorted(unknown)}. Known: {sorted(KNOWN_FILTERS)}", file=sys.stderr)
        sys.exit(2)
    return filters


def main() -> int:
    ap = argparse.ArgumentParser(description="YC network intel for CV tailoring")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="verify yc CLI is installed + authenticated").set_defaults(func=cmd_check)

    p = sub.add_parser("jobs", help="WAAS job summaries")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true", help="include link + skills")
    p.add_argument("--filters", type=_parse_filters, default=None)
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("postings", help="full postings with requirement fields")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--filters", type=_parse_filters, default=None)
    p.add_argument("--extra-fields", default=None)
    p.set_defaults(func=cmd_postings)

    p = sub.add_parser("skills", help="aggregate skills/experience across postings")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--filters", type=_parse_filters, default=None)
    p.set_defaults(func=cmd_skills)

    p = sub.add_parser("companies", help="YC companies (hiring signals)")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--filters", type=_parse_filters, default=None)
    p.set_defaults(func=cmd_companies)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
