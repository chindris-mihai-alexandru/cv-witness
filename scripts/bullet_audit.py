#!/usr/bin/env python3
"""Bullet audit: check CV bullets for the Action + Metric + Tool pattern.

Recruiters and AI screeners look for evidence, not duties: what you did (action),
at what scale (metric), with what (tool). A bullet that lacks any of the three is
a duty statement, not evidence. This script flags those bullets so they can be
rewritten before submission.

The check is lexical. It reports candidates for review; it does not judge meaning.

Usage:
    python3 scripts/bullet_audit.py CV.pdf
    python3 scripts/bullet_audit.py CV.pdf --json
    python3 scripts/bullet_audit.py CV.pdf --min-words 8

Exit codes:
    0 - every bullet has all three elements (or no bullets found)
    1 - at least one bullet is missing an element
    2 - input or tool error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class BulletAuditError(Exception):
    """Raised for input or tool failures."""


# Action verbs that signal owned work rather than exposure.
ACTION_VERBS = {
    "accelerated", "achieved", "added", "automated", "built", "cut", "delivered",
    "deployed", "designed", "developed", "drove", "eliminated", "enabled",
    "engineered", "established", "expanded", "generated", "grew", "headed",
    "implemented", "improved", "increased", "integrated", "introduced",
    "launched", "led", "maintained", "managed", "migrated", "modernized",
    "negotiated", "optimised", "optimized", "owned", "pioneered", "produced",
    "programmed", "prototyped", "reduced", "refactored", "released", "replaced",
    "resolved", "revamped", "scaled", "shipped", "simplified", "solved",
    "streamlined", "supported", "trained", "validated", "verified", "wrote",
    "acted", "covered", "monitored", "coordinated", "mentored", "documented",
    "tested", "audited", "hardened", "instrumented", "measured", "published",
}

DUTY_VERBS = {
    "assisted", "collaborated", "contributed", "helped", "participated",
    "responsible", "worked", "supported", "provided", "used", "utilised",
    "utilized", "involved", "handled", "dealt", "performed", "served",
    "spent", "familiar", "exposure", "various", "several", "multiple",
    "duties", "included", "including", "daily", "regular", "routine",
}

METRIC_RE = re.compile(
    r"(\d[\d,.]*\s*%|\d[\d,.]*\s*(?:x|k|m|thousand|million|billion)"
    r"|\b\d[\d,]*\b|\b(?:above|below|over|under|up\s+to|at\s+least|more\s+than|"
    r"less\s+than|no\s+more\s+than)\s+\d|\d+\+)"
)

TOOL_RE = re.compile(
    r"\b(?:Python|JavaScript|TypeScript|Java|C\+\+|C#|Go|Golang|Rust|Ruby|PHP|"
    r"Kotlin|Swift|R|SQL|NoSQL|PostgreSQL|MySQL|MongoDB|Redis|Elasticsearch|"
    r"AWS|Azure|GCP|Docker|Kubernetes|Terraform|Ansible|Jenkins|GitLab|GitHub|"
    r"CI/CD|Kafka|RabbitMQ|GraphQL|REST|gRPC|React|Vue|Angular|Next\.js|"
    r"Node\.js|FastAPI|Django|Flask|Spring|\.NET|Linux|Bash|PowerShell|"
    r"Prometheus|Grafana|Datadog|Splunk|AppDynamics|Sentry|New\s+Relic|"
    r"Terraform|Helm|OCM|Open\s+Cloud\s+Mesh|Azure\s+DevOps|Postman|Newman|"
    r"Jira|Confluence|Figma|SAP|Pentaho|IPFS|Stripe|AdalFlow|Pydantic)\b",
    re.I,
)


def read_text(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise BulletAuditError(f"File not found: {path}")
    if p.suffix.lower() == ".pdf":
        try:
            # -layout preserves the indentation that distinguishes bullets
            # from headings and flush-left body text.
            r = subprocess.run(["pdftotext", "-layout", path, "-"],
                               capture_output=True, text=True, check=False)
        except OSError as e:
            raise BulletAuditError(f"pdftotext failed: {e}") from e
        return r.stdout
    return p.read_text(encoding="utf-8", errors="replace")


def find_bullets(cv: str) -> list[str]:
    """Extract bullet lines from a CV text layer.

    PDF text extraction wraps bullets across lines, so consecutive indented
    lines are joined into one bullet before the marker is stripped.
    """
    raw_lines = cv.split("\n")
    bullets: list[str] = []
    buffer = ""
    in_scope = False

    def flush():
        nonlocal buffer
        if buffer and in_scope:
            cleaned = re.sub(r"^[\s•·▪‣·*-]+\s*", "", buffer)
            if len(cleaned.split()) >= 4:
                bullets.append(cleaned)
        buffer = ""

    for line in raw_lines:
        indented = line.startswith((" ", "\t", "  "))
        stripped = line.strip()

        # Only audit bullets in the experience / projects sections. The header
        # (name + contact) and the certifications list are indented too, but
        # they are not evidence bullets. Flush the pending bullet BEFORE the
        # heading changes scope, or the last out-of-scope bullet would leak in.
        is_heading = bool(re.fullmatch(r"[A-Z][A-Z\s/&()-]{3,}", stripped))
        if is_heading:
            flush()
            in_scope = bool(re.search(r"EXPERIENCE|PROJECT", stripped, re.I))

        if not stripped:
            flush()
            continue

        if indented:
            buffer = f"{buffer} {stripped}".strip()
        else:
            # Headings, dates, employer names, summary and skills lines sit at
            # the left margin and are not bullets.
            flush()

    flush()
    return bullets


def audit_bullet(bullet: str) -> dict:
    """Return the elements present and missing in one bullet."""
    first = re.split(r"[\s,;:(]+", bullet.strip().lower(), maxsplit=1)
    first_word = first[0].strip(".,;:") if first else ""

    has_action = first_word in ACTION_VERBS
    has_metric = bool(METRIC_RE.search(bullet))
    has_tool = bool(TOOL_RE.search(bullet))
    has_duty_verb = any(re.search(rf"\b{re.escape(v)}\b", bullet, re.I) for v in DUTY_VERBS)

    missing = []
    if not has_action:
        missing.append("action")
    if not has_metric:
        missing.append("metric")
    if not has_tool:
        missing.append("tool")

    return {
        "bullet": bullet,
        "first_word": first_word,
        "action": has_action,
        "metric": has_metric,
        "tool": has_tool,
        "duty_language": has_duty_verb,
        "missing": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit CV bullets for Action + Metric + Tool")
    ap.add_argument("cv", help="CV file (PDF or text)")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    ap.add_argument("--min-words", type=int, default=8,
                    help="Only audit bullets with at least this many words (default 8)")
    args = ap.parse_args()

    try:
        cv = read_text(args.cv)
    except BulletAuditError as e:
        print(f"bullet-audit: {e}", file=sys.stderr)
        return 2

    bullets = [b for b in find_bullets(cv) if len(b.split()) >= args.min_words]
    if not bullets:
        msg = "No bullets found at the requested length."
        if args.json:
            print(json.dumps({"bullets": [], "summary": {"total": 0, "flagged": 0}}, indent=2))
        else:
            print(msg)
        return 0

    audited = [audit_bullet(b) for b in bullets]
    flagged = [a for a in audited if a["missing"]]

    if args.json:
        print(json.dumps({
            "summary": {"total": len(audited), "flagged": len(flagged)},
            "bullets": audited,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"=== BULLET AUDIT: {len(flagged)} of {len(audited)} bullets flagged ===")
        for a in flagged:
            print(f"\n  missing: {', '.join(a['missing'])}")
            print(f"    starts with: '{a['first_word']}'")
            print(f"    {a['bullet'][:160]}")

    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
