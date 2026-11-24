#!/usr/bin/env python3
"""Number fact gate: fail a CV whose numbers are absent from the approved sources.

Ported in spirit from career-ops (career-ops-hq/career-ops), whose generate-pdf
fact gate blocks a CV whose numbers appear in neither cv.md nor the article
digest. cv-witness keeps the same promise - "tailored CVs, nothing invented" -
so every number a tailored CV claims must trace to an approved source file,
typically foundation.md and provenance.md.

Run after rendering and before delivery:

    python3 scripts/check_cv_numbers.py rendered.pdf \
        --source foundation.md --source provenance.md

Exit 0 when every number is backed by a source; exit 1 listing each
unverified number with surrounding context. Numbers that are pure years
(1900-2099), single digits, or fragments of alphanumeric identifiers
(AIF-C01, ITIL 4) are not claims and are skipped.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

if __package__:
    from .cv_checks import CheckError, read_text
else:
    from cv_checks import CheckError, read_text

NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+)(?![\w.])")
CONTEXT_CHARS = 45

UNITS = {
    "": 1, "k": 1_000, "thousand": 1_000,
    "m": 1_000_000, "million": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000,
}
CURRENCY = {"$": "$", "us$": "$", "usd": "$", "dollar": "$", "dollars": "$",
            "€": "€", "eur": "€", "euro": "€", "euros": "€",
            "£": "£", "gbp": "£"}
COUNT_NOUNS = ("engineers", "people", "users", "interns", "mentees", "hires",
               "apprentices", "customers", "clients", "projects", "servers",
               "nodes", "models", "datasets", "spaces", "collections",
               "repositories", "volunteers")
NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
PERCENT_RE = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(?:%|per cent|percent|pct)(?![a-z])", re.I)
CURRENCY_PREFIX_RE = re.compile(
    r"(?<![\w])([$]|US[$]|USD|€|EUR|£|GBP)\s*"
    r"([0-9]+(?:[.,][0-9]+)?|\d+(?:\s\d{3})*)\s*"
    r"(k|thousand|m|million|b|billion|dollars?|euros?)?\b", re.I)
CURRENCY_SUFFIX_RE = re.compile(
    r"(?<![\w.])([0-9]+(?:[.,][0-9]+)?|\d+(?:\s\d{3})*)\s*"
    r"(k|thousand|m|million|b|billion)?\s*"
    r"(USD|EUR|GBP|dollars?|euros?|[$€£])", re.I)
NUMBER_WORD_PATTERN = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True) +
                              ["hundred", "thousand", "million", "billion"])
WORD_COUNT_RE = re.compile(
    r"\b((?:" + NUMBER_WORD_PATTERN + r")(?:[- ](?:" + NUMBER_WORD_PATTERN + r")){0,5})"
    r"\s+(" + "|".join(COUNT_NOUNS) + r")\b", re.I)
DIGIT_COUNT_RE = re.compile(
    r"(?<![\w.])(\d+(?:[.,]\d+)?[km]?)\s+(" + "|".join(COUNT_NOUNS) + r")\b", re.I)
MULTIPLIER_RE = re.compile(
    r"(?<![\w.])(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"\s*(x|-?fold)\b", re.I)


def normalize(number_text):
    """Normalize a matched number for comparison: drop grouping commas."""
    return number_text.replace(",", "")


def is_claim(number_text):
    """Whether a matched number is a claim the sources must back."""
    value = normalize(number_text)
    if len(value) == 1:
        return False
    if value.isdigit() and 1900 <= int(value) <= 2099:
        return False
    return True


def _decimal(raw, trailing_separator=False):
    """Parse a numeric string, tolerating thousands spaces and EU decimals."""
    value = unicodedata.normalize("NFKC", raw).replace(" ", "").strip()
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            return float(value.replace(".", "").replace(",", "."))
        return float(value.replace(",", ""))
    if "," in value:
        parts = value.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and not trailing_separator:
            return float(value.replace(",", ""))
        return float(value.replace(",", "."))
    if trailing_separator and "." in value:
        parts = value.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            return float(value.replace(".", ""))
    return float(value)


def _scale(value):
    key = (value or "").casefold()
    if key in ("thousand", "k"):
        return 1_000, "k"
    if key in ("million", "m"):
        return 1_000_000, "m"
    if key in ("billion", "b"):
        return 1_000_000_000, "b"
    return 1, None


def _format_number(value, suffix=None):
    if suffix:
        scaled = value / UNITS[suffix]
        text = ("%g" % scaled)
        return text + suffix
    text = "%g" % value
    return text


def _words_to_number(phrase):
    tokens = unicodedata.normalize("NFKD", phrase.casefold()).replace("-", " ").split()
    total = current = 0
    for token in tokens:
        if token in NUMBER_WORDS:
            current += NUMBER_WORDS[token]
        elif token == "hundred":
            current = (current or 1) * 100
        elif token in ("thousand", "million", "billion"):
            multiplier = {"thousand": 1_000, "million": 1_000_000,
                          "billion": 1_000_000_000}[token]
            total += (current or 1) * multiplier
            current = 0
        else:
            return None
    return total + current


def canonical_claims(text, min_digits=2):
    """Yield (canonical form, start, end) for claims in any supported spelling."""
    found = []
    for match in NUMBER_PATTERN.finditer(text):
        raw = match.group(1)
        if is_claim(raw) and len(normalize(raw)) >= min_digits:
            found.append((normalize(raw), match.start(), match.end()))
    for match in PERCENT_RE.finditer(text.replace("\\%", "%")):
        value = _decimal(match.group(1))
        found.append((_format_number(value) + "%", match.start(), match.end()))
    for regex in (CURRENCY_PREFIX_RE, CURRENCY_SUFFIX_RE):
        for match in regex.finditer(text):
            if regex is CURRENCY_PREFIX_RE:
                symbol, raw, scale_word = match.group(1), match.group(2), match.group(3)
            else:
                raw, scale_word, symbol = match.group(1), match.group(2), match.group(3)
            symbol_raw = match.group(1 if regex is CURRENCY_PREFIX_RE else 3)
            code = symbol.casefold()
            if symbol_raw.isalpha() and symbol_raw != symbol_raw.upper() and \
                    code not in ("dollar", "dollars", "euro", "euros"):
                continue
            if code not in CURRENCY:
                continue
            factor, suffix = _scale(scale_word)
            if suffix is None and scale_word in ("dollars", "dollar", "euros", "euro"):
                factor, suffix = 1, None
            value = _decimal(raw, trailing_separator=symbol in ("€", "£")) * factor
            found.append((CURRENCY[code] + _format_number(value, suffix),
                          match.start(), match.end()))
    for match in WORD_COUNT_RE.finditer(text):
        value = _words_to_number(match.group(1))
        if value is None or value == 1:
            continue
        suffix = "m" if value >= 1_000_000 else "k" if value >= 1_000 and value % 1_000 == 0 else None
        found.append((_format_number(value, suffix) + " " + match.group(2).casefold(),
                      match.start(), match.end()))
    for match in DIGIT_COUNT_RE.finditer(text):
        raw = match.group(1)
        marker = raw[-1:].casefold()
        base = raw[:-1] if marker in ("k", "m") else raw
        factor = 1_000 if marker == "k" else 1_000_000 if marker == "m" else 1
        value = _decimal(base) * factor
        suffix = marker if marker in ("k", "m") else None
        found.append((_format_number(value, suffix) + " " + match.group(2).casefold(),
                      match.start(), match.end()))
    for match in MULTIPLIER_RE.finditer(text):
        raw = match.group(1).casefold()
        value = _words_to_number(raw) if raw in NUMBER_WORDS else _decimal(raw)
        if value is None or value < 4:
            continue
        found.append((_format_number(value) + "x", match.start(), match.end()))
    specialized = [(start, end) for form, start, end in found
                   if not re.fullmatch(r"\d+(?:\.\d+)?", form)]
    found = [item for item in found
             if not (re.fullmatch(r"\d+(?:\.\d+)?", item[0]) and
                     any(item[1] >= start and item[2] <= end
                         for start, end in specialized))]
    return found


def collect_unverified(text, source_texts, min_digits):
    """Yield (claim, context) for every claim missing from all sources."""
    source_claims = set()
    for source in source_texts:
        source_claims.update(form for form, _, _ in canonical_claims(source, min_digits))
    seen = set()
    for form, start, end in canonical_claims(text, min_digits):
        if form in source_claims or form in seen:
            continue
        seen.add(form)
        context_start = max(0, start - CONTEXT_CHARS)
        context_end = min(len(text), end + CONTEXT_CHARS)
        context = " ".join(text[context_start:context_end].split())
        yield form, context


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cv", help="Rendered CV (PDF) or extracted text file")
    parser.add_argument("--source", action="append", default=[],
                        metavar="FILE",
                        help="Approved source file; repeat for each source")
    parser.add_argument("--min-digits", type=int, default=2,
                        help="Smallest digit count treated as a claim (default 2)")
    args = parser.parse_args(argv)

    if not args.source:
        raise CheckError("Select at least one approved source with --source.")

    cv_text = read_text(args.cv)
    source_texts = [read_text(Path(source), pdf_allowed=False)
                    for source in args.source]

    unverified = list(collect_unverified(cv_text, source_texts,
                                         args.min_digits))
    if unverified:
        print(f"FAILED: {len(unverified)} number(s) not backed by the "
              f"{len(args.source)} approved source(s):")
        for value, context in unverified:
            print(f"  {value}\n      ...{context}...")
        sys.exit(1)

    print(f"Number gate passed: every claim traces to the approved sources "
          f"({len(args.source)} file(s)).")


if __name__ == "__main__":
    try:
        main()
    except CheckError as error:
        print(f"check-cv-numbers: {error}", file=sys.stderr)
        sys.exit(2)