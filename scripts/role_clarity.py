#!/usr/bin/env python3
"""Advisory six-point role-clarity check for one job posting.

Candidate-side port of career-ops' role-clarity helper. For six facts a
candidate needs before investing in interviews, report present/partial/missing
with an exact quoted substring from the posting. A separate soft-verb signal
lists wording that carries the weight of a duty without owning it. Advisory
only; it never changes the fit score and never sends anything.
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
import sys
from pathlib import Path

POINTS = {
    "supervisor": (
        r"(?:reports? to|reporting to|direct supervisor|line manager|department manager|"
        r"under the direction of|led by)[^\n.]{0,140}",
        r"(?:department|team you(?:'ll| will) join|"
        r"part of the (?:team|department|group|organisation|organization))[^\n.]{0,120}",
    ),
    "scope": (
        r"(?:scope of (?:work|the role)|key responsibilities|core responsibilities|"
        r"responsibilities include|you will (?:own|manage|build|develop|lead|maintain))[^\n.]{0,180}",
        r"(?:responsibilities|primary tasks|primary duties|what you(?:'ll| will) do)[^\n.]{0,140}",
    ),
    "deliverables": (
        r"(?:deliverables?|artifacts?|outputs?|what you(?:'ll| will) (?:build|deliver|ship|produce))[^\n.]{0,180}",
        r"(?:documentation|runbooks?|dashboards?|reports?|applications?)[^\n.]{0,140}",
    ),
    "success": (
        r"(?:success (?:measure|criteria|will be)|(?:measured|evaluated) by|KPIs?|OKRs?|"
        r"in the first (?:3|three|6|six) months|first (?:30|60|90) days)[^\n.]{0,180}",
        (r"(?:improve|increase|reduce|decrease|achieve)[^\n.]{0,140}"
         r"\b(?:uptime|latency|conversion|accuracy|quality|performance|retention|"
         r"cost|time|rate|target|metric|revenue|by\s+\d)\b"),
    ),
    "coordination": (
        r"(?:collaborat(?:e|ing|ion) with|coordinate(?:s|ing)? with|work(?:ing)? "
        r"(?:closely )?with|stakeholders?|cross-functional)[^\n.]{0,160}",
    ),
    "cadence": (
        r"(?:cadence|weekly|daily|sprint|stand-?up|review rhythm|"
        r"regular meetings?|monthly (?:meeting|review|sync|check-in|report))[^\n.]{0,140}",
    ),
}
QUESTION = {
    "supervisor": "Who does this role report to, and which department owns it?",
    "scope": "What work is in scope, and what is explicitly out of scope?",
    "deliverables": "What must this role deliver, and in what format?",
    "success": "How will success be measured in the first 3-6 months?",
    "coordination": "Which teams or people must this role coordinate with?",
    "cadence": "What is the delivery and review cadence?",
}
SOFT_VERBS = (
    "participate in", "support", "potential implementation", "other duties as assigned",
    "assist with", "contribute to", "help with", "may include", "could include",
)


MAX_QUOTE = 240


NOISE_LINE_RE = re.compile(
    r"(?:@context|outputFormat=|@media|text-align|font-family|font-size|"
    r"cookie preferences|accept all cookies|decline all non-necessary|"
    r"this website uses cookies|select which cookies)",
    re.I,
)


def _jsonld_description(line: str) -> str | None:
    """Return a JSON-LD job description as plain text, if this line has one."""
    stripped = line.strip()
    if not (stripped.startswith("{") and '"@context"' in stripped):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    description = payload.get("description")
    if not isinstance(description, str):
        return ""
    plain = html_module.unescape(re.sub(r"<[^>]+>", " ", description))
    return " ".join(plain.split())


def _candidate_text(text: str) -> str:
    """Drop raw HTML/CSS/JSON and cookie banners scraped with the job body.

    Postings are often saved by stripping tags from the whole page. Without
    this filter, role clarity quoted stylesheet and cookie text as job duties.
    The filter is deliberately conservative: it drops only lines carrying
    machine-readable or banner markers, not prose that merely mentions a
    monthly cadence or a team department.
    """
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        described = _jsonld_description(stripped)
        if described is not None:
            if described:
                lines.append(described)
            continue
        if NOISE_LINE_RE.search(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _placeholder_supervisor(value: str) -> bool:
    return bool(re.fullmatch(r"(?:reports? to|reporting to)?\s*(?:tbd|n/?a|the|a|team)[\s.!?]*", value, re.I))


def _first_quote(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    return " ".join(match.group(0).split())[:MAX_QUOTE]


def _sentence_at(text: str, position: int) -> str:
    start = max(text.rfind(".", 0, position), text.rfind("!", 0, position),
                text.rfind("?", 0, position), text.rfind("\n", 0, position)) + 1
    candidates = [text.find(mark, position) for mark in (".", "!", "?", "\n")]
    ends = [index for index in candidates if index != -1]
    end = min(ends) + 1 if ends else len(text)
    return text[start:end]


def analyze(text: str) -> dict:
    text = _candidate_text(text)
    if not text.strip():
        return {
            "status": "ok",
            "points": {name: {"status": "missing", "quote": None} for name in POINTS},
            "soft_verbs": {"count": 0, "heavy": False, "quotes": []},
            "askBeforeYouCommit": False,
            "questions": [],
            "note": "Empty posting: six-point shape retained, no questions inferred.",
        }
    points = {}
    for name, patterns in POINTS.items():
        strong = _first_quote(text, patterns[0])
        weak = _first_quote(text, patterns[1]) if len(patterns) > 1 else None
        if strong:
            status, quote = "present", strong
            if name == "supervisor" and not re.search(r"\bdepartment\b", quote, re.I):
                status = "partial"
            if name == "supervisor" and _placeholder_supervisor(quote or ""):
                status, quote = "missing", None
            if name == "success":
                quote_text = quote or ""
                sentence = _sentence_at(text, text.lower().find(quote_text[:40].lower()))
                if not (re.search(r"\b(?:first|within|in)\b[^.!?]{0,40}\b(?:3|three|6|six|30|60|90)\b", sentence, re.I)
                        and re.search(r"\b(?:measure|measured|success|kpi|okr|by)\b", sentence, re.I)):
                    status = "partial"
        elif weak:
            status, quote = "partial", weak
        else:
            status, quote = "missing", None
        points[name] = {"status": status, "quote": quote}

    soft = []
    for verb in SOFT_VERBS:
        match = re.search(re.escape(verb), text, re.I)
        if match:
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 60)
            soft.append(" ".join(text[start:end].split()))
    missing = [name for name, item in points.items() if item["status"] == "missing"]
    partial = [name for name, item in points.items() if item["status"] == "partial"]
    return {
        "status": "ok",
        "points": points,
        "soft_verbs": {"count": len(soft), "heavy": len(soft) >= 3, "quotes": soft},
        "askBeforeYouCommit": len(missing) >= 3,
        "questions": [QUESTION[name] for name in missing + partial],
        "note": ("Advisory lexical check, English only. 'present' means matching wording "
                 "exists; the reader still judges whether it is specific enough."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("posting", nargs="?", help="Posting text file; omit for stdin")
    parser.add_argument("--json", action="store_true", help="Print findings JSON only")
    args = parser.parse_args()
    text = (Path(args.posting).read_text(encoding="utf-8", errors="replace")
            if args.posting else sys.stdin.read())
    report = analyze(text)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    for name, item in report["points"].items():
        print(f"{name}: {item['status']}" + (f" — {item['quote']}" if item["quote"] else ""))
    print(f"soft verbs: {report['soft_verbs']['count']}"
          + (" (heavy)" if report["soft_verbs"]["heavy"] else ""))
    if report["askBeforeYouCommit"]:
        print("Ask before you commit:")
        for question in report["questions"]:
            print(f"  - {question}")
    print(report["note"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as error:
        raise SystemExit(f"Role clarity failed: {error}") from error
