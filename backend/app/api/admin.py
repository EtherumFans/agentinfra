"""Platform administration APIs.

Platform roles are deliberately separate from organization roles. Every
access mutation is version-checked, revokes active credentials, and writes a
system-scope audit event.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, UserRole
from app.models.agent import Agent
from app.models.oauth import OAuthClient, OAuthToken
from app.models.organization import Organization, OrganizationMember
from app.middleware.auth import get_admin_user
from app.config import settings
from app.services.system_audit import system_audit, tenant_owned_system_audit
from app.services.database_tenancy import bind_tenant_to_transaction

router = APIRouter(prefix="/api/admin", tags=["admin"])


UserAccessReason = Literal[
    "role_assignment",
    "role_revocation",
    "account_suspension",
    "account_reactivation",
    "security_response",
    "employment_change",
]
OrganizationChangeReason = Literal[
    "organization_suspension",
    "organization_reactivation",
    "security_response",
    "plan_change",
]


class PlatformUserAccessUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    expected_token_version: int = Field(..., ge=0)
    reason_code: UserAccessReason
    ticket_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    @model_validator(mode="after")
    def require_change(self):
        if self.role is None and self.is_active is None:
            raise ValueError("role or is_active is required")
        return self


class PlatformOrganizationUpdate(BaseModel):
    is_active: bool | None = None
    plan: Literal["free", "pro", "enterprise"] | None = None
    reason_code: OrganizationChangeReason
    ticket_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    @model_validator(mode="after")
    def require_change(self):
        if self.plan is None and self.is_active is None:
            raise ValueError("plan or is_active is required")
        return self


def _user_view(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "department": user.department,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "token_version": user.token_version,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


async def _organization_ids(db: AsyncSession) -> list[str]:
    return list(
        (
            await db.execute(
                select(Organization.id)
            )
        ).scalars().all()
    )


@router.get("/stats")
async def admin_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform statistics for admin dashboard."""
    agent_count = (await db.execute(select(func.count()).select_from(Agent))).scalar()
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar()
    org_count = (await db.execute(select(func.count()).select_from(Organization))).scalar()
    published_agents = (await db.execute(
        select(func.count()).select_from(Agent).where(Agent.status == "published")
    )).scalar()

    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "agents": {"total": agent_count, "published": published_agents},
        "users": {"total": user_count},
        "organizations": {"total": org_count},
    }


@router.get("/agents")
async def list_all_agents(
    status: str = "",
    category: str = "",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agents (admin view — includes drafts)."""
    q = select(Agent)
    if status: q = q.where(Agent.status == status)
    if category: q = q.where(Agent.category == category)
    q = q.order_by(Agent.created_at.desc())
    result = await db.execute(q)
    agents = result.scalars().all()

    from app.services.agent_dict_util import agent_to_dict
    items = []
    for a in agents:
        items.append(await agent_to_dict(a))
    return {"agents": items, "total": len(items)}


@router.get("/users")
async def list_users(
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str = Query("", max_length=64),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination."""
    q = select(User)
    if search:
        q = q.where(
            User.username.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    q = q.order_by(User.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    users = result.scalars().all()
    response.headers["Cache-Control"] = "no-store"
    return {
        "users": [_user_view(user) for user in users],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/users/{user_id}")
async def update_user_access(
    user_id: str,
    data: PlatformUserAccessUpdate,
    request: Request,
    response: Response,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign/revoke a platform role or activate/deactivate an account."""
    target = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    denied_details = {
        "target_user_id": target.id,
        "reason_code": data.reason_code,
        "ticket_id": data.ticket_id,
        "expected_token_version": data.expected_token_version,
        "actual_token_version": target.token_version,
    }
    if target.id == admin.id:
        await system_audit(
            db,
            action="platform_admin.user_access_update_denied",
            resource_type="user",
            resource_id=target.id,
            details={**denied_details, "reason": "self_modification_forbidden"},
            status="failure",
            user_id=admin.id,
            username=admin.username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Platform administrators cannot modify their own access")
    if target.token_version != data.expected_token_version:
        await system_audit(
            db,
            action="platform_admin.user_access_update_denied",
            resource_type="user",
            resource_id=target.id,
            details={**denied_details, "reason": "stale_token_version"},
            status="failure",
            user_id=admin.id,
            username=admin.username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_USER_ACCESS_VERSION",
                "actual_token_version": target.token_version,
            },
        )

    removes_active_admin = (
        target.role == UserRole.ADMIN
        and target.is_active
        and (
            (data.role is not None and data.role != UserRole.ADMIN)
            or data.is_active is False
        )
    )
    if removes_active_admin:
        active_admins = (
            await db.execute(
                select(func.count()).select_from(User).where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
        ).scalar_one()
        if active_admins <= 1:
            await system_audit(
                db,
                action="platform_admin.user_access_update_denied",
                resource_type="user",
                resource_id=target.id,
                details={**denied_details, "reason": "last_active_admin"},
                status="failure",
                user_id=admin.id,
                username=admin.username,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            await db.commit()
            raise HTTPException(status_code=409, detail="Cannot remove the last active platform administrator")

    old_role = target.role.value
    old_active = target.is_active
    new_role = data.role or target.role
    new_active = target.is_active if data.is_active is None else data.is_active
    changed = new_role != target.role or new_active != target.is_active
    if not changed:
        response.headers["Cache-Control"] = "no-store"
        return {"user": _user_view(target), "changed": False, "tokens_revoked": 0, "clients_disabled": 0}

    target.role = new_role
    target.is_active = new_active
    from app.api.auth import _revoke_user_tokens
    tokens_revoked = await _revoke_user_tokens(db, target.id, "platform_access_update")

    clients_disabled = 0
    if old_active and not new_active:
        for organization_id in await _organization_ids(db):
            await bind_tenant_to_transaction(db, organization_id)
            clients = (
                await db.execute(
                    select(OAuthClient).where(OAuthClient.owner_id == target.id)
                )
            ).scalars().all()
            for client in clients:
                if client.is_active:
                    client.is_active = False
                    clients_disabled += 1
            # Flush while the same tenant remains bound; do not accumulate
            # dirty rows from several RLS partitions.
            await db.flush()

    await system_audit(
        db,
        action="platform_admin.user_access_updated",
        resource_type="user",
        resource_id=target.id,
        details={
            "target_user_id": target.id,
            "old_role": old_role,
            "new_role": new_role.value,
            "old_active": old_active,
            "new_active": new_active,
            "reason_code": data.reason_code,
            "ticket_id": data.ticket_id,
            "tokens_revoked": tokens_revoked,
            "clients_disabled": clients_disabled,
        },
        user_id=admin.id,
        username=admin.username,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    await db.refresh(target)
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": _user_view(target),
        "changed": True,
        "tokens_revoked": tokens_revoked,
        "clients_disabled": clients_disabled,
    }


@router.get("/api-clients")
async def list_api_clients(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all OAuth API clients."""
    clients: list[dict] = []
    for organization_id in await _organization_ids(db):
        await bind_tenant_to_transaction(db, organization_id)
        rows = (await db.execute(select(OAuthClient))).scalars().all()
        clients.extend(
            {
                "client_id": client.client_id,
                "organization_id": client.organization_id,
                "name": client.name,
                "scopes": client.scopes,
                "is_active": client.is_active,
                "created_at": client.created_at.isoformat(),
            }
            for client in rows
        )
    return {"clients": clients}


# --- Organization Admin Endpoints ---

@router.get("/organizations")
async def list_all_organizations(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform-level: list all organizations."""
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = result.scalars().all()
    return {
        "organizations": [
            {"id": o.id, "name": o.name, "slug": o.slug, "plan": o.plan,
             "is_active": o.is_active, "created_at": o.created_at.isoformat()}
            for o in orgs
        ],
        "total": len(orgs),
    }


@router.patch("/organizations/{org_id}")
async def admin_update_organization(
    org_id: str,
    data: PlatformOrganizationUpdate,
    request: Request,
    response: Response,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Suspend/reactivate an organization or assign a validated plan."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    await bind_tenant_to_transaction(db, org.id)

    old_active = org.is_active
    old_plan = org.plan
    new_active = org.is_active if data.is_active is None else data.is_active
    new_plan = org.plan if data.plan is None else data.plan
    changed = new_active != old_active or new_plan != old_plan
    if not changed:
        response.headers["Cache-Control"] = "no-store"
        return {
            "id": org.id,
            "name": org.name,
            "is_active": org.is_active,
            "plan": org.plan,
            "changed": False,
            "user_tokens_revoked": 0,
            "clients_disabled": 0,
            "oauth_tokens_revoked": 0,
        }

    org.is_active = new_active
    org.plan = new_plan
    user_tokens_revoked = 0
    clients_disabled = 0
    oauth_tokens_revoked = 0
    if old_active and not new_active:
        users = (
            await db.execute(
                select(User)
                .join(OrganizationMember, OrganizationMember.user_id == User.id)
                .where(OrganizationMember.organization_id == org_id)
            )
        ).scalars().all()
        for user in users:
            user.token_version += 1
            user_tokens_revoked += 1

        clients = (
            await db.execute(select(OAuthClient).where(OAuthClient.organization_id == org_id))
        ).scalars().all()
        client_ids = [client.client_id for client in clients]
        for client in clients:
            if client.is_active:
                client.is_active = False
                clients_disabled += 1
        if client_ids:
            oauth_tokens = (
                await db.execute(
                    select(OAuthToken).where(
                        OAuthToken.client_id.in_(client_ids),
                        OAuthToken.is_revoked.is_(False),
                    )
                )
            ).scalars().all()
            for token in oauth_tokens:
                token.is_revoked = True
                oauth_tokens_revoked += 1

    await tenant_owned_system_audit(
        db,
        organization_id=org.id,
        action="platform_admin.organization_updated",
        resource_type="organization",
        resource_id=org.id,
        details={
            "old_active": old_active,
            "new_active": new_active,
            "old_plan": old_plan,
            "new_plan": new_plan,
            "reason_code": data.reason_code,
            "ticket_id": data.ticket_id,
            "tokens_revoked": user_tokens_revoked + oauth_tokens_revoked,
            "clients_disabled": clients_disabled,
        },
        user_id=admin.id,
        username=admin.username,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": org.id,
        "name": org.name,
        "is_active": org.is_active,
        "plan": org.plan,
        "changed": True,
        "user_tokens_revoked": user_tokens_revoked,
        "clients_disabled": clients_disabled,
        "oauth_tokens_revoked": oauth_tokens_revoked,
    }


@router.get("/organizations/{org_id}/usage")
async def org_usage_stats(
    org_id: str,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform-level: get usage statistics for an organization."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    user_count = (await db.execute(
        select(func.count()).select_from(OrganizationMember).where(
            OrganizationMember.organization_id == org_id
        )
    )).scalar()

    agent_count = (await db.execute(
        select(func.count()).select_from(Agent).where(Agent.organization_id == org_id)
    )).scalar()

    return {
        "organization": {"id": org.id, "name": org.name, "slug": org.slug},
        "members": user_count,
        "agents": agent_count,
        "plan": org.plan,
    }


# ── Runtime Dashboard (admin only) ──

@router.get("/runtime", response_class=HTMLResponse)
async def admin_runtime_dashboard(
    admin: User = Depends(get_admin_user),
):
    """Admin-only Runtime Dashboard embedded in main platform."""
    from pathlib import Path
    html_path = Path(__file__).parent.parent.parent / "icoder_runtime" / "dashboard.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>Dashboard not found</h1>"


@router.get("/runtime/status")
async def admin_runtime_status(
    admin: User = Depends(get_admin_user),
):
    """Get Embedded Runtime status for the platform."""
    from fastapi import Request
    # Access the platform runtime from app state
    from app.main import app as _app
    rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    if rt:
        status = rt.status()
        status["agents"] = rt.list_agents()
        return status
    return {"started": False, "error": "PlatformRuntime not initialized"}


# ── KMS Rotation (admin only) ──
# Phase A1D.7 (Pilot Prep Step 5a) — operator-driven KMS key rotation.
# Endpoint bumps the global KMSVersionToken + flushes CredentialVault cache
# + writes an audit row. Subsequent vault.resolve() calls re-read from env
# (dev) or the cloud secrets manager (prod, when adapter is wired).
#
# This closes the gap: an operator rotates the cloud KMS key via console,
# but the app keeps serving the old cached value. With this endpoint, the
# operator (or a cloud-function post-rotation hook) calls
# POST /api/admin/kms/rotate and every app instance drops its cached
# secrets on the next resolve().


class KMSRotationResponse(BaseModel):
    previous_version: int
    current_version: int
    invalidated_entries: int
    rotated_by: str


@router.get("/kms/version", response_model=KMSRotationResponse)
async def admin_kms_version(
    admin: User = Depends(get_admin_user),
):
    """Read the current KMS version token without rotating.

    Useful for health-check / canary: the operator can verify all app
    instances report the same version before initiating rotation.
    """
    from app.services.credential_vault import get_global_kms_version_token
    token = get_global_kms_version_token()
    return KMSRotationResponse(
        previous_version=token.current,
        current_version=token.current,
        invalidated_entries=0,
        rotated_by=admin.username,
    )


@router.post("/kms/rotate", response_model=KMSRotationResponse)
async def admin_kms_rotate(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Bump the KMS version token + flush the CredentialVault cache.

    Workflow (operator runbook):
      1. Rotate the cloud KMS key via cloud console (AWS / Aliyun / Azure).
      2. Wait for the new key material to propagate to secrets manager.
      3. Call POST /api/admin/kms/rotate on each app instance.
         (Or wire a cloud-function post-rotation hook to do this.)
      4. The next vault.resolve(service) call re-reads from the secrets
         manager and stamps the cache entry with the new token.

    The audit row captures previous_version → current_version so the
    operator can verify the bump took effect.
    """
    from app.services.credential_vault import (
        credential_vault,
        get_global_kms_version_token,
    )
    from app.middleware.audit import log_action

    token = get_global_kms_version_token()
    previous = token.current
    current = token.bump()

    # Defensive: stale-stamp check would catch this on next resolve(),
    # but we flush explicitly so the rotation is observable immediately
    # via health_check() / list_available_services().
    cached_count = len(credential_vault._cache)
    credential_vault.invalidate_all()
    invalidated = cached_count

    await log_action(
        db,
        user_id=admin.id,
        username=admin.username,
        action="kms.key_rotated",
        resource_type="kms",
        resource_id="global",
        details={
            "previous_version": previous,
            "current_version": current,
            "invalidated_entries": invalidated,
        },
    )
    await db.commit()

    return KMSRotationResponse(
        previous_version=previous,
        current_version=current,
        invalidated_entries=invalidated,
        rotated_by=admin.username,
    )
