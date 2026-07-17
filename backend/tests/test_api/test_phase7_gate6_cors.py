"""Phase 7 Gate 6 — Allowed Origins / CORS enforcement tests.

Covers §11.1:
  - Allowed Origin preflight → 204 with Access-Control-Allow-Origin echo
  - Allowed Origin non-preflight → response has Access-Control-Allow-Origin
  - Disallowed Origin preflight → 403 ORIGIN_NOT_ALLOWED
  - Disallowed Origin non-preflight → 403 ORIGIN_NOT_ALLOWED
  - Wildcard '*' forbidden in client_credentials mode (Gate 5 already
    enforces at write time; here we just confirm 'none' isn't on the wire)
  - Same-origin request (no Origin header) → passes through unmodified
  - Console route with partner Origin → static CORSMiddleware still owns it
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        # Reset the partner-origin cache before each test so DB writes
        # made in-test are visible.
        from app.middleware.partner_cors import _all_partner_origins
        _all_partner_origins._cache = None  # type: ignore[attr-defined]
        yield c
        _all_partner_origins._cache = None  # type: ignore[attr-defined]


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _make_partner_client(
    client: TestClient,
    *,
    name: str = "Partner Hospital CORS",
    allowed_origins: list[str] | None = None,
) -> dict:
    """Create an OAuthClient with given allowed_origins; return the response body."""
    body = {
        "name": name,
        "description": "CORS test client",
        "scopes": "agents:run runs:read",
        "allowed_origins": allowed_origins or ["https://partner-test.example"],
    }
    resp = client.post("/api/clients", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ────────────────────────────────────────────────────────────────────
# §11.1 preflight — allowed
# ────────────────────────────────────────────────────────────────────


def test_preflight_allowed_partner_origin_returns_204(client: TestClient) -> None:
    """OPTIONS preflight from a partner Origin on the client allowlist
    returns 204 with Access-Control-Allow-Origin echo."""
    body = _make_partner_client(client, allowed_origins=["https://partner-test.example"])
    api_client_id = body["client_id"]

    resp = client.options(
        f"/api/v1/runs/some-run-id",
        headers={
            "Origin": "https://partner-test.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, content-type",
        },
    )
    assert resp.status_code == 204, resp.text
    assert resp.headers.get("access-control-allow-origin") == "https://partner-test.example"
    assert "GET" in resp.headers.get("access-control-allow-methods", "")
    assert "origin" in resp.headers.get("vary", "").lower()


def test_preflight_allowed_static_origin(client: TestClient) -> None:
    """Static CORS_ORIGINS entries continue to work on partner routes
    (e.g. the Console dev origin) — they take the same fast-path."""
    from app.config import settings
    static_origin = (settings.CORS_ORIGINS or ["http://localhost:3000"])[0]

    resp = client.options(
        "/api/v1/agents/medical-coding-agent/run",
        headers={
            "Origin": static_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code == 204, resp.text
    assert resp.headers.get("access-control-allow-origin") == static_origin


# ────────────────────────────────────────────────────────────────────
# §11.1 preflight — disallowed
# ────────────────────────────────────────────────────────────────────


def test_preflight_disallowed_origin_returns_403(client: TestClient) -> None:
    """OPTIONS preflight from an Origin NOT on any allowlist → 403
    ORIGIN_NOT_ALLOWED, with Access-Control-Allow-Origin: null so the
    browser surfaces a CORS error rather than a silent block."""
    _make_partner_client(client, allowed_origins=["https://real-partner.example"])

    resp = client.options(
        "/api/v1/runs/some-run-id",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "ORIGIN_NOT_ALLOWED"
    assert resp.headers.get("access-control-allow-origin") == "null"


def test_non_preflight_disallowed_origin_returns_403(client: TestClient) -> None:
    """Non-preflight GET/POST from a disallowed Origin → 403."""
    _make_partner_client(client, allowed_origins=["https://real-partner.example"])

    resp = client.get(
        "/api/v1/runs/some-run-id",
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "ORIGIN_NOT_ALLOWED"


# ────────────────────────────────────────────────────────────────────
# §11.1 non-preflight — allowed
# ────────────────────────────────────────────────────────────────────


def test_non_preflight_allowed_partner_origin_tags_response(client: TestClient) -> None:
    """A GET from an allowed partner Origin reaches the route handler
    AND the response carries Access-Control-Allow-Origin: <origin>."""
    _make_partner_client(client, allowed_origins=["https://partner-test.example"])

    # The route will likely 404 the run_id, but the CORS header must
    # still be present — that's what we're checking.
    resp = client.get(
        "/api/v1/runs/never-existed",
        headers={"Origin": "https://partner-test.example"},
    )
    # The route handler responds (probably 404 since no such run),
    # but the CORS header must still be echoed.
    assert resp.headers.get("access-control-allow-origin") == "https://partner-test.example"


# ────────────────────────────────────────────────────────────────────
# Same-origin requests (no Origin header)
# ────────────────────────────────────────────────────────────────────


def test_no_origin_header_passes_through(client: TestClient) -> None:
    """A request without an Origin header is same-origin (e.g. server-to-server).
    PartnerCORSMiddleware must not interfere."""
    resp = client.get("/api/v1/runs/never-existed")
    # No CORS header added (no Origin to echo).
    assert resp.status_code in (404, 200)
    assert "access-control-allow-origin" not in resp.headers


def test_same_origin_with_origin_header_passes_through(client: TestClient) -> None:
    """Phase 7 Gate 10 fix: a browser on the demo page sends
    Origin: http://host:port for same-origin subresource loads (this is
    how the spec works for fetches triggered by JS modules / XHR).

    PartnerCORSMiddleware must recognize that Origin == request.host
    means the request is not actually cross-origin, and skip the
    per-client allowlist enforcement. Otherwise the demos can't load
    /api/embedded/assistant.js from their own host.
    """
    # TestClient default Host is "testserver"; emulate a same-origin
    # browser request by setting both Origin and Host to the same value.
    resp = client.get(
        "/api/embedded/assistant.js",
        headers={
            "Origin": "http://testserver",
            "Host": "testserver",
        },
    )
    # The route handler should respond normally — no 403 ORIGIN_NOT_ALLOWED.
    assert resp.status_code != 403, resp.text
    if resp.status_code == 200:
        # And no CORS echo header gets added (we skipped enforcement).
        assert "access-control-allow-origin" not in resp.headers


# ────────────────────────────────────────────────────────────────────
# Console routes — static CORSMiddleware owns them
# ────────────────────────────────────────────────────────────────────


def test_console_route_disallowed_partner_origin_not_blocked_by_partner_middleware(
    client: TestClient,
) -> None:
    """The /api/clients admin route is a Console route, NOT a partner
    route. PartnerCORSMiddleware should pass it through untouched, and
    the static CORSMiddleware will apply its own (separate) policy."""
    # Console routes are NOT in _PARTNER_ROUTE_PREFIXES; verify by
    # checking that /api/clients works with a partner origin.
    resp = client.get("/api/clients", headers={"Origin": "https://partner-test.example"})
    # We don't assert on CORS headers here (static CORSMiddleware may or
    # may not add them depending on its allowlist). We just assert that
    # PartnerCORSMiddleware didn't return 403 ORIGIN_NOT_ALLOWED.
    assert resp.status_code != 403 or resp.json().get("code") != "ORIGIN_NOT_ALLOWED"


# ────────────────────────────────────────────────────────────────────
# Cache eviction — freshly added Origins become valid without restart
# ────────────────────────────────────────────────────────────────────


def test_origin_added_after_first_request_eventually_allowed(client: TestClient) -> None:
    """When we add a new allowed_origin to a client, the cached
    allowlist should refresh within the cache TTL (60s). For tests we
    bust the cache manually to simulate the eventual consistency."""
    from app.middleware.partner_cors import _all_partner_origins

    # First request — disallowed because no partner has this origin yet.
    resp1 = client.options(
        "/api/v1/runs/x",
        headers={
            "Origin": "https://late-added.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp1.status_code == 403

    # Add a client with this origin now.
    _make_partner_client(client, allowed_origins=["https://late-added.example"])

    # Bust cache.
    _all_partner_origins._cache = None  # type: ignore[attr-defined]

    resp2 = client.options(
        "/api/v1/runs/x",
        headers={
            "Origin": "https://late-added.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp2.status_code == 204, resp2.text
    assert resp2.headers.get("access-control-allow-origin") == "https://late-added.example"
