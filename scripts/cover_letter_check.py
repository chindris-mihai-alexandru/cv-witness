#!/usr/bin/env python3
"""Advisory cover-letter checks. No score, no truth verdict, no edits.

Catches the mechanical failures that get a short letter ignored: placeholder
markers, missing role/company, hype wording, and (with --eu-citizen) the costly
mistake of implying an EU/EEA applicant still needs a Danish work permit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

if __package__:
    from .cv_checks import CheckError, normalized_text, read_text, words
else:
    from cv_checks import CheckError, normalized_text, read_text, words

HYPE = ("passionate", "thrilled", "excited", "world-class", "cutting-edge",
        "leverage", "synergy", "rockstar", "guru", "dream job", "very excited",
        "i am writing to apply", "please accept my application", "to whom it may concern")
PLACEHOLDERS = ("[FILL:", "[TODO:", "{{")
FORBIDDEN_PUNCTUATION = re.compile(r"[–—“”‘’]")


def check_letter(text, role="", company="", eu_citizen=False, min_words=180,
                 max_words=450):
    lowered = normalized_text(text)
    flags = []
    count = len(words(text))
    if count < min_words or count > max_words:
        flags.append(f"length {count} words (advised {min_words}-{max_words})")
    for marker in PLACEHOLDERS:
        if marker.lower() in lowered:
            flags.append(f"unresolved placeholder {marker}")
    if role and normalized_text(role) not in lowered:
        flags.append(f"role '{role}' not mentioned")
    if company and normalized_text(company) not in lowered:
        flags.append(f"company '{company}' not mentioned")
    for word in HYPE:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            flags.append(f"hype wording: {word}")
    punctuation = sorted(set(FORBIDDEN_PUNCTUATION.findall(text)))
    if punctuation:
        labels = {"–": "en dash", "—": "em dash", "“": "left curly quote",
                  "”": "right curly quote", "‘": "left curly apostrophe",
                  "’": "right curly apostrophe"}
        flags.append("forbidden punctuation: " + ", ".join(labels.get(p, str(p)) for p in punctuation))
    if eu_citizen:
        if re.search(r"(?<!not )(?<!n't )(?:need|require|apply for)"
                     r"(?:\s+\w+){0,3}\s+work permit", lowered):
            flags.append("implies a work permit is needed; EU/EEA citizens do not need one")
        if re.search(r"not yet.{0,30}work permit|work permit.{0,30}not yet", lowered):
            flags.append("'not yet' contradicts EU/EEA right to work without a permit")
    return {"word_count": count, "flags": flags, "passed": not flags,
            "note": "Advisory lexical checks only: no ATS score, truth verdict or interview guarantee."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("letter", help="Cover letter PDF, UTF-8 text or Markdown")
    parser.add_argument("--role", default="", help="Role title expected in the letter")
    parser.add_argument("--company", default="", help="Company name expected in the letter")
    parser.add_argument("--eu-citizen", action="store_true",
                        help="Flag wording that implies a Danish work permit is needed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = check_letter(read_text(args.letter), args.role, args.company,
                              args.eu_citizen)
    except CheckError as error:
        print(f"cover-letter: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Words: {report['word_count']}")
        print("Flags: " + (", ".join(report["flags"]) or "none"))
        print(report["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
