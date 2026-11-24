#!/usr/bin/env python3
"""Export canonical CV fields as parser-safe plain text.

This is not another CV design. It reuses the approved field values and emits a
single-column, real-text document with standard section headings. It is useful
as a TXT upload where accepted and as a source for reviewing ATS autofill.
It does not claim that any employer's ATS will parse a document correctly.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

if __package__:
    from .rms_metadata import html_text
else:
    from rms_metadata import html_text


def _span(fragment: str, class_name: str) -> str:
    match = re.search(
        rf'<span\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(.*?)</span>',
        fragment, re.I | re.S)
    return html_text(match.group(1)) if match else ""


def _blocks(value: str) -> list[str]:
    return [line for line in html_text(value).splitlines() if line.strip()]


def plain_text(fields: dict) -> str:
    """Build a deterministic plain-text CV from canonical template fields."""
    name = (fields.get("NAME") or "").strip() or "[NAME]"
    role = (fields.get("ROLE") or "").strip()
    contact = [
        (fields.get("LOCATION") or "").strip(),
        (fields.get("EMAIL") or "").strip(),
        (fields.get("PHONE") or "").strip(),
    ]
    links = []
    for key in ("LINKEDIN_URL", "GITHUB_URL", "SITE_URL", "HUGGINGFACE_URL"):
        value = (fields.get(key) or "").strip()
        if value and value not in links:
            links.append(value)
    contact = [part for part in contact if part]
    if links:
        contact.append(" · ".join(links))

    lines = [name]
    if role:
        lines.append(role)
    if contact:
        lines.append(" · ".join(contact))
    lines.append("")

    def section(title: str, body: list[str]) -> None:
        if not body:
            return
        lines.append(title)
        lines.extend(body)
        lines.append("")

    summary = html_text(fields.get("SUMMARY", ""))
    if fields.get("SUMMARY_2"):
        second = html_text(fields["SUMMARY_2"])
        summary = f"{summary}\n{second}" if summary else second
    section("PROFESSIONAL SUMMARY", [summary] if summary else [])
    section("SKILLS", _blocks(fields.get("SKILLS_BLOCK", "")))

    experience: list[str] = []
    company = (fields.get("COMPANY") or "").strip()
    company_location = (fields.get("COMPANY_LOCATION") or "").strip()
    employer = f"{company} - {company_location}" if company_location else company
    if employer:
        experience.append(employer)
    roles = re.split(r'<div class="role-line">', fields.get("ROLES_BLOCK", ""))[1:]
    for fragment in roles:
        head, _, rest = fragment.partition("</div>")
        role = _span(head, "title")
        dates = _span(head, "dates")
        line = f"{role} - {dates}" if role and dates else role or dates
        if line:
            experience.append(line)
        experience.extend(_blocks(rest))
    section("PROFESSIONAL EXPERIENCE", experience)

    projects: list[str] = []
    for fragment in re.split(r'<div class="project">', fields.get("PROJECTS_BLOCK", ""))[1:]:
        title = _span(fragment, "proj-name")
        meta = _span(fragment, "meta")
        dates = _span(fragment, "dates")
        header = " - ".join(part for part in (title, meta.lstrip("- "), dates) if part)
        if header:
            projects.append(header)
        live = re.search(r'<div class="live-line">(.*?)</div>', fragment, re.S | re.I)
        if live:
            projects.append(html_text(live.group(1)))
        projects.extend(_blocks("".join(re.findall(r"<li[^>]*>(.*?)</li>", fragment, re.S | re.I))))
    section("PROJECTS", projects)
    section("CERTIFICATIONS", _blocks(fields.get("CERTS_BLOCK", "")))
    section("EDUCATION", _blocks(fields.get("EDUCATION_BLOCK", "")))

    languages = (fields.get("LANGUAGES_ONE_LINE") or "").strip()
    section("LANGUAGES", [html_text(languages)] if languages else [])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields", type=Path, required=True, help="Canonical CV fields JSON")
    parser.add_argument("--output", type=Path, help="TXT destination; omit for stdout")
    args = parser.parse_args()

    payload = json.loads(args.fields.expanduser().read_text(encoding="utf-8"))
    fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
    if not isinstance(fields, dict):
        raise ValueError("Fields JSON must be an object")
    text = plain_text(fields)
    if args.output:
        target = args.output.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"Wrote parser-safe text: {target}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"ATS text export failed: {error}") from error
