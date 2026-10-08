#!/usr/bin/env python3
"""Pre-delivery checks for a local PDF; selected postings trigger overlap review."""

import argparse
import json
import sys

if __package__:
    from .cv_checks import CheckError, validate_pdf
else:
    from cv_checks import CheckError, validate_pdf


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf")
    parser.add_argument("--paper", choices=("a4", "letter"), default="a4")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--expected-text", action="append", default=[], help="Exact text that must extract; not printed in diagnostics")
    parser.add_argument("--posting", help="Selected local .txt/.md posting; never fetched automatically")
    parser.add_argument("--overlap-policy", choices=("strict", "review"), default="strict")
    parser.add_argument("--show-phrases", action="store_true", help="Opt in to private wording in diagnostics")
    args = parser.parse_args(argv)
    try:
        report = validate_pdf(args.pdf, args.paper, args.max_pages, args.expected_text,
                              args.posting, args.overlap_policy, args.show_phrases)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    except (CheckError, OSError) as error:
        print("check-cv: " + (str(error) if isinstance(error, CheckError) else "Local file operation failed."), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
