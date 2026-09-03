# Auth API Integration Tests
"""Phase 3-D0 Task 3 — fixed test_register isolation flake.

Root cause: tests used fixed emails/usernames ("new@example.com" /
"newuser") and the session-scoped DB only drops tables at the very
end. A re-run of test_register hits 400 (user already exists) instead
of 201 → flake. Fix: per-invocation unique suffix via uuid4.
"""
import uuid

import pytest


def _short_uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest.mark.asyncio
async def test_health_check(client):
    from app.config import settings

    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == settings.APP_NAME


@pytest.mark.asyncio
async def test_register(client):
    uid = _short_uid()
    response = await client.post("/api/auth/register", json={
        "username": f"newuser-{uid}",
        "email": f"new-{uid}@example.com",
        "password": "password123",
        "full_name": "New User",
        "role": "coder",
        "department": "内科",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == f"newuser-{uid}"


@pytest.mark.asyncio
async def test_public_registration_cannot_self_assign_admin_and_is_audited(client):
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.user import User

    uid = _short_uid()
    username = f"escalation-{uid}"
    response = await client.post("/api/auth/register", json={
        "username": username,
        "email": f"escalation-{uid}@example.com",
        "password": "password123",
        "full_name": "Privilege Probe",
        "role": "admin",
    })
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SELF_ASSIGNED_ROLE_FORBIDDEN"

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        audit = (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "auth.register.denied.role_escalation")
                .order_by(AuditLog.created_at.desc())
            )
        ).scalars().first()
    assert user is None
    assert audit is not None
    assert audit.tenancy_classification == "MODERN_SYSTEM"
    assert audit.details == {"requested_role": "admin"}


@pytest.mark.asyncio
async def test_register_duplicate(client):
    uid = _short_uid()
    username = f"dupuser-{uid}"
    # First registration
    await client.post("/api/auth/register", json={
        "username": username,
        "email": f"dup-{uid}@example.com",
        "password": "password123",
        "full_name": "Dup User",
    })
    # Duplicate (same username — must 400)
    response = await client.post("/api/auth/register", json={
        "username": username,
        "email": f"dup2-{uid}@example.com",
        "password": "password123",
        "full_name": "Dup User 2",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_register_same_default_organization_name_gets_safe_suffix(client):
    """Two people with the same full name must not trigger an org-name 500."""
    suffix = uuid.uuid4().hex[:8]
    first = await client.post("/api/auth/register", json={
        "username": f"same-name-a-{suffix}",
        "email": f"same-name-a-{suffix}@example.com",
        "password": "password123",
        "full_name": f"Same Name {suffix}",
    })
    second = await client.post("/api/auth/register", json={
        "username": f"same-name-b-{suffix}",
        "email": f"same-name-b-{suffix}@example.com",
        "password": "password123",
        "full_name": f"Same Name {suffix}",
    })

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    first_org = first.json()["organizations"][0]
    second_org = second.json()["organizations"][0]
    assert first_org["id"] != second_org["id"]
    assert first_org["name"] != second_org["name"]
    assert second_org["name"].endswith("-1")


@pytest.mark.asyncio
async def test_login_success(client):
    uid = _short_uid()
    username = f"loginuser-{uid}"
    # Register first
    await client.post("/api/auth/register", json={
        "username": username,
        "email": f"login-{uid}@example.com",
        "password": "loginpass123",
        "full_name": "Login User",
    })
    response = await client.post("/api/auth/login", json={
        "username": username,
        "password": "loginpass123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_failure(client):
    uid = _short_uid()
    response = await client.post("/api/auth/login", json={
        "username": f"nonexistent-{uid}",
        "password": "wrong",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(client, needs_auth):
    response = await client.get("/api/encounters")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(auth_client):
    response = await auth_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"


@pytest.mark.asyncio
async def test_password_reset_raw_credential_is_never_logged(
    client,
    monkeypatch,
    caplog,
):
    uid = _short_uid()
    email = f"reset-{uid}@example.com"
    await client.post("/api/auth/register", json={
        "username": f"reset-{uid}",
        "email": email,
        "password": "password123",
        "full_name": "Reset User",
    })
    raw_credential = "reset-credential-must-not-appear"
    monkeypatch.setattr("app.api.auth.secrets.token_urlsafe", lambda _size: raw_credential)

    with caplog.at_level("INFO", logger="app.api.auth"):
        response = await client.post("/api/auth/forgot-password", json={"email": email})

    assert response.status_code == 202
    assert raw_credential not in caplog.text
