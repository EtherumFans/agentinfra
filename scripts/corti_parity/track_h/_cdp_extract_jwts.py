"""One-shot CDP client to extract Corti JWTs from a running Chrome tab.

Chrome must be running with --remote-debugging-port=9222, and a tab must be
logged in to console.corti.app.

Sends Runtime.evaluate over CDP WebSocket to dump localStorage keys, find
Supabase auth tokens, and write them to .corti_creds.json in the format
expected by the existing Tier 2 scripts.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

import websockets


CDP_HTTP = "http://localhost:9222"
OUT = Path("scripts/corti_parity/track_h/.corti_creds.json")


async def extract() -> int:
    # Find Corti tab
    with urllib.request.urlopen(f"{CDP_HTTP}/json", timeout=5) as r:
        tabs = json.loads(r.read())
    tab = next((t for t in tabs if "console.corti.app" in t.get("url", "") and t.get("type") == "page"), None)
    if tab is None:
        print("ERROR: no console.corti.app page tab found", file=sys.stderr)
        return 2
    print(f"Tab: {tab['url']}", file=sys.stderr)
    ws_url = tab["webSocketDebuggerUrl"]

    async with websockets.connect(ws_url, max_size=None) as ws:
        # First dump all localStorage keys + small values.
        cmd = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    (() => {
                        const out = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const k = localStorage.key(i);
                            const v = localStorage.getItem(k);
                            out[k] = v;
                        }
                        return JSON.stringify(out);
                    })()
                """,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }
        await ws.send(json.dumps(cmd))
        resp = json.loads(await ws.recv())
        result = resp.get("result", {}).get("result", {}).get("value")
        if not result:
            print(f"ERROR: no localStorage result. resp={json.dumps(resp)[:500]}", file=sys.stderr)
            return 3
        ls: dict[str, str] = json.loads(result)

    print(f"localStorage has {len(ls)} keys:", file=sys.stderr)
    for k, v in ls.items():
        preview = (v[:60] + "...") if len(v) > 60 else v
        print(f"  {k}: {preview}", file=sys.stderr)

    # Find Supabase auth token. Key pattern: sb-<ref>-auth-token
    supabase_jwt = None
    for k, v in ls.items():
        if k.startswith("sb-") and k.endswith("-auth-token"):
            try:
                inner = json.loads(v)
            except json.JSONDecodeError:
                continue
            access = inner.get("access_token")
            if access and access.startswith("eyJ"):
                supabase_jwt = access
                print(f"Picked supabase_jwt from {k} (len={len(access)})", file=sys.stderr)
                break

    if supabase_jwt is None:
        # Fallback: maybe supabase stores the raw JWT under a different key.
        for k, v in ls.items():
            if v.startswith("eyJ") and len(v) > 200 and "." in v:
                supabase_jwt = v
                print(f"Fallback: picked supabase_jwt from {k}", file=sys.stderr)
                break

    if supabase_jwt is None:
        print("ERROR: no supabase_jwt found in localStorage", file=sys.stderr)
        return 4

    # Now fetch a Corti API JWT. The Corti runtime API uses region-prefixed tokens.
    # Supabase JWT is the one we already have; corti_jwt may be obtained by
    # exchanging supabase JWT at /v1/auth/corti-jwt or similar.
    #
    # In prior sessions we observed both supabase_jwt AND corti_jwt stored in
    # .corti_creds.json. If the page has both in localStorage (or in a JS
    # global), we grab both. Otherwise we keep the old corti_jwt from the
    # existing file (if still valid structurally) and let H1.x scripts fall
    # back to supabase_jwt.
    corti_jwt = None
    for k, v in ls.items():
        if "corti" in k.lower() and v.startswith("eyJ") and len(v) > 500:
            corti_jwt = v
            print(f"Picked corti_jwt from {k}", file=sys.stderr)
            break

    # Also try sessionStorage (Keycloak JWT lives here under access-token:PROJECT:CLIENT).
    async with websockets.connect(ws_url, max_size=None) as ws:
        cmd = {
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    (() => {
                        const out = {};
                        // session dump — values can be JSON-wrapped
                        try {
                            const sess = window.sessionStorage;
                            for (let i = 0; i < sess.length; i++) {
                                const k = sess.key(i);
                                const v = sess.getItem(k);
                                if (!v) continue;
                                // try direct JWT
                                if (v.startsWith('eyJ') && v.length > 500) {
                                    out['session.' + k] = v;
                                }
                                // try JSON-wrapped {data: 'eyJ...'}
                                if (v.startsWith('{')) {
                                    try {
                                        const j = JSON.parse(v);
                                        if (j && typeof j === 'object') {
                                            for (const [jk, jv] of Object.entries(j)) {
                                                if (typeof jv === 'string' && jv.startsWith('eyJ') && jv.length > 500) {
                                                    out['session.' + k + '.' + jk] = jv;
                                                }
                                            }
                                        }
                                    } catch (e) {}
                                }
                            }
                        } catch (e) {}
                        return JSON.stringify(out);
                    })()
                """,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }
        await ws.send(json.dumps(cmd))
        resp = json.loads(await ws.recv())
        result2 = resp.get("result", {}).get("result", {}).get("value")
        if result2:
            other = json.loads(result2)
            print(f"sessionStorage JWT candidates: {list(other.keys())}", file=sys.stderr)
            # Prefer access-token:PROJECT:CLIENT .data (Keycloak JWT per save_creds.py comment)
            for k, v in sorted(other.items()):
                if "access-token" in k and k.endswith(".data"):
                    corti_jwt = v
                    print(f"Picked corti_jwt from {k}", file=sys.stderr)
                    break
            # Fallback: any access-token* key
            if corti_jwt is None:
                for k, v in sorted(other.items()):
                    if "access-token" in k:
                        corti_jwt = v
                        print(f"Fallback corti_jwt from {k}", file=sys.stderr)
                        break
            # Last resort: any corti-named key
            if corti_jwt is None:
                for k, v in sorted(other.items()):
                    if "corti" in k.lower():
                        corti_jwt = v
                        print(f"Last-resort corti_jwt from {k}", file=sys.stderr)
                        break

    # If we still don't have corti_jwt, reuse the old one from the file.
    if corti_jwt is None and OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            corti_jwt = old.get("corti_jwt")
            if corti_jwt:
                print("Reusing corti_jwt from existing .corti_creds.json (will refresh later)", file=sys.stderr)
        except Exception:
            pass

    if corti_jwt is None:
        print("WARN: corti_jwt still missing — H1.x scripts may fail if they need it", file=sys.stderr)

    # Decode + check expirations.
    def _exp(tok: str) -> int | None:
        try:
            payload_b64 = tok.split(".")[1]
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            return payload.get("exp")
        except Exception:
            return None

    sb_exp = _exp(supabase_jwt)
    co_exp = _exp(corti_jwt) if corti_jwt else None
    now = int(time.time())
    print(f"supabase_jwt exp: {'VALID' if sb_exp and sb_exp > now else 'EXPIRED'} ({(sb_exp - now) / 60:.1f}min)" if sb_exp else "supabase_jwt exp: none", file=sys.stderr)
    if corti_jwt:
        print(f"corti_jwt exp:    {'VALID' if co_exp and co_exp > now else 'EXPIRED'} ({(co_exp - now) / 60:.1f}min)" if co_exp else "corti_jwt exp: none", file=sys.stderr)

    OUT.write_text(json.dumps({
        "supabase_jwt": supabase_jwt,
        "corti_jwt": corti_jwt or "",
    }, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(extract()))
