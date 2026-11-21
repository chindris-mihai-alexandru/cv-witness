#!/usr/bin/env python3
"""Public footprint evidence: Hugging Face profile + GitHub PR verification.

One thin provider layer over tools the user already has installed. No API keys
are stored here: `hf` uses its own saved CLI login and `gh` uses the logged-in
account. This module never edits a profile, a repo or a CV - it only reads
public facts that the agent must still verify against foundation.md before a
claim reaches a CV.

Design: mirror comp_data.py / trust_data.py. A function returns structured data
and a clear `error` on failure; no transport is re-implemented, no result is
cached in a file keyed by position, and nothing is written to public artifacts.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


def _run(cmd, timeout=45):
    """Run a read-only CLI command; return (ok, parsed-or-text, error)."""
    exe = cmd[0]
    if not shutil.which(exe):
        return False, None, f"{exe} is not installed or not on PATH"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, None, f"{exe} command timed out after {timeout}s"
    if p.returncode != 0:
        return False, None, (p.stderr or p.stdout or f"{exe} exited {p.returncode}").strip()[:400]
    out = (p.stdout or "").strip()
    if not out:
        return True, [], None
    try:
        return True, json.loads(out), None
    except json.JSONDecodeError:
        return True, out, None


def hf_footprint(author, hf_bin="hf", limit=100):
    """Read a public HF profile's models, datasets, spaces and collections.

    Facts returned: repo ids, created/last-modified dates, library/pipeline
    tags, downloads (current + all-time), likes. These are evidence leads, not
    quality verdicts: low download counts are reported honestly and never
    inflated into popularity claims.
    """
    result = {"author": author, "models": [], "datasets": [], "spaces": [],
              "collections": [], "errors": []}
    queries = (
        ("models", ["models", "ls", "--author", author,
                    "--expand", "downloads,downloadsAllTime,likes,lastModified,library_name,pipeline_tag",
                    "--limit", str(limit), "--format", "json"]),
        ("datasets", ["datasets", "ls", "--author", author,
                      "--expand", "downloads,downloadsAllTime,likes,lastModified",
                      "--limit", str(limit), "--format", "json"]),
        ("spaces", ["spaces", "ls", "--author", author,
                    "--expand", "likes,lastModified,private",
                    "--limit", str(limit), "--format", "json"]),
        ("collections", ["collections", "ls", "--owner", author,
                         "--limit", str(limit), "--format", "json"]),
    )
    for key, args in queries:
        ok, data, err = _run([hf_bin] + args)
        if not ok:
            result["errors"].append(f"{key}: {err}")
            continue
        # A bare CLI may not support --format json; keep raw text but flag it.
        if isinstance(data, str):
            result["errors"].append(f"{key}: CLI returned non-JSON output; upgrade hf CLI")
            continue
        result[key] = data if isinstance(data, list) else []
    return result


def verify_pr(url, gh_bin="gh"):
    """Verify an external PR's real merge state. Returns merged true only on MERGED.

    A CLOSED PR with mergedAt=null was NOT merged and must never be cited as
    merged. This closes the manual-only rule in SKILL.md / AGENTS.md.
    """
    ok, data, err = _run([gh_bin, "pr", "view", url,
                          "--json", "number,state,mergedAt,title"])
    if not ok:
        return {"url": url, "merged": False, "state": None, "error": err}
    if not isinstance(data, dict):
        return {"url": url, "merged": False, "state": None, "error": "unexpected PR response"}
    state = data.get("state")
    merged = state == "MERGED" and bool(data.get("mergedAt"))
    return {"url": url, "merged": merged, "state": state,
            "merged_at": data.get("mergedAt"), "number": data.get("number"),
            "title": data.get("title"), "error": None}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hf", help="read a public Hugging Face footprint")
    p.add_argument("--author", required=True)
    p.add_argument("--hf-bin", default="hf")
    p.add_argument("--limit", type=int, default=100)
    p = sub.add_parser("verify-pr", help="verify a PR is actually MERGED")
    p.add_argument("url")
    p.add_argument("--gh-bin", default="gh")
    a = ap.parse_args()
    if a.cmd == "hf":
        out = hf_footprint(a.author, a.hf_bin, a.limit)
    else:
        out = verify_pr(a.url, a.gh_bin)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if not out.get("error") and not out.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
