#!/usr/bin/env python3
"""Corti Reverse Engineer — Playwright crawler.

Captures API contracts + UI interactions from console.corti.app for 1:1
replication in iCoDer. Reuses a persistent Chrome user-data-dir so SSO
session survives across runs.

Usage:
    # 1. First run — user does Google SSO manually:
    python scripts/corti_reverse_engineer.py --auth-bootstrap

    # 2. Subsequent runs — auto, reuse SSO session:
    python scripts/corti_reverse_engineer.py --crawl

Output: docs/corti-reverse-engineered/
    api-contracts.json   — every XHR/Fetch (method, url, req_body, resp_body, headers)
    ui-flows.json        — click→API edges (selector → request_id)
    pages/*.png + *.html — screenshots + DOM snapshots per URL
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, Page, BrowserContext

CORTI_BASE = "https://console.corti.app"
USER_DATA_DIR = Path(".corti-user-data")
OUTPUT_DIR = Path("docs/corti-reverse-engineered")
PAGES_DIR = OUTPUT_DIR / "pages"

# Edge passes Google SSO "unsafe browser" check better than Chromium
BROWSER_CHANNEL = "msedge"
ANTI_DETECTION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-first-run",
    "--no-default-browser-check",
]

# ── 15 sidebar URLs to walk (from docs/corti-feature-inventory.md) ──────────
TARGET_URLS = [
    ("home",                       "/"),
    ("developer-quickstart",       "/developer-quickstart"),
    ("ai-studio-overview",         "/ai-studio"),
    ("ai-studio-agents",           "/ai-studio/agents"),
    ("ai-studio-agents-new",       "/ai-studio/agents/new"),
    ("ai-studio-speech-to-text",   "/ai-studio/speech-to-text"),
    ("ai-studio-text-generation",  "/ai-studio/text-generation"),
    ("ai-studio-fact-extraction",  "/ai-studio/fact-extraction"),
    ("ai-studio-embedded-asst",    "/ai-studio/embedded-assistant"),
    ("ai-studio-medical-coding",   "/ai-studio/medical-coding"),
    ("api-clients",                "/api-clients"),
    ("team",                       "/team"),
    ("billing",                    "/billing"),
    ("customers",                  "/customers"),
    ("templates",                  "/templates"),
    ("settings",                   "/settings"),
]


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


class NetworkRecorder:
    """Captures every XHR/Fetch + click→request edges."""

    def __init__(self):
        self.requests = []   # [{id, ts, method, url, req_body, resp_status, resp_body, resp_ct}]
        self.clicks = []     # [{ts, selector, tag, text, request_id}]
        self._next_id = 0

    def attach(self, page: Page):
        page.on("request", self._on_request(page))
        page.on("response", self._on_response(page))
        page.on("requestfailed", self._on_failed(page))

    def _on_request(self, page: Page):
        def handler(req):
            # Skip static assets and analytics
            url = req.url
            if any(s in url for s in ["/assets/", ".png", ".jpg", ".svg", ".css", ".ico",
                                        "google-analytics", "cookiebot", "datadog",
                                        "sentry", "fullstory", "segment.io"]):
                return
            rid = self._next_id
            self._next_id += 1
            try:
                body = req.post_data
            except Exception:
                body = None
            self.requests.append({
                "id": rid,
                "ts": datetime.now(timezone.utc).isoformat(),
                "method": req.method,
                "url": url,
                "req_headers": dict(req.headers),
                "req_body": body,
            })
        return handler

    def _on_response(self, page: Page):
        def handler(resp):
            url = resp.url
            if any(s in url for s in ["/assets/", ".png", ".jpg", ".svg", ".css", ".ico",
                                        "google-analytics", "cookiebot", "datadog",
                                        "sentry", "fullstory", "segment.io"]):
                return
            # Find matching request by url (most recent first)
            for r in reversed(self.requests):
                if r["url"] == url and "resp_status" not in r:
                    r["resp_status"] = resp.status
                    r["resp_headers"] = dict(resp.headers)
                    try:
                        # Only capture JSON / text bodies
                        ct = resp.headers.get("content-type", "")
                        if any(s in ct for s in ["json", "text"]):
                            r["resp_body"] = resp.text()[:8000]  # cap 8KB
                            r["resp_ct"] = ct
                    except Exception:
                        pass
                    break
        return handler

    def _on_failed(self, page: Page):
        def handler(req):
            for r in reversed(self.requests):
                if r["url"] == req.url and "resp_status" not in r:
                    r["resp_status"] = -1
                    r["resp_error"] = req.failure
                    break
        return handler

    def record_click_chain(self, page: Page):
        """Attach JS to record clicks → best-effort associate with last request."""
        page.evaluate("""
            window.__corti_clicks__ = [];
            document.addEventListener('click', (e) => {
                const t = e.target;
                const sel = (t.id && '#' + t.id)
                    || (t.dataset?.testid && '[data-testid="' + t.dataset.testid + '"]')
                    || (t.getAttribute('role') && '[role="' + t.getAttribute('role') + '"]')
                    || t.tagName.toLowerCase();
                window.__corti_clicks__.push({
                    ts: Date.now(),
                    selector: sel,
                    tag: t.tagName.toLowerCase(),
                    text: (t.innerText || '').slice(0, 60),
                    ariaLabel: t.getAttribute('aria-label'),
                });
            }, true);
        """)

    def drain_clicks(self, page: Page):
        try:
            clicks = page.evaluate("() => window.__corti_clicks__ || []")
            self.clicks.extend(clicks)
            page.evaluate("() => { window.__corti_clicks__ = []; }")
        except Exception:
            pass


def auth_bootstrap():
    """First run: open headed browser, poll URL until user lands on /project/<id>."""
    ensure_dirs()
    print(f"[auth] Opening headed Chromium at {CORTI_BASE}")
    print(f"[auth] User-data-dir: {USER_DATA_DIR.resolve()}")
    print(f"[auth] ACTION: complete Google SSO (songluhua@gmail.com) in the browser window.")
    print(f"[auth] Auto-detects when you land on /project/<id> (no need to come back here).")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel=BROWSER_CHANNEL,
            args=["--no-sandbox", "--disable-dev-shm-usage"] + ANTI_DETECTION_ARGS,
            viewport={"width": 1440, "height": 900},
            ignore_default_args=["--enable-automation"],
        )

        # Apply stealth patches to bypass automation detection
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(browser)
            print(f"[auth] Applied playwright-stealth patches")
        except ImportError:
            print(f"[auth] playwright-stealth not available, proceeding without stealth")
        except Exception as e:
            print(f"[auth] playwright-stealth failed: {type(e).__name__}: {e}")

        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(f"{CORTI_BASE}/", wait_until="domcontentloaded")

        # Poll URL every 2s up to 5 min — auto-detect successful login
        deadline = time.time() + 300
        last_url = None
        while time.time() < deadline:
            try:
                cur = page.url
            except Exception:
                cur = "<detached>"
            if cur != last_url:
                print(f"[auth] URL → {cur}")
                last_url = cur
            if "/project/" in cur:
                print(f"[auth] ✓ SSO complete — landed on project page.")
                page.wait_for_timeout(2000)
                break
            time.sleep(2)
        else:
            browser.close()
            sys.exit("[auth] ✗ Timed out waiting for /project/<id>. Re-run --auth-bootstrap.")

        browser.close()
    print(f"[auth] Session persisted to {USER_DATA_DIR}. Run --crawl to capture API contracts.")


def crawl():
    """Walk 15 URLs, capture network + UI per page."""
    ensure_dirs()
    rec = NetworkRecorder()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel=BROWSER_CHANNEL,
            args=["--no-sandbox", "--disable-dev-shm-usage"] + ANTI_DETECTION_ARGS,
            viewport={"width": 1440, "height": 900},
            ignore_default_args=["--enable-automation"],
        )

        # Apply stealth patches
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(browser)
        except Exception:
            pass

        page = browser.pages[0] if browser.pages else browser.new_page()
        rec.attach(page)

        # First: confirm we're authenticated
        page.goto(f"{CORTI_BASE}/", wait_until="domcontentloaded", timeout=30000)
        # Wait up to 8s for redirect to land on /project/<id> or similar
        for _ in range(16):
            page.wait_for_timeout(500)
            if "/login" not in page.url and "/signin" not in page.url and "accounts.google" not in page.url:
                break
        cur_url = page.url
        print(f"[crawl] Auth check URL: {cur_url}")
        if "/login" in cur_url or "/signin" in cur_url or "accounts.google" in cur_url:
            sys.exit(f"[crawl] Not authenticated. Run --auth-bootstrap first.\nCurrent URL: {cur_url}")

        # Resolve project_id from current URL
        project_url = page.url
        project_id = None
        if "/project/" in project_url:
            parts = project_url.split("/project/")[1].split("/")
            project_id = parts[0]
        print(f"[crawl] Authenticated. project_id={project_id}")

        # Walk each URL
        for name, path in TARGET_URLS:
            url_path = f"/project/{project_id}{path}" if project_id and path != "/" else f"{CORTI_BASE}{path}"
            print(f"\n[crawl] {name}: {url_path}")
            try:
                rec.record_click_chain(page)
                page.goto(url_path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)
                rec.drain_clicks(page)

                # Screenshot + DOM snapshot
                shot_path = PAGES_DIR / f"{name}.png"
                page.screenshot(path=str(shot_path), full_page=True)
                html_path = PAGES_DIR / f"{name}.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())

                # Mark requests as belonging to this URL
                for r in rec.requests:
                    if "page" not in r:
                        r["page"] = name
                        break  # only mark the latest un-marked one
                print(f"  → shot={shot_path.name}, html={html_path.name}, "
                      f"reqs={sum(1 for r in rec.requests if r.get('page') == name)}")

            except Exception as e:
                print(f"  → FAIL: {type(e).__name__}: {str(e)[:100]}")
                continue

        browser.close()

    # ── Persist artifacts ──
    print(f"\n[crawl] Writing artifacts...")
    api_contracts = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "user": "songluhua@gmail.com",
        "total_requests": len(rec.requests),
        "requests": rec.requests,
    }
    with open(OUTPUT_DIR / "api-contracts.json", "w", encoding="utf-8") as f:
        json.dump(api_contracts, f, ensure_ascii=False, indent=2)
    print(f"  → api-contracts.json ({len(rec.requests)} requests)")

    ui_flows = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "total_clicks": len(rec.clicks),
        "clicks": rec.clicks,
    }
    with open(OUTPUT_DIR / "ui-flows.json", "w", encoding="utf-8") as f:
        json.dump(ui_flows, f, ensure_ascii=False, indent=2)
    print(f"  → ui-flows.json ({len(rec.clicks)} clicks)")


def main():
    parser = argparse.ArgumentParser(description="Corti Reverse Engineer")
    parser.add_argument("--auth-bootstrap", action="store_true",
                        help="First run: open headed browser for manual Google SSO")
    parser.add_argument("--crawl", action="store_true",
                        help="Crawl 15 URLs, capture network + UI")
    args = parser.parse_args()

    if args.auth_bootstrap:
        auth_bootstrap()
    elif args.crawl:
        crawl()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()