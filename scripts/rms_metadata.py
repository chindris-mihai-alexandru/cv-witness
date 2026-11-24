#!/usr/bin/env python3
"""Write and verify Rezi Resume Metadata Standard (RMS) v2 XMP in a PDF.

The upstream standard is a set of XMP keys plus a C++ reader; it has no
machine-readable template file. This module derives the vocabulary from the
upstream ExifTool config, exposes it with ``--print-template``, and attaches a
minimal packet to a PDF using an incremental update. Incremental updates keep
the original page bytes untouched, so the visible layout cannot change.

The metadata is supplemental. No public evidence shows that Workday,
Greenhouse or other ATS vendors consume RMS, and Rezi's own tests lost data.
Do not treat an RMS check as an ATS score or a parsing guarantee.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape

PRODUCER = "rms_v2.0.1"
SCHEMA_URL = "https://github.com/rezi-io/resume-standard"
XMP_NS = "https://github.com/rezi-io/resume-standard"
PDF_NS = "http://ns.adobe.com/pdf/1.3/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NA = "n/a"
MAX_INDEX = 15

CONTACT_FIELDS = (
    "behance", "city", "country", "countryCode", "dribble", "email",
    "fullName", "github", "givenNames", "lastName", "linkedin", "phone",
    "state", "website",
)
SECTION_FIELDS = {
    "experience": (
        "company", "dateBegin", "dateBeginFormat", "dateBeginTS", "dateEnd",
        "dateEndFormat", "dateEndTS", "description", "isCurrent", "location",
        "role",
    ),
    "education": (
        "date", "dateFormat", "dateTS", "description", "institution",
        "isGraduate", "location", "minor", "qualification", "score",
        "scoreType",
    ),
    "certification": (
        "date", "dateFormat", "dateTS", "department", "description", "name",
    ),
    "coursework": (
        "date", "dateFormat", "dateTS", "department", "description", "name",
        "skill",
    ),
    "involvement": (
        "dateBegin", "dateBeginFormat", "dateBeginTS", "dateEnd",
        "dateEndFormat", "dateEndTS", "description", "location",
        "organization", "role",
    ),
    "project": (
        "dateBegin", "dateBeginFormat", "dateBeginTS", "dateEnd",
        "dateEndFormat", "dateEndTS", "description", "organization", "role",
        "title", "url",
    ),
    "skill": ("category", "keywords"),
    "publication": (
        "date", "dateFormat", "dateTS", "description", "organization", "role",
        "title", "type",
    ),
    "award": (
        "date", "dateFormat", "dateTS", "description", "organization",
        "title",
    ),
    "reference": (
        "email", "name", "organization", "phone", "role", "type",
    ),
}
COUNT_SECTIONS = tuple(SECTION_FIELDS)
TEMPLATE_KEYS = frozenset(
    ["rms_schema_details", "rms_summary"]
    + [f"rms_contact_{field}" for field in CONTACT_FIELDS]
    + [f"rms_{section}_count" for section in COUNT_SECTIONS]
    + [
        f"rms_{section}_{index}_{field}"
        for section, fields in SECTION_FIELDS.items()
        for index in range(MAX_INDEX + 1)
        for field in fields
    ]
)


def validate_payload(payload: dict[str, str]) -> list[str]:
    """Return RMS schema errors; an empty list means the payload is well-formed."""
    errors: list[str] = []
    for key, value in payload.items():
        if key not in TEMPLATE_KEYS:
            errors.append(f"unknown key: {key}")
            continue
        text = str(value)
        if key == "rms_schema_details" and text != SCHEMA_URL:
            errors.append("rms_schema_details must point to the upstream schema URL")
        elif key.endswith("_count"):
            if not text.isdigit() or not 0 <= int(text) <= MAX_INDEX + 1:
                errors.append(f"{key} must be an integer from 0 to {MAX_INDEX + 1}")
        elif key.endswith("TS"):
            if text != NA and not (text.isdigit() and int(text) >= 0):
                errors.append(f"{key} must be n/a or a non-negative Unix millisecond timestamp")
        elif key.rsplit("_", 1)[-1] in {"isCurrent", "isGraduate"}:
            if text not in {"true", "false", NA}:
                errors.append(f"{key} must be true, false or n/a")
        elif key.endswith("Format") and text not in {NA, "YYYY", "MMMM YYYY", "MMM YYYY", "MM/YYYY"}:
            errors.append(f"{key} has an unsupported date format: {text}")
    counts = {key: int(payload[key]) for key in payload
              if key.endswith("_count") and str(payload[key]).isdigit()}
    for key, value in payload.items():
        if str(value) == NA or not key.startswith("rms_"):
            continue
        match = re.match(r"rms_([a-z]+)_(\d+)_", key)
        if not match:
            continue
        count = counts.get(f"rms_{match.group(1)}_count")
        if count is not None and int(match.group(2)) >= count:
            errors.append(f"{key} has an index outside rms_{match.group(1)}_count={count}")
    return errors


def template_payload() -> dict[str, str]:
    """Return the full RMS v2 key vocabulary with synthetic empty values."""
    payload = {"rms_schema_details": SCHEMA_URL, "rms_summary": NA}
    for field in CONTACT_FIELDS:
        payload[f"rms_contact_{field}"] = NA
    for section in COUNT_SECTIONS:
        payload[f"rms_{section}_count"] = "0"
    for section, fields in SECTION_FIELDS.items():
        for index in range(MAX_INDEX + 1):
            for field in fields:
                payload[f"rms_{section}_{index}_{field}"] = NA
    return payload


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n• ")
        elif tag in {"br", "p", "div", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"li", "p", "div"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_text(fragment: str) -> str:
    parser = _TextExtractor()
    parser.feed(fragment or "")
    lines = []
    for line in "".join(parser.parts).replace("\xa0", " ").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _split_divs(fragment: str, class_name: str) -> list[str]:
    """Split top-level divs with a given class without a DOM dependency."""
    out: list[str] = []
    pattern = re.compile(rf'<div\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>', re.I)
    for match in pattern.finditer(fragment or ""):
        start = match.end()
        depth = 1
        pos = start
        while pos < len(fragment) and depth:
            opening = re.compile(r"<div\b", re.I).search(fragment, pos)
            closing = re.compile(r"</div\s*>", re.I).search(fragment, pos)
            if closing is None:
                break
            if opening is not None and opening.start() < closing.start():
                depth += 1
                pos = opening.end()
            else:
                depth -= 1
                pos = closing.end()
                if depth == 0:
                    out.append(fragment[start:closing.start()])
    return out


def _attr(fragment: str, tag: str, attr: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*\b{attr}=\"([^\"]*)\"", fragment, re.I)
    return match.group(1) if match else ""


def _span_text(fragment: str, class_name: str) -> str:
    match = re.search(
        rf'<span\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(.*?)</span>',
        fragment, re.I | re.S,
    )
    return html_text(match.group(1)) if match else ""


span_text = _span_text
split_divs = _split_divs


def _date_parts(value: str) -> tuple[str, str, str]:
    """Return display date, Unix-millisecond timestamp, and date format."""
    text = (value or "").strip()
    if not text or text.lower() in {"present", "current", "n/a"}:
        return text or NA, NA, "n/a"
    match = re.search(r"(\d{4})", text)
    if not match:
        return text, NA, "n/a"
    year = int(match.group(1))
    month_match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
    month = 1
    date_format = "YYYY"
    if month_match:
        month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                 "Sep", "Oct", "Nov", "Dec"].index(month_match.group(1).title()) + 1
        date_format = "MMM YYYY" if len(month_match.group(1)) == 3 else "MMMM YYYY"
    else:
        numeric = re.search(r"\b(\d{1,2})/(\d{4})\b", text)
        if numeric:
            month = int(numeric.group(1))
            year = int(numeric.group(2))
            date_format = "MM/YYYY"
    timestamp = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return text, str(timestamp), date_format


def _split_range(value: str) -> tuple[str, str]:
    parts = re.split(r"\s+(?:-|–|—|to)\s+", (value or "").strip(), maxsplit=1)
    return parts[0] if parts else "", parts[1] if len(parts) > 1 else ""


def _set_item(payload: dict[str, str], section: str, index: int, field: str, value) -> None:
    if section in SECTION_FIELDS and field in SECTION_FIELDS[section]:
        payload[f"rms_{section}_{index}_{field}"] = str(value if value not in (None, "") else NA)


def payload_from_fields(fields: dict) -> dict[str, str]:
    """Build an RMS payload from the canonical CV fields JSON."""
    explicit = fields.get("RMS") or fields.get("RMS_METADATA")
    if explicit is not None:
        if not isinstance(explicit, dict):
            raise ValueError("RMS metadata must be a JSON object")
        payload = {str(key): str(value) for key, value in explicit.items()}
        unknown = sorted(set(payload) - TEMPLATE_KEYS)
        if unknown:
            raise ValueError(f"Unknown RMS keys: {', '.join(unknown[:8])}")
        result = {"rms_schema_details": SCHEMA_URL}
        result.update(payload)
        return result

    payload = {"rms_schema_details": SCHEMA_URL}
    name = (fields.get("NAME") or "").strip()
    given, _, family = name.partition(" ")
    location = (fields.get("LOCATION") or "").strip()
    city, _, country = location.partition(",")
    contact = {
        "fullName": name,
        "givenNames": given,
        "lastName": family,
        "email": fields.get("EMAIL", ""),
        "phone": fields.get("PHONE", fields.get("PHONE_DIGITS", "")),
        "linkedin": fields.get("LINKEDIN_URL", ""),
        "github": fields.get("GITHUB_URL", ""),
        "website": fields.get("SITE_URL", ""),
        "city": city.strip(),
        "country": country.strip(),
        "countryCode": fields.get("COUNTRY_CODE", ""),
        "state": fields.get("STATE", ""),
        "behance": fields.get("BEHANCE_URL", ""),
        "dribble": fields.get("DRIBBBLE_URL", ""),
    }
    for field, value in contact.items():
        payload[f"rms_contact_{field}"] = str(value).strip() or NA
    payload["rms_summary"] = (fields.get("SUMMARY") or "").strip() or NA

    company = (fields.get("COMPANY") or "").strip() or NA
    company_location = (fields.get("COMPANY_LOCATION") or "").strip() or NA
    roles = []
    for fragment in re.split(r'<div class="role-line">', fields.get("ROLES_BLOCK", ""))[1:]:
        head, _, rest = fragment.partition("</div>")
        role = _span_text(head, "title")
        dates = _span_text(head, "dates")
        bullets = html_text(rest)
        roles.append((role, dates, bullets))
    for index, (role, dates, bullets) in enumerate(roles[:MAX_INDEX + 1]):
        begin, end = _split_range(dates)
        begin_value, begin_ts, begin_format = _date_parts(begin)
        end_value, end_ts, end_format = _date_parts(end)
        values = {
            "company": company,
            "location": company_location,
            "role": role or NA,
            "dateBegin": begin_value,
            "dateBeginTS": begin_ts,
            "dateBeginFormat": begin_format,
            "dateEnd": end_value,
            "dateEndTS": end_ts,
            "dateEndFormat": end_format,
            "isCurrent": "true" if end.lower() in {"present", "current"} else "false",
            "description": bullets or NA,
        }
        for field, value in values.items():
            _set_item(payload, "experience", index, field, value)
    payload["rms_experience_count"] = str(min(len(roles), MAX_INDEX + 1))

    projects = _split_divs(fields.get("PROJECTS_BLOCK", ""), "project")
    for index, fragment in enumerate(projects[:MAX_INDEX + 1]):
        values = {
            "title": _span_text(fragment, "proj-name") or NA,
            "url": _attr(fragment, "a", "href") or NA,
            "description": html_text(fragment) or NA,
            "organization": NA,
            "role": NA,
        }
        dates = _span_text(fragment, "dates")
        begin, end = _split_range(dates)
        begin_value, begin_ts, begin_format = _date_parts(begin or dates)
        values.update({
            "dateBegin": begin_value,
            "dateBeginTS": begin_ts,
            "dateBeginFormat": begin_format,
            "dateEnd": end or NA,
            "dateEndTS": NA,
            "dateEndFormat": "n/a",
        })
        for field, value in values.items():
            _set_item(payload, "project", index, field, value)
    payload["rms_project_count"] = str(min(len(projects), MAX_INDEX + 1))

    education = re.findall(r"<p[^>]*>(.*?)</p>", fields.get("EDUCATION_BLOCK", ""), re.S | re.I)
    for index, fragment in enumerate(education[:MAX_INDEX + 1]):
        parts = [part.strip() for part in html_text(fragment).split(",") if part.strip()]
        qualification = parts[0] if parts else NA
        institution = parts[1] if len(parts) > 1 else NA
        date = parts[-1] if len(parts) > 2 else NA
        date_value, date_ts, date_format = _date_parts(date)
        values = {
            "qualification": qualification,
            "institution": institution,
            "date": date_value,
            "dateTS": date_ts,
            "dateFormat": date_format,
            "isGraduate": "true",
            "description": NA,
            "location": NA,
            "minor": NA,
            "score": NA,
            "scoreType": NA,
        }
        for field, value in values.items():
            _set_item(payload, "education", index, field, value)
    payload["rms_education_count"] = str(min(len(education), MAX_INDEX + 1))

    certs = re.findall(r"<li[^>]*>(.*?)</li>", fields.get("CERTS_BLOCK", ""), re.S | re.I)
    if not certs:
        certs = re.findall(r"<p[^>]*>(.*?)</p>", fields.get("CERTS_BLOCK", ""), re.S | re.I)
    for index, fragment in enumerate(certs[:MAX_INDEX + 1]):
        text = html_text(fragment) or NA
        _set_item(payload, "certification", index, "name", text)
        _set_item(payload, "certification", index, "description", text)
        _set_item(payload, "certification", index, "department", NA)
        date_value, date_ts, date_format = _date_parts(text)
        _set_item(payload, "certification", index, "date", date_value)
        _set_item(payload, "certification", index, "dateTS", date_ts)
        _set_item(payload, "certification", index, "dateFormat", date_format)
    payload["rms_certification_count"] = str(min(len(certs), MAX_INDEX + 1))

    skills = []
    for fragment in re.findall(r"<p[^>]*>(.*?)</p>", fields.get("SKILLS_BLOCK", ""), re.S | re.I):
        text = html_text(fragment)
        if not text:
            continue
        category, separator, keywords = text.partition(":")
        skills.append((category.strip() if separator else "Skills", (keywords if separator else text).strip()))
    languages = (fields.get("LANGUAGES_ONE_LINE") or "").strip()
    if languages:
        skills.append(("Languages", languages))
    for index, (category, keywords) in enumerate(skills[:MAX_INDEX + 1]):
        _set_item(payload, "skill", index, "category", category or NA)
        _set_item(payload, "skill", index, "keywords", keywords or NA)
    payload["rms_skill_count"] = str(min(len(skills), MAX_INDEX + 1))

    for section in COUNT_SECTIONS:
        payload.setdefault(f"rms_{section}_count", "0")
    return payload


def _clean_value(value) -> str:
    text = str(value)
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    return text.replace("\r", " ").strip()


def build_xmp(payload: dict[str, str]) -> bytes:
    """Build a deterministic, schema-validated XMP packet for an RMS payload."""
    errors = validate_payload(payload)
    if errors:
        raise ValueError("Invalid RMS payload: " + "; ".join(errors[:8]))
    clean = {}
    for key, value in payload.items():
        if key == "producer":
            continue
        clean[key] = _clean_value(value)
    clean["rms_schema_details"] = clean.get("rms_schema_details") or SCHEMA_URL
    lines = [
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>',
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="cv-witness RMS writer">',
        f'<rdf:RDF xmlns:rdf="{RDF_NS}">',
        ' <rdf:Description rdf:about="" '
        f'xmlns:pdf="{PDF_NS}">',
        f"  <pdf:Producer>{PRODUCER}</pdf:Producer>",
        " </rdf:Description>",
        f' <rdf:Description rdf:about="" xmlns:rms="{XMP_NS}">',
        f"  <rms:producer>{PRODUCER}</rms:producer>",
    ]
    for key in sorted(clean):
        lines.append(f"  <rms:{key}>{escape(clean[key])}</rms:{key}>")
    lines.extend([" </rdf:Description>", "</rdf:RDF>", "</x:xmpmeta>", '<?xpacket end="w"?>'])
    return ("\n".join(lines) + "\n").encode("utf-8")


def read_xmp(data: bytes) -> dict[str, str]:
    """Read RMS keys from a PDF's XMP packet using only the standard library."""
    matches = re.findall(rb"<x:xmpmeta\b.*?</x:xmpmeta>", data, re.S)
    if not matches:
        raise ValueError("No XMP packet found")
    root = ET.fromstring(matches[-1])
    result: dict[str, str] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name.startswith("rms_") or name in {"producer", "Producer"}:
            result[name] = "".join(element.itertext())
    return result


def _last_startxref(data: bytes) -> int:
    matches = list(re.finditer(rb"startxref\s+(\d+)", data))
    if not matches:
        raise ValueError("PDF has no startxref")
    return int(matches[-1].group(1))


def _trailer_dict(data: bytes) -> dict[str, str]:
    start = data.rfind(b"trailer")
    if start == -1:
        raise ValueError("PDF has no classic trailer (xref streams unsupported)")
    end = data.find(b">>", start)
    if end == -1:
        raise ValueError("Malformed PDF trailer")
    block = data[start:end].decode("latin-1")
    result = {}
    for key in ("Root", "Info", "Size"):
        match = re.search(rf"/{key}\s+(\d+)", block)
        if match:
            result[key] = match.group(1)
    if re.search(r"/Encrypt\s+\d+\s+\d+\s+R", block):
        result["Encrypt"] = "yes"
    id_match = re.search(r"/ID\s*\[\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block)
    if id_match:
        result["ID1"] = id_match.group(1)
        result["ID2"] = id_match.group(2)
    if "Root" not in result:
        raise ValueError("PDF trailer has no /Root")
    return result


def _object_span(data: bytes, number: int) -> tuple[int, int]:
    matches = list(re.finditer(rb"(?<!\d)" + str(number).encode("ascii") + rb"\s+0\s+obj\b", data))
    if not matches:
        raise ValueError(f"PDF object {number} not found")
    start = matches[-1].start()
    end = data.find(b"endobj", matches[-1].end())
    if end == -1:
        raise ValueError(f"PDF object {number} has no endobj")
    return start, end + len(b"endobj")


def _catalog_with_metadata(data: bytes, root: int, metadata_id: int) -> bytes:
    start, end = _object_span(data, root)
    obj = data[start:end].decode("latin-1")
    if "/Metadata" in obj:
        updated = re.sub(r"/Metadata\s+\d+\s+0\s+R", f"/Metadata {metadata_id} 0 R", obj, count=1)
    else:
        close = obj.rfind(">>")
        if close == -1:
            raise ValueError("Catalog object has no dictionary")
        updated = obj[:close] + f" /Metadata {metadata_id} 0 R " + obj[close:]
    return updated.encode("latin-1")


def inject_xmp(pdf_path: Path, output: Path, payload: dict[str, str]) -> dict[str, object]:
    """Append an RMS XMP object via a PDF incremental update."""
    data = pdf_path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Not a PDF file")
    # Check the object at startxref, not arbitrary content streams that might
    # contain the literal text "/Type /XRef".
    old_start = _last_startxref(data)
    xref_head = data[old_start:old_start + 80]
    if re.search(rb"/Type\s*/XRef", xref_head):
        raise ValueError("PDF xref streams are not supported")
    try:
        read_xmp(data)
    except ValueError:
        pass
    else:
        raise ValueError("PDF already has an XMP packet; re-render a clean source PDF")
    trailer = _trailer_dict(data)
    if "Encrypt" in trailer:
        raise ValueError("Encrypted PDFs are not supported")
    root = int(trailer["Root"])
    object_ids = [int(match.group(1)) for match in re.finditer(rb"(?m)(\d+)\s+0\s+obj\b", data)]
    max_id = max(object_ids + [int(trailer.get("Size", "0")) - 1, root])
    metadata_id = max_id + 1
    xmp = build_xmp(payload)
    catalog = _catalog_with_metadata(data, root, metadata_id)

    additions = bytearray()
    metadata_offset = len(data) + len(additions)
    additions += (
        f"{metadata_id} 0 obj\n<< /Type /Metadata /Subtype /XML /Length {len(xmp)} >>\nstream\n"
    ).encode("latin-1")
    additions += xmp + b"endstream\nendobj\n"
    catalog_offset = len(data) + len(additions)
    additions += catalog + b"\n"
    xref_offset = len(data) + len(additions)
    ids = sorted([(root, catalog_offset), (metadata_id, metadata_offset)])
    additions += f"xref\n{ids[0][0]} 1\n{ids[0][1]:010d} 00000 n \n".encode("latin-1")
    additions += f"{ids[1][0]} 1\n{ids[1][1]:010d} 00000 n \n".encode("latin-1")
    info = f" /Info {trailer['Info']} 0 R" if "Info" in trailer else ""
    id_block = (
        f" /ID [<{trailer['ID1']}><{trailer['ID2']}>]".format(**trailer)
        if "ID1" in trailer else ""
    )
    additions += (
        f"trailer\n<< /Size {metadata_id + 1} /Root {root} 0 R{info}{id_block} "
        f"/Prev {old_start} >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")

    result = data + bytes(additions)
    # Self-verification before writing: the original bytes must be preserved,
    # the xref pointer must land on the new xref, and the XMP must round-trip.
    if not result.startswith(data):
        raise ValueError("Incremental update did not preserve original PDF bytes")
    if not result[xref_offset:].startswith(b"xref"):
        raise ValueError("startxref does not point to the new xref section")
    read_back = read_xmp(result)
    if read_back.get("producer") != PRODUCER:
        raise ValueError("XMP producer did not round-trip")
    for key in ("rms_experience_count", "rms_education_count", "rms_skill_count"):
        if key in payload and read_back.get(key) != str(payload[key]):
            raise ValueError(f"XMP key {key} did not round-trip")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    return {
        "status": "ok",
        "producer": PRODUCER,
        "keys": len(payload),
        "metadata_object": metadata_id,
        "output": str(output),
    }


def load_fields(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "fields" in payload:
        payload = payload["fields"]
    if not isinstance(payload, dict):
        raise ValueError("Fields JSON must be an object")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Input PDF")
    parser.add_argument("--fields", type=Path, help="Canonical CV fields JSON")
    parser.add_argument("--metadata", type=Path, help="Explicit RMS key/value JSON")
    parser.add_argument("--output", type=Path, help="Output PDF (must differ from input)")
    parser.add_argument("--in-place", action="store_true", help="Replace input atomically")
    parser.add_argument("--verify", action="store_true", help="Verify RMS metadata in a PDF")
    parser.add_argument("--print-template", action="store_true", help="Print full RMS v2 key template")
    args = parser.parse_args(argv)

    if args.print_template:
        print(json.dumps(template_payload(), indent=2, sort_keys=True))
        return 0
    if args.verify:
        if not args.pdf:
            parser.error("--verify requires --pdf")
        metadata = read_xmp(args.pdf.read_bytes())
        summary = {
            "status": "ok" if metadata.get("producer") == PRODUCER else "missing",
            "producer": metadata.get("producer", NA),
            "schema": metadata.get("rms_schema_details", NA),
            "experience_count": metadata.get("rms_experience_count", NA),
            "education_count": metadata.get("rms_education_count", NA),
            "project_count": metadata.get("rms_project_count", NA),
            "skill_count": metadata.get("rms_skill_count", NA),
            "keys": len(metadata),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if summary["status"] == "ok" else 1
    if not args.pdf or not (args.fields or args.metadata):
        parser.error("writing requires --pdf and either --fields or --metadata")
    if not args.output and not args.in_place:
        parser.error("writing requires --output or --in-place")

    if args.metadata:
        explicit = json.loads(args.metadata.read_text(encoding="utf-8"))
        if not isinstance(explicit, dict):
            raise ValueError("Metadata JSON must be an object")
        payload = {"rms_schema_details": SCHEMA_URL}
        payload.update({str(key): str(value) for key, value in explicit.items()})
    else:
        payload = payload_from_fields(load_fields(args.fields))
    if args.in_place:
        target = args.pdf.resolve()
        with tempfile.NamedTemporaryFile(prefix="cv-witness-rms-", suffix=".pdf",
                                         dir=target.parent, delete=False) as handle:
            temp = Path(handle.name)
        try:
            inject_xmp(args.pdf, temp, payload)
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()
        destination = target
    else:
        destination = args.output.resolve()
        if destination == args.pdf.resolve():
            parser.error("use --in-place to overwrite the input")
        result = inject_xmp(args.pdf, destination, payload)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(json.dumps({"status": "ok", "output": str(destination), "keys": len(payload)},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError) as error:
        raise SystemExit(f"RMS metadata failed: {error}") from error
