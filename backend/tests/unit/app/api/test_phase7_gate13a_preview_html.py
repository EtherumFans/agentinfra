"""Phase 7 Gate 13A-2/3/5/6 — secure preview.html integration tests.

Verifies the iframe HTML response:

- Gate 13A-2/3: only `?psid=` is read; no token/PHI in URL → response
- Gate 13A-5: ships strict CSP, sandbox, no-store, no-referrer
- Gate 13A-6: psid is HTML-escaped; XSS payloads in psid are neutralized
- Gate 13A-3: response contains the MessageChannel handshake boilerplate
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_preview_html_only_reads_psid(client):
    """Only the psid query param is used; all other params ignored."""
    resp = await client.get(
        "/api/embedded/preview.html"
        "?psid=psid-xyz-123"
        "&token=should-not-appear"
        "&patientName=%E5%BC%A0%E4%B8%89"
        "&patientId=P001"
    )
    assert resp.status_code == 200
    body = resp.text
    assert "psid-xyz-123" in body
    # Sensitive params MUST NOT leak through to the HTML.
    assert "should-not-appear" not in body
    assert "P001" not in body
    # patientName is URL-encoded 张三 — neither the encoded nor the
    # decoded form may appear.
    assert "%E5%BC%A0" not in body
    assert "张三" not in body


async def test_preview_html_has_csp_header(client):
    """Response ships Content-Security-Policy with nonce."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    csp = resp.headers.get("content-security-policy", "")
    assert "script-src" in csp
    assert "nonce-" in csp
    assert "frame-ancestors" in csp


async def test_preview_html_has_no_store_header(client):
    """Cache-Control: no-store prevents HAR + browser history leaks."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    cc = resp.headers.get("cache-control", "")
    assert "no-store" in cc


async def test_preview_html_has_no_referrer_header(client):
    """Referrer-Policy: no-referrer strips iframe URL from sub-resource
    requests (T4)."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    assert resp.headers.get("referrer-policy", "") == "no-referrer"


async def test_preview_html_has_sandbox_header(client):
    """Sandbox restricts the iframe to allow-scripts + allow-same-origin."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    sandbox = resp.headers.get("content-security-policy-sandbox", "")
    assert "allow-scripts" in sandbox
    assert "allow-same-origin" in sandbox
    # No allow-top-navigation, no allow-popups, no allow-forms.
    assert "allow-top-navigation" not in sandbox
    assert "allow-popups" not in sandbox


async def test_preview_html_has_messagechannel_handshake(client):
    """The response body contains the MessageChannel handshake code
    (parent + iframe proving nonce knowledge)."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    body = resp.text
    assert "icoder:open-port" in body
    assert "icoder:ready-ping" in body
    assert "icoder:bootstrap" in body
    # Strict source check (event.source !== window.parent).
    assert "ev.source !== window.parent" in body


async def test_preview_html_has_xss_safe_psid(client):
    """psid is HTML-escaped; an XSS payload can't break out of the
    <code> element (Gate 13A-6)."""
    xss = "<script>alert('xss')</script>"
    resp = await client.get(f"/api/embedded/preview.html?psid={xss}")
    body = resp.text
    # The raw payload MUST NOT appear verbatim — the sanitizer drops
    # any non-alphanumeric / non -/_ char.
    assert "<script>alert('xss')</script>" not in body


async def test_preview_html_widget_loads_from_same_origin(client):
    """The widget bundle is loaded same-origin (no cross-origin
    preflight needed)."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    body = resp.text
    assert "/api/embedded/assistant.js" in body
    # No external CDN URL.
    assert "unpkg.com" not in body
    assert "cdn.jsdelivr.net" not in body


async def test_preview_html_no_wildcard_postmessage(client):
    """Gate 13A-2 — no postMessage(..., '*') anywhere in the response."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    body = resp.text
    assert "postMessage(" not in body or "', '*')" not in body
    # Specifically the dangerous wildcard send pattern.
    assert "postMessage(*" not in body
    assert "', '*')" not in body
