#!/usr/bin/env python3
"""Company context gate: should this application be started at all?

Runs before tailoring. Combines three questions into one verdict:

1. HARD GATES - can the candidate legally and literally do this job?
   Delegates to ``knockout_check`` (work rights, clearance, experience floor,
   education, licences, locations).
2. TRUST - is the employer financially real and stable enough to be worth a
   career move? Curated EU hiring lists, European startup funding data
   (funding.tech.eu MCP, optional) and tech layoff records (optional).
3. RELOCATION - does the role fit the candidate's move? EU/EEA freedom of
   movement, English-speaking workplace, sponsorship.

Output is PROCEED / STOP / CONFIRM with reasons. STOP means a hard gate fails;
CONFIRM means a fact is missing and a human must answer it; PROCEED means the
gate is clear and tailoring can start.

Usage:
    python3 scripts/company_context.py --posting posting.txt --cv CV.pdf \
        --company "Example Energy" --citizen RO
    python3 scripts/company_context.py --posting posting.txt --cv CV.pdf \
        --company "Atreides" --citizen RO --sponsorship no --funding

Exit codes: 0 PROCEED, 1 STOP or CONFIRM, 2 input/tool error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

if __package__:
    from . import knockout_check
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import knockout_check

ROOT = Path(__file__).resolve().parents[1]
LISTS_DIR = ROOT / "references" / "company_lists"

# Workplaces where English is the normal working language in practice, not just
# a posted requirement. Used only as a soft signal; the posting's own language
# is always the primary evidence.
ENGLISH_WORKPLACE_COUNTRIES = {"GB", "IE", "NL", "SE", "DK", "NO", "FI", "MT", "CY"}

FUNDING_MCP_URL = "https://funding.tech.eu/api/mcp"


class ContextError(Exception):
    """Raised for input or tool failures."""


# --- curated lists ----------------------------------------------------------

def load_european_remote() -> dict[str, dict]:
    """Company name -> row from the EuropeanRemote EU hiring list (8 columns)."""
    path = LISTS_DIR / "european_remote.tsv"
    if not path.is_file():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        name, hq, domain, mode, stack, salary, global_salary, hiring = parts[:8]
        rows[name.strip().lower()] = {
            "name": name.strip(), "hq": hq, "domain": domain, "work_mode": mode,
            "tech_stack": stack,
            "salary_transparency": salary.strip().lower() == "yes",
            "global_salary": global_salary.strip().lower() == "yes",
            "hiring_now": hiring.strip().lower() == "yes",
        }
    return rows


def load_remote_dna() -> set[str]:
    path = LISTS_DIR / "remote_dna.txt"
    if not path.is_file():
        return set()
    return {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def match_company(name: str, table: dict | set) -> str | None:
    """Case-insensitive match, tolerating a parenthetical suffix."""
    key = re.sub(r"\s+", " ", name.strip().lower())
    key = re.sub(r"\s*\([^)]*\)\s*$", "", key).strip()
    if isinstance(table, dict):
        return key if key in table else None
    return key if key in table else None


# --- optional live feeds ----------------------------------------------------

def mcp_funding_lookup(company: str) -> dict | None:
    """Query the funding.tech.eu MCP for European startup funding data.

    Returns parsed content or None when the server is unreachable. Never raises:
    a missing feed is a gap, not a failure.
    """
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "find_companies", "arguments": {"query": company}},
    }
    request = urllib.request.Request(
        FUNDING_MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            envelope = json.loads(line[5:].strip())
        except json.JSONDecodeError:
            continue
        result = envelope.get("result", {})
        content = result.get("content")
        if isinstance(content, list) and content:
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
    return None


def layoff_records(path: str | None, company: str) -> list[dict]:
    """Filter a layoffs CSV (layoffs.fyi format) to one company."""
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    key = company.strip().lower()
    hits = []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    header = lines[0].split(",") if lines else []
    idx = {name: i for i, name in enumerate(header)}
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) < 2:
            continue
        name = cells[idx.get("Company", 0)].strip().lower()
        if key and key in name:
            hits.append({
                "company": cells[idx.get("Company", 0)].strip(),
                "total_laid_off": cells[idx.get("total_laid_off", 4)].strip(),
                "date": cells[idx.get("date", 3)].strip(),
                "stage": cells[idx.get("stage", 8)].strip(),
            })
    return hits


# --- the gate ---------------------------------------------------------------

def build_context(posting_path: str, cv_path: str, company: str, citizen: str | None,
                  sponsorship: bool, holds_clearance: bool, funding: bool,
                  layoffs_csv: str | None) -> dict:
    posting = knockout_check.read_text(posting_path)
    cv = knockout_check.read_text(cv_path)
    signals = knockout_check.extract_signals(posting)
    profile = {
        "citizen": citizen,
        "sponsorship": sponsorship,
        "holds_clearance": holds_clearance,
        "work_auth_countries": signals.get("work_auth_countries", []),
    }
    if signals.get("work_auth_sponsorship") is False:
        profile["sponsorship"] = False

    gates = []
    for name, value in signals.items():
        if name in knockout_check.META_SIGNALS or name == "location" and "locations" in signals:
            continue
        status, detail = knockout_check.check_signal(name, value, cv, profile)
        gates.append({"signal": name, "requirement": value, "status": status, "detail": detail})

    hard_fail = [g for g in gates if g["status"] == "FAIL"]
    unclear = [g for g in gates if g["status"] == "UNCLEAR"]
    confirm = [g for g in gates if g["status"] == "CONFIRM"]

    # Trust: curated lists first (offline, deterministic).
    eu_table = load_european_remote()
    dna = load_remote_dna()
    trust = {
        "european_remote_list": None,
        "remote_dna_list": None,
        "funding": None,
        "layoffs": [],
    }
    eu_key = match_company(company, eu_table)
    if eu_key:
        trust["european_remote_list"] = eu_table[eu_key]
    dna_key = match_company(company, dna)
    if dna_key:
        trust["remote_dna_list"] = dna_key
    if funding:
        trust["funding"] = mcp_funding_lookup(company)
    trust["layoffs"] = layoff_records(layoffs_csv, company)

    # Relocation fit.
    locations = signals.get("locations", [])
    countries = []
    for place in locations:
        iso = knockout_check.country_iso2(place)
        if iso:
            countries.append(iso)
    if not countries:
        for place in [signals.get("location", "")]:
            iso = knockout_check.country_iso2(str(place))
            if iso:
                countries.append(iso)
    relocation = {
        "locations": locations,
        "countries": sorted(set(countries)),
        "eu_free_movement": bool(countries) and all(
            c in knockout_check.EU_EEA_FREE_MOVEMENT for c in countries
        ),
        "english_friendly": bool(countries) and any(
            c in ENGLISH_WORKPLACE_COUNTRIES for c in countries
        ),
        "sponsorship_offered": not profile["sponsorship"],
    }

    # Verdict.
    reasons = []
    if hard_fail:
        verdict = "STOP"
        reasons.extend(f"{g['signal']}: {g['detail']}" for g in hard_fail)
    elif unclear or confirm:
        verdict = "CONFIRM"
        reasons.extend(f"{g['signal']}: {g['detail']}" for g in unclear + confirm)
    else:
        verdict = "PROCEED"
    if trust["layoffs"]:
        verdict = "CONFIRM" if verdict == "PROCEED" else verdict
        reasons.append(f"{len(trust['layoffs'])} recorded layoff event(s) for this company")
    if not relocation["eu_free_movement"] and verdict == "PROCEED":
        verdict = "CONFIRM"
        reasons.append("no workable location under EU/EEA free movement")

    return {
        "company": company,
        "verdict": verdict,
        "reasons": reasons,
        "gates": gates,
        "trust": trust,
        "relocation": relocation,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Decide whether to pursue a role before tailoring")
    ap.add_argument("--posting", required=True)
    ap.add_argument("--cv", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--citizen", help="ISO-3166-1 alpha-2 citizenship, e.g. RO")
    ap.add_argument("--sponsorship", choices=["yes", "no"], default="yes")
    ap.add_argument("--holds-clearance", action="store_true")
    ap.add_argument("--funding", action="store_true", help="Query the funding.tech.eu MCP")
    ap.add_argument("--layoffs-csv", help="layoffs.fyi-format CSV for a layoff check")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        context = build_context(
            args.posting, args.cv, args.company, args.citizen,
            args.sponsorship == "yes", args.holds_clearance,
            args.funding, args.layoffs_csv,
        )
    except (ContextError, knockout_check.KnockoutError) as error:
        print(f"company-context: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(context, indent=2, ensure_ascii=False))
    else:
        print(f"=== COMPANY CONTEXT: {context['company']} ===")
        print(f"  VERDICT: {context['verdict']}")
        for reason in context["reasons"]:
            print(f"    - {reason}")
        print("  GATES")
        for gate in context["gates"]:
            print(f"    [{gate['status']}] {gate['signal']}: {gate['detail']}")
        rel = context["relocation"]
        print("  RELOCATION")
        print(f"    locations: {rel['locations'] or 'n/a'}  countries: {rel['countries'] or 'n/a'}")
        print(f"    EU/EEA free movement: {rel['eu_free_movement']}   "
              f"English-friendly: {rel['english_friendly']}   "
              f"sponsorship needed: {rel['sponsorship_offered']}")
        trust = context["trust"]
        print("  TRUST")
        print(f"    EuropeanRemote EU hiring list: {trust['european_remote_list'] or 'not listed'}")
        print(f"    Remote-DNA list: {trust['remote_dna_list'] or 'not listed'}")
        print(f"    funding: {trust['funding'] or 'not queried'}")
        print(f"    layoffs: {trust['layoffs'] or 'none recorded'}")

    return 0 if context["verdict"] == "PROCEED" else 1


if __name__ == "__main__":
    sys.exit(main())
