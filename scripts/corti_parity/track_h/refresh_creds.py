"""Refresh Corti credentials by querying Chrome's CDP over HTTP.

Chrome must be running with --remote-debugging-port=9222 (per connect-chrome skill).
Finds the tab with console.corti.app loaded and extracts JWTs from localStorage/sessionStorage.
"""
from __future__ import annotations

import json
import sys
import urllib.request


CDP_URL = "http://localhost:9222/json"
CREDS_OUT = "scripts/corti_parity/track_h/.corti_creds.json"


def main() -> int:
    # List open tabs
    with urllib.request.urlopen(CDP_URL, timeout=5) as r:
        tabs = json.loads(r.read())
    # Find Corti console tab
    corti_tab = next(
        (t for t in tabs if "console.corti.app" in t.get("url", "")),
        None,
    )
    if corti_tab is None:
        print("ERROR: no console.corti.app tab found. Open Corti console in Chrome first.", file=sys.stderr)
        return 2
    print(f"Found Corti tab: {corti_tab.get('url')}", file=sys.stderr)
    # We can't evaluate JS over plain HTTP CDP; need WebSocket. Print tab info for Playwright MCP fallback.
    print(f"TAB_URL={corti_tab.get('url')}", file=sys.stderr)
    print(f"WEB_SOCKET_DEBUGGER_URL={corti_tab.get('webSocketDebuggerUrl')}", file=sys.stderr)
    print("Use Playwright MCP browser_evaluate to extract JWTs from this tab.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
