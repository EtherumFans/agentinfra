"""B-007 — Runtime Token 2-segment decode_token fix.

Pre-B-007: ``decode_token`` in ``backend/app/middleware/auth.py`` only handled
3-segment JWTs. Phase 7 Gate 13A's Runtime Token (trace_token format,
``payload.signature`` 2 segments, type='rt') raised "Not enough segments" →
every Console preview iframe run returned 401.

B-007 fix: ``decode_token`` detects segment count and routes 2-segment tokens
through ``verify_runtime_token``, translating to a JWT-like payload so the
rest of the auth pipeline works unchanged. ``get_current_user_or_oauth_client``
gets a third branch (``token_type=="runtime_token"``) that skips the long-lived
JWT token_version gate (Runtime Token is HMAC-signed + 10min TTL).

Tests:
  1. 3-segment JWT still decodes (no regression).
  2. 2-segment Runtime Token decodes successfully.
  3. Malformed 2-segment token (bad signature) raises 401.
  4. ``get_current_user_or_oauth_client`` with runtime_token returns the
     right user + sentinel client_id.
  5. runtime_token path skips token_version revocation gate.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 3-segment JWT regression
# ─────────────────────────────────────────────────────────────────────


def test_decode_token_jwt_3_segments_still_works() -> None:
    """A regular 3-segment JWT decodes via PyJWT as before."""
    from app.middleware.auth import create_access_token
    from app.middleware.auth import decode_token

    token = create_access_token(
        user_id="user-123",
        username="alice",
        role="admin",
        org_id="org_default1",
    )
    assert token.count(".") == 2, "fixture: JWT must have 3 segments (header.payload.sig)"

    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload.get("org_id") == "org_default1" or payload.get("org") == "org_default1"


# ─────────────────────────────────────────────────────────────────────
# §2 2-segment Runtime Token decodes
# ─────────────────────────────────────────────────────────────────────


def test_decode_token_runtime_token_2_segments_decodes() -> None:
    """A 2-segment Runtime Token decodes via verify_runtime_token path."""
    from app.services.preview_ticket import issue_runtime_token
    from app.middleware.auth import decode_token

    rt = issue_runtime_token(
        preview_session_id="psid_test_b_007",
        organization_id="org_default1",
        user_id="user-test-b-007",
        allowed_scopes=["agents:run", "runs:read"],
    )
    assert rt.count(".") == 1, "fixture: Runtime Token must have 2 segments (payload.sig)"

    payload = decode_token(rt)
    assert payload["type"] == "runtime_token"
    assert payload["sub"] == "user-test-b-007"
    assert payload["org_id"] == "org_default1"
    assert payload["preview_session_id"] == "psid_test_b_007"
    assert "agents:run" in payload["scopes"]
    assert isinstance(payload["exp"], int)


# ─────────────────────────────────────────────────────────────────────
# §3 Malformed 2-segment token raises 401
# ─────────────────────────────────────────────────────────────────────


def test_decode_token_malformed_2_segments_raises_401() -> None:
    """A 2-segment token with a bad signature is rejected with 401."""
    from app.services.preview_ticket import issue_runtime_token, _b64url_encode
    from app.services.preview_ticket import _sign as _pt_sign
    from app.middleware.auth import decode_token
    from fastapi import HTTPException

    rt = issue_runtime_token(
        preview_session_id="psid_bad_sig",
        organization_id="org_default1",
        user_id="user-bad",
    )
    payload_b64, _ = rt.rsplit(".", 1)
    bad_sig = _pt_sign(_b64url_encode(b"tampered"))  # signature over wrong data
    tampered = f"{payload_b64}.{bad_sig}"

    with pytest.raises(HTTPException) as exc:
        decode_token(tampered)
    assert exc.value.status_code == 401
    assert "runtime token" in exc.value.detail.lower()


# ─────────────────────────────────────────────────────────────────────
# §4 get_current_user_or_oauth_client returns user via runtime_token
# ─────────────────────────────────────────────────────────────────────


async def _seed_testuser(client) -> tuple[str, str]:
    """Register testuser via HTTP so a real row exists in the test DB.

    The default `client` fixture + autouse auth bypass means /api/auth/login
    is short-circuited (returns mock_user without touching DB). To get a
    real row, we POST /api/auth/register which writes to DB regardless of
    the auth bypass. Returns the user's id.
    """
    resp = await client.post("/api/auth/register", json={
        "username": "testuser-b007",
        "email": "testuser-b007@example.com",
        "password": "Testpass123!",
        "full_name": "B-007 Test User",
        "role": "coder",
        "department": "测试科",
    })
    # 200/201 = newly registered; 400/409 = already exists — both fine.
    assert resp.status_code in (200, 201, 400, 409), resp.text
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.organization import OrganizationMember
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "testuser-b007").limit(1))
        user = result.scalar_one()
        organization_id = (
            await db.execute(
                select(OrganizationMember.organization_id).where(
                    OrganizationMember.user_id == user.id
                ).limit(1)
            )
        ).scalar_one()
    return user.id, organization_id


@pytest.mark.asyncio
async def test_get_current_user_or_oauth_client_runtime_token_returns_user(client) -> None:
    """Runtime Token path returns the issuing Console user + sentinel client_id."""
    from app.services.preview_ticket import issue_runtime_token
    from app.middleware.auth import get_current_user_or_oauth_client
    from fastapi.security import HTTPAuthorizationCredentials
    from app.database import AsyncSessionLocal

    user_id, organization_id = await _seed_testuser(client)

    rt = issue_runtime_token(
        preview_session_id="psid_user_lookup",
        organization_id=organization_id,
        user_id=user_id,
        allowed_scopes=["agents:run", "runs:read"],
    )

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=rt)
    async with AsyncSessionLocal() as db:
        resolved_user, principal = await get_current_user_or_oauth_client(creds, db)

    assert resolved_user is not None
    assert resolved_user.id == user_id
    assert principal["type"] == "runtime_token"
    assert principal["preview_session_id"] == "psid_user_lookup"
    assert principal["client_id"] == "console-preview:psid_user_lookup"
    assert "agents:run" in principal["scopes"]


# ─────────────────────────────────────────────────────────────────────
# §5 runtime_token skips token_version revocation gate
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_token_skips_token_version_gate(client) -> None:
    """Runtime Token must NOT be rejected when user.token_version is bumped.

    Long-lived JWTs carry a ``token_version`` claim that's checked against
    ``user.token_version`` to support revocation (e.g., after password
    change). Runtime Tokens are short-lived (10min) + HMAC-signed, so the
    same gate would falsely revoke still-valid preview tokens whenever the
    Console user changes password. The B-007 fix deliberately omits this
    check on the runtime_token branch.
    """
    from app.services.preview_ticket import issue_runtime_token
    from app.middleware.auth import get_current_user_or_oauth_client
    from fastapi.security import HTTPAuthorizationCredentials
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    user_id, organization_id = await _seed_testuser(client)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id).limit(1))
        user = result.scalar_one()
        original_tv = user.token_version or 0
        # Simulate a password change / revocation event.
        user.token_version = original_tv + 999
        await db.commit()

    try:
        rt = issue_runtime_token(
            preview_session_id="psid_post_revoke",
            organization_id=organization_id,
            user_id=user_id,
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=rt)
        async with AsyncSessionLocal() as db:
            resolved_user, principal = await get_current_user_or_oauth_client(creds, db)
        # Token still works despite the bumped user.token_version.
        assert resolved_user is not None
        assert resolved_user.id == user_id
        assert principal["type"] == "runtime_token"
    finally:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == user_id).limit(1))
            user = result.scalar_one_or_none()
            if user is not None:
                user.token_version = original_tv
                await db.commit()
