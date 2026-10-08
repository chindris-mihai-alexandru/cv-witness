#!/usr/bin/env python3
"""Review literal job-posting overlap. No match is an originality certificate."""

import argparse
import json
import sys

if __package__:
    from .cv_checks import CheckError, overlap_report, read_text, words
else:
    from cv_checks import CheckError, overlap_report, read_text, words


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cv", help="PDF, UTF-8 text or Markdown CV")
    parser.add_argument("posting", help="UTF-8 text or Markdown posting")
    parser.add_argument("--strict", action="store_true", help="Fail on any literal run of four or more shared words")
    parser.add_argument("--show-phrases", action="store_true", help="Opt in to printing shared wording; may expose private text")
    parser.add_argument("--json", action="store_true", help="Print machine-readable metrics")
    args = parser.parse_args(argv)
    try:
        report = overlap_report(read_text(args.cv), read_text(args.posting, pdf_allowed=False), args.show_phrases)
    except CheckError as error:
        print("jd-overlap: " + str(error), file=sys.stderr)
        return 2
    failed = args.strict and report["shared_runs"] > 0
    report["strict"] = args.strict
    report["passed"] = not failed
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"JD overlap: {report['shared_runs']} shared runs; longest {report['longest_run_words']} words.")
        for run in report["runs"]:
            location = f"CV word {run['cv_word']}, posting word {run['posting_word']}: {run['words']} words"
            print("  " + location + (" | " + run["phrase"] if args.show_phrases else ""))
        print(report["note"])
        print("strict: FAIL" if failed else "strict: PASS" if args.strict else "Review shared wording in context before delivery.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
