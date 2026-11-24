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
import unicodedata
from pathlib import Path

if __package__:
    from .check_cv_numbers import NUMBER_PATTERN, is_claim, normalize
else:
    from check_cv_numbers import NUMBER_PATTERN, is_claim, normalize


MARKER = re.compile(r"user-cannot-confirm", re.I)
MARKER_LINE = re.compile(r"^\s*(?:[-*>]?\s*)?(?:\*\*Provenance:\*\*\s*)?user-cannot-confirm\s*$", re.I | re.M)
CONTEXT = 60
STOPWORDS = {"a", "an", "and", "by", "for", "from", "in", "of", "on", "or", "the",
             "to", "was", "were", "with", "reduced", "increased", "saved", "cut",
             "grew", "improved", "percent", "pct", "hours", "people", "users",
             "x", "fold", "k", "m"}


def _sentence_at(text: str, position: int) -> str:
    start = max(text.rfind(".", 0, position), text.rfind("!", 0, position),
                text.rfind("?", 0, position), text.rfind("\n", 0, position)) + 1
    candidates = [text.find(mark, position) for mark in (".", "!", "?", "\n")]
    ends = [index for index in candidates if index != -1]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _unit_at(text: str, position: int) -> str:
    tail = text[position:position + 40].casefold()
    if re.match(r"\s*(?:%|percent|per cent|pct|\\%)", tail):
        return "percent"
    for unit in ("hours", "people", "users", "engineers", "days", "months", "weeks"):
        if re.search(r"\b" + unit + r"\b", tail):
            return unit
    if re.search(r"\b(?:x|fold)\b", tail):
        return "multiplier"
    if re.search(r"[$€£]", tail):
        return "currency"
    return "count"


def _tokens(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKC", text).casefold()
    return {word for word in re.findall(r"\w+", folded, re.UNICODE)
            if len(word) > 2 and word not in STOPWORDS}


def _marker_block(text: str, position: int) -> bool:
    heading = text.rfind("\n### ", 0, position)
    if heading == -1 and text.startswith("### "):
        heading = 0
    next_heading = text.find("\n### ", position + 1)
    block = text[heading:next_heading if next_heading != -1 else len(text)]
    return bool(MARKER_LINE.search(block))


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
        if MARKER.search(same_line) or _marker_block(text, match.start()):
            bucket = "user-cannot-confirm"
        else:
            value = normalize(raw)
            unit = _unit_at(text, match.end())
            story_tokens = _tokens(_sentence_at(text, match.start()))
            bucket = "derived-unverified"
            for source in sources:
                for source_match in re.finditer(r"(?<!\d)" + re.escape(value) + r"(?!\d)", source):
                    if _unit_at(source, source_match.end()) != unit:
                        continue
                    if story_tokens & _tokens(_sentence_at(source, source_match.start())):
                        bucket = "existing"
                        break
                if bucket == "existing":
                    break
        claims.append({"number": normalize(raw), "bucket": bucket, "context": context,
                       "display": "[unconfirmed figure]" if bucket == "user-cannot-confirm" else normalize(raw)})
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
