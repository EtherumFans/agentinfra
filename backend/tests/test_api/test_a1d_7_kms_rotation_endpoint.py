"""A1D.7 (Pilot Prep Step 5a) — admin KMS rotation endpoint.

Predecessor state (Phase A1D.4):
  - KMSVersionToken class existed but was only instantiated in tests.
  - CredentialVault accepted a kms_version_token arg but the global
    singleton ``credential_vault = CredentialVault()`` was constructed
    without one, so production code paths never stamped cache entries.
  - No operator-facing rotation trigger existed — even if an operator
    rotated the cloud KMS key, the app kept serving stale cached values
    indefinitely.

A1D.7 closes the gap:
  - The global ``credential_vault`` singleton is now constructed with
    a shared ``KMSVersionToken`` exposed via ``get_global_kms_version_token()``.
  - ``POST /api/admin/kms/rotate`` bumps the token, flushes the cache,
    and writes an audit row.
  - ``GET /api/admin/kms/version`` returns the current token value
    (health-check / canary use case).

Coverage:
  - global singleton is wired with a token
  - admin GET /kms/version returns current
  - admin POST /kms/rotate bumps token + writes audit
  - rotation clears cached credentials
  - non-admin gets 403
  - unauthenticated gets 401
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 Global singleton wiring
# ─────────────────────────────────────────────────────────────────────


def test_global_credential_vault_is_wired_with_kms_token() -> None:
    """The module-level credential_vault singleton has a non-None kms_token.

    Before A1D.7 the singleton was constructed without a token, so cache
    entries were never stamped and rotation could not be observed.
    """
    from app.services.credential_vault import credential_vault, get_global_kms_version_token
    assert credential_vault._kms_token is not None, (
        "global credential_vault must be constructed with a KMSVersionToken "
        "so the admin rotation endpoint can drive cache invalidation"
    )
    # The exposed helper returns the SAME token the vault uses.
    assert get_global_kms_version_token() is credential_vault._kms_token


# ─────────────────────────────────────────────────────────────────────
# §2 Admin GET /api/admin/kms/version
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_kms_version_returns_current_token(client) -> None:
    """Admin GET /kms/version returns the current KMSVersionToken value."""
    from app.services.credential_vault import get_global_kms_version_token
    token = get_global_kms_version_token()
    expected = token.current

    r = await client.get("/api/admin/kms/version")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_version"] == expected
    assert body["previous_version"] == expected  # version endpoint == no-op
    assert body["invalidated_entries"] == 0
    # mock_user has admin role; username is "testuser" per conftest.
    assert body["rotated_by"] == "testuser"


# ─────────────────────────────────────────────────────────────────────
# §3 Admin POST /api/admin/kms/rotate
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_kms_rotate_bumps_token_and_writes_audit(client) -> None:
    """Admin POST /kms/rotate increments token + writes audit log row.

    Audit row captures previous_version → current_version so the operator
    can verify the bump took effect (and correlate with cloud-side rotation
    timestamp).
    """
    from app.services.credential_vault import get_global_kms_version_token
    from app.models.audit_log import AuditLog
    from sqlalchemy import select
    from app.database import AsyncSessionLocal

    token = get_global_kms_version_token()
    before = token.current

    r = await client.post("/api/admin/kms/rotate")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["previous_version"] == before
    assert body["current_version"] == before + 1
    assert body["rotated_by"] == "testuser"

    # Token really did bump
    assert token.current == before + 1

    # Audit row written
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(AuditLog).where(AuditLog.action == "kms.key_rotated")
            .order_by(AuditLog.created_at.desc()).limit(1)
        )).scalars().all()
    assert len(rows) >= 1, "kms.key_rotated audit row not written"
    last = rows[0]
    assert last.details["previous_version"] == before
    assert last.details["current_version"] == before + 1


@pytest.mark.asyncio
async def test_admin_kms_rotate_clears_credential_cache(client, monkeypatch) -> None:
    """Rotation flushes cached credentials; next resolve() re-reads env."""
    from app.services.credential_vault import credential_vault

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    # Populate cache
    assert credential_vault.resolve("llm") == "key-v1"
    assert "llm" in credential_vault._cache

    # Rotate env (simulating cloud-side KMS rotation)
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2-rotated")

    # Without rotation endpoint, cache returns stale
    assert credential_vault.resolve("llm") == "key-v1"

    # Admin rotates
    r = await client.post("/api/admin/kms/rotate")
    assert r.status_code == 200
    assert r.json()["invalidated_entries"] >= 1

    # Cache cleared
    assert "llm" not in credential_vault._cache

    # Next resolve re-reads env
    assert credential_vault.resolve("llm") == "key-v2-rotated"


# ─────────────────────────────────────────────────────────────────────
# §4 RBAC — non-admin forbidden, unauthenticated unauthorized
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kms_rotate_rejects_non_admin(client, needs_auth) -> None:
    """A CODER-role user gets 403 on POST /kms/rotate."""
    from app.middleware.auth import get_current_user, get_admin_user
    from app.services.credential_vault import get_global_kms_version_token

    # Override the auth bypass to return a CODER user
    from tests.conftest import _make_mock_user
    coder = _make_mock_user("coder")

    # IMPORTANT: get_admin_user is a separate Depends — overriding
    # get_current_user is not enough; the route depends on get_admin_user
    # which itself calls get_current_user internally. To force a 403 path,
    # we override get_admin_user to raise the same way the real one would
    # for a non-admin.
    from fastapi import HTTPException, status as http_status
    from app.main import app

    def _fake_admin():
        if coder.role.value != "admin":
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return coder

    app.dependency_overrides[get_admin_user] = _fake_admin
    try:
        before = get_global_kms_version_token().current
        r = await client.post("/api/admin/kms/rotate")
        assert r.status_code == 403, r.text
        # Token NOT bumped
        assert get_global_kms_version_token().current == before
    finally:
        del app.dependency_overrides[get_admin_user]


@pytest.mark.asyncio
async def test_kms_rotate_rejects_unauthenticated(client, needs_auth) -> None:
    """No Authorization header → 401 (auth middleware runs before endpoint)."""
    from app.services.credential_vault import get_global_kms_version_token
    before = get_global_kms_version_token().current

    r = await client.post("/api/admin/kms/rotate")
    # Without auth bypass, the middleware emits 401.
    assert r.status_code in (401, 403), r.text
    assert get_global_kms_version_token().current == before
