#!/usr/bin/env python3
"""Humane wording audit: a lexical BS/hype review aid for CV bullets + summary.

Inspired by the "BS meter" idea (score every sentence for hype, evasion and
unsupported claims), but deliberately honest about what it is: a LEXICAL REVIEW
AID, not a verdict. It flags words and phrases commonly associated with hype,
buzzwords, superlatives-without-evidence and self-flattery, so a human can review
them against the verified sources (foundation.md / provenance.md).

It does NOT judge truth or quality. The number-provenance gate
(check_cv_numbers.py) and the stack-honesty audit do that. A hype flag here is a
prompt to ask "does the evidence support this wording, and is it plain and
human?", not a finding of dishonesty.

Advisory only: always exits 0. A flag is a review candidate, not a defect. Some
flagged words are legitimate in context; read before rewriting. Compare against
the approved baseline / plain professional prose, not an absolute "zero hype"
target: sentence-level flags run high for everyone, so calibrate relatively.

Usage:
    python3 scripts/humane_audit.py <cv.pdf>
    python3 scripts/humane_audit.py <source.html>
    python3 scripts/humane_audit.py <draft.txt>
"""
from __future__ import annotations

import argparse
import html as _html
import re
import subprocess
import sys
from pathlib import Path

# Conservative, low-noise marker sets. These are review prompts, not verdicts.
CATEGORIES: dict[str, list[str]] = {
    "hype/buzzword": [
        r"\bsynerg\w*", r"\bleverage[sd]?\b", r"\bspearhead\w*",
        r"\bresults[- ]driven\b", r"\bproven track record\b",
        r"\bworld[- ]class\b", r"\bcutting[- ]edge\b", r"\brevolutionary\b",
        r"\bgame[- ]chang\w*", r"\bbest[- ]in[- ]class\b", r"\bguru\b",
        r"\bninja\b", r"\brockstar\b", r"\bwizard\b", r"\bevangelist\b",
        r"\bdisrupt\w*", r"\bparadigm\b",
    ],
    "superlative (needs evidence)": [
        r"\bunparalleled\b", r"\bunmatched\b", r"\bexceptional\b",
        r"\boutstanding\b", r"\bremarkable\b", r"\bincredible\b",
        r"\bamazing\b", r"\bworld[- ]leading\b", r"\btop[- ]tier\b",
        r"\bunbeatable\b", r"\bsecond to none\b",
    ],
    "self-flattery": [
        r"\bpassionate\b", r"\bdedicated\b", r"\bhard[- ]working\b",
        r"\bteam player\b", r"\bempathetic\b", r"\benthusiastic\b",
        r"\bself[- ]motivated\b", r"\bgo[- ]getter\b", r"\bdetail[- ]oriented\b",
    ],
}
_COMPILED = {
    cat: [re.compile(p, re.I) for p in pats] for cat, pats in CATEGORIES.items()
}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout
    raw = path.read_text(encoding="utf-8")
    if suffix in {".html", ".htm"}:
        raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<[^>]+>", "\n", raw)
        return _html.unescape(raw)
    return raw


def scan(text: str) -> list[dict]:
    """Return one record per flagged line: line number, text, categories, hits."""
    findings = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        hits = {}
        for cat, regs in _COMPILED.items():
            matched = sorted({m.group(0).lower() for r in regs for m in r.finditer(stripped)})
            if matched:
                hits[cat] = matched
        if hits:
            findings.append({"line": n, "text": stripped, "hits": hits})
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cv", type=Path, help="CV PDF, source HTML, or plain-text draft")
    ap.add_argument("--json", action="store_true", help="emit JSON findings")
    args = ap.parse_args(argv)

    text = extract_text(args.cv.expanduser())
    findings = scan(text)

    if args.json:
        import json
        print(json.dumps({"advisory": True, "flagged_lines": len(findings),
                          "findings": findings}, indent=2))
        return 0

    print("=== HUMANE WORDING AUDIT (advisory review aid, not a verdict) ===")
    if not findings:
        print("No hype/buzzword/superlative/self-flattery markers found.")
    for f in findings:
        cats = "; ".join(f"{c}: {', '.join(w)}" for c, w in f["hits"].items())
        print(f"  line {f['line']}: [{cats}]")
        print(f"    {f['text'][:140]}")
    print(f"\n{len(findings)} line(s) flagged for review.")
    print("These are lexical review prompts, not findings of dishonesty. For each:")
    print("  1. Does the evidence (foundation.md / provenance.md) support the claim?")
    print("  2. Is the wording plain, specific and human, or hype/self-flattery?")
    print("Rewrite only what fails both; a flagged word can be legitimate in context.")
    print("Compare against the approved baseline, not an absolute zero-hype target.")
    return 0


if __name__ == "__main__":
    sys.exit(main())