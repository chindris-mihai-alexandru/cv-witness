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


# Block kinds whose bullets must follow the three-bullet contract.
CONTRACT_BLOCK_KINDS = ("role-sub", "project")


def count_block_bullets(source_html: str, kind: str) -> list[dict]:
    """Count <li> bullets inside every <ul class="kind"> of an HTML CV source.

    The rendered PDF text layer cannot reliably group bullets under their role
    or project heading, so the HTML template (the authoring input) is the
    deterministic ground truth for the bullet-count contract.
    """
    pattern = re.compile(
        rf'<ul class="{re.escape(kind)}">(.*?)</ul>', re.DOTALL)
    blocks = []
    for i, m in enumerate(pattern.finditer(source_html), start=1):
        li_count = len(re.findall(r"<li>", m.group(1)))
        blocks.append({"kind": kind, "index": i, "bullets": li_count})
    return blocks


def check_three_bullet_contract(source_html: str, min_bullets: int = 3,
                                max_bullets: int | None = None) -> list[dict]:
    """Return contract violations (blocks not within [min_bullets, max]).

    The house rule (verified with the user's own Wonsulting practice and the
    REA of their approved CVs) is exactly three evidence bullets per role and
    per project. min_bullets floors the count; max_bullets (default = min)
    caps it. Reads only the template's own <ul class="role-sub"> and
    <ul class="project"> blocks.
    """
    if max_bullets is None:
        max_bullets = min_bullets
    violations = []
    for kind in CONTRACT_BLOCK_KINDS:
        for block in count_block_bullets(source_html, kind):
            n = block["bullets"]
            if n < min_bullets or n > max_bullets:
                violations.append({**block, "min": min_bullets, "max": max_bullets})
    return violations


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
    ap.add_argument("--source-html", metavar="FILE",
                    help="HTML source of the CV; enforces the exactly-N-bullets "
                         "contract per role and per project (default min=max=3)")
    ap.add_argument("--bullets", type=int, default=3,
                    help="Bullets required per role/project block (default 3)")
    ap.add_argument("--max-bullets", type=int, default=None,
                    help="Upper bound per block (default: same as --bullets)")
    args = ap.parse_args()

    violations: list[dict] = []
    if args.source_html:
        try:
            src = read_text(args.source_html)
        except BulletAuditError as e:
            print(f"bullet-audit: {e}", file=sys.stderr)
            return 2
        violations = check_three_bullet_contract(src, args.bullets, args.max_bullets)
        if not args.json:
            print(f"=== BULLET CONTRACT: {len(violations)} block(s) outside "
                  f"{args.bullets}" + ("" if args.max_bullets is None
                                       else f"-{args.max_bullets}") + " bullets ===")
            for v in violations:
                print(f"  {v['kind']} block #{v['index']}: {v['bullets']} bullets")

    try:
        cv = read_text(args.cv)
    except BulletAuditError as e:
        print(f"bullet-audit: {e}", file=sys.stderr)
        return 2

    bullets = [b for b in find_bullets(cv) if len(b.split()) >= args.min_words]
    audited = [audit_bullet(b) for b in bullets]
    flagged = [a for a in audited if a["missing"]]

    if args.json:
        # One document, whatever combination of checks ran: contract +
        # bullet audit, each key absent when that check could not apply.
        report: dict = {}
        if args.source_html:
            report["contract"] = {"kind": "exact_per_block",
                                  "min": args.bullets,
                                  "max": args.max_bullets or args.bullets,
                                  "violations": violations}
        if bullets:
            report["summary"] = {"total": len(audited), "flagged": len(flagged)}
            report["bullets"] = audited
        else:
            report["summary"] = {"total": 0, "flagged": 0}
            report["bullets"] = []
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if not bullets:
            print("No bullets found at the requested length.")
        else:
            print(f"=== BULLET AUDIT: {len(flagged)} of {len(audited)} bullets flagged ===")
            for a in flagged:
                print(f"\n  missing: {', '.join(a['missing'])}")
                print(f"    starts with: '{a['first_word']}'")
                print(f"    {a['bullet'][:160]}")

    return 1 if (flagged or violations) else 0


if __name__ == "__main__":
    sys.exit(main())
