#!/usr/bin/env python3
"""Import a candidate's own LinkedIn Data Export into a local snapshot.

This is the cv-witness analogue of LinkedIn's documented
`linkedin_get_profile_context`: read-only, member-owned, local-only. It never
signs in to LinkedIn, never reads a session cookie, and never calls a network
endpoint. The user supplies the export; the script only parses selected files.

Usage:
    python3 scripts/linkedin_export_import.py <export.zip|export-dir> \
        --output snapshot.json --json

The snapshot contains only fields useful for a CV: name, headline, summary,
current company, websites, positions, projects, education, skills, languages
and certifications. Sensitive fields (birth date, address, phone, maiden name)
are deliberately excluded. Every row carries its source file and row number so
a later diff can point back to the candidate's own data.

All output is private. Do not commit a real snapshot to a public repository.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 200 * 1024 * 1024
MAX_FILES = 100

FILE_KEYS = {
    "profile": ("profile.csv", "user.csv"),
    "positions": ("positions.csv", "experience.csv"),
    "projects": ("projects.csv",),
    "education": ("education.csv",),
    "skills": ("skills.csv",),
    "languages": ("languages.csv",),
    "certifications": ("certifications.csv", "licensesandcertifications.csv"),
}

FIELD_ALIASES = {
    "firstname": "first_name", "lastname": "last_name", "headline": "headline",
    "summary": "summary", "about": "summary", "currentcompany": "current_company",
    "websites": "websites", "website": "websites", "url": "url",
    "companyname": "company", "company": "company", "title": "title",
    "position": "title", "location": "location", "startdate": "start_date",
    "enddate": "end_date", "description": "description", "role": "role",
    "schoolname": "school", "school": "school", "degreename": "degree",
    "degree": "degree", "fieldofstudy": "field_of_study", "name": "name",
    "issuingorganization": "issuer", "issuer": "issuer", "issuedate": "issue_date",
    "credentialid": "credential_id", "proficiency": "proficiency",
}

SENSITIVE_HEADERS = {"birthdate", "address", "phonenumber", "phonenumbers",
                     "maidenname", "instantmessengers", "twitterhandles"}


def normalize_header(header: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", (header or "").casefold())
    return FIELD_ALIASES.get(key, key)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV is not UTF-8 or UTF-16")


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def read_csv_records(raw: bytes, source: str, warnings: list[str]) -> list[dict]:
    """Parse one CSV into normalized records with source provenance."""
    text = _decode(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        warnings.append(f"{source}: no CSV header")
        return []
    fields = {name: normalize_header(name) for name in reader.fieldnames}
    dropped = sorted({name for name, normalized in fields.items()
                      if normalized in SENSITIVE_HEADERS})
    if dropped:
        warnings.append(f"{source}: excluded sensitive fields: {', '.join(dropped)}")
    records = []
    for row_number, row in enumerate(reader, start=2):
        record = {}
        for original, normalized in fields.items():
            if normalized in SENSITIVE_HEADERS:
                continue
            value = _clean(row.get(original))
            if value:
                record[normalized] = value
        if record:
            record["_source"] = source
            record["_row"] = row_number
            records.append(record)
    return records


def _iter_export_files(path: Path, warnings: list[str]):
    """Yield (logical_name, bytes, display_source) from a zip or directory."""
    if path.is_dir():
        seen = set()
        for child in sorted(path.rglob("*")):
            if child.is_symlink() or not child.is_file() or child.suffix.casefold() != ".csv":
                continue
            key = child.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            size = child.stat().st_size
            if size > MAX_FILE_BYTES:
                warnings.append(f"{child.name}: skipped, over {MAX_FILE_BYTES} bytes")
                continue
            yield key, child.read_bytes(), child.name
        return
    if not zipfile.is_zipfile(path):
        raise ValueError("input must be a LinkedIn Data Export directory or .zip")
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist()
                 if not info.is_dir() and info.filename.casefold().endswith(".csv")]
        if len(infos) > MAX_FILES:
            warnings.append(f"zip has {len(infos)} CSV files; reading first {MAX_FILES}")
            infos = infos[:MAX_FILES]
        for info in infos:
            if info.file_size > MAX_FILE_BYTES:
                warnings.append(f"{info.filename}: skipped, over {MAX_FILE_BYTES} bytes")
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                warnings.append("zip CSV payload exceeds total size cap; stopping")
                break
            basename = Path(info.filename).name.casefold()
            yield basename, archive.read(info), info.filename


def build_snapshot(path: Path) -> dict:
    """Build a normalized snapshot from a user-supplied LinkedIn export."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"export path does not exist: {path}")
    snapshot: dict[str, object] = {key: [] for key in FILE_KEYS}
    snapshot["profile"] = {}
    warnings: list[str] = []
    files_seen: list[str] = []
    meta: dict[str, object] = {
        "source": str(path),
        "files_seen": files_seen,
        "warnings": warnings,
        "note": "Local-only snapshot from the candidate's own export. No network access.",
    }
    snapshot["_meta"] = meta
    for logical, raw, display in _iter_export_files(path, warnings):
        kinds = [kind for kind, names in FILE_KEYS.items() if logical in names]
        if not kinds:
            continue
        files_seen.append(display)
        records = read_csv_records(raw, display, warnings)
        for kind in kinds:
            if kind == "profile":
                if records:
                    snapshot["profile"] = records[0]
                    for extra in records[1:]:
                        warnings.append(f"{display}: ignored additional profile row {extra.get('_row')}")
            else:
                bucket = snapshot[kind]
                assert isinstance(bucket, list)
                bucket.extend(records)
    expected = {name for names in FILE_KEYS.values() for name in names}
    seen = {Path(name).name.casefold() for name in files_seen}
    missing = sorted(name for name in expected if name not in seen)
    if missing:
        warnings.append("recognized export files not found: " + ", ".join(missing))
    counts: dict[str, int] = {}
    for key in FILE_KEYS:
        value = snapshot[key]
        counts[key] = 1 if key == "profile" and value else len(value)  # type: ignore[arg-type]
    meta["counts"] = counts
    return snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="LinkedIn Data Export zip or directory")
    parser.add_argument("--output", type=Path, help="write snapshot JSON here")
    parser.add_argument("--json", action="store_true", help="print counts as JSON")
    args = parser.parse_args(argv)
    try:
        snapshot = build_snapshot(args.export)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"linkedin-export-import: {error}", file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    if args.json:
        print(json.dumps(snapshot["_meta"], ensure_ascii=False, indent=2))
    else:
        counts = snapshot["_meta"]["counts"]
        print("LinkedIn snapshot: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
        for warning in snapshot["_meta"]["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
