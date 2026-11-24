#!/usr/bin/env python3
"""Advisory provenance check for STAR+R story numbers.

Inspired by career-ops' story-provenance-check: numbers in interview stories
are not facts just because they were generated from a CV. Classify them against
approved sources as existing, user-cannot-confirm (explicit marker), or
derived-unverified. Never edits files and never blocks delivery.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __package__:
    from .check_cv_numbers import NUMBER_PATTERN, is_claim, normalize
else:
    from check_cv_numbers import NUMBER_PATTERN, is_claim, normalize

MARKER = re.compile(r"user-cannot-confirm", re.I)
CONTEXT = 60


def analyze(text: str, sources: list[str], min_digits: int = 2) -> dict:
    claims = []
    for match in NUMBER_PATTERN.finditer(text):
        raw = match.group(1)
        if not is_claim(raw) or len(normalize(raw)) < min_digits:
            continue
        start = max(0, match.start() - CONTEXT)
        end = min(len(text), match.end() + CONTEXT)
        context = " ".join(text[start:end].split())
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        same_line = text[line_start:line_end]
        if MARKER.search(same_line):
            bucket = "user-cannot-confirm"
        elif any(re.search(r"(?<!\d)" + re.escape(normalize(raw)) + r"(?!\d)", source)
                 for source in sources):
            bucket = "existing"
        else:
            bucket = "derived-unverified"
        claims.append({"number": normalize(raw), "bucket": bucket, "context": context})
    counts = {name: sum(1 for item in claims if item["bucket"] == name)
              for name in ("existing", "user-cannot-confirm", "derived-unverified")}
    return {"status": "ok", "counts": counts, "claims": claims,
            "note": ("Advisory only. 'user-cannot-confirm' is durable; do not let repetition "
                     "turn an unverified figure into a verified one.")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", help="STAR+R story Markdown or text file")
    parser.add_argument("--source", action="append", required=True, metavar="FILE",
                        help="Approved source file; repeatable")
    parser.add_argument("--min-digits", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    text = Path(args.stories).read_text(encoding="utf-8", errors="replace")
    sources = [normalize(Path(path).read_text(encoding="utf-8", errors="replace"))
               for path in args.source]
    report = analyze(text, sources, args.min_digits)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("Story number provenance: " + ", ".join(f"{k}={v}" for k, v in report["counts"].items()))
    for item in report["claims"]:
        if item["bucket"] == "derived-unverified":
            print(f"  {item['number']}: ...{item['context']}...")
    print(report["note"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as error:
        raise SystemExit(f"Story provenance failed: {error}") from error
