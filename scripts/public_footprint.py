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
        pass
    # Edge case: some CLI versions print an update/new-version banner to stdout
    # before the JSON. Recover the payload from the first JSON opener instead of
    # throwing away every repo (a "non-JSON output" error lost all HF evidence).
    for i, ch in enumerate(out):
        if ch in "[{":
            try:
                return True, json.loads(out[i:]), None
            except json.JSONDecodeError:
                break
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


def gh_pr_summary(author, gh_bin="gh", exclude_prefixes=None):
    """Live, verifiable PR counts for a GitHub author via the search API.

    Returns authored/merged totals and, when exclude_prefixes is given, a
    precise external-only merged count with the repo breakdown. This gives
    provenance files a refresh path instead of stale hand-counted numbers.
    """
    exclude_prefixes = [p.lower().rstrip("/") + "/" for p in (exclude_prefixes or [])]
    result = {"author": author, "authored": None, "merged": None,
              "external_merged": None, "external_repos": {}, "error": None}

    def total(query):
        ok, data, err = _run([gh_bin, "api",
                              f"search/issues?q={query}&per_page=1"], timeout=60)
        if not ok:
            raise RuntimeError(err)
        if not isinstance(data, dict) or "total_count" not in data:
            raise RuntimeError("unexpected search response")
        return data["total_count"]

    try:
        result["authored"] = total(f"author:{author}+type:pr")
        result["merged"] = total(f"author:{author}+type:pr+is:merged")
        # Only enumerate repos when the caller wants an external split.
        if exclude_prefixes:
            merged = []
            for page in range(1, 6):  # cap at 500 PRs; report if truncated
                ok, data, err = _run([gh_bin, "api",
                                      f"search/issues?q=author:{author}+type:pr+is:merged"
                                      f"&per_page=100&page={page}"], timeout=60)
                if not ok or not isinstance(data, dict):
                    raise RuntimeError(err or "unexpected search response")
                items = data.get("items", [])
                merged += items
                if len(merged) >= data.get("total_count", 0) or not items:
                    break
            repos = {}
            for pr in merged:
                url = pr.get("html_url", "")
                repo = url.split("github.com/")[-1].split("/pull/")[0] if "github.com/" in url else "?"
                repos[repo] = repos.get(repo, 0) + 1
            external = {r: n for r, n in repos.items()
                        if not any(r.lower().startswith(p) for p in exclude_prefixes)}
            result["external_repos"] = external
            result["external_merged"] = sum(external.values())
            if len(merged) >= 500:
                result["error"] = "merged list truncated at 500; external count may be low"
    except RuntimeError as e:
        result["error"] = str(e)
    return result


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
    p = sub.add_parser("pr-summary", help="live PR counts + external merged split")
    p.add_argument("--author", required=True)
    p.add_argument("--gh-bin", default="gh")
    p.add_argument("--exclude-repo", action="append", default=[],
                   help="repo prefix to exclude from external split (repeatable)")
    a = ap.parse_args()
    if a.cmd == "hf":
        out = hf_footprint(a.author, a.hf_bin, a.limit)
    elif a.cmd == "verify-pr":
        out = verify_pr(a.url, a.gh_bin)
    else:
        out = gh_pr_summary(a.author, a.gh_bin, a.exclude_repo)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if not out.get("error") and not out.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
