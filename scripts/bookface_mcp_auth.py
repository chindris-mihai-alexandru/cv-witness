#!/usr/bin/env python3
"""Bootstrap an access token for the Bookface / YC MCP server.

The endpoint (https://api.ycombinator.com/v1/mcp) is OAuth-protected. This
script performs the parts that happen before a user opens the consent page:

 1. Dynamic client registration against the YC authorization server
    (https://account.ycombinator.com). The server supports RFC 7591-style
    registration and also client_id metadata documents; no pre-approved
    client ID is needed.
 2. Prints the authorize URL (PKCE S256) for the user to open in a browser
    where they are logged in to YC.
 3. Runs a local redirect listener on 127.0.0.1:8090 and exchanges the code
    for an access token + refresh token (RFC 8707 resource parameter).

Token is written to ~/.cv-witness/.bookface_token (chmod 600). Refresh:
  ACCESS_TOKEN=$(python3 scripts/bookface_mcp_auth.py --token-only)  # reuses refresh token

Security: the token is a live credential. Never write it into the skill repo,
never print it to a transcript, and treat it like the user's password.

Usage:
  python3 scripts/bookface_mcp_auth.py            # full flow (register → print URL → listen → token)
  python3 scripts/bookface_mcp_auth.py --token-only  # refresh token if the flow already ran
  python3 scripts/bookface_mcp_auth.py --list-actions  # call tools/list after auth

Requires Python 3.10+ stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTH_SERVER = "https://account.ycombinator.com"
MCP_ENDPOINT = "https://api.ycombinator.com/v1/mcp"
RESOURCE = "https://api.ycombinator.com"
REDIRECT_URI = "http://127.0.0.1:8090/callback"
SCOPE = "mcp:access"
DEFAULT_TOKEN_PATH = os.path.expanduser("~/.cv-witness/.bookface_token")


# --- OAuth helpers ---------------------------------------------------------

def _post(url: str, data: dict | bytes, headers: dict | None = None) -> tuple[int, str]:
    body = data if isinstance(data, bytes) else urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def register_client() -> str:
    """Register a throwaway OAuth client. Returns client_id."""
    payload = {
        "client_name": "cv-witness bookface intel",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "native",
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{AUTH_SERVER}/oauth/register", data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            info = json.loads(r.read().decode())
        return info["client_id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"client registration failed: HTTP {e.code} {e.read()[:200]!r}")


def authorize_url(client_id: str) -> tuple[str, str]:
    """Build the authorize URL and return (url, code_verifier)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    qs = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": RESOURCE,
    })
    return f"{AUTH_SERVER}/oauth/authorize?{qs}", verifier


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code_file: str = ""

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        data = {"code": q.get("code", [None])[0], "error": q.get("error", [None])[0], "path": self.path}
        with open(self.code_file, "w") as f:
            json.dump(data, f)
        body = b"<html><body><h1>Auth complete</h1><p>Close this tab.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # keep stdout private  # noqa: A002
        pass


def _wait_for_code(code_file: str, timeout_seconds: int = 300) -> str:
    import time
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if os.path.exists(code_file):
            with open(code_file) as f:
                data = json.load(f)
            if data.get("error"):
                raise RuntimeError(f"authorization error: {data['error']}")
            if data.get("code"):
                return data["code"]
        time.sleep(1)
    raise RuntimeError("timed out waiting for the OAuth redirect")


def exchange_code(client_id: str, verifier: str, code: str) -> dict:
    status, body = _post(f"{AUTH_SERVER}/oauth/token", {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
        "resource": RESOURCE,
    })
    if status != 200:
        raise RuntimeError(f"token exchange failed: HTTP {status} {body[:200]}")
    return json.loads(body)


def refresh_token(client_id: str, refresh: str) -> dict:
    status, body = _post(f"{AUTH_SERVER}/oauth/token", {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
        "resource": RESOURCE,
    })
    if status != 200:
        raise RuntimeError(f"refresh failed: HTTP {status} {body[:200]}")
    return json.loads(body)


def _read_token_file(path: str) -> dict | None:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_token_file(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    os.chmod(path, 0o600)


def _mcp_call(token: str, method: str, params: dict | None = None, reqid: int = 1) -> dict:
    payload = {"jsonrpc": "2.0", "id": reqid, "method": method}
    if params:
        payload["params"] = params
    req = urllib.request.Request(
        MCP_ENDPOINT, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode(errors="replace"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read()[:200]!r}"}


# --- commands --------------------------------------------------------------

def cmd_token_only(token_path: str) -> int:
    saved = _read_token_file(token_path)
    if not saved or "refresh_token" not in saved:
        print("No saved token; run the full flow first.", file=sys.stderr)
        return 2
    resp = refresh_token(saved["client_id"], saved["refresh_token"])
    resp.setdefault("client_id", saved["client_id"])
    if "access_token" not in resp:
        print("Refresh failed; re-run the full flow.", file=sys.stderr)
        return 1
    resp["refresh_token"] = resp.get("refresh_token", saved["refresh_token"])
    _write_token_file(token_path, resp)
    print(resp["access_token"])
    return 0


def cmd_list_actions(token_path: str) -> int:
    saved = _read_token_file(token_path)
    if not saved or "access_token" not in saved:
        print("No access token; run the full flow first.", file=sys.stderr)
        return 2
    out = _mcp_call(saved["access_token"], "tools/list", {"cursor": None}, 1)
    tools = out.get("result", {}).get("tools")
    if tools is None:
        print("tools/list failed:", json.dumps(out)[:300], file=sys.stderr)
        return 1
    print(f"{len(tools)} tools advertised by the MCP server:")
    seen = set()
    for t in tools:
        name = t.get("name")
        if name in seen:
            continue
        seen.add(name)
        print(f"  - {name}")
    return 0


def cmd_full(token_path: str) -> int:
    client_id = register_client()
    url, verifier = authorize_url(client_id)
    print("1) Open this URL in a browser where you are logged in to YC:")
    print(f"\n   {url}\n")
    print("2) Approve the consent screen, then wait here (the local redirect listener")
    print("   captures the code at 127.0.0.1:8090).")

    import socketserver
    import threading

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    code_file = f"/tmp/yc-oauth-code-{os.getpid()}.json"
    handler = type("H", (_CallbackHandler,), {"code_file": code_file})
    srv = Server(("127.0.0.1", 8090), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    try:
        code = _wait_for_code(code_file)
    finally:
        srv.shutdown()
        if os.path.exists(code_file):
            os.unlink(code_file)

    tok = exchange_code(client_id, verifier, code)
    tok["client_id"] = client_id
    _write_token_file(token_path, tok)
    print("\nAccess token saved. Expires:", tok.get("expires_in"), "seconds; refresh token kept.")
    print("Run with --list-actions to see what tools the account exposes.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap Bookface MCP OAuth token")
    ap.add_argument("--token-only", action="store_true", help="refresh as needed and print the access token")
    ap.add_argument("--list-actions", action="store_true", help="call tools/list with the saved token")
    ap.add_argument("--token-path", default=DEFAULT_TOKEN_PATH)
    args = ap.parse_args()

    if args.token_only:
        return cmd_token_only(args.token_path)
    if args.list_actions:
        return cmd_list_actions(args.token_path)
    return cmd_full(args.token_path)


if __name__ == "__main__":
    sys.exit(main())
