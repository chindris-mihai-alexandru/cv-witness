#!/usr/bin/env python3
"""Advisory posting-integrity scan for untrusted job descriptions.

Candidate-side port of the useful shape of career-ops' posting-guard: detects
obvious hidden blocks, invisible Unicode, instruction-shaped lines and mixed-
script words before a posting is used to tailor a CV. It never follows posting
instructions, never edits the source file and never blocks a workflow.
Detection is triage, not a security guarantee.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\b|"
    r"font-size\s*:\s*0(?:px|pt|em|rem)?\b|color\s*:\s*transparent|"
    r"clip\s*:|position\s*:\s*absolute[^;]*left\s*:\s*-?\d{3,}", re.I)
HIDDEN_ATTR = re.compile(r"\b(?:hidden|aria-hidden\s*=\s*['\"]true['\"])\b", re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
NON_TEXT_BLOCK = re.compile(r"<(script|style|noscript|template|svg)\b[^>]*>.*?</\1\s*>", re.I | re.S)
PAIR_TAG = re.compile(r"<([a-z][\w:-]*)\b([^>]*)>(.*?)</\1\s*>", re.I | re.S)
URL = re.compile(r"https?://[^\s\"'<>]+")
INSTRUCTION = re.compile(
    r"ignore (?:all )?(?:previous|prior|above) instructions|"
    r"if you are (?:an? )?ai|"
    r"system\s*:|assistant\s*:|developer\s*:|"
    r"include the (?:phrase|word|token)|"
    r"do not (?:submit|apply)|rate (?:this|the) candidate", re.I)
INVISIBLE = {
    "\u00ad": "soft hyphen", "\u200b": "zero-width space",
    "\u200c": "zero-width non-joiner", "\u200d": "zero-width joiner",
    "\u200e": "left-to-right mark", "\u200f": "right-to-left mark",
    "\u202a": "left-to-right embedding", "\u202b": "right-to-left embedding",
    "\u202c": "pop directional formatting", "\u202d": "left-to-right override",
    "\u202e": "right-to-left override", "\u2060": "word joiner",
    "\ufeff": "byte order mark",
}
TAG_FLAG = re.compile("\U0001f3f4[\U000e0060-\U000e007f]{3,7}\U000e007f")
MAX_EXCERPT = 160


def _excerpt(text: str) -> str:
    return " ".join(text.split())[:MAX_EXCERPT]


def _strip_invisible(text: str) -> tuple[str, dict[str, int], list[str], bool]:
    counts: dict[str, int] = {}
    tampering: list[str] = []
    result = []
    for position, char in enumerate(text):
        if char in INVISIBLE:
            name = INVISIBLE[char]
            counts[name] = counts.get(name, 0) + 1
            before = text[position - 1] if position else ""
            after = text[position + 1] if position + 1 < len(text) else ""
            if name.startswith("zero-width") and before.isalnum() and after.isalnum():
                tampering.append(name)
            if "override" in name or "embedding" in name:
                tampering.append(name)
            continue
        result.append(char)
    # Tag characters are preserved above; do not append them a second time.
    tag_flags = list(TAG_FLAG.finditer(text))
    if tag_flags:
        counts["unicode tag flag"] = len(tag_flags)
    return "".join(result), counts, tampering, bool(tampering)


def _hidden_blocks(text: str) -> tuple[str, list[str]]:
    without = COMMENT.sub(" ", text)
    without = NON_TEXT_BLOCK.sub(" ", without)
    blocks: list[str] = []

    def replace(match: re.Match) -> str:
        attrs = match.group(2) or ""
        if HIDDEN_STYLE.search(attrs) or HIDDEN_ATTR.search(attrs):
            body = _excerpt(match.group(3))
            if body:
                blocks.append(body)
            return " "
        return match.group(0)

    cleaned = PAIR_TAG.sub(replace, without)
    return cleaned, blocks


def _mixed_scripts(text: str) -> list[str]:
    found = []
    for word in re.findall(r"[^\W\d_]+", text, re.UNICODE):
        if len(word) < 3:
            continue
        scripts = set()
        for char in word:
            name = unicodedata.name(char, "")
            for script in ("LATIN", "CYRILLIC", "GREEK"):
                if script in name:
                    scripts.add(script)
        if len(scripts) > 1:
            found.append(word)
    return sorted(set(found))


def scan(text: str, is_html: bool = False) -> dict:
    cleaned, hidden = _hidden_blocks(text) if is_html else (text, [])
    visible, invisible_counts, tampering, has_tampering = _strip_invisible(cleaned)
    mixed = _mixed_scripts(visible)
    lines = []
    for line in visible.splitlines():
        if INSTRUCTION.search(line):
            excerpt = _excerpt(line)
            if excerpt:
                lines.append(excerpt)
    hidden_urls = sorted({url for block in hidden for url in URL.findall(block)})
    visible_urls = set(URL.findall(visible))
    hidden_only = [url for url in hidden_urls if url not in visible_urls]
    significant_invisible = {key: value for key, value in invisible_counts.items()
                             if key != "unicode tag flag"}
    verdict = ("flagged" if (has_tampering or lines or mixed) else
               "context" if (hidden or significant_invisible or hidden_only) else "clean")
    return {
        "status": "ok",
        "verdict": verdict,
        "hidden_blocks": hidden,
        "hidden_only_urls": hidden_only,
        "invisible_characters": invisible_counts,
        "instruction_shaped_lines": lines,
        "mixed_script_words": mixed,
        "note": ("Advisory only. Hidden navigation is common. Detection is triage, "
                 "not a security guarantee; keep the human-in-the-loop boundary."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("posting", nargs="?", help="Posting text/HTML file; omit for stdin")
    parser.add_argument("--html", action="store_true", help="Treat input as HTML")
    parser.add_argument("--json", action="store_true", help="Print findings JSON only")
    args = parser.parse_args()
    if args.posting:
        text = Path(args.posting).read_text(encoding="utf-8", errors="replace")
    else:
        text = sys.stdin.read()
    report = scan(text, args.html)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"Posting integrity: {report['verdict'].upper()}")
    print(f"  hidden blocks: {len(report['hidden_blocks'])}")
    print(f"  hidden-only URLs: {len(report['hidden_only_urls'])}")
    print(f"  invisible characters: {sum(report['invisible_characters'].values())}")
    print(f"  instruction-shaped lines: {len(report['instruction_shaped_lines'])}")
    print(f"  mixed-script words: {len(report['mixed_script_words'])}")
    print(report["note"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as error:
        raise SystemExit(f"Posting integrity failed: {error}") from error
