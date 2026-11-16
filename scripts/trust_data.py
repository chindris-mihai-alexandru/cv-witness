#!/usr/bin/env python3
"""Employer-trust providers (EU-first).

The trust signal is fragmented across providers; no single EU-wide
employer-reputation API exists. This module is a provider layer, not a
dataset: each provider is queried live, and a provider that is unreachable
returns None so the caller reports the gap instead of inventing a verdict.

Providers:

  Hirelog        shared, evidence-backed hiring memory for job-search agents.
                 Live MCP endpoint (streamable HTTP); reads need no key.
                 Every note carries a kind, a status and a trust score, and
                 decays. A single observation is "unverified"; "corroborated"
                 means at least two confirmations and a score >= 2.0.
  Jobs Brief     hand-picked EU cloud/platform/SRE/AI-infra roles. A job
                 source, not an employer signal; documented so a curated-list
                 fetch can be added without a second implementation.

Figures, Ravio and levels.fyi are compensation platforms with no public API;
they are documented in ``comp_data`` and never queried here.

Nothing in this module invents a judgement: it returns what the provider said,
with the provider's own trust status attached.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

HIRELOG_URL = "https://hirelog.dev/mcp"

# Hirelog's own published threshold for "rely on it".
CORROBORATED_SCORE = 2.0


class TrustError(Exception):
    """Raised for input errors; network failures return None, never raise."""


def _post(url: str, payload: dict, timeout: int = 25,
          transport=None) -> dict | None:
    """POST a JSON-RPC envelope and return the parsed response, or None.

    ``transport`` is an injectable ``callable(payload) -> dict | None`` so the
    parsing and the gate logic can be tested without the network.
    """
    if transport is not None:
        return transport(payload)
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "User-Agent": "cv-witness/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None
    return _parse_envelope(body)


def _parse_envelope(body: str) -> dict | None:
    """Accept either a bare JSON envelope or an SSE stream carrying one."""
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _tool_call(name: str, arguments: dict, url: str, transport=None) -> dict | None:
    envelope = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}},
                     transport=transport)
    if not isinstance(envelope, dict):
        return None
    result = envelope.get("result")
    if not isinstance(result, dict):
        return None
    if result.get("isError"):
        return {"error": _first_text(result) or "tool returned an error"}
    text = _first_text(result)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


def _first_text(result: dict) -> str | None:
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            return first["text"]
    return None


def _normalise_notes(payload: dict) -> dict:
    """Flatten Hirelog's note list into the fields the gate needs."""
    notes = []
    for note in payload.get("notes", []) or []:
        if not isinstance(note, dict):
            continue
        trust = note.get("trust") or {}
        evidence = note.get("evidence") or {}
        notes.append({
            "kind": note.get("kind"),
            "status": note.get("status"),
            "text": note.get("text_en") or note.get("text"),
            "score": trust.get("score"),
            "confirms": trust.get("confirms"),
            "disputes": trust.get("disputes"),
            "freshness": trust.get("freshness"),
            "evidence": evidence.get("type"),
            "observed_at": evidence.get("observed_at"),
            "subject": (note.get("subject") or {}).get("name"),
        })
    return {"provider": "hirelog", "found": bool(payload.get("found")),
            "notes": notes}


def hirelog_company(name: str, transport=None) -> dict | None:
    """Hiring brief for one employer, from Hirelog. None when unreachable."""
    if not name or not name.strip():
        raise TrustError("company name is required")
    payload = _tool_call("hirelog_company", {"name": name.strip()},
                         HIRELOG_URL, transport=transport)
    if payload is None or "error" in payload:
        return None
    brief = _normalise_notes(payload)
    brief["hint"] = payload.get("hint")
    # A payload with neither "found" nor "notes" is not a brief; keep it so the
    # caller can show what the provider actually said instead of a silent empty.
    if "found" not in payload and "notes" not in payload:
        brief["raw"] = payload.get("text") or payload
    return brief


def hirelog_check_posting(url: str, company: str | None = None,
                          transport=None) -> dict | None:
    """Pre-application warnings for one posting URL, from Hirelog."""
    if not url or not url.strip():
        raise TrustError("posting url is required")
    arguments: dict = {"url": url.strip()}
    if company:
        arguments["company"] = company.strip()
    payload = _tool_call("hirelog_check_posting", arguments,
                         HIRELOG_URL, transport=transport)
    if payload is None or "error" in payload:
        return None
    return {"provider": "hirelog", "source": "check_posting", **payload}


def hirelog_search(query: str | None = None, kind: str | None = None,
                   region: str | None = None, limit: int = 10,
                   transport=None) -> dict | None:
    """Full-text search over Hirelog notes."""
    arguments: dict = {"limit": limit}
    if query:
        arguments["query"] = query
    if kind:
        arguments["kind"] = kind
    if region:
        arguments["region"] = region
    payload = _tool_call("hirelog_search", arguments, HIRELOG_URL,
                         transport=transport)
    if payload is None or "error" in payload:
        return None
    return {"provider": "hirelog", "source": "search", **payload}


def hirelog_market(slug: str, transport=None) -> dict | None:
    """Measured facts about a market segment, e.g. ``ai-engineering-europe``."""
    if not slug or not slug.strip():
        raise TrustError("market slug is required")
    payload = _tool_call("hirelog_market", {"slug": slug.strip()},
                         HIRELOG_URL, transport=transport)
    if payload is None or "error" in payload:
        return None
    return {"provider": "hirelog", "source": "market", **payload}


def actionable_notes(brief: dict | None, kinds: tuple[str, ...]) -> list[dict]:
    """Notes of the given kinds that Hirelog's own model says to rely on.

    "Rely on it" is the provider's published bar: status ``corroborated`` or a
    trust score at or above ``CORROBORATED_SCORE``. A single unverified
    observation is returned by ``all_notes`` instead, so it is visible without
    being treated as settled.
    """
    if not brief:
        return []
    out = []
    for note in brief.get("notes", []):
        if note.get("kind") not in kinds:
            continue
        # Accept both the flattened shape _normalise_notes produces and a raw
        # Hirelog note, where the score sits under "trust".
        trust = note.get("trust") or {}
        score = note.get("score", trust.get("score"))
        if note.get("status") == "corroborated" or (
                isinstance(score, (int, float)) and score >= CORROBORATED_SCORE):
            out.append(note)
    return out


def all_notes(brief: dict | None, kinds: tuple[str, ...]) -> list[dict]:
    """Every note of the given kinds, whatever its trust status."""
    if not brief:
        return []
    return [n for n in brief.get("notes", []) if n.get("kind") in kinds]


def provider_catalog() -> list[dict]:
    """Trust providers and how to reach them, for --help and SKILL.md."""
    return [
        {"name": "hirelog", "signal": "hiring facts, red flags, knockouts, pay bands",
         "access": "MCP (streamable HTTP)", "key": None, "scope": "EU-aware, global",
         "cost": "free reads / free key for writes"},
        {"name": "jobs-brief", "signal": "hand-picked EU cloud/platform/SRE/AI-infra roles",
         "access": "MCP", "key": None, "scope": "EU / Poland", "cost": "free",
         "wired": False},
        {"name": "kununu", "signal": "employer reviews and 14-factor scores (DACH)",
         "access": "Apify MCP / Scrappa REST", "key": "APIFY_TOKEN or SCRAPPA_KEY",
         "scope": "Germany, Austria, Switzerland", "cost": "paid"},
    ]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Look up employer-trust notes (EU-first)")
    ap.add_argument("--company", help="employer name, e.g. 'Example Energy'")
    ap.add_argument("--posting-url", help="job posting URL for pre-application warnings")
    ap.add_argument("--search", help="free-text search over notes")
    ap.add_argument("--kind", help="note kind, e.g. red_flag")
    ap.add_argument("--region", help="region filter, e.g. EU, DE, UK")
    ap.add_argument("--market", help="market segment slug, e.g. ai-engineering-europe")
    ap.add_argument("--actionable", action="store_true",
                    help="only notes Hirelog's model says to rely on")
    ap.add_argument("--catalog", action="store_true")
    args = ap.parse_args()

    if args.catalog:
        print(json.dumps(provider_catalog(), indent=2))
    elif args.company:
        brief = hirelog_company(args.company)
        notes = brief.get("notes", []) if brief else []
        if args.kind:
            notes = [n for n in notes if n["kind"] == args.kind]
        if args.actionable:
            notes = actionable_notes(brief, (args.kind or "red_flag",))
        print(json.dumps({"company": args.company, "notes": notes,
                          "hint": brief.get("hint") if brief else "provider unreachable"},
                         indent=2, ensure_ascii=False))
    elif args.posting_url:
        print(json.dumps(hirelog_check_posting(args.posting_url, args.company),
                         indent=2, ensure_ascii=False))
    elif args.search or args.kind or args.region:
        print(json.dumps(hirelog_search(args.search, args.kind, args.region),
                         indent=2, ensure_ascii=False))
    elif args.market:
        print(json.dumps(hirelog_market(args.market), indent=2, ensure_ascii=False))
    else:
        ap.print_help()
