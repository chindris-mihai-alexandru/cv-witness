#!/usr/bin/env python3
"""Build a STAR+R interview worksheet from approved CV fields.

Inspired by career-ops' STAR+R story bank: every generated section is anchored
to a bullet the candidate already approved. Situation, Task, Action, Result and
Reflection stay as explicit blanks. The script does not invent stories, metrics
or seniority; the candidate fills them from verified evidence. Output goes to a
file only, so private CV text is not printed to a terminal or log.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

if __package__:
    from .rms_metadata import html_text, span_text, split_divs
else:
    from rms_metadata import html_text, span_text, split_divs


def _role_entries(fields: dict) -> list[dict[str, str]]:
    company = (fields.get("COMPANY") or "").strip() or "Unknown employer"
    entries = []
    for fragment in re.split(r'<div class="role-line">', fields.get("ROLES_BLOCK", ""))[1:]:
        head, _, rest = fragment.partition("</div>")
        role = span_text(head, "title") or "Unknown role"
        dates = span_text(head, "dates") or "unknown dates"
        for bullet in re.findall(r"<li[^>]*>(.*?)</li>", rest, re.S | re.I):
            text = html_text(bullet)
            if text:
                entries.append({"source_type": "Experience", "company": company,
                                "role": role, "dates": dates, "bullet": text})
    return entries


def _project_entries(fields: dict) -> list[dict[str, str]]:
    entries = []
    for fragment in split_divs(fields.get("PROJECTS_BLOCK", ""), "project"):
        title = span_text(fragment, "proj-name") or "Unknown project"
        dates = span_text(fragment, "dates") or "unknown dates"
        for bullet in re.findall(r"<li[^>]*>(.*?)</li>", fragment, re.S | re.I):
            text = html_text(bullet)
            if text:
                entries.append({"source_type": "Project", "company": "Unknown employer",
                                "role": title, "dates": dates, "bullet": text})
    return entries


def worksheet(fields: dict) -> str:
    entries = _role_entries(fields) + _project_entries(fields)
    parts = [
        "# STAR+R interview worksheet",
        "",
        "Generated from approved CV fields. Each section is anchored to an approved bullet.",
        "Fill S/T/A/R/Reflection from verified evidence only. Do not invent metrics,",
        "scope or seniority. Every number must trace to an approved source.",
        "",
    ]
    if not entries:
        parts.append("No approved bullets were found in the fields JSON.")
        return "\n".join(parts) + "\n"
    for index, entry in enumerate(entries, 1):
        short = re.sub(r"\s+", " ", entry["bullet"])[:70].rstrip()
        parts.extend([
            f"## {index}. {entry['source_type']}: {entry['role']}",
            "",
            f"**Source:** approved fields — {entry['company']} — {entry['role']} — {entry['dates']}",
            "",
            f"**Approved bullet:** {entry['bullet']}",
            "",
            f"**Best for questions about:** [fill: {short}]",
            "",
            "**S (Situation):** [fill from verified evidence]",
            "",
            "**T (Task):** [fill from verified evidence]",
            "",
            "**A (Action):** [fill from verified evidence]",
            "",
            "**R (Result):** [fill from verified evidence]",
            "",
            "**Reflection:** [fill: what you learned or would do differently]",
            "",
        ])
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", type=Path, required=True, help="Canonical CV fields JSON")
    parser.add_argument("--output", type=Path, required=True, help="Private Markdown destination")
    args = parser.parse_args()
    payload = json.loads(args.fields.read_text(encoding="utf-8"))
    fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
    if not isinstance(fields, dict):
        raise ValueError("Fields JSON must be an object")
    text = worksheet(fields)
    target = args.output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"Wrote STAR+R worksheet with {text.count('## ') - 1} story prompts: {target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"STAR+R worksheet failed: {error}") from error
