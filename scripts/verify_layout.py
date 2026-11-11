#!/usr/bin/env python3
"""Run the full pre-delivery check battery over an ALREADY RENDERED CV PDF.

The structured pipeline (`build_cv.py`) runs every check while rendering. A CV
produced by any other authoring path (template.html fills, Amazon Quick's CV
feature, DOCX exported to PDF, a user's own tool) never touches that pipeline,
so its layout was previously verified only by hand. This gate closes that gap:
same checks, same code, run over the finished PDF.

Checks (all reuse existing modules - nothing new here):
  - cv_checks.validate_pdf: paper size, page limit, expected/ordered section
    text, placeholder-marker scan, posting overlap review.
  - cv_layout.check_layout: date right-alignment, heading-gap consistency,
    bullet left edges from pdftotext -bbox-layout.

Usage:
  python3 scripts/verify_layout.py <cv.pdf> [--paper a4|letter] [--max-pages 1]
      [--expected "Heading A,Heading B"] [--ordered "Heading A,..."]
      [--posting posting.txt] [--json]

Exit codes:
  0 - all checks passed
  1 - check failures (page limit, layout, missing headings, markers)
  2 - input/tool error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__:
    from .cv_checks import CheckError, CheckFailure, MAX_BYTES, validate_pdf
    from .cv_layout import parse_pages, check_layout
else:
    from cv_checks import CheckError, CheckFailure, MAX_BYTES, validate_pdf
    from cv_layout import parse_pages, check_layout


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify an already rendered CV PDF")
    ap.add_argument("pdf", help="Rendered CV PDF")
    ap.add_argument("--paper", choices=("a4", "letter"), default="a4")
    ap.add_argument("--max-pages", type=int, default=1)
    ap.add_argument("--expected", default="", help="comma-separated headings that must extract")
    ap.add_argument("--ordered", default="", help="comma-separated headings in expected order")
    ap.add_argument("--posting", default=None, help="posting text for overlap review")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"verify-layout: file not found: {pdf}", file=sys.stderr)
        return 2
    if pdf.stat().st_size > MAX_BYTES:
        print(f"verify-layout: {pdf.name} exceeds {MAX_BYTES // (1024 * 1024)} MiB", file=sys.stderr)
        return 2

    expected = [h.strip() for h in args.expected.split(",") if h.strip()]
    ordered = [h.strip() for h in args.ordered.split(",") if h.strip()]
    if not expected and not ordered:
        # Default: the seven standard section headings, in the approved order.
        expected = ["Professional Summary", "Skills", "Professional Experience",
                    "Projects", "Education", "Certifications", "Languages"]

    try:
        report = validate_pdf(str(pdf), args.paper, args.max_pages, tuple(expected),
                              args.posting, source_html=None, ordered_text=tuple(ordered),
                              strict_ordered_text=bool(ordered))
    except CheckError as e:
        print(f"verify-layout: {e}", file=sys.stderr)
        return 2

    # Layout gate: date alignment, heading gaps, bullet edges (same as render_cv).
    bbox = subprocess.run(["pdftotext", "-bbox-layout", str(pdf), "-"],
                          capture_output=True, text=True)
    if bbox.returncode == 0 and bbox.stdout:
        try:
            layout_problems = check_layout(parse_pages(bbox.stdout))
            if layout_problems:
                report["layout_problems"] = layout_problems
        except Exception:
            report["layout_problems"] = [{"code": "layout_check_unavailable",
                                          "detail": "pdftotext bbox parse failed"}]

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        ok = report.get("passed", False) and not report.get("layout_problems")
        print("PASS" if ok else "FAIL")
        for problem in report.get("problems", []):
            print(f"  - {problem.get('code')}: {problem.get('detail', problem)}")
        for problem in report.get("layout_problems", []):
            print(f"  - {problem.get('code')}: {problem.get('detail', problem)}")

    if report.get("layout_problems") or not report.get("passed", False):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
