#!/usr/bin/env python3
"""JD-overlap lint: flag CV phrasing that is shared with the job posting.

Enforces the cv-witness no-mirroring gate mechanically. The script only
surfaces shared word runs; a human (or the agent) decides which are generic
industry phrases and which are copied JD wording that must be rewritten.

Usage:
    python3 jd_overlap.py <cv-file> <posting-file> [--strict]

    <cv-file>       .pdf (via pdftotext), .txt, or .md
    <posting-file>  .txt or .md
    --strict        exit 1 when any run of 4+ words is shared

Exit codes: 0 no 4+ word overlaps, 1 strict violations found, 2 usage error.
"""
import re
import subprocess
import sys
import unicodedata
from pathlib import Path


def text_of(path: str) -> str:
    p = Path(path)
    if not p.exists():
        sys.exit(f"error: {path} not found")
    if p.suffix.lower() == ".pdf":
        try:
            out = subprocess.run(
                ["pdftotext", str(p), "-"], capture_output=True, text=True, check=True
            )
        except FileNotFoundError:
            sys.exit("error: pdftotext not installed; cannot read PDF input")
        return out.stdout
    return p.read_text(encoding="utf-8", errors="ignore")


def words(text: str) -> list:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.split()


def ngrams(ws: list, n: int) -> set:
    return {" ".join(ws[i : i + n]) for i in range(len(ws) - n + 1)}


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    cv_w = words(text_of(args[0]))
    jd_w = words(text_of(args[1]))
    if not cv_w or not jd_w:
        sys.exit("error: one of the inputs extracted to no text")

    hits: dict = {}
    for n in (6, 5, 4, 3):
        shared = ngrams(jd_w, n) & ngrams(cv_w, n)
        if shared:
            hits[n] = sorted(shared)

    # Keep only the longest runs: a 5-word hit subsumes its 4- and 3-word parts.
    long_runs = {run for n in (6, 5, 4) for run in hits.get(n, [])}
    triples = [t for t in hits.get(3, []) if not any(t in run for run in long_runs)]

    print("JD-overlap lint")
    print(f"  cv: {args[0]}  ({len(cv_w)} words)")
    print(f"  jd: {args[1]}  ({len(jd_w)} words)")
    four_plus = [run for n in (6, 5, 4) for run in hits.get(n, [])]
    if four_plus:
        print("\n  SHARED RUNS (4+ words) - rewrite these unless they are your own:")
        for run in four_plus:
            print(f"    [{run.count(' ') + 1}w] {run}")
    else:
        print("\n  no shared runs of 4+ words")
    if triples:
        print("  shared 3-word runs (usually generic; review):")
        for run in triples:
            print(f"    [3w] {run}")
    if strict and four_plus:
        print("\nstrict: FAIL")
        sys.exit(1)
    print("\nverdict: no verbatim JD-mirroring detected" + (" (strict pass)" if strict else ""))


if __name__ == "__main__":
    main()
