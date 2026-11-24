#!/usr/bin/env python3
"""Advisory ATS payload lints for canonical CV fields.

Port of the three lints in career-ops' ats-payload: employer-in-role,
parenthetical-in-company and multiple-date-ranges. Each needs a human decision,
so findings are reported and never applied. This script never edits fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__:
    from .rms_metadata import span_text
else:
    from rms_metadata import span_text

DATE_RANGE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*"
    r"(?:-|–|—|to)\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|present|current)",
    re.I)
COMPANY_SUFFIXES = {"inc", "llc", "ltd", "co", "corp", "gmbh", "bv", "sa", "plc"}
STOP_TOKENS = {"the", "and", "of", "for", "group", "systems", "technologies"}


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z]{3,}", value.lower())
            if token not in COMPANY_SUFFIXES and token not in STOP_TOKENS}


def lint(fields: dict) -> dict:
    findings = []
    company = (fields.get("COMPANY") or "").strip()
    if re.search(r"\([^)]*\)", company):
        findings.append({
            "code": "parenthetical-in-company",
            "detail": "A parenthetical in the employer field can create an unmatched parsed employer.",
            "value": company,
        })
    company_tokens = _tokens(company)
    roles = []
    for fragment in re.split(r'<div class="role-line">', fields.get("ROLES_BLOCK", ""))[1:]:
        head, _, _ = fragment.partition("</div>")
        role = span_text(head, "title")
        dates = span_text(head, "dates")
        roles.append((role, dates))
        overlap = company_tokens & _tokens(role)
        if overlap:
            findings.append({
                "code": "employer-in-role",
                "detail": "Employer wording appears in the role title; this may create a phantom employer.",
                "value": role,
                "overlap": sorted(overlap),
            })
        ranges = DATE_RANGE.findall(dates)
        if len(ranges) > 1:
            findings.append({
                "code": "multiple-date-ranges",
                "detail": "Two date ranges in one role can parse as one stint and misallocate bullets.",
                "value": dates,
            })
    skills = fields.get("SKILLS_BLOCK", "")
    if re.search(r"core competencies", skills, re.I):
        findings.append({
            "code": "nonstandard-skills-heading",
            "detail": "'Core Competencies' is not a standard parser heading; use Skills.",
            "value": "Core Competencies",
        })
    return {"status": "ok", "roles_checked": len(roles), "findings": findings,
            "note": "Advisory only. Findings are questions for the author, never automatic edits."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fields", help="Canonical CV fields JSON")
    parser.add_argument("--json", action="store_true", help="Print findings JSON only")
    args = parser.parse_args()
    payload = json.loads(Path(args.fields).read_text(encoding="utf-8"))
    fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
    if not isinstance(fields, dict):
        raise ValueError("Fields JSON must be an object")
    report = lint(fields)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"Payload lints: {len(report['findings'])} finding(s) in {report['roles_checked']} role(s)")
    for finding in report["findings"]:
        print(f"  - {finding['code']}: {finding['value']}")
    print(report["note"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Payload lint failed: {error}") from error
