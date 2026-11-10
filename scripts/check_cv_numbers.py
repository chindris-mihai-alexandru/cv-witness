#!/usr/bin/env python3
"""Number fact gate: fail a CV whose numbers are absent from the approved sources.

Ported in spirit from career-ops (career-ops-hq/career-ops), whose generate-pdf
fact gate blocks a CV whose numbers appear in neither cv.md nor the article
digest. cv-witness keeps the same promise - "tailored CVs, nothing invented" -
so every number a tailored CV claims must trace to an approved source file,
typically foundation.md and provenance.md.

Run after rendering and before delivery:

    python3 scripts/check_cv_numbers.py rendered.pdf \
        --source foundation.md --source provenance.md

Exit 0 when every number is backed by a source; exit 1 listing each
unverified number with surrounding context. Numbers that are pure years
(1900-2099), single digits, or fragments of alphanumeric identifiers
(AIF-C01, ITIL 4) are not claims and are skipped.
"""

import argparse
import re
import sys
from pathlib import Path

if __package__:
    from .cv_checks import CheckError, read_text
else:
    from cv_checks import CheckError, read_text

NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+)(?![\w.])")
CONTEXT_CHARS = 45


def normalize(number_text):
    """Normalize a matched number for comparison: drop grouping commas."""
    return number_text.replace(",", "")


def is_claim(number_text):
    """Whether a matched number is a claim the sources must back."""
    value = normalize(number_text)
    if len(value) == 1:
        return False
    if value.isdigit() and 1900 <= int(value) <= 2099:
        return False
    return True


def collect_unverified(text, source_texts, min_digits):
    """Yield (number, context) for every claim missing from all sources."""
    for match in NUMBER_PATTERN.finditer(text):
        raw = match.group(1)
        value = normalize(raw)
        if not is_claim(raw) or len(value) < min_digits:
            continue
        if any(re.search(r"(?<!\d)" + re.escape(value) + r"(?!\d)",
                         normalized_source)
               for normalized_source in source_texts):
            continue
        start = max(0, match.start() - CONTEXT_CHARS)
        end = min(len(text), match.end() + CONTEXT_CHARS)
        context = " ".join(text[start:end].split())
        yield value, context


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cv", help="Rendered CV (PDF) or extracted text file")
    parser.add_argument("--source", action="append", default=[],
                        metavar="FILE",
                        help="Approved source file; repeat for each source")
    parser.add_argument("--min-digits", type=int, default=2,
                        help="Smallest digit count treated as a claim (default 2)")
    args = parser.parse_args(argv)

    if not args.source:
        raise CheckError("Select at least one approved source with --source.")

    cv_text = read_text(args.cv)
    source_texts = [normalize(read_text(Path(source), pdf_allowed=False))
                    for source in args.source]

    unverified = list(collect_unverified(cv_text, source_texts,
                                         args.min_digits))
    if unverified:
        print(f"FAILED: {len(unverified)} number(s) not backed by the "
              f"{len(args.source)} approved source(s):")
        for value, context in unverified:
            print(f"  {value}\n      ...{context}...")
        sys.exit(1)

    print(f"Number gate passed: every claim traces to the approved sources "
          f"({len(args.source)} file(s)).")


if __name__ == "__main__":
    try:
        main()
    except CheckError as error:
        print(f"check-cv-numbers: {error}", file=sys.stderr)
        sys.exit(2)