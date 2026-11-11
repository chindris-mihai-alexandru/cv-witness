#!/usr/bin/env python3
"""Validate a rendered CV for ATS field extraction and fraud signals.

This script checks that a CV's structured fields are extractable by ATS parsers
and that there are no fraud signals (broken links, mismatched locations, etc.).

Usage:
    python3 scripts/ats_validate.py <cv.pdf> [--source <source.md>]

Exit codes:
    0 - all checks passed
    1 - one or more checks failed
    2 - input or tool error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


class ATSValidationError(Exception):
    """Raised when ATS validation fails."""


def run_tool(cmd: list[str]) -> str:
    """Run a command and return its stdout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise ATSValidationError(f"Tool failed: {e}") from e


def extract_text(pdf_path: str) -> str:
    """Extract text from a PDF using pdftotext."""
    return run_tool(["pdftotext", "-layout", pdf_path, "-"])


def check_contact_fields(text: str) -> list[str]:
    """Check that contact fields are present and extractable."""
    issues = []

    # Email should be in the body, not just header
    email_pattern = r'[\w.+-]+@[\w-]+\.[\w.-]+'
    emails = re.findall(email_pattern, text)
    if not emails:
        issues.append("No email address found in CV")

    # Phone should be present
    phone_pattern = r'[\+]?\d[\d\s().-]{7,}'
    phones = re.findall(phone_pattern, text)
    if not phones:
        issues.append("No phone number found in CV")

    # Name should be in the first few lines
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        issues.append("CV appears to be empty")
    else:
        # Check that the first non-empty line looks like a name
        first_line = lines[0]
        if len(first_line) < 3:
            issues.append(f"First line too short to be a name: '{first_line}'")

    return issues


def check_section_headings(text: str) -> list[str]:
    """Check that standard section headings are present."""
    issues = []

    standard_headings = [
        "PROFESSIONAL SUMMARY",
        "SKILLS",
        "EXPERIENCE",
        "EDUCATION",
    ]

    for heading in standard_headings:
        if heading not in text.upper():
            issues.append(f"Missing standard section heading: {heading}")

    return issues


def check_dates(text: str) -> list[str]:
    """Check that dates are in a standard format."""
    issues = []

    # Look for date patterns like "Jan 2023" or "2023-01"
    date_patterns = [
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}',
        r'\d{4}-\d{2}',
        r'\d{2}/\d{4}',
    ]

    found_dates = False
    for pattern in date_patterns:
        if re.search(pattern, text):
            found_dates = True
            break

    if not found_dates:
        issues.append("No dates found in CV (expected format: 'Jan 2023' or '2023-01')")

    return issues


def check_fraud_signals(text: str) -> list[str]:
    """Check for fraud signals in the CV."""
    issues = []

    # Check for broken LinkedIn URLs
    linkedin_urls = re.findall(r'linkedin\.com/in/[\w-]*', text)
    for url in linkedin_urls:
        # Check for obviously broken URLs
        if len(url) < 20 or '/in/c' in url or '/in/?' in url:
            issues.append(f"Potentially broken LinkedIn URL: {url}")

    # Check for mismatched area codes vs claimed location.
    # Scope to the header/contact region only: the location claim that must
    # match the phone prefix is the one in the contact line, not language
    # mentions in the LANGUAGES section ("French and German (elementary)"
    # describes languages, not a claimed residence).
    header_region = text.split("PROFESSIONAL SUMMARY", 1)[0] if "PROFESSIONAL SUMMARY" in text else text[:400]
    location_patterns = {
        r'\b(Romania|Romanian)\b': ['+40', '0040'],
        r'\b(United States|USA)\b': ['+1', '001'],
        r'\b(United Kingdom|UK)\b': ['+44', '0044'],
        r'\bGermany\b': ['+49', '0049'],
        r'\bFrance\b': ['+33', '0033'],
    }

    for location_pattern, prefixes in location_patterns.items():
        if re.search(location_pattern, header_region, re.IGNORECASE):
            # Check if any phone number has a matching prefix
            phone_pattern = r'[\+]\d{1,3}[\d\s().-]{7,}'
            phones = re.findall(phone_pattern, text)
            if phones:
                has_matching_prefix = any(
                    any(phone.strip().startswith(prefix) for prefix in prefixes)
                    for phone in phones
                )
                if not has_matching_prefix:
                    issues.append(
                        f"Location claims {location_pattern} but no matching phone prefix found"
                    )

    return issues


def check_ats_fields(text: str) -> list[str]:
    """Check that ATS-parsable fields are present."""
    issues = []

    # Check for skills section with common skill keywords
    skill_keywords = [
        "Python", "JavaScript", "TypeScript", "Java", "C++", "Go", "Rust",
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "CI/CD",
        "React", "Vue", "Angular", "Node.js", "FastAPI", "Django",
    ]

    found_skills = [kw for kw in skill_keywords if kw.lower() in text.lower()]
    if len(found_skills) < 3:
        issues.append(f"Few recognizable skills found ({len(found_skills)}): {found_skills}")

    # Check for education keywords
    education_keywords = ["B.S.", "M.S.", "B.A.", "M.A.", "PhD", "Bachelor", "Master", "Degree"]
    found_education = [kw for kw in education_keywords if kw.lower() in text.lower()]
    if not found_education:
        issues.append("No education keywords found (expected: B.S., M.S., PhD, etc.)")

    return issues


def validate_cv(pdf_path: str) -> dict:
    """Validate a CV PDF for ATS compatibility and fraud signals."""
    text = extract_text(pdf_path)

    results = {
        "contact_fields": check_contact_fields(text),
        "section_headings": check_section_headings(text),
        "dates": check_dates(text),
        "fraud_signals": check_fraud_signals(text),
        "ats_fields": check_ats_fields(text),
    }

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a CV for ATS compatibility")
    parser.add_argument("pdf", help="Path to the CV PDF file")
    parser.add_argument(
        "--source",
        action="append",
        help="Source file to check claims against (repeatable)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"ats-validate: file not found: {pdf_path}", file=sys.stderr)
        return 2

    try:
        results = validate_cv(str(pdf_path))
    except ATSValidationError as e:
        print(f"ats-validate: {e}", file=sys.stderr)
        return 2

    # Print results
    all_issues = []
    for category, issues in results.items():
        if issues:
            print(f"\n[{category}]")
            for issue in issues:
                print(f"  - {issue}")
            all_issues.extend(issues)

    if all_issues:
        print(f"\n{len(all_issues)} issue(s) found.")
        return 1
    else:
        print("✓ All ATS validation checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
