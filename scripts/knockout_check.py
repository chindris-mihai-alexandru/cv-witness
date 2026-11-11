#!/usr/bin/env python3
"""Knockout check: verify a CV against a posting's hard requirements.

Recruiters apply "knockout" filters before a human ever reads a resume: work
authorization, years of experience, location, education, required licences.
A missing knockout is an automatic archive, so it is worth checking before
tailoring rather than after.

This script is deterministic and read-only. It extracts candidate knockout
signals from a posting with conservative patterns, then looks for evidence in
the CV. It reports PASS / FAIL / UNCLEAR per signal, never a single verdict.

Usage:
    python3 scripts/knockout_check.py --posting posting.txt --cv CV.pdf
    python3 scripts/knockout_check.py --posting posting.txt --cv CV.pdf --json

Exit codes:
    0 - every extracted signal has evidence in the CV
    1 - at least one signal is FAIL or UNCLEAR
    2 - input or tool error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class KnockoutError(Exception):
    """Raised for input or tool failures."""


# --- posting signal extraction ---------------------------------------------

MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

EXPERIENCE_PATTERNS = [
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:professional\s+|relevant\s+|post[- ]?graduation\s+)?experience", re.I),
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?experience\s+(?:in|with)", re.I),
    re.compile(r"experience\s*(?:of\s*)?(?:at\s+least\s*)?(\d+)\s*\+?\s*years?", re.I),
    re.compile(r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:industry\s+|work\s+)?experience", re.I),
]

EDUCATION_PATTERNS = [
    (re.compile(r"\b(ph\.?d\.?|doctorate|doctoral)\b", re.I), "PhD"),
    (re.compile(r"\bmaster'?s?\b|\bm\.?sc?\.?\b|\bm\.?eng\.?\b|\bmba\b", re.I), "Master's"),
    (re.compile(r"\bbachelor'?s?\b|\bb\.?a\.?\b|\bb\.?sc?\.?\b|\bb\.?eng\.?\b|\bundergraduate\s+degree\b", re.I), "Bachelor's"),
]

# "City, Country" / "City, State, Country" in a posting header. Spaces only —
# never newlines, so a header line cannot swallow the next line. The match is
# post-filtered in _first_place() to drop department-style fragments.
PLACE_RE = re.compile(
    r"\b([A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+)?,[ \t]*[A-Z][A-Za-z.'-]+(?:[ \t]+[A-Z][A-Za-z.'-]+)?)\b"
)

# Acronym-like first words that mark department fragments ("AFC Ops, KYC Ops",
# "MLRO France, KYC France") rather than city names. Pure 1-4 cap words.
_ACRONYM_TOKEN = re.compile(r"^[A-Z]{1,4}$")

# Places whose official name includes an article; do not strip it.
_ARTICLE_NAME_EXCEPTIONS = {"the hague"}

# Job-title words that can precede a city in a header ("Backend Engineer
# Berlin, Germany"): drop them when they lead the first token.
_ROLE_PREFIX_WORDS = {
    "backend", "frontend", "software", "senior", "junior", "lead", "head",
    "principal", "staff", "engineer", "engineers", "developer", "developers",
    "manager", "managers", "consultant", "consultants", "analyst", "analysts",
    "specialist", "specialists", "director", "directors", "full", "stack",
    "cloud", "devops", "data", "ml", "ai", "platform", "infrastructure",
    "systems", "product", "project", "program", "programmer", "programmers",
    "architect", "architects", "scientist", "scientists", "ops", "technical",
    "intern", "trainee", "apprentice", "associate", "support", "test",
    "testing", "qa", "security", "network", "site", "reliability",
}


def _first_place(posting: str) -> str | None:
    """Return the best 'City, Country' signal, or None.

    Filters PLACE_RE hits that are list fragments or acronym-pair department
    names, so "SAR, RFI and STR reporting" or "AFC Ops, KYC Ops team" do not
    masquerade as locations. Also strips job-title prefixes ("Backend
    Engineer Berlin, Germany" -> "Berlin, Germany").
    """
    m = PLACE_RE.search(posting)
    if not m:
        return None
    place = m.group(1).strip()
    t1, _, t2 = place.partition(",")
    w1 = t1.strip().split()
    w2 = t2.strip().split()
    if not w1 or not w2:
        return None

    def has_acronym(words, limit=3):
        return any(_ACRONYM_TOKEN.match(w) for w in words[:limit])

    # Both halves starting with acronym-like tokens = department fragment.
    if has_acronym(w1) and has_acronym(w2):
        return None
    # "City, Country and X" = a list continuation, not a location.
    if re.match(r"\s+(?:and|&)\s+[A-Za-z]", posting[m.end():]):
        return None
    # Drop job-title prefixes from the first token, keeping at least one word.
    while len(w1) > 1 and w1[0].lower() in _ROLE_PREFIX_WORDS:
        w1 = w1[1:]
    place = " ".join(w1) + ", " + " ".join(w2)
    # Strip a leading article unless the official name needs it ("The Hague").
    if " ".join(w1).lower() not in _ARTICLE_NAME_EXCEPTIONS:
        place = re.sub(r"^(?:The|A|An)\s+", "", place).strip()
    return place or None

LOCATION_PATTERNS = [
    re.compile(r"\b(?:located\s+in|based\s+in|location\s*[:=]?)\s+([A-Z][A-Za-z .'-]{2,40})"),
    re.compile(r"\b(remote(?:\s+only)?|hybrid|on[- ]?site|in[- ]?office)\b", re.I),
]

WORK_AUTH_PATTERNS = [
    re.compile(r"\b(?:must\s+be\s+)?authorized\s+to\s+work\s+(?:in|for)\s+([A-Za-z .'-]{2,40})", re.I),
    re.compile(r"\bvisa\s+sponsorship\b", re.I),
    re.compile(r"\bwork\s+permit\b", re.I),
    re.compile(r"\bcitizenship\b", re.I),
]

CERTIFICATION_PATTERNS = [
    re.compile(r"\b(certified|certification|certificate|license|licence)\s+(?:in\s+)?([A-Z][A-Za-z0-9 .+/#-]{2,40})"),
    re.compile(r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,4})\s+certification\s+(?:is\s+)?(?:required|preferred|mandatory)", re.I),
]


def read_text(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise KnockoutError(f"File not found: {path}")
    if p.suffix.lower() == ".pdf":
        try:
            r = subprocess.run(["pdftotext", "-layout", path, "-"],
                               capture_output=True, text=True, check=False)
        except OSError as e:
            raise KnockoutError(f"pdftotext failed: {e}") from e
        return r.stdout
    return p.read_text(encoding="utf-8", errors="replace")


def extract_signals(posting: str) -> dict:
    """Extract candidate knockout signals from a posting. Conservative by design."""
    signals = {}

    # Years of experience (take the largest stated minimum)
    years = []
    for pat in EXPERIENCE_PATTERNS:
        for m in pat.finditer(posting):
            try:
                years.append(int(m.group(1)))
            except (ValueError, IndexError):
                continue
    if years:
        signals["min_years"] = max(years)

    # Education floor. "Master's or PhD" means the floor is the lower degree;
    # "Master's and 5 years" still means Master's. Only take the highest when the
    # posting does not present the degrees as alternatives.
    mentioned = []
    for pat, label in EDUCATION_PATTERNS:
        if pat.search(posting):
            mentioned.append(label)
    if mentioned:
        rank = {"Bachelor's": 1, "Master's": 2, "PhD": 3}
        mentioned.sort(key=lambda x: rank.get(x, 0))
        floor = mentioned[0]
        # An explicit "or" between degree mentions marks an either/or floor.
        if len(mentioned) > 1 and re.search(
            r"\b" + re.escape(mentioned[-1]) + r"\b.{0,80}?\bor\b.{0,80}?\b" + re.escape(mentioned[0]) + r"\b",
            posting, re.I | re.S,
        ):
            floor = mentioned[0]
        elif len(mentioned) > 1:
            # "PhD ... or ... Master's" — the lower degree is the floor.
            floor = mentioned[0]
        signals["education"] = floor

    # Location: prefer a named place in the header over a work-mode word.
    place = _first_place(posting)
    if place:
        signals["location"] = place
    else:
        for pat in LOCATION_PATTERNS:
            m = pat.search(posting)
            if m:
                signals["location"] = m.group(0).strip()
                break

    # Work authorization
    for pat in WORK_AUTH_PATTERNS:
        m = pat.search(posting)
        if m:
            signals["work_auth"] = m.group(0).strip()
            break

    # Certifications
    certs = set()
    for pat in CERTIFICATION_PATTERNS:
        for m in pat.finditer(posting):
            label = (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)).strip()
            if label and len(label) > 2:
                certs.add(label)
    if certs:
        signals["certifications"] = sorted(certs)

    return signals


# --- CV evidence matching ---------------------------------------------------

def years_from_cv(cv: str) -> list[int]:
    """Find explicit year counts in the CV (tenure spans, 'X years')."""
    found = []
    for m in re.finditer(r"(\d+)\s*\+?\s*years?\b", cv, re.I):
        try:
            n = int(m.group(1))
            if 0 < n <= 45:
                found.append(n)
        except ValueError:
            continue
    # Tenure spans like "Jul 2021 - Mar 2022" or "Nov 2022 - Apr 2025"
    for m in re.finditer(
        rf"({MONTHS}\s+\d{{4}})\s*[-–—]\s*({MONTHS}\s+\d{{4}}|present|current)",
        cv, re.I,
    ):
        try:
            start_match = re.search(r"\d{4}", m.group(1))
            end_match = re.search(r"\d{4}", m.group(2))
            if start_match is None:
                continue
            start = int(start_match.group(0))
            end = int(end_match.group(0)) if end_match else 2026
            span = end - start
            if 0 < span <= 45:
                found.append(span)
        except (ValueError, AttributeError):
            continue
    return found


def check_signal(name: str, value, cv: str) -> tuple[str, str]:
    """Return (status, detail) for one signal."""
    cv_low = cv.lower()

    if name == "min_years":
        spans = years_from_cv(cv)
        if not spans:
            return "UNCLEAR", f"posting requires {value}+ years; no year counts found in CV"
        total = max(spans)
        if total >= value:
            return "PASS", f"posting requires {value}+ years; CV shows up to {total}"
        return "FAIL", f"posting requires {value}+ years; CV shows max {total}"

    if name == "education":
        rank = {"Bachelor's": 1, "Master's": 2, "PhD": 3}
        cv_evidence = None
        for pat, label in EDUCATION_PATTERNS:
            if pat.search(cv):
                cv_evidence = label
                break
        if cv_evidence is None:
            return "UNCLEAR", f"posting requires {value}; no degree found in CV"
        if rank.get(cv_evidence, 0) >= rank.get(value, 0):
            return "PASS", f"posting requires {value}; CV shows {cv_evidence}"
        return "FAIL", f"posting requires {value}; CV shows {cv_evidence}"

    if name == "location":
        loc = str(value)
        # Remote/hybrid/onsite signals
        if loc.lower() in ("remote", "remote only", "hybrid", "on-site", "onsite", "in-office"):
            if loc.lower() in ("remote", "remote only"):
                return "UNCLEAR", "posting is remote; confirm work location matches"
            return "UNCLEAR", f"posting is {loc}; confirm work location matches"
        # Named place: look for it in the CV
        key = loc.strip().split(",")[0].strip().lower()
        if key and key in cv_low:
            return "PASS", f"posting location '{loc}' appears in CV"
        return "UNCLEAR", f"posting location '{loc}' not found in CV"

    if name == "work_auth":
        return "UNCLEAR", "work authorization must be confirmed against the posting's exact wording"

    if name == "certifications":
        missing = [c for c in value if c.lower() not in cv_low]
        if not missing:
            return "PASS", f"all {len(value)} certification signal(s) found in CV"
        if len(missing) == len(value):
            return "FAIL", f"none of {value} found in CV"
        return "UNCLEAR", f"{len(missing)} of {len(value)} certification signal(s) not found: {missing}"

    return "UNCLEAR", "no checker for this signal"


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a CV against a posting's hard requirements")
    ap.add_argument("--posting", required=True, help="Posting text file or URL-sourced text")
    ap.add_argument("--cv", required=True, help="CV file (PDF or text)")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args()

    try:
        posting = read_text(args.posting)
        cv = read_text(args.cv)
    except KnockoutError as e:
        print(f"knockout-check: {e}", file=sys.stderr)
        return 2

    signals = extract_signals(posting)
    if not signals:
        msg = "No knockout signals extracted from the posting; nothing to check."
        if args.json:
            print(json.dumps({"signals": {}, "results": []}, indent=2))
        else:
            print(msg)
        return 0

    results = []
    for name, value in signals.items():
        status, detail = check_signal(name, value, cv)
        results.append({"signal": name, "requirement": value, "status": status, "detail": detail})

    if args.json:
        print(json.dumps({"signals": signals, "results": results}, indent=2, ensure_ascii=False))
    else:
        print(f"=== KNOCKOUT CHECK ({len(results)} signal(s)) ===")
        for r in results:
            mark = {"PASS": "PASS", "FAIL": "FAIL", "UNCLEAR": "UNCLEAR"}[r["status"]]
            print(f"  [{mark}] {r['signal']}: {r['detail']}")

    if any(r["status"] in ("FAIL", "UNCLEAR") for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
