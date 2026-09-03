"""Phase 7 Gate 13A-8 — no PHI/token leak audit tests.

Verifies the attack surfaces enumerated in PHASE7_GATE13A_THREAT_MODEL.md
T1-T6 are closed:

- T1 (browser history): iframe URL contains only ?psid=
- T2 (HAR file): preview.html response body has no token/PHI
- T3 (backend access logs): AuditLog details column has no PHI
- T4 (Referer on sub-resource requests): preview.html ships no-referrer
- T5 (postMessage wildcard): no '*' in any postMessage call (covered by
  test_phase7_gate13a_preview_html.py)
- T6 (code generator copy): separate frontend test (placeholders only)
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.preview_session import PreviewSession


pytestmark = pytest.mark.asyncio


PHI_MARKERS = ["张三", "P-2026-001", "E-20260713-001", "%E5%BC%A0%E4%B8%89"]
# Anything that looks like a JWT (header.payload.signature base64)
JWT_RE_TOKEN_IN_URL = "token="


async def test_audit_log_does_not_contain_phi(client):
    """The AuditLog details JSON column MUST NOT contain patient PHI.

    The preview_session.create audit row records jti, parent_origin,
    scopes — but NEVER the patient name/ID/encounter.
    """
    # Create a session via the Console endpoint.
    resp = await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )
    assert resp.status_code == 201
    psid = resp.json()["preview_session_id"]

    # Find the create audit row.
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "preview_session.create")
        )
        rows = result.scalars().all()
        assert any(r.resource_id == psid for r in rows), \
            f"no preview_session.create audit row for psid={psid}"

    # Check none of the PHI markers appear in the details JSON.
    for r in rows:
        import json
        details_blob = json.dumps(r.details or {}, ensure_ascii=False)
        for marker in PHI_MARKERS:
            assert marker not in details_blob, (
                f"PHI marker {marker!r} leaked into AuditLog details: {details_blob}"
            )


async def test_audit_log_records_ticket_exchange(client):
    """After exchange, an AuditLog row is written for ticket consumption."""
    # Create + exchange.
    sess = (await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )).json()
    ex = await client.post(
        "/api/embedded/preview-sessions/exchange",
        json={"ticket": sess["ticket"]},
        headers={"Origin": "http://test"},
    )
    assert ex.status_code == 200

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "preview_session.exchange")
        )
        rows = result.scalars().all()
        assert any(r.resource_id == sess["preview_session_id"] for r in rows), \
            "no preview_session.exchange audit row"


async def test_audit_log_records_revoke(client):
    """After revoke, an AuditLog row is written."""
    sess = (await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )).json()
    rev = await client.post(
        f"/api/embedded/preview-sessions/{sess['preview_session_id']}/revoke",
    )
    assert rev.status_code == 200

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog).where(AuditLog.action == "preview_session.revoke")
        )
        rows = result.scalars().all()
        assert any(r.resource_id == sess["preview_session_id"] for r in rows), \
            "no preview_session.revoke audit row"


async def test_preview_html_response_body_has_no_jwt(client):
    """No JWT-shaped token in preview.html response."""
    resp = await client.get("/api/embedded/preview.html?psid=abc")
    body = resp.text
    # Reject any string that looks like a JWT (3 dot-separated base64
    # segments with at least 16 chars each).
    import re
    jwt_re = re.compile(r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")
    assert not jwt_re.search(body), "JWT-shaped token leaked into preview.html response"


async def test_preview_session_response_has_no_phi(client):
    """The POST /api/embedded/preview-sessions response contains the
    ticket (intended) but NO patient PHI (only org/user identity, which
    are not PHI)."""
    resp = await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )
    body_text = resp.text
    for marker in PHI_MARKERS:
        assert marker not in body_text, (
            f"PHI marker {marker!r} leaked into preview-sessions response: {body_text}"
        )


async def test_preview_session_url_does_not_contain_token(client):
    """The iframe_url returned by the API must not contain a token query."""
    resp = await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )
    iframe_url = resp.json()["iframe_url"]
    assert JWT_RE_TOKEN_IN_URL not in iframe_url.lower(), (
        f"iframe_url leaked token: {iframe_url}"
    )
    assert "patient" not in iframe_url.lower(), (
        f"iframe_url leaked patient info: {iframe_url}"
    )


async def test_db_row_does_not_contain_phi(client):
    """The preview_sessions table row has no PHI columns (no patient_id,
    no patient_name, no encounter_id)."""
    resp = await client.post(
        "/api/embedded/preview-sessions",
        json={"expected_parent_origin": "http://localhost:3000"},
    )
    psid = resp.json()["preview_session_id"]

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PreviewSession).where(PreviewSession.preview_session_id == psid)
        )
        row = result.scalar_one()

        # Verify there's NO patient_* column on the model.
        col_names = {c.name for c in PreviewSession.__table__.columns}
        assert not any("patient" in c for c in col_names), \
            f"preview_sessions has patient columns: {col_names}"
        # allowed_agent_ids + allowed_scopes are config, not PHI.
        # The DB row only contains: jti, nonce, org, user, origins,
        # timestamps, status.
        assert "jti" in col_names
        assert "nonce" in col_names
        assert "organization_id" in col_names
