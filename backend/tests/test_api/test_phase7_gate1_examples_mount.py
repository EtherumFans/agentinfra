"""Phase 7 Gate 1 — /examples/* static mount tests.

Verifies the backend mount for the 3 partner demos:
- /examples/                  → index
- /examples/medical-coding/   → Medical Coding demo
- /examples/cdi/              → CDI demo
- /examples/drg-dip/          → DRG/DIP demo
- /examples/config.js         → env-driven partner config (no secrets)

Covers Phase 7 §6.1-6.3 requirements:
- production asset serving (HTML, not src)
- version metadata
- Cache-Control + CSP + nosniff + frame-ancestors none
- correct MIME types
- no source directory exposure
- no directory traversal
- env-driven config injection without secrets
"""
from __future__ import annotations

import os
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_examples_index_lists_all_3_demos():
    from app.main import app

    client = TestClient(app)
    r = client.get("/examples/")
    assert r.status_code == 200
    body = r.text
    for slug in ("medical-coding", "cdi", "drg-dip"):
        assert f"/examples/{slug}/" in body, f"index missing link to {slug}"


def test_each_demo_serves_html_with_security_headers():
    from app.main import app

    client = TestClient(app)
    for slug in ("medical-coding", "cdi", "drg-dip"):
        r = client.get(f"/examples/{slug}/")
        assert r.status_code == 200, f"{slug} failed"
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers.get("x-content-type-options") == "nosniff"
        assert r.headers.get("x-frame-options") == "DENY"
        csp = r.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp
        assert "default-src 'self'" in csp
        assert r.headers.get("x-icoder-demo-version") == "1.0.0-phase7-gate6"
        assert r.headers.get("cache-control") == "no-cache, must-revalidate"
        assert "1.0.0-phase7-gate6" in r.text
        assert "<icoder-embedded" in r.text
        # Demos load partner config.js before widget init (Phase 7 Gate 1)
        assert "/examples/config.js" in r.text


def test_config_js_injects_env_values_without_secrets():
    from app.main import app

    client = TestClient(app)
    env_patch = {
        "ICODER_BASE_URL": "https://partner.icoder.cloud",
        "ICODER_AGENT_REF": "cdi",
        "ICODER_API_CLIENT_ID": "partner-001",
        "ICODER_ORGANIZATION_ID": "org-123",
    }
    with patch.dict(os.environ, env_patch, clear=False):
        r = client.get("/examples/config.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    body = r.text
    assert "window.icoderConfig" in body
    assert "partner.icoder.cloud" in body
    assert "partner-001" in body
    assert "org-123" in body
    # Per §6.3: real secrets never ship to the browser.
    assert "client_secret" not in body.lower()
    assert "api_client_secret" not in body.lower()


def test_config_js_defaults_when_env_absent():
    from app.main import app

    client = TestClient(app)
    # Strip all ICODER_* env vars so the defaults kick in
    env_keys = [
        k for k in os.environ
        if k.startswith("ICODER_BASE_URL")
        or k.startswith("ICODER_AGENT_REF")
        or k.startswith("ICODER_API_CLIENT_ID")
        or k.startswith("ICODER_ORGANIZATION_ID")
    ]
    env_patch = {k: None for k in env_keys}
    with patch.dict(os.environ, env_patch, clear=True):
        r = client.get("/examples/config.js")
    assert r.status_code == 200
    assert "window.icoderConfig" in r.text
    # Defaults: localhost backend, medical-coding-agent
    assert "localhost:8000" in r.text or "baseUrl" in r.text


def test_unknown_demo_returns_404():
    from app.main import app

    client = TestClient(app)
    r = client.get("/examples/evil-demo/")
    assert r.status_code == 404


def test_directory_traversal_blocked():
    """Phase 7 §6.1: 不允许目录遍历."""
    from app.main import app

    client = TestClient(app)
    # Path traversal attempts — all must 404 (or 400 from Starlette
    # path normalization). Either way, never serve a file outside demos/.
    attempts = [
        "/examples/..%2F..%2Fetc%2Fpasswd",
        "/examples/%2e%2e/%2e%2e/etc/passwd",
        "/examples/medical-coding/../../etc/passwd",
    ]
    for attempt in attempts:
        r = client.get(attempt, follow_redirects=False)
        assert r.status_code in (404, 400), (
            f"traversal attempt {attempt!r} returned {r.status_code}; "
            "expected 404 or 400"
        )


def test_demos_use_compiled_widget_bundle_not_src():
    """Phase 7 §6.1: 使用正式构建产物 — demos load /api/embedded/assistant.js
    (the compiled dist), not /src/icoder-assistant.ts or similar."""
    from app.main import app

    client = TestClient(app)
    for slug in ("medical-coding", "cdi", "drg-dip"):
        r = client.get(f"/examples/{slug}/")
        assert "/api/embedded/assistant.js" in r.text, (
            f"{slug} should load compiled /api/embedded/assistant.js"
        )
        assert "/src/" not in r.text, f"{slug} should not reference src/ files"
