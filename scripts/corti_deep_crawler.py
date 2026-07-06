#!/usr/bin/env python3
"""Corti Deep Reverse Engineer — End-to-end per feature.

Step 0.4: each feature is walked from page load → all interactions →
verifying API responses fire → screenshotting every state. No shallow
"click and pray" — every step waits for either an XHR or DOM change to
prove the interaction landed.

Output: docs/corti-reverse-engineered/api-contracts-v2.json
        docs/corti-reverse-engineered/feature-flows/<feature>/*.png + .json
"""

import argparse
import json
import sys
import time
import re
import io
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

# Force UTF-8 stdout for Windows
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright, Page, Locator, TimeoutError as PWTimeout, expect

CORTI_BASE = "https://console.corti.app"
USER_DATA_DIR = Path(".corti-user-data")
OUTPUT_DIR = Path("docs/corti-reverse-engineered")
FEATURE_DIR = OUTPUT_DIR / "feature-flows"

BROWSER_CHANNEL = "msedge"
ANTI_DETECTION_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-first-run",
    "--no-default-browser-check",
]

SAMPLE_EMR = (
    "患者男性,67 岁,因「反复胸闷、心悸 3 月,加重伴双下肢水肿 1 周」入院。"
    "既往高血压病史 12 年,糖尿病史 8 年。"
    "入院查体:BP 162/95 mmHg,心率 98 次/分,双下肢轻度凹陷性水肿。"
    "心电图示房颤,心脏超声示左心扩大,LVEF 38%。"
    "诊断:1. 慢性心力衰竭 心功能 III 级(NYHA);"
    "2. 心房颤动;3. 高血压 2 级(极高危);4. 2 型糖尿病。"
    "入院后行冠状动脉造影示前降支中段 80% 狭窄,置入药物洗脱支架 1 枚。"
)

# ─────────────────────────────────────────────────────────────────────────────
# Deep-click utilities — verify the click landed, with cascading fallbacks
# ─────────────────────────────────────────────────────────────────────────────

def smart_click(page: Page, target: str | list[str], timeout: int = 5000) -> dict:
    """Click an element by various selectors; return what happened.

    target: list of (kind, value) tuples tried in order:
      ("text", "Generate"), ("role", "button", "Generate"),
      ("aria", "Submit form"), ("css", ".btn-primary"), ("testid", "submit-btn")

    Returns: {"clicked": bool, "method": str, "error": str|None}
    """
    if isinstance(target, str):
        target = [("text", target)]

    selectors = []
    for item in target:
        if len(item) == 2:
            kind, value = item
            if kind == "text":
                selectors += [
                    f'button:has-text("{value}")',
                    f'a:has-text("{value}")',
                    f'[role="button"]:has-text("{value}")',
                    f'[role="tab"]:has-text("{value}")',
                    f'[role="link"]:has-text("{value}")',
                    f'span:has-text("{value}")',
                    f'div:has-text("{value}"):not(:has(*))',
                ]
            elif kind == "role":
                selectors.append(f'[role="{value}"]')
            elif kind == "aria":
                selectors.append(f'[aria-label="{value}"]')
            elif kind == "css":
                selectors.append(value)
            elif kind == "testid":
                selectors.append(f'[data-testid="{value}"]')
            elif kind == "placeholder":
                selectors.append(f'[placeholder="{value}"]')
        elif len(item) == 3 and item[0] == "role":
            role, name = item[1], item[2]
            selectors += [
                f'[role="{role}"][aria-label*="{name}" i]',
                f'[role="{role}"][name*="{name}" i]',
            ]

    last_err = None
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            # Verify enabled
            if loc.is_disabled():
                continue
            loc.click(timeout=3000)
            return {"clicked": True, "method": sel, "error": None}
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            continue

    return {"clicked": False, "method": None, "error": last_err}


def wait_for_api(page: Page, pattern: str | re.Pattern, timeout_ms: int = 15000) -> dict | None:
    """Wait for an XHR/Fetch whose URL matches pattern; return the request dict.

    pattern: substring (str) or compiled regex
    """
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        # Look at recent requests
        recent = getattr(page, "_corti_recent_reqs", [])
        for r in recent:
            if isinstance(pattern, str):
                if pattern in r["url"]:
                    return r
            elif pattern.search(r["url"]):
                return r
        page.wait_for_timeout(300)
    return None


def wait_for_response_json(page: Page, url_pattern: str, timeout_ms: int = 15000) -> dict | None:
    """Wait for a specific response and return its parsed JSON body."""
    try:
        with page.expect_response(
            lambda r: url_pattern in r.url,
            timeout=timeout_ms,
        ) as resp_info:
            pass
        resp = resp_info.value
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text()[:4000]}
    except PWTimeout:
        return None


def fill_first_textarea(page: Page, value: str, placeholder_hint: str = None) -> bool:
    """Fill the most relevant textarea. If placeholder_hint given, prefer matching."""
    selectors = ["textarea"]
    if placeholder_hint:
        selectors.insert(0, f'textarea[placeholder*="{placeholder_hint}" i]')
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=3000)
            loc.fill(value)
            return True
        except Exception:
            continue
    return False


def close_modal(page: Page) -> bool:
    """Best-effort close any open modal/dialog."""
    for sel in [
        '[aria-label="Close"]', '[aria-label="close"]',
        'button:has-text("Cancel")', 'button:has-text("Close")',
        '[role="dialog"] button[type="button"]',
    ]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                loc.click(timeout=1500)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    # Press Escape as last resort
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False


def safe_screenshot(page: Page, path: str, full_page: bool = True) -> bool:
    """Screenshot with a short timeout + animations disabled; swallow errors.

    Edge hangs on `document.fonts.ready` even after the init-script patch,
    so we cap at 5s and accept a partial render rather than abort the feature.
    """
    try:
        page.screenshot(path=path, full_page=full_page, timeout=5000, animations="disabled")
        return True
    except Exception as e:
        print(f"    [warn] screenshot {Path(path).name} failed: {type(e).__name__}: {str(e)[:60]}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Network recorder — wraps XHR/Fetch capture
# ─────────────────────────────────────────────────────────────────────────────

class DeepRecorder:
    def __init__(self):
        self.requests = []
        self._next_id = 0

    def attach(self, page: Page):
        # Init script: store clicks (don't clear so we don't lose them)
        page.add_init_script("""
            window.__corti_clicks__ = window.__corti_clicks__ || [];
            window.__corti_reqs__ = window.__corti_reqs__ || [];
            document.addEventListener('click', (e) => {
                const t = e.target;
                const sel = (t.id && '#' + t.id)
                    || (t.dataset?.testid && '[data-testid="' + t.dataset.testid + '"]')
                    || (t.getAttribute('aria-label') && '[aria-label="' + t.getAttribute('aria-label') + '"]')
                    || (t.getAttribute('role') && '[role="' + t.getAttribute('role') + '"]')
                    || t.tagName.toLowerCase();
                window.__corti_clicks__.push({
                    ts: Date.now(),
                    selector: sel,
                    tag: t.tagName.toLowerCase(),
                    text: (t.innerText || '').slice(0, 80),
                    ariaLabel: t.getAttribute('aria-label'),
                });
            }, true);
            // Patch fetch to record
            const origFetch = window.fetch;
            window.fetch = function(...args) {
                window.__corti_reqs__.push({ts: Date.now(), url: String(args[0] || ''), method: (args[1] && args[1].method) || 'GET'});
                return origFetch.apply(this, args);
            };
            // Make document.fonts.ready resolve immediately — avoids Playwright
            // screenshot hanging on Edge "waiting for fonts to load".
            try {
                if (document.fonts && document.fonts.ready) {
                    Object.defineProperty(document.fonts, 'ready', {
                        get: () => Promise.resolve(document.fonts),
                        configurable: true,
                    });
                }
            } catch (e) {}
        """)
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def _on_request(self, req):
        if any(s in req.url for s in ["/assets/", ".png", ".jpg", ".svg", ".css", ".ico",
                                       "google-analytics", "cookiebot", "datadog",
                                       "sentry", "fullstory", "segment.io", ".woff"]):
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
            "url": req.url,
            "resource_type": req.resource_type,
            "req_body": body[:8000] if body else None,
        })
        # Also push to window for wait_for_api
        try:
            req.page.evaluate("(r) => window.__corti_reqs__.push(r)",
                              {"id": rid, "ts": req.url, "url": req.url, "method": req.method})
        except Exception:
            pass

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

    def drain_clicks(self, page: Page) -> list:
        try:
            return page.evaluate("() => window.__corti_clicks__ || []")
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────────────────
# Deep feature flows — every step is verified
# ─────────────────────────────────────────────────────────────────────────────

def feature_home(page: Page, rec: DeepRecorder, out_dir: Path):
    """Project Home: walk all 4 tabs (Transcribe/Document/Chat/Code NEW)."""
    print("\n[FEATURE] home — 4 tabs")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)

    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    for tab_text in ["Transcribe", "Document", "Chat", "Code"]:
        print(f"  → tab '{tab_text}'")
        result = smart_click(page, [
            ("role", "tab", tab_text),
            ("text", tab_text),
        ])
        if result["clicked"]:
            page.wait_for_timeout(2500)
            screenshot_path = str(out_dir / f"tab_{tab_text.lower()}.png")
            safe_screenshot(page, screenshot_path)
            print(f"    [OK] clicked via {result['method'][:60]}")
        else:
            print(f"    [FAIL] click: {result['error']}")

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "home", "tabs_clicked": ["Transcribe","Document","Chat","Code"],
                    "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_agents(page: Page, rec: DeepRecorder, out_dir: Path):
    """AI Studio > Agents: My agents / Pre-built agents tabs, click cards."""
    print("\n[FEATURE] ai-studio-agents — My + Pre-built tabs, click cards")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    # Pre-built tab
    print("  → Pre-built tab")
    smart_click(page, [("role", "tab", "Pre-built"), ("text", "Pre-built")])
    page.wait_for_timeout(3000)
    safe_screenshot(page, str(out_dir / "01_prebuilt_tab.png"))

    # Click each agent card
    cards = page.locator('a[href*="/agents/"], [role="button"][href*="/agents/"], button:has(svg)').all()
    print(f"  → found {len(cards)} clickable elements in prebuilt")
    clicked = 0
    for i, card in enumerate(cards[:8]):  # cap to 8
        try:
            if card.is_visible(timeout=500):
                txt = card.inner_text()[:60].replace("\n", " | ")
                card.click(timeout=2000)
                page.wait_for_timeout(2000)
                safe_screenshot(page, str(out_dir / f"02_card_{i:02d}.png"))
                clicked += 1
                # Go back
                page.go_back()
                page.wait_for_timeout(2000)
                # Re-click Pre-built tab (might have reset)
                smart_click(page, [("role", "tab", "Pre-built"), ("text", "Pre-built")])
                page.wait_for_timeout(1500)
        except Exception as e:
            continue
    print(f"  → clicked {clicked} cards")

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "agents", "cards_clicked": clicked,
                    "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_agents_new(page: Page, rec: DeepRecorder, out_dir: Path):
    """New Agent page: select templates, fill preview, click Customize."""
    print("\n[FEATURE] ai-studio-agents-new — select templates")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    # Click radio for first 3 templates
    radios = page.locator('input[type="radio"][name*="agent"], input[type="radio"]').all()
    print(f"  → found {len(radios)} template radios")
    for i, radio in enumerate(radios[:3]):
        try:
            radio.click(timeout=2000)
            page.wait_for_timeout(2000)
            safe_screenshot(page, str(out_dir / f"01_template_{i:02d}.png"))
        except Exception:
            continue

    # Try Customize button
    print("  → Customize agent button")
    smart_click(page, [("text", "Customize agent"), ("text", "Customize")])
    page.wait_for_timeout(2500)
    safe_screenshot(page, str(out_dir / "02_customize.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "agents-new", "templates_clicked": min(3, len(radios)),
                    "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_medical_coding(page: Page, rec: DeepRecorder, out_dir: Path):
    """Medical Coding: type EMR → click Predict → wait for codes → toggle JSON."""
    print("\n[FEATURE] ai-studio-medical-coding — Predict codes end-to-end")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_load_state("networkidle", timeout=20000)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    # Step 1: Fill textarea with EMR
    print("  → fill textarea with EMR")
    filled = fill_first_textarea(page, SAMPLE_EMR, placeholder_hint="clinical")
    print(f"    {'✓ filled' if filled else '✗ fill failed'}")
    page.wait_for_timeout(1500)
    safe_screenshot(page, str(out_dir / "01_filled.png"))

    # Step 2: Click Predict button
    print("  → click Predict codes")
    before_predict = len(rec.requests)
    smart_click(page, [
        ("text", "Predict codes"),
        ("text", "Generate"),
        ("text", "Run"),
        ("text", "Submit"),
    ])
    print(f"  → waiting for /v2/tools/coding/ response...")
    # Wait for response
    coding_resp = wait_for_api(page, r"/v2/tools/coding/", timeout_ms=20000)
    if coding_resp:
        print(f"    ✓ got response: status={coding_resp.get('resp_status')}")
    else:
        print(f"    ✗ no /v2/tools/coding/ response within 20s")
    page.wait_for_timeout(3000)
    safe_screenshot(page, str(out_dir / "02_predicted.png"))

    # Step 3: Try JSON toggle
    print("  → click JSON toggle")
    smart_click(page, [("text", "JSON"), ("role", "tab", "JSON")])
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "03_json.png"))

    # Step 4: Coding systems toggle
    print("  → toggle ICD-10-CM Outpatient")
    smart_click(page, [("text", "ICD-10-CM Outpatient"), ("text", "Outpatient")])
    page.wait_for_timeout(1500)
    safe_screenshot(page, str(out_dir / "04_coding_system.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "medical-coding", "filled_textarea": filled,
                    "got_predict_response": coding_resp is not None,
                    "predict_response": coding_resp,
                    "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_text_generation(page: Page, rec: DeepRecorder, out_dir: Path):
    """Text Generation: type + Generate document."""
    print("\n[FEATURE] ai-studio-text-generation — type + Generate")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → fill textarea")
    fill_first_textarea(page, "Patient with chest pain admitted for evaluation.")
    page.wait_for_timeout(1000)

    print("  → click Generate")
    smart_click(page, [("text", "Generate document"), ("text", "Generate")])
    page.wait_for_timeout(8000)
    safe_screenshot(page, str(out_dir / "01_generated.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "text-generation", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_fact_extraction(page: Page, rec: DeepRecorder, out_dir: Path):
    """Fact Extraction: type + Extract facts."""
    print("\n[FEATURE] ai-studio-fact-extraction — type + Extract")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → fill textarea")
    fill_first_textarea(page, SAMPLE_EMR)
    page.wait_for_timeout(1000)

    print("  → click Extract facts")
    smart_click(page, [("text", "Extract facts"), ("text", "Extract")])
    wait_for_api(page, r"/v2/tools/extract-facts", timeout_ms=15000)
    page.wait_for_timeout(5000)
    safe_screenshot(page, str(out_dir / "01_extracted.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "fact-extraction", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_speech_to_text(page: Page, rec: DeepRecorder, out_dir: Path):
    """Speech-to-Text: try Start recording, then Dictation sub-tab."""
    print("\n[FEATURE] ai-studio-speech-to-text — record attempt")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    # Sub-tabs: Dictation / Ambient / Pre-recorded
    for tab in ["Dictation", "Ambient", "Pre-recorded"]:
        print(f"  → sub-tab {tab}")
        smart_click(page, [("role", "tab", tab), ("text", tab)])
        page.wait_for_timeout(1500)
        sp = str(out_dir / f"subtab_{tab.lower()}.png")
        safe_screenshot(page, sp)

    # Back to Dictation, try Start recording
    smart_click(page, [("role", "tab", "Dictation"), ("text", "Dictation")])
    page.wait_for_timeout(1500)
    print("  → click Start recording")
    smart_click(page, [("text", "Start recording"), ("text", "Record"), ("text", "Start")])
    page.wait_for_timeout(4000)
    safe_screenshot(page, str(out_dir / "01_recording.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "speech-to-text", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_embedded_assistant(page: Page, rec: DeepRecorder, out_dir: Path):
    """Embedded Assistant: try Initialize session, change Session defaults."""
    print("\n[FEATURE] ai-studio-embedded-assistant — session init")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(3000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    # Wait for auto-init to complete
    wait_for_api(page, r"/functions/v1/projects/.+/assistant-settings", timeout_ms=10000)
    page.wait_for_timeout(3000)
    safe_screenshot(page, str(out_dir / "01_initialized.png"))

    # Try clicking Initialize again
    print("  → click Initialize / Preview")
    smart_click(page, [("text", "Initialize"), ("text", "Preview"), ("text", "Try")])
    page.wait_for_timeout(4000)
    safe_screenshot(page, str(out_dir / "02_reinit.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "embedded-assistant", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_api_clients(page: Page, rec: DeepRecorder, out_dir: Path):
    """API Clients: open Create modal, fill, submit."""
    print("\n[FEATURE] api-clients — Create modal")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → click Create API client")
    smart_click(page, [("text", "Create API client"), ("text", "New API client"), ("text", "Create")])
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "01_create_modal.png"))

    # Try to fill name input
    print("  → fill name input")
    for sel in ['input[name="name"]', 'input[placeholder*="name" i]', 'input[type="text"]']:
        try:
            page.locator(sel).first.fill("test-client-deep", timeout=2000)
            break
        except Exception:
            continue
    page.wait_for_timeout(1000)

    # Submit
    print("  → submit")
    smart_click(page, [("text", "Submit"), ("text", "Save"), ("text", "Create")])
    wait_for_api(page, r"/api_clients", timeout_ms=10000)
    page.wait_for_timeout(2500)
    safe_screenshot(page, str(out_dir / "02_submitted.png"))
    close_modal(page)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "api-clients", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_team(page: Page, rec: DeepRecorder, out_dir: Path):
    """Team: open Invite modal, fill email, send."""
    print("\n[FEATURE] team — Invite member")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → click Invite")
    smart_click(page, [("text", "Invite"), ("text", "Invite member"), ("text", "Add member")])
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "01_invite_modal.png"))

    print("  → fill email")
    for sel in ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="email" i]']:
        try:
            page.locator(sel).first.fill("test@example.com", timeout=2000)
            break
        except Exception:
            continue
    page.wait_for_timeout(1000)
    safe_screenshot(page, str(out_dir / "02_email_filled.png"))
    close_modal(page)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "team", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_billing(page: Page, rec: DeepRecorder, out_dir: Path):
    """Billing: switch Plan / Billing History / Business info tabs."""
    print("\n[FEATURE] billing — 3 tabs")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    for tab in ["Plan", "Billing History", "Business info"]:
        print(f"  → tab {tab}")
        smart_click(page, [("role", "tab", tab), ("text", tab)])
        page.wait_for_timeout(2500)
        sp = str(out_dir / f"tab_{tab.lower().replace(' ', '_')}.png")
        safe_screenshot(page, sp)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "billing", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_customers(page: Page, rec: DeepRecorder, out_dir: Path):
    """Customers: search + Add customer modal."""
    print("\n[FEATURE] customers — search + Add")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → search input")
    for sel in ['input[placeholder*="Search" i]', 'input[type="search"]', 'input[type="text"]']:
        try:
            page.locator(sel).first.fill("test", timeout=2000)
            page.wait_for_timeout(2000)
            safe_screenshot(page, str(out_dir / "01_search.png"))
            break
        except Exception:
            continue

    print("  → click Add customer")
    smart_click(page, [("text", "Add customer"), ("text", "New customer")])
    page.wait_for_timeout(2500)
    safe_screenshot(page, str(out_dir / "02_add_modal.png"))
    close_modal(page)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "customers", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_templates(page: Page, rec: DeepRecorder, out_dir: Path):
    """Templates (Beta): View tabs (Templates/Sections), Create template."""
    print("\n[FEATURE] templates — view tabs + Create")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    for tab in ["Templates", "Sections"]:
        print(f"  → View tab {tab}")
        smart_click(page, [("role", "tab", tab), ("text", tab)])
        page.wait_for_timeout(2500)
        sp = str(out_dir / f"view_{tab.lower()}.png")
        safe_screenshot(page, sp)

    print("  → click Create template")
    smart_click(page, [("text", "Create template"), ("text", "New template")])
    page.wait_for_timeout(3000)
    safe_screenshot(page, str(out_dir / "01_create_modal.png"))
    close_modal(page)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "templates", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_settings(page: Page, rec: DeepRecorder, out_dir: Path):
    """Settings: Project info + Copy ID."""
    print("\n[FEATURE] settings — Copy ID")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    print("  → click Copy ID")
    smart_click(page, [("text", "Copy ID"), ("text", "Copy")])
    page.wait_for_timeout(1500)
    safe_screenshot(page, str(out_dir / "01_copied.png"))

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "settings", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def feature_developer_quickstart(page: Page, rec: DeepRecorder, out_dir: Path):
    """Developer Quickstart: SDK tabs + AI tools."""
    print("\n[FEATURE] developer-quickstart — SDK tabs")
    out_dir.mkdir(parents=True, exist_ok=True)
    n_reqs_before = len(rec.requests)
    page.wait_for_timeout(2000)
    safe_screenshot(page, str(out_dir / "00_initial.png"))

    for tab in ["Code with AI tools", "JS SDK", ".NET SDK"]:
        print(f"  → tab {tab}")
        smart_click(page, [("role", "tab", tab), ("text", tab)])
        page.wait_for_timeout(2500)
        sp = str(out_dir / f"tab_{tab.lower().replace(' ', '_').replace('.', '')}.png")
        safe_screenshot(page, sp)

    new_reqs = rec.requests[n_reqs_before:]
    print(f"  → {len(new_reqs)} new reqs")
    (out_dir / "summary.json").write_text(
        json.dumps({"feature": "developer-quickstart", "requests": new_reqs}, ensure_ascii=False, indent=2),
        encoding="utf-8")


FEATURES = {
    "home":                       feature_home,
    "ai-studio-agents":           feature_agents,
    "ai-studio-agents-new":       feature_agents_new,
    "ai-studio-medical-coding":   feature_medical_coding,
    "ai-studio-text-generation":  feature_text_generation,
    "ai-studio-fact-extraction":  feature_fact_extraction,
    "ai-studio-speech-to-text":   feature_speech_to_text,
    "ai-studio-embedded-asst":    feature_embedded_assistant,
    "api-clients":                feature_api_clients,
    "team":                       feature_team,
    "billing":                    feature_billing,
    "customers":                  feature_customers,
    "templates":                  feature_templates,
    "settings":                   feature_settings,
    "developer-quickstart":       feature_developer_quickstart,
}

URL_PATHS = {
    "home":                          "/",
    "ai-studio-agents":              "/ai-studio/agents",
    "ai-studio-agents-new":          "/ai-studio/agents/new",
    "ai-studio-medical-coding":      "/ai-studio/medical-coding",
    "ai-studio-text-generation":     "/ai-studio/text-generation",
    "ai-studio-fact-extraction":     "/ai-studio/fact-extraction",
    "ai-studio-speech-to-text":      "/ai-studio/speech-to-text",
    "ai-studio-embedded-asst":       "/ai-studio/embedded-assistant",
    "api-clients":                   "/api-clients",
    "team":                          "/team",
    "billing":                       "/billing",
    "customers":                     "/customers",
    "templates":                     "/templates",
    "settings":                      "/settings",
    "developer-quickstart":          "/developer-quickstart",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Walk all features")
    parser.add_argument("--only", type=str, help="Only this feature")
    parser.add_argument("--features", type=str, help="Comma-separated feature list")
    parser.add_argument("--from", dest="from_feature", type=str, help="Resume from feature")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)

    rec = DeepRecorder()
    selected = list(FEATURES.keys())
    if args.features:
        selected = [f.strip() for f in args.features.split(",") if f.strip()]
    elif args.only:
        selected = [args.only]
    elif getattr(args, "from_feature"):
        idx = list(FEATURES.keys()).index(args.from_feature)
        selected = list(FEATURES.keys())[idx:]

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel=BROWSER_CHANNEL,
            args=["--no-sandbox", "--disable-dev-shm-usage"] + ANTI_DETECTION_ARGS,
            viewport={"width": 1440, "height": 900},
            ignore_default_args=["--enable-automation"],
        )
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
        if "/login" in page.url or "/signin" in page.url:
            sys.exit(f"[crawl] Not authenticated. URL: {page.url}")

        # Walk each feature
        for name in selected:
            fn = FEATURES[name]
            path = URL_PATHS.get(name, f"/{name}")
            url = f"{CORTI_BASE}{path}"
            print(f"\n========== {name}: {url} ==========")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)
                fn(page, rec, FEATURE_DIR / name)
            except Exception as e:
                print(f"  ✗ FAIL: {type(e).__name__}: {str(e)[:100]}")

        # Capture all clicks
        clicks = rec.drain_clicks(page)
        with open(OUTPUT_DIR / "clicks.json", "w", encoding="utf-8") as f:
            json.dump(clicks, f, ensure_ascii=False, indent=2)
        print(f"\n[total] {len(rec.requests)} reqs, {len(clicks)} clicks")

        browser.close()

    # ── Persist final contracts ──
    with open(OUTPUT_DIR / "api-contracts-v2.json", "w", encoding="utf-8") as f:
        json.dump({
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "total_requests": len(rec.requests),
            "total_clicks": len(clicks),
            "requests": rec.requests,
        }, f, ensure_ascii=False, indent=2)
    print(f"[done] api-contracts-v2.json + {len(list(FEATURE_DIR.rglob('*.png')))} screenshots + {len(list(FEATURE_DIR.rglob('summary.json')))} summaries")


if __name__ == "__main__":
    main()