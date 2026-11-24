#!/usr/bin/env python3
"""Advisory check that tailored role titles match the approved master.

Ported in spirit from career-ops' cv-title-check: pair a tailored entry with a
master entry by {company, dates}, never by title, then compare titles exactly
after case/whitespace normalization. Title mismatch is a warning, not an error:
reframing can be a deliberate candidate choice. The check itself must complete;
unparseable input, unmatched or ambiguous pairs are reported, never hidden.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__:
    from .rms_metadata import html_text, span_text
else:
    from rms_metadata import html_text, span_text


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("–", "-").replace("—", "-")).strip().casefold()


def parse_master(text: str) -> tuple[str, dict[tuple[str, str], list[str]]]:
    """Parse the approved master's Experience section into {(company, dates): titles}."""
    lines = text.splitlines()
    section = []
    inside = False
    company = ""
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            match = re.match(r"##\s+Experience\s+-\s+([^(\n]+)", line, re.I)
            if match:
                inside = True
                company = match.group(1).strip()
            continue
        if inside:
            section.append(line)
    if not inside or not company:
        raise ValueError("No '## Experience - <company>' section found in master")

    entries: dict[tuple[str, str], list[str]] = {}
    pattern = re.compile(r"^Role\s+[^:]*:\s*(.+?)\s+\(([^()]*\d{4}[^()]*)\)\s*$", re.I)
    for line in section:
        match = pattern.match(line.strip())
        if not match:
            continue
        key = (normal(company), normal(match.group(2)))
        entries.setdefault(key, []).append(match.group(1).strip())
    if not entries:
        raise ValueError("No 'Role N: Title (dates)' entries found in master")
    return company, entries


def parse_fields(fields: dict) -> list[tuple[str, str, str]]:
    company = (fields.get("COMPANY") or "").strip()
    if not company:
        raise ValueError("Canonical fields have no COMPANY")
    roles = []
    for fragment in re.split(r'<div class="role-line">', fields.get("ROLES_BLOCK", ""))[1:]:
        head, _, _ = fragment.partition("</div>")
        title = span_text(head, "title")
        dates = span_text(head, "dates")
        if not title or not dates:
            raise ValueError("A role in ROLES_BLOCK is missing title or dates")
        roles.append((company, title, dates))
    if not roles:
        raise ValueError("No roles found in ROLES_BLOCK")
    return roles


def compare(fields: dict, master_text: str) -> dict:
    _, master = parse_master(master_text)
    roles = parse_fields(fields)
    exact, mismatches, unmatched, ambiguous = [], [], [], []
    for company, title, dates in roles:
        key = (normal(company), normal(dates))
        candidates = master.get(key, [])
        if not candidates:
            unmatched.append({"role": title, "dates": dates})
        elif len(candidates) > 1:
            ambiguous.append({"role": title, "dates": dates, "candidates": candidates})
        elif normal(candidates[0]) == normal(title):
            exact.append(title)
        else:
            mismatches.append({"tailored": title, "approved": candidates[0], "dates": dates})
    return {"exact": exact, "mismatches": mismatches,
            "unmatched": unmatched, "ambiguous": ambiguous}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", type=Path, required=True, help="Canonical CV fields JSON")
    parser.add_argument("--source", type=Path, required=True, help="Approved master markdown")
    args = parser.parse_args()
    payload = json.loads(args.fields.read_text(encoding="utf-8"))
    fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
    result = compare(fields, args.source.read_text(encoding="utf-8"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0  # Advisory: a title mismatch never fails the build.


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"Title check failed: {error}") from error
