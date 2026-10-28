#!/usr/bin/env python3
"""Grounded fit scorer: combine per-criterion judgments into an inspectable fit band.

The judge (an agent session, a local model or a hosted decision model) answers one
narrow question per criterion against described levels. This script owns everything
that should not be left to a model: weights, hard gates, experience arithmetic,
evidence verification, uncertainty and the final band. See docs/fit-scoring.md.
The result is triage for deciding where to spend effort, not an ATS score.
"""

import argparse
import datetime
import json
import math
import re
import sys

if __package__:
    from .cv_checks import CheckError, load_json, read_text, words
else:
    from cv_checks import CheckError, load_json, read_text, words

MAX_JSON_BYTES = 1024 * 1024
MAX_CRITERIA = 30
MAX_RANGES = 50
ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
CONFIDENCE_LABELS = {"high": 0.9, "medium": 0.6, "low": 0.3}
UNGROUNDED_CAP = 0.4
MIN_QUOTE_WORDS, MAX_QUOTE_WORDS = 4, 60
DEFAULT_BANDS = (80.0, 65.0, 50.0)
BAND_NAMES = ("great", "good", "fair", "bad")
DISCLAIMER = ("Triage signal from a judge's answers and verified evidence. Bands are uncalibrated "
              "defaults, not an ATS score, ranking or hiring prediction.")


def number(value, what, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or not low <= value <= high:
        raise CheckError(f"{what} must be a number from {low:g} to {high:g}.")
    return float(value)


def text(value, what, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise CheckError(f"{what} must be a nonempty string of at most {limit} characters.")


def only_keys(item, allowed, what):
    if not isinstance(item, dict) or set(item) - set(allowed):
        raise CheckError(f"{what} must be an object with only the documented fields.")


def parse_criteria(data):
    only_keys(data, ("schema_version", "role", "criteria"), "Criteria file")
    if data.get("schema_version") != 1:
        raise CheckError("Criteria file needs schema_version 1.")
    items = data.get("criteria")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CRITERIA:
        raise CheckError(f"Provide between 1 and {MAX_CRITERIA} criteria.")
    criteria, seen = [], set()
    for position, item in enumerate(items, 1):
        only_keys(item, ("id", "weight", "gate_min", "question", "levels", "min_years"), f"Criterion {position}")
        cid = item.get("id")
        if not isinstance(cid, str) or not ID.match(cid) or cid in seen:
            raise CheckError(f"Criterion {position} needs a unique id of lowercase letters, digits and underscores.")
        seen.add(cid)
        weight = number(item.get("weight"), f"Weight of {cid}", 0, 1000)
        gate = item.get("gate_min")
        gate = None if gate is None else number(gate, f"Gate of {cid}", 0.01, 1)
        if weight == 0 and gate is None:
            raise CheckError(f"Criterion {cid} has zero weight and no gate.")
        if ("levels" in item) == ("min_years" in item):
            raise CheckError(f"Criterion {cid} needs exactly one of levels or min_years.")
        entry = {"id": cid, "weight": weight, "gate_min": gate}
        if "min_years" in item:
            entry["min_years"] = number(item["min_years"], f"Minimum years of {cid}", 0.5, 50)
        else:
            text(item.get("question"), f"Question of {cid}", 400)
            levels = item["levels"]
            if not isinstance(levels, list) or not 2 <= len(levels) <= 10:
                raise CheckError(f"Criterion {cid} needs between 2 and 10 described levels.")
            for level in levels:
                text(level, f"A level of {cid}", 300)
            entry["levels"] = len(levels)
        criteria.append(entry)
    if sum(entry["weight"] for entry in criteria) <= 0:
        raise CheckError("At least one criterion needs a positive weight.")
    return criteria


def parse_judgments(data, criteria):
    only_keys(data, ("schema_version", "judge", "judgments"), "Judgments file")
    if data.get("schema_version") != 1 or not isinstance(data.get("judgments"), dict):
        raise CheckError("Judgments file needs schema_version 1 and a judgments object.")
    by_id = {entry["id"]: entry for entry in criteria}
    for cid in data["judgments"]:
        if cid not in by_id:
            raise CheckError("A judgment refers to a criterion that does not exist.")
        if "min_years" in by_id[cid]:
            raise CheckError(f"Criterion {cid} is computed in code and must not be judged.")
    return data["judgments"]


def distribution(cid, judgment, levels):
    """Return (probability per level, confidence) for one judgment."""
    only_keys(judgment, ("level", "probabilities", "confidence", "evidence"), f"Judgment {cid}")
    if ("level" in judgment) == ("probabilities" in judgment):
        raise CheckError(f"Judgment {cid} needs exactly one of level or probabilities.")
    if "probabilities" in judgment:
        if "confidence" in judgment:
            raise CheckError(f"Judgment {cid}: confidence is derived from probabilities.")
        raw = judgment["probabilities"]
        if not isinstance(raw, list) or len(raw) != levels:
            raise CheckError(f"Judgment {cid} needs one probability per level.")
        probabilities = [number(value, f"A probability in {cid}", 0, 1) for value in raw]
        total = sum(probabilities)
        if abs(total - 1) > 0.02:
            raise CheckError(f"Probabilities in {cid} must sum to 1.")
        probabilities = [value / total for value in probabilities]
        entropy = -sum(value * math.log(value) for value in probabilities if value > 0)
        return probabilities, 1 - entropy / math.log(levels)
    level = judgment["level"]
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level < levels:
        raise CheckError(f"Level in {cid} must be a whole number within the criterion's levels.")
    confidence = judgment.get("confidence")
    confidence = CONFIDENCE_LABELS.get(confidence) if isinstance(confidence, str) else \
        number(confidence, f"Confidence in {cid}", 0, 1)
    if confidence is None:
        raise CheckError(f"Confidence in {cid} must be high, medium, low or a number from 0 to 1.")
    probabilities = [(1 - confidence) / (levels - 1)] * levels
    probabilities[level] = confidence
    return probabilities, confidence


def moments(probabilities):
    top = len(probabilities) - 1
    mean = sum(p * i / top for i, p in enumerate(probabilities))
    variance = sum(p * (i / top - mean) ** 2 for i, p in enumerate(probabilities))
    return mean, variance


def padded(token_list):
    return " " + " ".join(token_list) + " "


def check_evidence(evidence, sources):
    """Count quotes found verbatim (token-wise) in the approved evidence sources."""
    if evidence is None:
        evidence = []
    if not isinstance(evidence, list) or len(evidence) > 10:
        raise CheckError("Evidence must be a list of at most 10 quotes.")
    verified = unverified = 0
    for quote in evidence:
        if not isinstance(quote, str):
            raise CheckError("Each evidence quote must be a string.")
        tokens = words(quote)
        found = MIN_QUOTE_WORDS <= len(tokens) <= MAX_QUOTE_WORDS and any(padded(tokens) in s for s in sources)
        verified, unverified = verified + found, unverified + (not found)
    return verified, unverified


def month_index(value, what):
    match = MONTH.match(value)
    if not match:
        raise CheckError(f"{what} must look like YYYY-MM.")
    return int(match[1]) * 12 + int(match[2]) - 1


def experience_months(ranges, today):
    """Months covered by inclusive YYYY-MM:YYYY-MM|present ranges; overlaps counted once."""
    if len(ranges) > MAX_RANGES:
        raise CheckError(f"Provide at most {MAX_RANGES} experience ranges.")
    now = today.year * 12 + today.month - 1
    spans = []
    for value in ranges:
        start_text, separator, end_text = value.partition(":")
        if not separator:
            raise CheckError("Experience ranges must look like YYYY-MM:YYYY-MM or YYYY-MM:present.")
        start = month_index(start_text, "A range start")
        end = now if end_text == "present" else month_index(end_text, "A range end")
        if start > end:
            raise CheckError("A range starts after it ends.")
        if start <= now:
            spans.append((start, min(end, now)))
    total, current = 0, None
    for start, end in sorted(spans):
        if current and start <= current[1] + 1:
            current[1] = max(current[1], end)
        else:
            total += current[1] - current[0] + 1 if current else 0
            current = [start, end]
    return total + (current[1] - current[0] + 1 if current else 0)


def band_of(value, bands):
    return next((name for name, floor in zip(BAND_NAMES, bands) if value >= floor), BAND_NAMES[-1])


def assess(criterion, judgments, sources, months):
    """Return the scored row for one criterion (assessed False when no input exists)."""
    row = {"id": criterion["id"], "weight": criterion["weight"], "assessed": False}
    if "min_years" in criterion:
        if months is not None:
            row.update(assessed=True, mean=min(1.0, months / (criterion["min_years"] * 12)), variance=0.0,
                       confidence=1.0, grounded=True, verified_quotes=0, unverified_quotes=0, capped=False)
        return row
    judgment = judgments.get(criterion["id"])
    if judgment is None:
        return row
    probabilities, confidence = distribution(criterion["id"], judgment, criterion["levels"])
    mean, variance = moments(probabilities)
    verified, unverified = check_evidence(judgment.get("evidence"), sources)
    capped = mean > UNGROUNDED_CAP and not verified
    row.update(assessed=True, mean=UNGROUNDED_CAP if capped else mean, variance=variance,
               confidence=confidence, grounded=bool(verified) or mean <= UNGROUNDED_CAP,
               verified_quotes=verified, unverified_quotes=unverified, capped=capped)
    return row


def score(criteria_doc, judgments_doc, evidence_paths, experience=(), today=None,
          bands=DEFAULT_BANDS, min_coverage=0.6):
    criteria = parse_criteria(criteria_doc)
    judgments = parse_judgments(judgments_doc, criteria)
    if not evidence_paths:
        raise CheckError("Provide at least one approved evidence file.")
    sources = [padded(words(read_text(path, pdf_allowed=False))) for path in evidence_paths]
    months = experience_months(list(experience), today or datetime.date.today()) if experience else None
    rows = [assess(entry, judgments, sources, months) for entry in criteria]
    for entry, row in zip(criteria, rows):
        row["gate_min"] = entry["gate_min"]
    assessed = [row for row in rows if row["assessed"]]
    total_weight = sum(row["weight"] for row in rows)
    assessed_weight = sum(row["weight"] for row in assessed)
    coverage = assessed_weight / total_weight
    blocked = [row["id"] for row in assessed if row["gate_min"] is not None and row["mean"] < row["gate_min"]]
    gate_unassessed = any(row["gate_min"] is not None and not row["assessed"] for row in rows)
    reasons = {reason for row in assessed for reason, flag in
               (("ungrounded_claim", row["capped"]), ("unverified_quote", row["unverified_quotes"]))
               if flag}
    value = spread = None
    if assessed_weight > 0:
        value = 100 * sum(row["weight"] * row["mean"] for row in assessed) / assessed_weight
        spread = 100 * math.sqrt(sum((row["weight"] / assessed_weight) ** 2 * row["variance"] for row in assessed))
    low = None if value is None else max(0.0, value - spread)
    high = None if value is None else min(100.0, value + spread)
    if blocked:
        verdict = "blocked"
    elif value is None or coverage < min_coverage or gate_unassessed:
        verdict = "insufficient_evidence"
    else:
        verdict = band_of(value, bands)
        if band_of(low, bands) != band_of(high, bands):
            reasons.add("range_crosses_band")
    settled = verdict in BAND_NAMES
    present = lambda number_: None if number_ is None else round(number_, 1)
    return {
        "verdict": verdict,
        "score": present(value) if settled else None,
        "partial_score": None if settled else present(value),
        "range": [present(low), present(high)] if value is not None else None,
        "needs_review": bool(reasons) or verdict == "insufficient_evidence",
        "review_reasons": sorted(reasons),
        "coverage": round(coverage, 3),
        "blocked_by": blocked,
        "not_assessed": [row["id"] for row in rows if not row["assessed"]],
        "strengths": [row["id"] for row in assessed if row["mean"] >= 0.7],
        "gaps": [row["id"] for row in sorted(assessed, key=lambda r: -r["weight"]) if row["mean"] < 0.5],
        "breakdown": [{"id": row["id"], "weight_share": round(row["weight"] / total_weight, 3),
                       "score": present(100 * row["mean"]) if row["assessed"] else None,
                       "confidence": round(row["confidence"], 2) if row["assessed"] else None,
                       "grounded": row["grounded"] if row["assessed"] else None,
                       "verified_quotes": row.get("verified_quotes"), "unverified_quotes": row.get("unverified_quotes")}
                      for row in rows],
        "bands": dict(zip(BAND_NAMES[:3], bands)),
        "disclaimer": DISCLAIMER,
    }


def parse_bands(value):
    try:
        bands = tuple(float(part) for part in value.split(","))
    except ValueError as error:
        raise CheckError("Bands must be three comma-separated numbers.") from error
    if len(bands) != 3 or not all(0 < b <= 100 for b in bands) or not bands[0] > bands[1] > bands[2]:
        raise CheckError("Bands must be three descending numbers within 0-100, e.g. 80,65,50.")
    return bands


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("criteria", help="Criteria JSON built from the posting")
    parser.add_argument("judgments", help="Judgments JSON produced by the judge")
    parser.add_argument("--evidence", action="append", required=True, metavar="FILE",
                        help="Approved evidence file (.md/.txt) used to verify quotes; repeatable")
    parser.add_argument("--experience", action="append", default=[], metavar="YYYY-MM:YYYY-MM|present",
                        help="Counted experience range for min_years criteria; repeatable, overlaps merge")
    parser.add_argument("--today", help="Override today's date (YYYY-MM-DD) for reproducible runs")
    parser.add_argument("--bands", default="80,65,50", help="great,good,fair floors (default 80,65,50)")
    parser.add_argument("--min-coverage", type=float, default=0.6,
                        help="Minimum assessed weight share before a band is given (default 0.6)")
    args = parser.parse_args(argv)
    try:
        if not 0 < args.min_coverage <= 1:
            raise CheckError("Minimum coverage must be above 0 and at most 1.")
        try:
            today = datetime.date.fromisoformat(args.today) if args.today else None
        except ValueError as error:
            raise CheckError("Today must be a date like 2026-10-28.") from error
        result = score(load_json(args.criteria, "criteria", MAX_JSON_BYTES),
                       load_json(args.judgments, "judgments", MAX_JSON_BYTES),
                       args.evidence, args.experience, today, parse_bands(args.bands), args.min_coverage)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except CheckError as error:
        print("fit-score: " + str(error), file=sys.stderr)
    except OSError:
        print("fit-score: Local file operation failed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())