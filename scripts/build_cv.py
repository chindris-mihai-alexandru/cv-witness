#!/usr/bin/env python3
"""Build a checked CV from approved structured wording; lanes only reorder sections."""

import argparse
import html
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit

if __package__:
    from .cv_checks import CheckError, CheckFailure, MARKER, MAX_BYTES
    from .render_cv import render_html
else:
    from cv_checks import CheckError, CheckFailure, MARKER, MAX_BYTES
    from render_cv import render_html

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ("summary", "skills", "experience", "projects", "education", "certifications", "publications", "languages")
HEADINGS = dict(zip(SECTIONS, ("Professional Summary", "Skills", "Professional Experience", "Projects", "Education", "Certifications", "Publications", "Languages")))
LANES = {
    "engineering": SECTIONS,
    "operations": ("summary", "experience", "skills", "certifications", "projects", "education", "publications", "languages"),
    "research": ("summary", "education", "experience", "publications", "projects", "skills", "certifications", "languages"),
    "management": ("summary", "experience", "projects", "skills", "education", "certifications", "publications", "languages"),
}


def object_fields(value, allowed, required=(), location="document"):
    if not isinstance(value, dict):
        raise CheckError(location + " must be an object.")
    if set(value) - set(allowed):
        raise CheckError(location + " has unknown fields; review the version-1 input contract.")
    if set(required) - set(value):
        raise CheckError(location + " lacks a required field.")


def text(value, location, optional=False):
    if optional and value == "":
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > 8000:
        raise CheckError(location + " must be a nonempty string within 8,000 characters.")
    if any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise CheckError(location + " contains a control character or invalid Unicode.")
    if MARKER.search(value):
        raise CheckError(location + " contains an unresolved fill/template marker.")
    return unicodedata.normalize("NFC", value.strip())


def collection(value, location, minimum=0, maximum=200):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise CheckError(location + " must be a list within the supported entry limits.")
    return value


def link(value, location):
    value = text(value, location)
    if any(c.isspace() for c in value):
        raise CheckError(location + " URL cannot contain whitespace.")
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in {"http", "https", "mailto", "tel"}
        if parsed.scheme in {"http", "https"}:
            valid = valid and bool(parsed.hostname) and not parsed.username and not parsed.password
            _ = parsed.port
        elif parsed.scheme in {"mailto", "tel"}:
            valid = valid and bool(parsed.path) and not parsed.netloc
    except ValueError as error:
        raise CheckError(location + " URL is invalid.") from error
    if not valid:
        raise CheckError(location + " URL needs an explicit HTTP(S), mailto or tel scheme.")
    return value


def validate_document(data):
    object_fields(data, ("schema_version", "header", "note", *SECTIONS), ("schema_version", "header"))
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise CheckError("Structured input needs integer schema_version 1.")
    header = data["header"]
    object_fields(header, ("name", "role", "contacts"), ("name",), "header")
    result = {"schema_version": 1, "header": {"name": text(header["name"], "header.name")}}
    if "role" in header:
        result["header"]["role"] = text(header["role"], "header.role", optional=True)
    contacts = []
    for entry in collection(header.get("contacts", []), "header.contacts", maximum=12):
        object_fields(entry, ("label", "value", "url"), ("label", "value"), "contact")
        contact = {"label": text(entry["label"], "contact.label"), "value": text(entry["value"], "contact.value")}
        if "url" in entry:
            contact["url"] = link(entry["url"], "contact.url")
        contacts.append(contact)
    result["header"]["contacts"] = contacts
    if "note" in data:
        text(data["note"], "note")
    if "summary" in data:
        result["summary"] = text(data["summary"], "summary", optional=True)
    for section in ("education", "certifications", "languages"):
        result[section] = [text(entry, section) for entry in collection(data.get(section, []), section)]
    result["skills"] = []
    for entry in collection(data.get("skills", []), "skills"):
        object_fields(entry, ("category", "text"), ("category", "text"), "skill")
        result["skills"].append({"category": text(entry["category"], "skill.category"), "text": text(entry["text"], "skill.text")})
    result["experience"] = []
    for employer in collection(data.get("experience", []), "experience"):
        object_fields(employer, ("employer", "location", "roles"), ("employer", "roles"), "experience entry")
        entry = {"employer": text(employer["employer"], "experience.employer"), "location": text(employer.get("location", ""), "experience.location", optional=True), "roles": []}
        for role in collection(employer["roles"], "experience.roles", minimum=1):
            object_fields(role, ("title", "dates", "bullets"), ("title", "dates", "bullets"), "role")
            entry["roles"].append({"title": text(role["title"], "role.title"), "dates": text(role["dates"], "role.dates"), "bullets": [text(bullet, "role.bullet") for bullet in collection(role["bullets"], "role.bullets", minimum=1)]})
        result["experience"].append(entry)
    result["projects"] = []
    for project in collection(data.get("projects", []), "projects"):
        object_fields(project, ("name", "description", "dates", "url", "bullets"), ("name", "bullets"), "project")
        entry = {"name": text(project["name"], "project.name"), "bullets": [text(b, "project.bullet") for b in collection(project["bullets"], "project.bullets", minimum=1)]}
        for field in ("description", "dates"):
            entry[field] = text(project.get(field, ""), "project." + field, optional=True)
        if "url" in project:
            entry["url"] = link(project["url"], "project.url")
        result["projects"].append(entry)
    result["publications"] = []
    for publication in collection(data.get("publications", []), "publications"):
        object_fields(publication, ("citation", "url"), ("citation",), "publication")
        entry = {"citation": text(publication["citation"], "publication.citation")}
        if "url" in publication:
            entry["url"] = link(publication["url"], "publication.url")
        result["publications"].append(entry)
    if not any(result.get(section) for section in SECTIONS):
        raise CheckError("Provide at least one nonempty CV section.")
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckError("Duplicate JSON key in the structured input.")
        result[key] = value
    return result


def load_document(path):
    path = Path(path).expanduser()
    if path.suffix.lower() != ".json" or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise CheckError("Select a structured JSON document within 16 MiB.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeError, RecursionError) as error:
        raise CheckError("Structured CV input must be valid UTF-8 JSON.") from error
    return validate_document(data)


def build_html(data, lane="engineering", section_order=None):
    data = validate_document(data)
    if lane not in LANES:
        raise CheckError("Choose engineering, operations, research or management.")
    active = {section for section in SECTIONS if data.get(section)}
    order = list(section_order) if section_order is not None else [section for section in LANES[lane] if section in active]
    if set(order) != active or len(order) != len(active):
        raise CheckError("Section order must contain every nonempty section exactly once.")
    expected = []

    def escaped(value):
        expected.append(value)
        return html.escape(value, quote=True)

    def anchor(value, url=None):
        visible = escaped(value)
        return '<a href="' + html.escape(url, quote=True) + '">' + visible + '</a>' if url else visible

    header = data["header"]
    content = ["<header><h1>" + escaped(header["name"]) + "</h1>"]
    if header.get("role"):
        content.append('<p class="role">' + escaped(header["role"]) + "</p>")
    if header["contacts"]:
        values = [escaped(entry["label"]) + ": " + anchor(entry["value"], entry.get("url")) for entry in header["contacts"]]
        content.append('<p class="contact">' + " · ".join(values) + "</p>")
    content.append("</header>")
    for section in order:
        content.append('<section id="' + section + '"><h2>' + escaped(HEADINGS[section]) + "</h2>")
        entries = data[section]
        if section == "summary":
            content.append("<p>" + escaped(entries) + "</p>")
        elif section == "skills":
            for entry in entries:
                content.append("<p><strong>" + escaped(entry["category"]) + ":</strong> " + escaped(entry["text"]) + "</p>")
        elif section == "experience":
            for entry in entries:
                label = escaped(entry["employer"]) + (" · " + escaped(entry["location"]) if entry["location"] else "")
                for index, role in enumerate(entry["roles"]):
                    content.append('<div class="entry"><h3>' + (label + "<br>" if index == 0 else "") + escaped(role["title"]) + "</h3>")
                    content.append('<p class="metadata">' + escaped(role["dates"]) + "</p><ul>")
                    content.extend("<li>" + escaped(bullet) + "</li>" for bullet in role["bullets"])
                    content.append("</ul></div>")
        elif section == "projects":
            for entry in entries:
                content.append('<div class="entry"><h3>' + escaped(entry["name"]) + "</h3>")
                for field in ("description", "dates"):
                    if entry[field]:
                        content.append("<p>" + escaped(entry[field]) + "</p>")
                if entry.get("url"):
                    content.append("<p>" + anchor(entry["url"], entry["url"]) + "</p>")
                content.append("<ul>")
                content.extend("<li>" + escaped(bullet) + "</li>" for bullet in entry["bullets"])
                content.append("</ul></div>")
        elif section == "publications":
            content.extend('<p class="compact">' + anchor(entry["citation"], entry.get("url")) + "</p>" for entry in entries)
        else:
            content.extend("<p>" + escaped(entry) + "</p>" for entry in entries)
        content.append("</section>")
    shell = (ROOT / "templates" / "structured.html").read_text(encoding="utf-8")
    if set(re.findall(r"\{\{([A-Z_]+)\}\}", shell)) != {"TITLE", "CONTENT"}:
        raise CheckError("Structured shell has an invalid placeholder contract.")
    source = shell.replace("{{TITLE}}", html.escape(header["name"] + " - CV", quote=True)).replace("{{CONTENT}}", "\n".join(content))
    return source, list(dict.fromkeys(expected)), order


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Approved structured JSON")
    parser.add_argument("output", help="Checked PDF output")
    parser.add_argument("--lane", choices=tuple(LANES), default="engineering")
    parser.add_argument("--paper", choices=("a4", "letter"), default="a4")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--section-order", help="Comma-separated keys; must include every nonempty section")
    parser.add_argument("--posting")
    parser.add_argument("--overlap-policy", choices=("strict", "review"), default="strict")
    parser.add_argument("--browser")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no-sandbox", action="store_true", help="Only for an already isolated CI/container")
    args = parser.parse_args(argv)
    try:
        source, expected, order = build_html(load_document(args.input), args.lane,
                                            args.section_order.split(",") if args.section_order is not None else None)
        report = render_html(source, args.output, args.paper, args.max_pages, expected,
                             args.posting, args.overlap_policy, args.browser, args.replace, args.no_sandbox)
        report["lane"] = args.lane
        report["section_order"] = order
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except CheckFailure as error:
        print(json.dumps(error.report, ensure_ascii=False, indent=2))
        return 1
    except (CheckError, OSError, UnicodeError, RecursionError) as error:
        print("build-cv: " + (str(error) if isinstance(error, CheckError) else "Local input/output operation failed."), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
