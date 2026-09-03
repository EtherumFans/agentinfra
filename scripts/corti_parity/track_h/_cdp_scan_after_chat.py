"""After user clicks 'send' in Corti chat, scan all client-side storage + recent network responses for the Keycloak JWT.

The Keycloak JWT format: ~2600 chars, eyJ... prefix, RS256 signed, payload has typ=Bearer + azp.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import websockets


OUT = Path("scripts/corti_parity/track_h/.corti_creds.json")
KEYCLOAK_HINTS = ("azp", "realm_access", "resource_access", "typ\":\"Bearer", "iss\":\"https://", "preferred_username")


def _looks_like_keycloak(jwt: str) -> bool:
    """Heuristic: Keycloak JWTs are long RS256 with azp/realm_access in payload."""
    if not jwt.startswith("eyJ") or len(jwt) < 1000:
        return False
    parts = jwt.split(".")
    if len(parts) < 2:
        return False
    try:
        pl_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        pl = json.loads(base64.urlsafe_b64decode(pl_b64).decode("utf-8"))
    except Exception:
        return False
    text = json.dumps(pl)
    return any(h in text for h in KEYCLOAK_HINTS) or "corti" in text.lower()


async def scan() -> int:
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        tabs = json.loads(r.read())
    tab = next((t for t in tabs if "console.corti.app" in t.get("url", "") and t.get("type") == "page"), None)
    if tab is None:
        print("ERROR: no Corti tab", file=sys.stderr)
        return 2
    ws_url = tab["webSocketDebuggerUrl"]
    print(f"Tab: {tab['url']}", file=sys.stderr)

    async with websockets.connect(ws_url, max_size=None) as ws:
        # Dump every storage surface
        cmd = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    (() => {
                        const out = {};
                        const scan = (store, label) => {
                            const found = {};
                            try {
                                for (let i = 0; i < store.length; i++) {
                                    const k = store.key(i);
                                    let v = store.getItem(k);
                                    found[k] = v;
                                }
                            } catch (e) { found.__err = String(e); }
                            return found;
                        };
                        out.localStorage = scan(localStorage, 'ls');
                        out.sessionStorage = scan(sessionStorage, 'ss');
                        out.cookie = document.cookie;
                        // Scan window for JWT-like strings
                        const winJwts = {};
                        try {
                            const stack = [[window, 'window', new Set()]];
                            let n = 0;
                            while (stack.length && n < 5000) {
                                const [obj, path, seen] = stack.pop();
                                n++;
                                if (!obj || typeof obj !== 'object' || seen.has(obj)) continue;
                                seen.add(obj);
                                try {
                                    for (const k of Object.keys(obj)) {
                                        try {
                                            const v = obj[k];
                                            if (typeof v === 'string' && v.startsWith('eyJ') && v.length > 1000) {
                                                winJwts[path + '.' + k] = v;
                                            } else if (typeof v === 'object' && v !== null && path.split('.').length < 5) {
                                                stack.push([v, path + '.' + k, seen]);
                                            }
                                        } catch (e) {}
                                    }
                                } catch (e) {}
                            }
                        } catch (e) {}
                        out.window_jwts = winJwts;
                        return JSON.stringify(out);
                    })()
                """,
                "returnByValue": True,
                "awaitPromise": False,
            },
        }
        await ws.send(json.dumps(cmd))
        resp = json.loads(await ws.recv())
        v = resp.get("result", {}).get("result", {}).get("value")
        if not v:
            print(f"empty result: {json.dumps(resp)[:400]}", file=sys.stderr)
            return 3
        data = json.loads(v)

    candidates: list[tuple[str, str]] = []
    for store in ("localStorage", "sessionStorage"):
        for k, val in data.get(store, {}).items():
            if isinstance(val, str):
                # Direct JWT
                if val.startswith("eyJ") and len(val) > 500:
                    candidates.append((f"{store}:{k}", val))
                # JSON-wrapped
                if val.startswith("{"):
                    try:
                        inner = json.loads(val)
                        if isinstance(inner, dict):
                            for ik, iv in inner.items():
                                if isinstance(iv, str) and iv.startswith("eyJ") and len(iv) > 500:
                                    candidates.append((f"{store}:{k}.{ik}", iv))
                    except json.JSONDecodeError:
                        pass
    for k, val in data.get("window_jwts", {}).items():
        candidates.append((k, val))

    print(f"\n{len(candidates)} JWT candidates found:", file=sys.stderr)
    for src, val in candidates:
        is_kc = _looks_like_keycloak(val)
        print(f"  [{'KC' if is_kc else 'sb'}] {src} (len={len(val)})", file=sys.stderr)

    # Pick the first Keycloak-shaped JWT
    keycloak = next((v for s, v in candidates if _looks_like_keycloak(v)), None)
    if keycloak is None:
        print("\nNo Keycloak JWT found. Will dump all cookies + retry with Network.enable.", file=sys.stderr)
        print(f"Cookies: {data.get('cookie', '')[:300]}", file=sys.stderr)
        return 4

    print(f"\nPicked Keycloak JWT ({len(keycloak)} chars)", file=sys.stderr)

    # Decode payload to confirm
    pl_b64 = keycloak.split(".")[1]
    pl_b64 += "=" * (-len(pl_b64) % 4)
    pl = json.loads(base64.urlsafe_b64decode(pl_b64).decode("utf-8"))
    exp = pl.get("exp")
    now = int(time.time())
    print(f"  exp: {(exp - now) / 60:.1f} min from now", file=sys.stderr)
    print(f"  azp: {pl.get('azp', '?')}", file=sys.stderr)
    print(f"  iss: {pl.get('iss', '?')}", file=sys.stderr)

    # Read existing supabase_jwt
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        sb = old.get("supabase_jwt", "")
    else:
        sb = ""

    OUT.write_text(json.dumps({"supabase_jwt": sb, "corti_jwt": keycloak}, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(scan()))
