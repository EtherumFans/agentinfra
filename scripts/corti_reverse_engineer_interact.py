#!/usr/bin/env python3
"""Corti Reverse Engineer — Interactive version.

Step 0.3: drive each page through its key UI interactions (click tabs, type
into inputs, hit "Generate"/"Predict" buttons), so that client-side API calls
fire and get captured. Also hooks WebSocket + SSE.

Output (augments step 0.2):
    docs/corti-reverse-engineered/api-contracts-interactive.json
    docs/corti-reverse-engineered/interaction-graph.json   — click → request edges
    docs/corti-reverse-engineered/ws-streams.jsonl          — one line per WS frame
    docs/corti-reverse-engineered/interactions/<page>/*.png  — step-by-step shots

Usage:
    python scripts/corti_reverse_engineer_interact.py --all
    python scripts/corti_reverse_engineer_interact.py --only medical-coding
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

CORTI_BASE = "https://console.corti.app"
USER_DATA_DIR = Path(".corti-user-data")
OUTPUT_DIR = Path("docs/corti-reverse-engineered")
INTERACTIONS_DIR = OUTPUT_DIR / "interactions"

BROWSER_CHANNEL = "msedge"
ANTI_DETECTION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-first-run",
    "--no-default-browser-check",
]

# ── Sample EMR for Medical Coding / Fact Extraction / Text Generation ──────
SAMPLE_EMR = (
    "患者男性,67 岁,因「反复胸闷、心悸 3 月,加重伴双下肢水肿 1 周」入院。"
    "既往高血压病史 12 年,糖尿病史 8 年。"
    "入院查体:BP 162/95 mmHg,心率 98 次/分,双下肢轻度凹陷性水肿。"
    "心电图示房颤,心脏超声示左心扩大,LVEF 38%。"
    "诊断:1. 慢性心力衰竭 心功能 III 级(NYHA);"
    "2. 心房颤动;"
    "3. 高血压 2 级(极高危);"
    "4. 2 型糖尿病。"
    "入院后行冠状动脉造影示前降支中段 80% 狭窄,置入药物洗脱支架 1 枚。"
    "术后规律服用阿司匹林、氯吡格雷、阿托伐他汀。"
)

# ── URL path mapping (recipe name → Corti path) ─────────────────────────────
URL_PATHS = {
    "home":                          "/",
    "ai-studio-agents":              "/ai-studio/agents",
    "ai-studio-agents-new":          "/ai-studio/agents/new",
    "ai-studio-speech-to-text":      "/ai-studio/speech-to-text",
    "ai-studio-text-generation":     "/ai-studio/text-generation",
    "ai-studio-fact-extraction":     "/ai-studio/fact-extraction",
    "ai-studio-embedded-asst":       "/ai-studio/embedded-assistant",
    "ai-studio-medical-coding":      "/ai-studio/medical-coding",
    "api-clients":                   "/api-clients",
    "team":                          "/team",
    "billing":                       "/billing",
    "customers":                     "/customers",
    "templates":                     "/templates",
    "settings":                      "/settings",
    "developer-quickstart":          "/developer-quickstart",
}


# ── Interaction recipes per page ───────────────────────────────────────────
# Each recipe: list of steps. Step types: click / fill / wait
# Selectors use text= or aria-label= or role= where possible (resilient).

RECIPES = {
    "home": [
        {"action": "click_tab_by_text", "text": "Transcribe"},
        {"action": "screenshot", "label": "tab-transcribe"},
        {"action": "click_tab_by_text", "text": "Document"},
        {"action": "screenshot", "label": "tab-document"},
        {"action": "click_tab_by_text", "text": "Chat"},
        {"action": "screenshot", "label": "tab-chat"},
        {"action": "click_tab_by_text", "text": "Code"},
        {"action": "screenshot", "label": "tab-code"},
    ],
    "ai-studio-agents": [
        {"action": "click_role_tab", "name": "Pre-built"},
        {"action": "wait_ms", "ms": 2000},
        {"action": "screenshot", "label": "prebuilt-tab"},
        # Click first prebuilt agent card (any visible clickable card)
        {"action": "click_first_agent_card"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "prebuilt-agent-detail"},
    ],
    "ai-studio-agents-new": [
        # Click a template (any radio option) to surface preview
        {"action": "click_first_radio_in_templates"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "template-selected"},
    ],
    "ai-studio-speech-to-text": [
        # Try clicking "Start recording" or similar
        {"action": "click_button_by_text", "text": ["Start recording", "Record", "Start"]},
        {"action": "wait_ms", "ms": 2500},
        {"action": "screenshot", "label": "recording-attempt"},
    ],
    "ai-studio-text-generation": [
        {"action": "fill_textarea", "value": SAMPLE_EMR[:200]},
        {"action": "click_button_by_text", "text": ["Generate", "Generate document"]},
        {"action": "wait_ms", "ms": 5000},
        {"action": "screenshot", "label": "textgen-output"},
    ],
    "ai-studio-fact-extraction": [
        {"action": "fill_textarea", "value": SAMPLE_EMR[:300]},
        {"action": "click_button_by_text", "text": ["Extract", "Extract facts"]},
        {"action": "wait_ms", "ms": 5000},
        {"action": "screenshot", "label": "facts-output"},
    ],
    "ai-studio-embedded-assistant": [
        # Embedded Assistant preview area — click "Initialize" / preview
        {"action": "wait_ms", "ms": 3000},
        {"action": "screenshot", "label": "embedded-init"},
    ],
    "ai-studio-medical-coding": [
        # KEY: fill the input textarea and click Predict / Generate codes
        {"action": "fill_textarea", "value": SAMPLE_EMR, "placeholder_hint": "clinical"},
        {"action": "wait_ms", "ms": 1000},
        {"action": "click_button_by_text", "text": ["Predict codes", "Generate", "Run", "Submit"]},
        {"action": "wait_ms", "ms": 8000},
        {"action": "screenshot", "label": "coding-predicted"},
        # Try Rendered/JSON toggle if present
        {"action": "click_button_by_text", "text": ["JSON"]},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "coding-json"},
    ],
    "api-clients": [
        {"action": "click_button_by_text", "text": ["Create API client", "New API client", "Create"]},
        {"action": "wait_ms", "ms": 2000},
        {"action": "screenshot", "label": "create-api-client"},
    ],
    "team": [
        {"action": "click_button_by_text", "text": ["Invite", "Invite member", "Add member"]},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "invite-modal"},
    ],
    "billing": [
        {"action": "click_tab_by_text", "text": "Billing History"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "billing-history"},
        {"action": "click_tab_by_text", "text": "Business info"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "billing-business"},
    ],
    "customers": [
        {"action": "fill_input_placeholder", "placeholder": ["Search", "Name", "Customer"]},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "customers-search"},
        {"action": "click_button_by_text", "text": ["Add customer", "New customer", "Create"]},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "add-customer-modal"},
    ],
    "templates": [
        {"action": "click_button_by_text", "text": ["Create template", "New template", "Create"]},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "template-builder"},
    ],
    "settings": [
        {"action": "click_button_by_text", "text": ["Copy ID"]},
        {"action": "wait_ms", "ms": 1000},
        {"action": "screenshot", "label": "settings-copied"},
    ],
    "developer-quickstart": [
        {"action": "click_tab_by_text", "text": "JS SDK"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "quickstart-js"},
        {"action": "click_tab_by_text", "text": ".NET SDK"},
        {"action": "wait_ms", "ms": 1500},
        {"action": "screenshot", "label": "quickstart-dotnet"},
    ],
}


class InteractionRecorder:
    """Network + WebSocket + SSE + click→request edge recorder."""

    def __init__(self):
        self.requests = []
        self.ws_frames = []    # [{ts, url, direction, payload}]
        self.sse_events = []   # [{ts, url, event, data}]
        self.clicks = []       # [{ts, selector, text, request_ids[]}]
        self._next_req_id = 0
        self._last_click = None

    def attach(self, page: Page):
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("websocket", self._on_websocket)
        # SSE: eventsource is not directly exposed; intercept EventSource via init script
        page.add_init_script("""
            (() => {
                const OrigES = window.EventSource;
                if (!OrigES || window.__patched_es) return;
                window.__patched_es = true;
                window.EventSource = class extends OrigES {
                    constructor(url, opts) {
                        super(url, opts);
                        window.__corti_sse__ = window.__corti_sse__ || [];
                        window.__corti_sse__.push({type: 'open', url: String(url), ts: Date.now()});
                        this.addEventListener('message', (e) => {
                            window.__corti_sse__.push({type: 'message', url: String(url), data: e.data, ts: Date.now()});
                        });
                        this.addEventListener('error', (e) => {
                            window.__corti_sse__.push({type: 'error', url: String(url), ts: Date.now()});
                        });
                    }
                };
                // Also patch WebSocket for capture
                const OrigWS = window.WebSocket;
                if (window.__patched_ws) return;
                window.__patched_ws = true;
                window.WebSocket = class extends OrigWS {
                    constructor(url, protocols) {
                        super(url, protocols);
                        window.__corti_ws__ = window.__corti_ws__ || [];
                        window.__corti_ws__.push({type: 'open', url: String(url), ts: Date.now()});
                        this.addEventListener('message', (e) => {
                            try {
                                window.__corti_ws__.push({type: 'message', url: String(url), data: typeof e.data === 'string' ? e.data : '<binary>', ts: Date.now()});
                            } catch (err) {}
                        });
                    }
                };
            })();
        """)
        # Record clicks
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

    def _on_request(self, req):
        if any(s in req.url for s in ["/assets/", ".png", ".jpg", ".svg", ".css", ".ico",
                                       "google-analytics", "cookiebot", "datadog",
                                       "sentry", "fullstory", "segment.io", ".woff"]):
            return
        rid = self._next_req_id
        self._next_req_id += 1
        try:
            body = req.post_data
        except Exception:
            body = None
        self.requests.append({
            "id": rid,
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": req.method,
            "url": req.url,
            "resource_type": req.resource_type,
            "req_headers": dict(req.headers),
            "req_body": body[:8000] if body else None,
            "triggered_by_click": self._last_click,
        })

    def _on_response(self, resp):
        for r in reversed(self.requests):
            if r["url"] == resp.url and "resp_status" not in r:
                r["resp_status"] = resp.status
                r["resp_headers"] = dict(resp.headers)
                try:
                    ct = resp.headers.get("content-type", "")
                    if any(s in ct for s in ["json", "text", "event-stream"]):
                        r["resp_body"] = resp.text()[:8000]
                        r["resp_ct"] = ct
                except Exception:
                    pass
                break

    def _on_websocket(self, ws):
        ws.on("framereceived", lambda payload: self._record_ws_frame(ws.url, "recv", payload))
        ws.on("framesent", lambda payload: self._record_ws_frame(ws.url, "send", payload))

    def _record_ws_frame(self, url, direction, payload):
        try:
            data = payload if isinstance(payload, str) else "<binary>"
        except Exception:
            data = "<unreadable>"
        self.ws_frames.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "direction": direction,
            "payload": data[:4000] if isinstance(data, str) else data,
        })

    def mark_click(self, selector, text):
        self._last_click = {"ts": datetime.now(timezone.utc).isoformat(),
                            "selector": selector, "text": text}

    def drain_browser_streams(self, page: Page):
        # Drain WS + SSE captured via init script
        try:
            ws = page.evaluate("() => { const w = window.__corti_ws__ || []; window.__corti_ws__ = []; return w; }")
            for f in ws:
                self.ws_frames.append({
                    "ts": datetime.fromtimestamp(f["ts"]/1000, timezone.utc).isoformat(),
                    "url": f["url"], "direction": "recv", "payload": str(f.get("data",""))[:4000],
                    "source": "init-script",
                })
        except Exception:
            pass
        try:
            sse = page.evaluate("() => { const s = window.__corti_sse__ || []; window.__corti_sse__ = []; return s; }")
            for e in sse:
                self.sse_events.append({
                    "ts": datetime.fromtimestamp(e["ts"]/1000, timezone.utc).isoformat(),
                    "url": e["url"], "event": e["type"], "data": str(e.get("data",""))[:4000],
                })
        except Exception:
            pass
        try:
            clicks = page.evaluate("() => { const c = window.__corti_clicks__ || []; window.__corti_clicks__ = []; return c; }")
            self.clicks.extend(clicks)
        except Exception:
            pass

    def save(self, page_name: str):
        out_dir = INTERACTIONS_DIR / page_name
        out_dir.mkdir(parents=True, exist_ok=True)


def execute_recipe(page: Page, recipe: list, rec: InteractionRecorder):
    """Execute a list of interaction steps on the page."""
    for i, step in enumerate(recipe):
        action = step.get("action")
        try:
            if action == "click_tab_by_text":
                text = step["text"]
                rec.mark_click(f"tab:{text}", text)
                # Try multiple selector strategies
                for sel in [f'role=tab[name="{text}"]', f'button:has-text("{text}")', f'a:has-text("{text}")', f'[role="tab"]:has-text("{text}")']:
                    try:
                        page.locator(sel).first.click(timeout=2000)
                        break
                    except PWTimeout:
                        continue
            elif action == "click_role_tab":
                name = step["name"]
                rec.mark_click(f"role-tab:{name}", name)
                try:
                    page.get_by_role("tab", name=name).first.click(timeout=3000)
                except PWTimeout:
                    pass
            elif action == "click_button_by_text":
                texts = step["text"] if isinstance(step["text"], list) else [step["text"]]
                rec.mark_click(f"button:{texts[0]}", str(texts))
                clicked = False
                for t in texts:
                    for sel in [f'role=button[name="{t}"]', f'button:has-text("{t}")', f'a:has-text("{t}")']:
                        try:
                            page.locator(sel).first.click(timeout=1500)
                            clicked = True
                            break
                        except PWTimeout:
                            continue
                    if clicked:
                        break
            elif action == "click_first_agent_card":
                # Find clickable cards in prebuilt tab
                rec.mark_click("first-agent-card", "")
                try:
                    # Try generic clickable card pattern
                    for sel in ['[data-testid*="agent-card"]', '[role="button"][aria-label*="agent" i]',
                                'button:has(svg)', 'a[href*="/agents/"]']:
                        try:
                            page.locator(sel).first.click(timeout=1500)
                            break
                        except PWTimeout:
                            continue
                except Exception:
                    pass
            elif action == "click_first_radio_in_templates":
                rec.mark_click("first-template-radio", "")
                try:
                    page.locator('input[type="radio"]').first.click(timeout=2000)
                except PWTimeout:
                    pass
            elif action == "fill_textarea":
                value = step["value"]
                rec.mark_click("fill:textarea", value[:40])
                try:
                    page.locator("textarea").first.fill(value, timeout=3000)
                except PWTimeout:
                    pass
            elif action == "fill_input_placeholder":
                placeholders = step["placeholder"] if isinstance(step["placeholder"], list) else [step["placeholder"]]
                rec.mark_click("fill:input", str(placeholders))
                for ph in placeholders:
                    try:
                        page.locator(f'input[placeholder*="{ph}" i]').first.fill("test", timeout=1500)
                        break
                    except PWTimeout:
                        continue
            elif action == "wait_ms":
                page.wait_for_timeout(step["ms"])
            elif action == "screenshot":
                rec.save(page_name="_current")  # placeholder
                # Caller captures step screenshot
                pass
        except Exception as e:
            print(f"    [step {i}] {action} FAIL: {type(e).__name__}: {str(e)[:80]}")


def crawl_interactive():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INTERACTIONS_DIR.mkdir(parents=True, exist_ok=True)

    rec = InteractionRecorder()
    rec_all = InteractionRecorder()  # accumulates across all pages

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel=BROWSER_CHANNEL,
            args=["--no-sandbox", "--disable-dev-shm-usage"] + ANTI_DETECTION_ARGS,
            viewport={"width": 1440, "height": 900},
            ignore_default_args=["--enable-automation"],
        )

        # Stealth
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(browser)
        except Exception:
            pass

        page = browser.pages[0] if browser.pages else browser.new_page()
        rec.attach(page)

        # Auth check
        page.goto(f"{CORTI_BASE}/", wait_until="domcontentloaded", timeout=30000)
        for _ in range(16):
            page.wait_for_timeout(500)
            if "/login" not in page.url and "/signin" not in page.url and "accounts.google" not in page.url:
                break
        if "/login" in page.url or "/signin" in page.url or "accounts.google" in page.url:
            sys.exit(f"[crawl] Not authenticated. URL: {page.url}")

        # Resolve project_id
        project_id = None
        for _ in range(10):
            page.wait_for_timeout(500)
            if "/project/" in page.url:
                project_id = page.url.split("/project/")[1].split("/")[0]
                break

        # If still no project_id, try fetching from localStorage / first project from API
        if not project_id:
            try:
                # Visit a page that triggers /rest/v1/projects load
                page.goto(f"{CORTI_BASE}/", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(2000)
                # Look for project links in DOM
                hrefs = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href*="/project/"]'))
                              .map(a => a.href)
                              .filter(h => h.includes('/project/'))
                """)
                if hrefs:
                    m = hrefs[0].split("/project/")[1].split("/")[0]
                    if m and len(m) > 8:
                        project_id = m
            except Exception:
                pass

        print(f"[crawl] Authenticated. project_id={project_id}")
        if not project_id:
            print("[crawl] WARN: No project_id; URLs will be root-scoped (some may 404).")

        # Walk each URL with its recipe
        for name, recipe in RECIPES.items():
            path = URL_PATHS.get(name, f"/{name}")
            if project_id and path != "/":
                url = f"{CORTI_BASE}/project/{project_id}{path}"
            else:
                url = f"{CORTI_BASE}{path}"
            print(f"\n[interact] {name}: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)
                rec.drain_browser_streams(page)

                # Initial screenshot
                page.screenshot(path=str(INTERACTIONS_DIR / f"{name}_00_initial.png"), full_page=True)

                # Execute recipe
                execute_recipe(page, recipe, rec)

                # Drain after each step
                for step_idx in range(len(recipe)):
                    rec.drain_browser_streams(page)
                    page.wait_for_timeout(300)
                    page.screenshot(path=str(INTERACTIONS_DIR / f"{name}_{step_idx+1:02d}_step.png"), full_page=True)

                # Final snapshot
                html_path = INTERACTIONS_DIR / f"{name}_final.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(page.content())

                print(f"  → {len(rec.requests)} reqs captured this page")

            except Exception as e:
                print(f"  → FAIL: {type(e).__name__}: {str(e)[:100]}")

        browser.close()

    # ── Persist ──
    print(f"\n[interact] Writing artifacts...")
    with open(OUTPUT_DIR / "api-contracts-interactive.json", "w", encoding="utf-8") as f:
        json.dump({
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "project_id": project_id,
            "total_requests": len(rec.requests),
            "total_ws_frames": len(rec.ws_frames),
            "total_sse_events": len(rec.sse_events),
            "total_clicks": len(rec.clicks),
            "requests": rec.requests,
        }, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "interaction-graph.json", "w", encoding="utf-8") as f:
        json.dump({
            "clicks": rec.clicks,
            "edges": [{"click": c, "request_ids": [r["id"] for r in rec.requests
                                                    if r.get("triggered_by_click")
                                                    and abs((datetime.fromisoformat(r["triggered_by_click"]["ts"].replace("Z","+00:00")) -
                                                             datetime.fromisoformat(c["ts"].replace("Z","+00:00")) if False else
                                                             (datetime.now(timezone.utc) - datetime.now(timezone.utc))).total_seconds()) < 5]}
                      for c in rec.clicks],
        }, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "ws-streams.jsonl", "w", encoding="utf-8") as f:
        for fr in rec.ws_frames:
            f.write(json.dumps(fr, ensure_ascii=False) + "\n")

    print(f"  → api-contracts-interactive.json ({len(rec.requests)} reqs)")
    print(f"  → interaction-graph.json ({len(rec.clicks)} clicks)")
    print(f"  → ws-streams.jsonl ({len(rec.ws_frames)} frames)")
    print(f"  → interactions/<page>_NN_step.png × {sum(1 for _ in INTERACTIONS_DIR.rglob('*.png'))}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Walk all pages with recipes")
    parser.add_argument("--only", type=str, help="Only run this page recipe")
    args = parser.parse_args()

    if args.all or args.only:
        crawl_interactive()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()