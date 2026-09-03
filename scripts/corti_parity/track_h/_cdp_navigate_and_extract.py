"""Navigate Corti tab to Agent chat page via CDP, wait, re-extract session.

The Corti SPA materializes the Keycloak JWT (corti_jwt) into sessionStorage
lazily — only when the user opens an Agent that requires runtime auth. By
navigating the existing tab to the Agents list / chat page, we trigger that
materialization.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request

import websockets


# Project + agent IDs from 02_run_cdi_sse_40.py
PROJECT_ID = "4c4193c7-c6bb-4a71-a275-0ed6c53172d0"
AGENT_DEF_ID = "fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2"


async def nav_and_extract(target_url: str, wait_s: float = 6.0) -> dict:
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        tabs = json.loads(r.read())
    tab = next((t for t in tabs if "console.corti.app" in t.get("url", "") and t.get("type") == "page"), None)
    if tab is None:
        print("ERROR: no Corti tab", file=sys.stderr)
        return {}
    ws_url = tab["webSocketDebuggerUrl"]
    print(f"Nav target: {target_url}", file=sys.stderr)

    async with websockets.connect(ws_url, max_size=None) as ws:
        # Navigate
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.navigate",
            "params": {"url": target_url},
        }))
        # Discard navigation response (and any events)
        for _ in range(5):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if '"id":1' in msg:
                    break
            except asyncio.TimeoutError:
                break
        # Wait for SPA to settle
        await asyncio.sleep(wait_s)
        # Dump sessionStorage
        await ws.send(json.dumps({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    (() => {
                        const out = {};
                        try {
                            const ss = window.sessionStorage;
                            for (let i = 0; i < ss.length; i++) {
                                const k = ss.key(i);
                                out[k] = ss.getItem(k);
                            }
                        } catch (e) {}
                        return JSON.stringify(out);
                    })()
                """,
                "returnByValue": True,
            },
        }))
        while True:
            msg = await ws.recv()
            d = json.loads(msg)
            if d.get("id") == 2:
                return d.get("result", {}).get("result", {}).get("value") or ""


async def main() -> int:
    # Try several plausible Corti URLs that should trigger Keycloak exchange
    targets = [
        f"https://console.corti.app/projects/{PROJECT_ID}/agents",
        f"https://console.corti.app/projects/{PROJECT_ID}/agents/{AGENT_DEF_ID}",
        f"https://console.corti.app/projects/{PROJECT_ID}/agents/{AGENT_DEF_ID}/chat",
        f"https://console.corti.app/",
    ]
    for url in targets:
        result = await nav_and_extract(url, wait_s=8.0)
        if not result:
            print(f"  -> empty result", file=sys.stderr)
            continue
        sess = json.loads(result)
        print(f"  -> {len(sess)} sessionStorage keys", file=sys.stderr)
        for k in sess:
            print(f"     {k}", file=sys.stderr)
        # Look for any access-token / corti key
        for k, v in sess.items():
            if "access-token" in k.lower() or "corti" in k.lower() or "keycloak" in k.lower():
                print(f"  HIT: {k}", file=sys.stderr)
        # If found new keys, dump and exit
        if any("access-token" in k.lower() or "keycloak" in k.lower() for k in sess):
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
