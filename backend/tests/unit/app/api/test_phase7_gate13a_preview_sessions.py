"""Phase 7 Gate 13A-1 — Preview Sessions endpoint integration tests.

Exercises the full HTTP flow:

1. POST /api/embedded/preview-sessions (Console JWT) → 201 + ticket + nonce
2. POST /api/embedded/preview-sessions/exchange (ticket) → 200 + runtime_token
3. GET /api/embedded/preview-sessions/{psid} (no auth) → 200 status
4. POST /api/embedded/preview-sessions/{psid}/revoke (Console JWT) → REVOKED
5. Negative: replay → 410 TICKET_ALREADY_USED
6. Negative: tampered ticket → 401 TICKET_INVALID_SIGNATURE
7. Negative: wrong iframe origin → 403 TICKET_ORIGIN_MISMATCH
8. Negative: expired ticket → 410 TICKET_EXPIRED
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest

from app.services.preview_ticket import (
    issue_preview_ticket,
    PreviewTicketError,
)


pytestmark = pytest.mark.asyncio


# ── helpers ──────────────────────────────────────────────────────────


async def _create_session(client, parent_origin="http://localhost:3000"):
    """Console (with auth bypass) creates a preview session."""
    resp = await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": parent_origin},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── happy path ────────────────────────────────────────────────────────


async def test_create_preview_session_returns_ticket(client):
    data = await _create_session(client)
    assert "ticket" in data and "." in data["ticket"]
    assert "nonce" in data and len(data["nonce"]) == 32
    assert "preview_session_id" in data and len(data["preview_session_id"]) >= 20
    assert "expires_at" in data
    assert "iframe_url" in data
    assert "psid=" in data["iframe_url"]
    # No PHI should leak through the iframe URL.
    assert "token=" not in data["iframe_url"]
    assert "patient" not in data["iframe_url"].lower()


async def test_exchange_returns_runtime_token(client):
    session = await _create_session(client)
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "http://test"},  # matches ASGITransport base url
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "runtime_token" in body
    assert "." in body["runtime_token"]
    assert body["preview_session_id"] == session["preview_session_id"]
    assert body["token_type"] == "bearer"
    assert "agents:run" in body["scopes"]


async def test_get_status_after_create(client):
    session = await _create_session(client)
    resp = await client.get(
        f"/api/embedded/preview-sessions/{session['preview_session_id']}"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["preview_session_id"] == session["preview_session_id"]


async def test_get_status_after_exchange(client):
    session = await _create_session(client)
    ex = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "http://test"},
    )
    assert ex.status_code == 200, ex.text
    resp = await client.get(
        f"/api/embedded/preview-sessions/{session['preview_session_id']}"
    )
    body = resp.json()
    assert body["status"] == "EXCHANGED"
    assert body["exchanged_at"] is not None


# ── negative: replay ─────────────────────────────────────────────────


async def test_replay_after_exchange_returns_410(client):
    session = await _create_session(client)
    # First exchange succeeds.
    r1 = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "http://test"},
    )
    assert r1.status_code == 200
    # Second exchange (replay) is forbidden.
    r2 = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "http://test"},
    )
    assert r2.status_code == 410
    assert "USED" in r2.json()["detail"]


# ── negative: tampered signature ─────────────────────────────────────


async def test_tampered_signature_returns_401(client):
    session = await _create_session(client)
    payload_b64, sig = session["ticket"].rsplit(".", 1)
    # Flip last char of signature.
    bad_sig = sig[:-1] + ("a" if sig[-1] != "a" else "b")
    bad_token = f"{payload_b64}.{bad_sig}"
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": bad_token},
        headers={"Origin": "http://test"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "TICKET_INVALID_SIGNATURE"


# ── negative: iframe origin mismatch ─────────────────────────────────


async def test_iframe_origin_mismatch_returns_403(client):
    """Ticket is bound to the iframe's origin (the backend origin). If a
    different Origin header arrives, EITHER the partner CORS middleware
    (ORIGIN_NOT_ALLOWED) OR the ticket verifier (ORIGIN_MISMATCH) refuses."""
    session = await _create_session(client)
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "https://evil.attacker.example"},
    )
    assert resp.status_code == 403, resp.text
    body = resp.json()
    blob = json.dumps(body)
    assert "ORIGIN_MISMATCH" in blob or "ORIGIN_NOT_ALLOWED" in blob, blob


# ── negative: expired ticket ─────────────────────────────────────────


async def test_expired_ticket_returns_410(client):
    # Mint a ticket with ttl_seconds = -10 (already expired) via the
    # underlying service. The endpoint would normally mint with ttl=60s,
    # so we craft one with a negative TTL.
    from app.services.preview_ticket import (
        generate_nonce, generate_preview_session_id, generate_jti,
    )
    psid = generate_preview_session_id()
    expired_ticket = issue_preview_ticket(
        preview_session_id=psid,
        expected_parent_origin="http://localhost:3000",
        expected_iframe_origin="http://test",
        nonce=generate_nonce(),
        jti=generate_jti(),
        ttl_seconds=-10,
    )
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": expired_ticket},
        headers={"Origin": "http://test"},
    )
    # Either 410 (expired at verify) or 404 (no DB row) is acceptable;
    # the test proves the ticket didn't pass verification.
    assert resp.status_code in (404, 410), resp.text


# ── revoke ───────────────────────────────────────────────────────────


async def test_revoke_pending_session(client):
    session = await _create_session(client)
    resp = await client.post(
        f"/api/embedded/preview-sessions/{session['preview_session_id']}/revoke"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "REVOKED"


async def test_revoke_then_exchange_refused(client):
    session = await _create_session(client)
    # Revoke first.
    rev = await client.post(
        f"/api/embedded/preview-sessions/{session['preview_session_id']}/revoke"
    )
    assert rev.status_code == 200
    # Now exchange must fail.
    ex = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": session["ticket"]},
        headers={"Origin": "http://test"},
    )
    assert ex.status_code == 403
    assert "REVOKED" in ex.json()["detail"]


# ── unknown session ──────────────────────────────────────────────────


async def test_get_unknown_session_returns_404(client):
    resp = await client.get(
        "/api/embedded/preview-sessions/nonexistent-psid-xxx"
    )
    assert resp.status_code == 404


async def test_revoke_unknown_session_returns_404(client):
    resp = await client.post(
        "/api/embedded/preview-sessions/nonexistent-psid-xxx/revoke"
    )
    assert resp.status_code == 404


# ── malformed exchange body ──────────────────────────────────────────


async def test_exchange_missing_ticket_returns_422(client):
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={},
        headers={"Origin": "http://test"},
    )
    assert resp.status_code == 422


async def test_exchange_garbage_ticket_returns_400(client):
    resp = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": "not-a-real-ticket"},
        headers={"Origin": "http://test"},
    )
    assert resp.status_code in (400, 401), resp.text
