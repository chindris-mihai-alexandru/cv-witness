#!/usr/bin/env python3
"""Compensation and employer-trust data providers (EU-first).

One provider layer, two transports. Scripts call these functions directly; an
MCP client calls the same functions through ``mcp/comp_server.py``. Neither
transport re-implements a provider.

Providers, best first for a European job search:

  EUPTD          advertised tech salary bands from job postings, open data
                 (CC BY 4.0 via the Aramente eu-tech-jobs corpus). No key.
                 Rebuilt on a schedule, so the as-of date is reported.
  WageAPI        Eurostat SES / Destatis / INSEE salary percentiles for 28 EU
                 countries. Needs WAGEAPI_KEY.
  Kununu         DACH employer reviews and 14-factor scores. No official API;
                 reachable through the Apify MCP or the Scrappa API (key).
  Figures, Ravio European comp benchmarking platforms. No public API; documented
                 here so a paid tier can be added without guessing.

Nothing in this module invents a number: a provider that is unreachable returns
None and the caller reports the gap.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

EUPTD_BASE = "https://euptd.eu/salary"
WAGEAPI_BASE = "https://salary.wageapi.com/api/v1"

# Role slugs published by EUPTD (checked 2026-11-16).
EUPTD_ROLES = (
    "care-worker", "customer-support", "data-analyst", "data-engineer",
    "data-scientist", "designer", "devops-engineer", "engineering-manager",
    "finance", "legal", "machine-learning-engineer", "marketing", "operations",
    "people-hr", "product-manager", "project-manager", "qa-engineer", "retail",
    "sales", "security-engineer", "software-engineer",
)

# Job-family keywords mapped to the closest EUPTD role, so a free-form title
# ("Cloud Platform Engineer") can be benchmarked without a new source.
ROLE_ALIASES = {
    "cloud": "devops-engineer", "platform": "devops-engineer",
    "devops": "devops-engineer", "sre": "devops-engineer",
    "site reliability": "devops-engineer", "infrastructure": "devops-engineer",
    "sysadmin": "devops-engineer", "backend": "software-engineer",
    "frontend": "software-engineer", "fullstack": "software-engineer",
    "full stack": "software-engineer", "software": "software-engineer",
    "support": "customer-support", "ml": "machine-learning-engineer",
    "machine learning": "machine-learning-engineer", "ai": "machine-learning-engineer",
    "security": "security-engineer", "qa": "qa-engineer", "test": "qa-engineer",
    "data": "data-engineer", "designer": "designer", "product": "product-manager",
    "project": "project-manager", "hr": "people-hr", "legal": "legal",
    "finance": "finance", "sales": "sales", "marketing": "marketing",
    "operations": "operations", "retail": "retail", "care": "care-worker",
}


class ProviderError(Exception):
    """Raised for input errors; network failures return None, never raise."""


def _get(url: str, headers: dict | None = None, timeout: int = 25) -> str | None:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "cv-witness/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None


def _text_from_html(body: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    import html
    body = html.unescape(body)
    return re.sub(r"\s+", " ", body)


def normalise_role(title: str) -> str:
    """Map a free-form job title to an EUPTD role slug."""
    key = re.sub(r"[^a-z ]", " ", title.lower())
    key = re.sub(r"\s+", " ", key).strip()
    for candidate in (key, key.replace(" ", "-")):
        if candidate in EUPTD_ROLES:
            return candidate
    # Longest alias first so "machine learning" wins over "ml" and "data"
    # scientist is not swallowed by the generic "data" alias.
    for needle, role in sorted(ROLE_ALIASES.items(), key=lambda kv: -len(kv[0])):
        if needle in key:
            return role
    return "software-engineer"


def _parse_band(text: str) -> dict | None:
    band = re.search(r"Typical advertised range\s*(€[\d,]+–€[\d,]+)\s*per year", text)
    sample = re.search(r"Based on\s*(\d+)\s*advertised ranges", text)
    employers = re.search(r"Employers\s*(\d+)", text)
    span = re.search(r"Full span observed:\s*(€[\d,]+–€[\d,]+)", text)
    as_of = re.search(r"Data as of\s*([\d-]+)", text)
    if not band:
        return None
    return {
        "band": band.group(1).replace(",", ""),
        "span": span.group(1).replace(",", "") if span else None,
        "sample_size": int(sample.group(1)) if sample else None,
        "employers": int(employers.group(1)) if employers else None,
        "as_of": as_of.group(1) if as_of else None,
    }


def euptd_role(title: str) -> dict | None:
    """Europe-wide advertised band for a role, from EUPTD (open data)."""
    role = normalise_role(title)
    body = _get(f"{EUPTD_BASE}/{role}/")
    if not body:
        return None
    parsed = _parse_band(_text_from_html(body))
    if parsed:
        parsed.update({"provider": "euptd", "scope": "Europe", "role": role})
    return parsed


def euptd_country(country: str) -> dict | None:
    """Country-wide advertised band across all roles, from EUPTD (open data)."""
    code = country.strip().lower()
    if len(code) != 2:
        return None
    body = _get(f"{EUPTD_BASE}/country/{code}/")
    if not body:
        return None
    parsed = _parse_band(_text_from_html(body))
    if parsed:
        parsed.update({"provider": "euptd", "scope": code.upper(), "role": "all roles"})
    return parsed


def wageapi_salary(job_title: str, country: str) -> dict | None:
    """Eurostat/Destatis/INSEE salary percentiles. Requires WAGEAPI_KEY."""
    key = os.environ.get("WAGEAPI_KEY")
    if not key:
        return None
    url = f"{WAGEAPI_BASE}/salary?job_title={urllib.parse.quote(job_title)}&country={urllib.parse.quote(country)}"
    body = _get(url, headers={"X-API-Key": key})
    if not body:
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("detail"):
        return None
    return {"provider": "wageapi", "raw": data}


def provider_catalog() -> list[dict]:
    """Documented providers and how to reach them, for --help and SKILL.md."""
    return [
        {"name": "euptd", "signal": "advertised tech salary band (EU / country)",
         "access": "open", "key": None, "scope": "Europe", "cost": "free"},
        {"name": "wageapi", "signal": "salary percentiles (Eurostat/Destatis/INSEE)",
         "access": "REST + MCP", "key": "WAGEAPI_KEY", "scope": "28 EU countries", "cost": "free tier / paid"},
        {"name": "kununu", "signal": "employer reviews and 14-factor scores (DACH)",
         "access": "Apify MCP / Scrappa REST", "key": "APIFY_TOKEN or SCRAPPA_KEY",
         "scope": "Germany, Austria, Switzerland", "cost": "paid"},
        {"name": "figures", "signal": "EU base + variable pay benchmarks",
         "access": "no public API", "key": None, "scope": "EU + UK", "cost": "from EUR 2,500/yr"},
        {"name": "ravio", "signal": "EU total comp incl. equity",
         "access": "no public API", "key": None, "scope": "EU, 48+ countries", "cost": "from GBP 5,000/yr"},
        {"name": "levels.fyi", "signal": "tech total comp and levels",
         "access": "paid MCP/API", "key": "LEVELS_API_KEY", "scope": "US-centric", "cost": "from USD 800/mo"},
    ]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Look up EU compensation benchmarks")
    ap.add_argument("--role", help="job title, e.g. 'Cloud Platform Engineer'")
    ap.add_argument("--country", help="ISO country code, e.g. DE")
    ap.add_argument("--salary", action="store_true", help="also try WageAPI (needs WAGEAPI_KEY)")
    ap.add_argument("--catalog", action="store_true")
    args = ap.parse_args()
    if args.catalog:
        print(json.dumps(provider_catalog(), indent=2))
    elif args.role:
        print(json.dumps(euptd_role(args.role), indent=2, ensure_ascii=False))
    elif args.country:
        print(json.dumps(euptd_country(args.country), indent=2, ensure_ascii=False))
    else:
        ap.print_help()
