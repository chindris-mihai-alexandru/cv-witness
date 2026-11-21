#!/usr/bin/env python3
"""Advisory exact-term coverage review for a posting's required terms.

This is a review aid, not an ATS simulator and not a score. It reports which
supplied terms appear verbatim in a CV and which do not. A missing term is a
gap to verify against trusted evidence, never a licence to add an unsupported
claim. The script never edits a document.
"""
from __future__ import annotations

import argparse
import json
import sys

if __package__:
    from .cv_checks import CheckError, normalized_text, read_text
else:
    from cv_checks import CheckError, normalized_text, read_text


def coverage(cv_text, terms):
    """Return per-term presence counts using normalized exact matching."""
    haystack = normalized_text(cv_text)
    results = []
    for term in terms:
        needle = normalized_text(term)
        count = haystack.count(needle) if needle else 0
        results.append({"term": term, "present": count > 0, "occurrences": count})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cv", help="CV PDF, UTF-8 text or Markdown")
    parser.add_argument("--term", action="append", default=[],
                        help="exact required term to check (repeatable)")
    parser.add_argument("--terms-file", help="UTF-8 file, one required term per line")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    terms = list(args.term)
    if args.terms_file:
        try:
            with open(args.terms_file, encoding="utf-8") as handle:
                terms += [line.strip() for line in handle
                          if line.strip() and not line.lstrip().startswith("#")]
        except OSError as error:
            print(f"jd-coverage: {error}", file=sys.stderr)
            return 2
    if not terms:
        print("jd-coverage: supply at least one --term or --terms-file", file=sys.stderr)
        return 2
    try:
        rows = coverage(read_text(args.cv), terms)
    except CheckError as error:
        print(f"jd-coverage: {error}", file=sys.stderr)
        return 2

    report = {
        "terms": rows,
        "covered": [row["term"] for row in rows if row["present"]],
        "missing": [row["term"] for row in rows if not row["present"]],
        "note": ("Advisory exact-term review only: no ATS score, ranking or pass is "
                 "certified. A missing term is a gap to verify against trusted "
                 "evidence, never a reason to invent a claim."),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Covered: " + (", ".join(report["covered"]) or "none"))
        print("Missing: " + (", ".join(report["missing"]) or "none"))
        print(report["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
