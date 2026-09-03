"""Real-JWT regression coverage for organization RBAC and invitations."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


def _uid() -> str:
    return uuid.uuid4().hex[:10]


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


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_org_path_is_bound_to_jwt_context_and_refresh_is_not_access_token(client, needs_auth):
    owner_a = await _register(client, "tenant-a")
    owner_b = await _register(client, "tenant-b")
    org_b = owner_b["current_org_id"]
    headers_a = _headers(owner_a["access_token"])

    for path in (
        f"/api/organizations/{org_b}",
        f"/api/organizations/{org_b}/members",
        f"/api/organizations/{org_b}/invites",
    ):
        response = await client.get(path, headers=headers_a)
        assert response.status_code == 404, (path, response.text)

    refresh_as_access = await client.get(
        "/api/organizations/current",
        headers=_headers(owner_a["refresh_token"]),
    )
    assert refresh_as_access.status_code == 401


@pytest.mark.asyncio
async def test_invite_is_hashed_one_time_tenant_scoped_and_role_changes_revoke_tokens(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.organization import OrganizationInvite

    owner = await _register(client, "owner")
    invitee = await _register(client, "invitee")
    outsider = await _register(client, "outsider")
    org_id = owner["current_org_id"]
    owner_headers = _headers(owner["access_token"])
    invitee_email = invitee["user"]["email"]

    created = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=owner_headers,
        json={"email": invitee_email, "role": "member"},
    )
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "no-store"
    raw_token = created.json()["invite_token"]
    invite_id = created.json()["invite_id"]

    async with AsyncSessionLocal() as db:
        persisted = (
            await db.execute(select(OrganizationInvite).where(OrganizationInvite.id == invite_id))
        ).scalar_one()
        assert persisted.token != raw_token
        assert persisted.token == hashlib.sha256(raw_token.encode()).hexdigest()

    listed = await client.get(f"/api/organizations/{org_id}/invites", headers=owner_headers)
    assert listed.status_code == 200
    assert "token" not in listed.text

    wrong_identity = await client.post(
        "/api/organizations/invites/accept",
        headers=_headers(outsider["access_token"]),
        json={"token": raw_token},
    )
    assert wrong_identity.status_code == 403

    accepted = await client.post(
        "/api/organizations/invites/accept",
        headers=_headers(invitee["access_token"]),
        json={"token": raw_token},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["id"] == org_id

    replay = await client.post(
        "/api/organizations/invites/accept",
        headers=_headers(invitee["access_token"]),
        json={"token": raw_token},
    )
    assert replay.status_code == 409

    switched = await client.post(
        "/api/auth/switch-org",
        headers=_headers(invitee["access_token"]),
        json={"org_id": org_id},
    )
    assert switched.status_code == 200, switched.text
    member_token = switched.json()["access_token"]
    denied_invite = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=_headers(member_token),
        json={"email": outsider["user"]["email"], "role": "viewer"},
    )
    assert denied_invite.status_code == 403

    members = await client.get(f"/api/organizations/{org_id}/members", headers=owner_headers)
    invitee_member = next(item for item in members.json() if item["email"] == invitee_email)
    promoted = await client.patch(
        f"/api/organizations/{org_id}/members/{invitee_member['user_id']}",
        headers=owner_headers,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert (await client.get("/api/auth/me", headers=_headers(member_token))).status_code == 401

    async with AsyncSessionLocal() as db:
        audit_actions = set((await db.execute(
            select(AuditLog.action).where(AuditLog.organization_id == org_id)
        )).scalars().all())
    assert {"org.invite.create", "org.invite.accept", "org.member.role_update"} <= audit_actions

    removed = await client.delete(
        f"/api/organizations/{org_id}/members/{invitee_member['user_id']}",
        headers=owner_headers,
    )
    assert removed.status_code == 204


@pytest.mark.asyncio
async def test_admin_cannot_grant_admin_or_remove_admin_and_team_facade_is_scoped(client, needs_auth):
    owner = await _register(client, "policy-owner")
    admin = await _register(client, "policy-admin")
    member = await _register(client, "policy-member")
    foreign = await _register(client, "foreign")
    org_id = owner["current_org_id"]
    owner_headers = _headers(owner["access_token"])

    async def invite_and_accept(account: dict, role: str) -> str:
        made = await client.post(
            f"/api/organizations/{org_id}/invites",
            headers=owner_headers,
            json={"email": account["user"]["email"], "role": role},
        )
        assert made.status_code == 201, made.text
        accepted = await client.post(
            "/api/organizations/invites/accept",
            headers=_headers(account["access_token"]),
            json={"token": made.json()["invite_token"]},
        )
        assert accepted.status_code == 200
        switched = await client.post(
            "/api/auth/switch-org",
            headers=_headers(account["access_token"]),
            json={"org_id": org_id},
        )
        assert switched.status_code == 200
        return switched.json()["access_token"]

    admin_token = await invite_and_accept(admin, "admin")
    member_token = await invite_and_accept(member, "member")
    members = (await client.get(f"/api/organizations/{org_id}/members", headers=owner_headers)).json()
    admin_row = next(item for item in members if item["email"] == admin["user"]["email"])
    member_row = next(item for item in members if item["email"] == member["user"]["email"])

    grant_admin = await client.patch(
        f"/api/organizations/{org_id}/members/{member_row['user_id']}",
        headers=_headers(admin_token),
        json={"role": "admin"},
    )
    assert grant_admin.status_code == 403
    remove_admin = await client.delete(
        f"/api/organizations/{org_id}/members/{admin_row['user_id']}",
        headers=_headers(admin_token),
    )
    assert remove_admin.status_code in {400, 403}

    team_members = await client.get("/api/team/members", headers=owner_headers)
    assert team_members.status_code == 200
    visible_emails = {item["email"] for item in team_members.json()["members"]}
    assert foreign["user"]["email"] not in visible_emails
    assert {owner["user"]["email"], admin["user"]["email"], member["user"]["email"]} <= visible_emails

    # Member cannot mutate through the legacy compatibility surface either.
    team_denied = await client.put(
        f"/api/team/members/{member_row['id']}?role=viewer",
        headers=_headers(member_token),
    )
    assert team_denied.status_code == 403


@pytest.mark.asyncio
async def test_paid_plan_cannot_be_self_assigned_and_revoked_refresh_is_rejected(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.user import User

    owner = await _register(client, "billing-probe")
    forbidden = await client.post(
        "/api/organizations",
        headers=_headers(owner["access_token"]),
        json={"name": f"Paid Probe {_uid()}", "plan": "enterprise"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "PLAN_ASSIGNMENT_FORBIDDEN"

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.id == owner["user"]["id"]))
        ).scalar_one()
        user.token_version += 1
        await db.commit()

    refreshed = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": owner["refresh_token"]},
    )
    assert refreshed.status_code == 401


@pytest.mark.asyncio
async def test_invites_can_be_revoked_and_expire_durably(client, needs_auth):
    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationInvite

    owner = await _register(client, "lifecycle-owner")
    revoked_user = await _register(client, "revoked-user")
    expired_user = await _register(client, "expired-user")
    org_id = owner["current_org_id"]
    owner_headers = _headers(owner["access_token"])

    revoked = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=owner_headers,
        json={"email": revoked_user["user"]["email"], "role": "viewer"},
    )
    assert revoked.status_code == 201
    revoke_response = await client.delete(
        f"/api/organizations/{org_id}/invites/{revoked.json()['invite_id']}",
        headers=owner_headers,
    )
    assert revoke_response.status_code == 204
    rejected = await client.post(
        "/api/organizations/invites/accept",
        headers=_headers(revoked_user["access_token"]),
        json={"token": revoked.json()["invite_token"]},
    )
    assert rejected.status_code == 409

    expired = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=owner_headers,
        json={"email": expired_user["user"]["email"], "role": "member"},
    )
    assert expired.status_code == 201
    expired_id = expired.json()["invite_id"]
    async with AsyncSessionLocal() as db:
        invite = (
            await db.execute(select(OrganizationInvite).where(OrganizationInvite.id == expired_id))
        ).scalar_one()
        invite.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db.commit()

    gone = await client.post(
        "/api/organizations/invites/accept",
        headers=_headers(expired_user["access_token"]),
        json={"token": expired.json()["invite_token"]},
    )
    assert gone.status_code == 410
    async with AsyncSessionLocal() as db:
        status_value = (
            await db.execute(select(OrganizationInvite.status).where(OrganizationInvite.id == expired_id))
        ).scalar_one()
    assert status_value == "expired"


@pytest.mark.asyncio
async def test_deleted_organization_is_removed_from_login_context_and_revokes_tokens(client, needs_auth):
    owner = await _register(client, "delete-owner")
    org_id = owner["current_org_id"]
    deleted = await client.delete(
        f"/api/organizations/{org_id}",
        headers=_headers(owner["access_token"]),
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/auth/me", headers=_headers(owner["access_token"]))).status_code == 401

    login = await client.post(
        "/api/auth/login",
        json={"username": owner["user"]["username"], "password": "SecurePass123!"},
    )
    assert login.status_code == 200
    assert login.json()["current_org_id"] == ""
    assert all(org["id"] != org_id for org in login.json()["organizations"])
