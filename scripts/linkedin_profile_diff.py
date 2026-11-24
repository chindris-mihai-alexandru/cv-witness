#!/usr/bin/env python3
"""Alias-aware diff and preview planner for a candidate's LinkedIn export.

This is the cv-witness analogue of LinkedIn's documented
`linkedin_resolve_referenced_entities` and `linkedin_preview_profile_section`.
It is read-only and local-only: it never signs in to LinkedIn, never writes to
a profile, and never treats posting/profile text as instructions.

It compares a locally imported LinkedIn snapshot with the candidate's approved
master sources and reports exact matches, approved aliases, differences and
unmatched entries. An optional private alias file resolves deliberate wording
differences, for example a LinkedIn title and the approved CV title for the
same dated role. A generated preview is a draft for human review, not an
approval envelope and not a write.

Usage:
    python3 scripts/linkedin_profile_diff.py snapshot.json \
        --source foundation.md --provenance provenance.md \
        --json --preview linkedin-update-preview.md

Alias file shape (private, never commit with real data):
    {
      "roles": {"Application Support Specialist": "IT Operations & Support Engineer"},
      "companies": {},
      "projects": {},
      "skills": {}
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

if __package__:
    from .cv_checks import normalized_text
    from .rms_metadata import html_text
    from .check_cv_titles import normal, parse_master
else:
    from cv_checks import normalized_text
    from rms_metadata import html_text
    from check_cv_titles import normal, parse_master


def _years(text: str) -> set[str]:
    return set(re.findall(r"(?:19|20)\d{2}", text or ""))


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normal(text)))


def _normalize_aliases(data: dict | None) -> dict:
    data = data or {}
    result = {}
    for kind in ("roles", "companies", "projects", "skills"):
        value = data.get(kind, {})
        if not isinstance(value, dict):
            raise ValueError(f"alias file key '{kind}' must be an object")
        result[kind] = {normal(k): str(v) for k, v in value.items()}
    return result


def _load_alias_map(path: Path | None) -> dict:
    if path is None:
        return _normalize_aliases({})
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("alias file must be a JSON object")
    return _normalize_aliases(data)


def _fields_from_mapping(fields: dict) -> dict:
    def upper(key: str) -> str:
        for candidate in (key, key.upper()):
            if candidate in fields:
                return str(fields[candidate] or "").strip()
        return ""
    def _clean_skill(part: str) -> str:
        value = " ".join(part.split()).strip(" .:-")
        return re.sub(r"^[A-Za-z][\w /&-]{0,30}:\s*", "", value).strip(" .:-")

    skills = html_text(upper("SKILLS_BLOCK"))
    return {
        "summary": upper("SUMMARY"),
        "role": upper("ROLE"),
        "skills": [clean for part in re.split(r",|;|\n", skills)
                   if (clean := _clean_skill(part))],
    }


def _equivalent(left: str, right: str, aliases: dict) -> bool:
    if not left or not right:
        return False
    left_key = normal(left)
    right_key = normal(right)
    if left_key == right_key:
        return True
    if any(normal(mapped) == right_key or normal(mapped) == left_key
           for bucket in aliases.values() if isinstance(bucket, dict)
           for source, mapped in bucket.items()
           if normal(source) in (left_key, right_key)):
        return True
    return bool(_token_set(left)) and _token_set(left) == _token_set(right)


def _resolve(value: str, aliases: dict, kind: str) -> str:
    return aliases.get(kind, {}).get(normal(value), value)


def parse_source_sections(text: str) -> dict:
    """Parse the small set of private master sections the diff needs."""
    result = {"projects": [], "skills": [], "languages": [], "certifications": []}
    section = ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().casefold()
            continue
        if not line.startswith("- ") or not section:
            continue
        item = line[2:].strip()
        if section.startswith("projects"):
            name = re.split(r"\s+-\s+| \([^)]*\)", item, maxsplit=1)[0].strip()
            if name:
                result["projects"].append(name)
        elif section.startswith("skills"):
            category, _, rest = item.partition(":")
            values = rest if rest else category
            result["skills"].extend(part.strip() for part in re.split(r",|/", values)
                                    if part.strip())
        elif section.startswith("languages"):
            result["languages"].extend(part.strip() for part in item.split("·") if part.strip())
        elif section.startswith("certifications"):
            result["certifications"].append(item)
    return result


def _fields_data(fields_path: Path | None) -> dict:
    if fields_path is None:
        return {}
    payload = json.loads(fields_path.read_text(encoding="utf-8"))
    fields = payload["fields"] if isinstance(payload, dict) and "fields" in payload else payload
    if not isinstance(fields, dict):
        raise ValueError("fields JSON must be an object")
    return _fields_from_mapping(fields)


def analyze(snapshot: dict, source_text: str, provenance_text: str = "",
            aliases: dict | None = None, fields: dict | None = None) -> dict:
    """Return an advisory diff. Never edits, writes or uploads anything."""
    aliases = _normalize_aliases(aliases)
    fields = _fields_from_mapping(fields or {})
    warnings = list(snapshot.get("_meta", {}).get("warnings", []))
    source = parse_source_sections(source_text)
    combined = normalized_text(source_text + "\n" + provenance_text)

    profile = snapshot.get("profile", {}) or {}
    profile_checks = []
    for field, label in (("first_name", "first name"), ("last_name", "last name"),
                         ("headline", "headline"), ("summary", "summary"),
                         ("current_company", "current company")):
        value = str(profile.get(field) or "").strip()
        if not value:
            profile_checks.append({"field": label, "linkedin": None, "status": "missing_in_export"})
        elif normalized_text(value) in combined:
            profile_checks.append({"field": label, "linkedin": value, "status": "present_in_source"})
        else:
            profile_checks.append({"field": label, "linkedin": value, "status": "review_required"})

    company_name = ""
    try:
        company_name, master = parse_master(source_text)
    except ValueError as error:
        master = {}
        warnings.append(f"master role parsing skipped: {error}")

    master_roles = []
    for (company_key, dates), titles in master.items():
        for title in titles:
            master_roles.append({"company": company_name, "company_key": company_key,
                                 "title": title, "dates": dates,
                                 "years": sorted(_years(dates))})

    positions = []
    for position in snapshot.get("positions", []) or []:
        title = str(position.get("title") or "").strip()
        company = str(position.get("company") or "").strip()
        dates = " ".join(str(position.get(key) or "") for key in ("start_date", "end_date"))
        years = sorted(_years(dates))
        candidates = [role for role in master_roles
                      if _equivalent(company, role["company"], aliases)
                      or normal(company) == role["company_key"]]
        if years:
            dated = [role for role in candidates if set(years) & set(role["years"])]
            if dated:
                candidates = dated
        if not candidates:
            status, match = "unmatched", None
        elif len(candidates) > 1:
            status, match = "ambiguous", None
        else:
            match = candidates[0]
            title_target = _resolve(match["title"], aliases, "roles")
            if normal(title) == normal(title_target):
                status = "exact"
            elif _equivalent(title, title_target, aliases):
                status = "alias"
            else:
                status = "title_difference"
        positions.append({
            "linkedin": {"title": title, "company": company, "dates": dates,
                         "location": str(position.get("location") or ""),
                         "source": position.get("_source"), "row": position.get("_row")},
            "cv": match,
            "status": status,
        })

    def compare_named(items, cv_items, kind):
        rows = []
        for item in items:
            name = str((item if isinstance(item, str) else item.get("name")) or "").strip()
            if not name:
                continue
            target = _resolve(name, aliases, kind)
            status = ("present_in_source" if _equivalent(target, name, aliases)
                      and any(_equivalent(target, cv, aliases) for cv in cv_items)
                      else "review_required")
            rows.append({"name": name, "status": status,
                         "source": item.get("_source") if isinstance(item, dict) else None,
                         "row": item.get("_row") if isinstance(item, dict) else None})
        return rows

    projects = compare_named(snapshot.get("projects", []) or [], source["projects"], "projects")
    skills = compare_named(snapshot.get("skills", []) or [], source["skills"], "skills")
    languages = compare_named(snapshot.get("languages", []) or [], source["languages"], "skills")
    education = compare_named(snapshot.get("education", []) or [], source["certifications"], "companies")

    return {
        "profile_context": profile_checks,
        "positions": positions,
        "projects": projects,
        "skills": skills,
        "languages": languages,
        "education": education,
        "proposed_linkedin_draft": {
            "headline": fields.get("role", ""),
            "summary": fields.get("summary", ""),
            "skills": fields.get("skills", []),
        },
        "warnings": warnings,
        "note": ("Advisory local review only. No LinkedIn write, no approval envelope, "
                 "and no claim that a difference is an error."),
    }


def render_preview(report: dict) -> str:
    """Render a private draft. It contains checkboxes, never auto-approval."""
    lines = [
        "# LinkedIn update preview (private draft)",
        "",
        "No changes were applied to LinkedIn. Review each item against your own export "
        "and approve manually in the LinkedIn UI.",
        "",
        "## Profile context",
    ]
    for item in report["profile_context"]:
        value = item.get("linkedin") or "(not in export)"
        lines.append(f"- [ ] {item['field']}: {item['status']} - {value}")
    lines += ["", "## Experience entries"]
    for item in report["positions"]:
        linked = item["linkedin"]
        cv = item.get("cv") or {}
        lines.append(f"- [ ] {item['status']}: {linked.get('title') or '(no title)'} at "
                     f"{linked.get('company') or '(no company)'} "
                     f"(export row {linked.get('row') or '?'})")
        if cv:
            lines.append(f"  - Approved CV title: {cv.get('title') or '(none)'} "
                         f"({cv.get('dates') or 'dates unavailable'})")
    for label in ("projects", "skills", "languages", "education"):
        lines += ["", f"## {label.title()}"]
        for item in report.get(label, []):
            lines.append(f"- [ ] {item['status']}: {item['name']}")
    draft = report.get("proposed_linkedin_draft", {})
    if draft.get("headline") or draft.get("summary") or draft.get("skills"):
        lines += ["", "## Draft wording from approved CV fields", "",
                  "Copy only what you can defend in an interview.", ""]
        if draft.get("headline"):
            lines.append(f"- Headline: {draft['headline']}")
        if draft.get("summary"):
            lines.append(f"- Summary: {draft['summary']}")
        if draft.get("skills"):
            lines.append("- Skills: " + ", ".join(draft["skills"]))
    lines += ["", report["note"], ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Local LinkedIn snapshot JSON")
    parser.add_argument("--source", type=Path, required=True, help="Approved master markdown")
    parser.add_argument("--provenance", type=Path, help="Private provenance markdown")
    parser.add_argument("--aliases", type=Path, help="Private alias JSON")
    parser.add_argument("--fields", type=Path, help="Canonical CV fields JSON for draft wording")
    parser.add_argument("--preview", type=Path, help="Write a private preview markdown")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        source_text = args.source.read_text(encoding="utf-8")
        provenance_text = args.provenance.read_text(encoding="utf-8") if args.provenance else ""
        aliases = _load_alias_map(args.aliases)
        fields = _fields_data(args.fields)
        report = analyze(snapshot, source_text, provenance_text, aliases, fields)
        if args.preview:
            args.preview.parent.mkdir(parents=True, exist_ok=True)
            args.preview.write_text(render_preview(report), encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"linkedin-profile-diff: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for label in ("profile_context", "positions", "projects", "skills", "languages", "education"):
            rows = report[label]
            statuses = {}
            for row in rows:
                statuses[row["status"]] = statuses.get(row["status"], 0) + 1
            print(f"{label}: " + (", ".join(f"{k}={v}" for k, v in sorted(statuses.items())) or "none"))
        for warning in report["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
