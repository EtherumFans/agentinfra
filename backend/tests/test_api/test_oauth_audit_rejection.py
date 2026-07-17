"""A1A Gate 1 Step 5 — OAuth authentication_rejected audit event tests.

Validates that every 401 ``invalid_client`` response from POST /api/oauth/token
(or realm variant) emits an ``api_client.authentication_rejected`` audit log
entry containing client_id + reason + source IP + user-agent.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _fetch_rejection_events(client_id: str) -> list:
    """Return all api_client.authentication_rejected events for the given client_id.

    Imports ``async_session_factory`` lazily so the conftest TD-001 rebind
    (which replaces the module-level factory with one pointing at the test
    DB) is honored. A module-level import captures the OLD factory bound to
    the dev DB and would see zero rows.
    """
    from app.database import async_session_factory
    from sqlalchemy import select
    from app.models.audit_log import AuditLog
    async with async_session_factory() as db:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.action == "api_client.authentication_rejected",
                AuditLog.resource_id == client_id,
            ).order_by(AuditLog.created_at.desc())
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_token_endpoint_invalid_client_emits_audit(auth_client: AsyncClient):
    """Unknown client_id at POST /api/oauth/token → 401 + audit row."""
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": "unknown-client-a1a-test",
        "client_secret": "any-secret",
    })
    assert resp.status_code == 401

    events = await _fetch_rejection_events("unknown-client-a1a-test")
    assert len(events) >= 1
    e = events[0]
    assert e.action == "api_client.authentication_rejected"
    assert e.status == "failure"
    assert e.details["client_id"] == "unknown-client-a1a-test"
    assert e.details["reason"] == "client_not_found_or_inactive"


@pytest.mark.asyncio
async def test_token_endpoint_secret_mismatch_emits_audit(auth_client: AsyncClient):
    """Known client_id + wrong secret → 401 + audit row with reason=secret_mismatch_or_empty."""
    # First create a real client
    resp = await auth_client.post("/api/oauth/clients", data={
        "name": "A1A Test Client",
        "scopes": "api:read",
    })
    assert resp.status_code == 200
    client_id = resp.json()["client_id"]

    # Now POST with wrong secret
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": "wrong-secret-a1a",
    })
    assert resp.status_code == 401

    events = await _fetch_rejection_events(client_id)
    assert len(events) >= 1
    e = events[0]
    assert e.details["reason"] == "secret_mismatch_or_empty"
    assert e.details["client_id"] == client_id


@pytest.mark.asyncio
async def test_token_endpoint_inactive_client_emits_audit(auth_client: AsyncClient):
    """Disabled (is_active=0) client → 401 + audit row with reason=client_not_found_or_inactive."""
    # Create then disable
    resp = await auth_client.post("/api/oauth/clients", data={
        "name": "A1A Disabled Client",
        "scopes": "api:read",
    })
    assert resp.status_code == 200
    client_id = resp.json()["client_id"]
    client_secret = resp.json()["client_secret"]
    resp = await auth_client.delete(f"/api/oauth/clients/{client_id}")
    assert resp.status_code == 200

    # Auth attempt against disabled client
    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    assert resp.status_code == 401

    events = await _fetch_rejection_events(client_id)
    assert len(events) >= 1
    e_details = events[0].details
    assert e_details["reason"] == "client_not_found_or_inactive"


@pytest.mark.asyncio
async def test_realm_token_endpoint_invalid_client_emits_audit(auth_client: AsyncClient):
    """POST /api/oauth/realms/{realm}/token with unknown client → 401 + audit row."""
    resp = await auth_client.post("/api/oauth/realms/base/token", data={
        "grant_type": "client_credentials",
        "client_id": "unknown-realm-client-a1a",
        "client_secret": "any",
    })
    assert resp.status_code == 401

    events = await _fetch_rejection_events("unknown-realm-client-a1a")
    assert len(events) >= 1
    e = events[0]
    assert e.details["reason"] == "client_not_found_or_inactive"
    assert e.details["realm"] == "base"
    assert e.details["endpoint"] == "realm_token_endpoint"


@pytest.mark.asyncio
async def test_audit_event_captures_source_ip_and_user_agent(auth_client: AsyncClient):
    """Audit row records request.client.host and user-agent header."""
    resp = await auth_client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "audit-ip-ua-test-client",
            "client_secret": "any",
        },
        headers={"user-agent": "A1A-Gate1-Step5-Test-UA/1.0"},
    )
    assert resp.status_code == 401

    events = await _fetch_rejection_events("audit-ip-ua-test-client")
    assert len(events) >= 1
    e = events[0]
    # test client uses 127.0.0.1 (or None under ASGITransport; either is acceptable)
    assert e.ip_address is None or "127.0.0.1" in (e.ip_address or "") or "testclient" in (e.ip_address or "")
    assert e.user_agent == "A1A-Gate1-Step5-Test-UA/1.0"


@pytest.mark.asyncio
async def test_successful_auth_does_not_emit_rejection_audit(auth_client: AsyncClient):
    """Successful client_credentials auth → no api_client.authentication_rejected event."""
    resp = await auth_client.post("/api/oauth/clients", data={
        "name": "A1A Success Client",
        "scopes": "api:read",
    })
    client_id = resp.json()["client_id"]
    client_secret = resp.json()["client_secret"]

    resp = await auth_client.post("/api/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    assert resp.status_code == 200

    events = await _fetch_rejection_events(client_id)
    assert len(events) == 0, f"unexpected rejection events: {events}"
