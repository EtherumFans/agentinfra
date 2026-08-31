"""Real-JWT platform administration and credential revocation coverage."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client, label: str) -> dict:
    suffix = _uid()
    response = await client.post(
        "/api/auth/register",
        json={
            "username": f"{label}-{suffix}",
            "email": f"{label}-{suffix}@example.com",
            "password": "SecurePass123!",
            "full_name": f"{label} {suffix}",
            "role": "coder",
            "organization_name": f"{label} Org {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _promote_bootstrap_admin(client, account: dict) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.user import User, UserRole

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == account["user"]["id"]))
        ).scalar_one()
        user.role = UserRole.ADMIN
        await db.commit()
    login = await client.post(
        "/api/auth/login",
        json={"username": account["user"]["username"], "password": "SecurePass123!"},
    )
    assert login.status_code == 200, login.text
    return login.json()


async def _seed_client_and_token(owner: dict, org_id: str) -> tuple[str, str]:
    from app.database import AsyncSessionLocal
    from app.models.oauth import OAuthClient, OAuthToken

    client_id = f"platform-access-{_uid()}"
    raw_token = f"oauth-test-{_uid()}"
    async with AsyncSessionLocal() as db:
        db.add(OAuthClient(
            organization_id=org_id,
            name="Platform access revocation fixture",
            client_id=client_id,
            client_secret_hash=hashlib.sha256(b"fixture-secret").hexdigest(),
            scopes="api:read api:write",
            is_active=True,
            owner_id=owner["user"]["id"],
        ))
        db.add(OAuthToken(
            organization_id=org_id,
            client_id=client_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            scopes="api:read",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_revoked=False,
        ))
        await db.commit()
    return client_id, raw_token


@pytest.mark.asyncio
async def test_platform_role_update_is_admin_only_versioned_audited_and_revokes_tokens(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.oauth import OAuthClient, OAuthToken

    bootstrap = await _register(client, "platform-admin")
    admin = await _promote_bootstrap_admin(client, bootstrap)
    target = await _register(client, "platform-target")
    admin_headers = _headers(admin["access_token"])

    denied = await client.get("/api/admin/users", headers=_headers(target["access_token"]))
    assert denied.status_code == 403

    listed = await client.get("/api/admin/users", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    row = next(item for item in listed.json()["users"] if item["id"] == target["user"]["id"])
    assert row["token_version"] == 0

    self_change = await client.patch(
        f"/api/admin/users/{admin['user']['id']}",
        headers=admin_headers,
        json={
            "role": "coder",
            "expected_token_version": admin["user"].get("token_version", 0),
            "reason_code": "role_revocation",
            "ticket_id": "SEC-SELF-1",
        },
    )
    assert self_change.status_code == 403

    promoted = await client.patch(
        f"/api/admin/users/{target['user']['id']}",
        headers=admin_headers,
        json={
            "role": "clinician",
            "expected_token_version": 0,
            "reason_code": "role_assignment",
            "ticket_id": "IAM-1001",
        },
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["user"]["role"] == "clinician"
    assert promoted.json()["user"]["token_version"] == 1
    assert promoted.json()["changed"] is True
    assert (await client.get("/api/auth/me", headers=_headers(target["access_token"]))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": target["refresh_token"]})).status_code == 401

    stale = await client.patch(
        f"/api/admin/users/{target['user']['id']}",
        headers=admin_headers,
        json={
            "role": "qc",
            "expected_token_version": 0,
            "reason_code": "role_assignment",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "STALE_USER_ACCESS_VERSION"

    make_admin = await client.patch(
        f"/api/admin/users/{target['user']['id']}",
        headers=admin_headers,
        json={
            "role": "admin",
            "expected_token_version": 1,
            "reason_code": "role_assignment",
            "ticket_id": "IAM-1002",
        },
    )
    assert make_admin.status_code == 200
    assert make_admin.json()["user"]["token_version"] == 2

    target_admin_login = await client.post(
        "/api/auth/login",
        json={"username": target["user"]["username"], "password": "SecurePass123!"},
    )
    assert target_admin_login.status_code == 200
    assert (await client.get("/api/admin/users", headers=_headers(target_admin_login.json()["access_token"]))).status_code == 200

    client_id, _ = await _seed_client_and_token(target, target["current_org_id"])
    deactivated = await client.patch(
        f"/api/admin/users/{target['user']['id']}",
        headers=admin_headers,
        json={
            "is_active": False,
            "expected_token_version": 2,
            "reason_code": "account_suspension",
            "ticket_id": "SEC-2001",
        },
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["user"]["is_active"] is False
    assert deactivated.json()["clients_disabled"] == 1
    assert (await client.get("/api/admin/users", headers=_headers(target_admin_login.json()["access_token"]))).status_code in {401, 403}

    async with AsyncSessionLocal() as db:
        oauth_client = (
            await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
        ).scalar_one()
        oauth_token = (
            await db.execute(select(OAuthToken).where(OAuthToken.client_id == client_id))
        ).scalar_one()
        audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action.in_([
                        "platform_admin.user_access_updated",
                        "platform_admin.user_access_update_denied",
                    ])
                )
            )
        ).scalars().all()
    assert oauth_client.is_active is False
    assert oauth_token.is_revoked is True
    assert len(audits) >= 5
    assert all(audit.organization_id is None for audit in audits)
    assert all(audit.tenancy_classification == "MODERN_SYSTEM" for audit in audits)
    assert any(audit.details.get("ticket_id") == "IAM-1001" for audit in audits)


@pytest.mark.asyncio
async def test_platform_organization_suspension_revokes_member_and_client_credentials(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.oauth import OAuthClient, OAuthToken

    bootstrap = await _register(client, "org-control-admin")
    admin = await _promote_bootstrap_admin(client, bootstrap)
    tenant_user = await _register(client, "org-control-user")
    client_id, _ = await _seed_client_and_token(tenant_user, tenant_user["current_org_id"])

    invalid_plan = await client.patch(
        f"/api/admin/organizations/{tenant_user['current_org_id']}",
        headers=_headers(admin["access_token"]),
        json={"plan": "unlimited", "reason_code": "plan_change"},
    )
    assert invalid_plan.status_code == 422

    suspended = await client.patch(
        f"/api/admin/organizations/{tenant_user['current_org_id']}",
        headers=_headers(admin["access_token"]),
        json={
            "is_active": False,
            "reason_code": "organization_suspension",
            "ticket_id": "SEC-ORG-1",
        },
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["is_active"] is False
    assert suspended.json()["user_tokens_revoked"] == 1
    assert suspended.json()["clients_disabled"] == 1
    assert suspended.json()["oauth_tokens_revoked"] == 1
    assert (await client.get("/api/auth/me", headers=_headers(tenant_user["access_token"]))).status_code == 401

    async with AsyncSessionLocal() as db:
        oauth_client = (
            await db.execute(select(OAuthClient).where(OAuthClient.client_id == client_id))
        ).scalar_one()
        oauth_token = (
            await db.execute(select(OAuthToken).where(OAuthToken.client_id == client_id))
        ).scalar_one()
        audit = (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.action == "platform_admin.organization_updated")
                .order_by(AuditLog.created_at.desc())
            )
        ).scalars().first()
    assert oauth_client.is_active is False
    assert oauth_token.is_revoked is True
    assert audit is not None
    assert audit.organization_id == tenant_user["current_org_id"]
    assert audit.tenancy_classification == "MODERN_SYSTEM"
    assert audit.details["reason_code"] == "organization_suspension"


@pytest.mark.asyncio
async def test_password_change_revokes_current_sessions_and_owned_oauth_tokens(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.oauth import OAuthToken

    user = await _register(client, "password-change")
    client_id, _ = await _seed_client_and_token(user, user["current_org_id"])
    changed = await client.post(
        "/api/auth/change-password",
        headers=_headers(user["access_token"]),
        json={"current_password": "SecurePass123!", "new_password": "NewSecurePass456!"},
    )
    assert changed.status_code == 200, changed.text
    assert (await client.get("/api/auth/me", headers=_headers(user["access_token"]))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": user["refresh_token"]})).status_code == 401
    async with AsyncSessionLocal() as db:
        revoked = (
            await db.execute(select(OAuthToken.is_revoked).where(OAuthToken.client_id == client_id))
        ).scalar_one()
    assert revoked is True


@pytest.mark.asyncio
async def test_first_admin_bootstrap_is_dry_run_by_default_one_time_and_audited():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models.audit_log import AuditLog
    from app.models.user import User, UserRole
    from scripts.bootstrap_platform_admin import bootstrap_platform_admin

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            user = User(
                username=f"bootstrap-{_uid()}",
                email=f"bootstrap-{_uid()}@example.com",
                hashed_password="unused-test-hash",
                full_name="Bootstrap Operator",
                role=UserRole.CODER,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            preview = await bootstrap_platform_admin(
                db,
                identifier=user.email,
                ticket_id="IAM-BOOT-1",
                execute=False,
            )
            assert preview["mode"] == "dry_run"
            assert user.role == UserRole.CODER
            assert user.token_version == 0

            applied = await bootstrap_platform_admin(
                db,
                identifier=user.email,
                ticket_id="IAM-BOOT-1",
                execute=True,
            )
            assert applied["mode"] == "execute"
            await db.refresh(user)
            assert user.role == UserRole.ADMIN
            assert user.token_version == 1
            audit = (
                await db.execute(
                    select(AuditLog).where(AuditLog.action == "platform_admin.user_access_updated")
                )
            ).scalar_one()
            assert audit.tenancy_classification == "MODERN_SYSTEM"
            assert audit.details["reason_code"] == "initial_bootstrap"

            with pytest.raises(RuntimeError, match="already exists"):
                await bootstrap_platform_admin(
                    db,
                    identifier=user.email,
                    ticket_id="IAM-BOOT-2",
                    execute=True,
                )
    finally:
        await engine.dispose()
