"""Dump all sessionStorage keys + value previews."""
import asyncio, json, urllib.request
import websockets

async def main():
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        tabs = json.loads(r.read())
    tab = next((t for t in tabs if "console.corti.app" in t.get("url", "") and t.get("type") == "page"), None)
    print(f"Tab: {tab['url']}", file=__import__('sys').stderr)
    ws_url = tab["webSocketDebuggerUrl"]

    async with websockets.connect(ws_url, max_size=None) as ws:
        cmd = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                    (() => {
                        const out = {};
                        try {
                            const ls = window.localStorage;
                            const lsOut = {};
                            for (let i = 0; i < ls.length; i++) {
                                const k = ls.key(i);
                                lsOut[k] = ls.getItem(k);
                            }
                            out.localStorage = lsOut;
                        } catch (e) { out.localStorageErr = String(e); }
                        try {
                            const ss = window.sessionStorage;
                            const ssOut = {};
                            for (let i = 0; i < ss.length; i++) {
                                const k = ss.key(i);
                                ssOut[k] = ss.getItem(k);
                            }
                            out.sessionStorage = ssOut;
                        } catch (e) { out.sessionStorageErr = String(e); }
                        // cookie preview
                        out.cookie = document.cookie.slice(0, 500);
                        // try fetch corti api to see if we can exchange supabase for corti jwt
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
        d = json.loads(v)
        print("\n=== localStorage keys ===")
        for k, val in d.get("localStorage", {}).items():
            preview = val[:120].replace("\n", " ") + ("..." if len(val) > 120 else "")
            print(f"  {k}: {preview}")
        print("\n=== sessionStorage keys ===")
        for k, val in d.get("sessionStorage", {}).items():
            preview = val[:120].replace("\n", " ") + ("..." if len(val) > 120 else "")
            print(f"  {k}: {preview}")
        print(f"\n=== cookie (first 500 chars) ===")
        print(d.get("cookie", ""))

asyncio.run(main())
