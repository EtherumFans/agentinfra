"""Tenant compatibility API backed by the production Organization model.

Organizations remain the persistence primitive.  These endpoints expose the
Corti-style Tenant vocabulary without introducing a second tenant database or
claiming that an Environment assignment has been provisioned.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _slugify
from app.api.platform_environments import _catalog
from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization, OrganizationMember, OrgRole
from app.models.user import User


router = APIRouter(prefix="/api/tenants", tags=["platform-tenants"])


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    plan: str = Field(default="free", pattern="^(free|pro|enterprise)$")
    country: str = Field(default="CN", min_length=2, max_length=2)
    use_cases: list[str] = Field(default_factory=list, max_length=32)
    features_enabled: list[str] = Field(default_factory=list, max_length=64)
    environment_assignments: list[str] = Field(default_factory=list, max_length=8)


def _tenant_view(org: Organization) -> dict[str, Any]:
    settings = dict(org.settings or {})
    assignments = list(settings.get("environment_assignments") or [])
    return {
        "id": org.id,
        "project_name": org.name,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan,
        "country": settings.get("country", "CN"),
        "use_cases": list(settings.get("use_cases") or []),
        "features_enabled": list(settings.get("features_enabled") or []),
        "environment_assignments": assignments,
        "verified": bool(settings.get("verified", False)),
        "is_active": org.is_active,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
    }


@router.get("/current", summary="Get the current Tenant")
async def get_current_tenant(
    current_org: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    return _tenant_view(current_org)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a Tenant")
async def create_tenant(
    data: TenantCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if getattr(current_user.role, "value", current_user.role) != "admin":
        raise HTTPException(status_code=403, detail="Platform admin role required")

    declared_environments = {
        str(item.get("code")) for item in _catalog()["environments"]
    }
    unknown_assignments = sorted(
        set(data.environment_assignments) - declared_environments
    )
    if unknown_assignments:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Unknown Environment assignment",
                "unknown": unknown_assignments,
                "allowed": sorted(declared_environments),
            },
        )

    existing_name = (
        await db.execute(select(Organization.id).where(Organization.name == data.name))
    ).scalar_one_or_none()
    if existing_name:
        raise HTTPException(status_code=409, detail="Tenant name already exists")

    base_slug = _slugify(data.name)
    slug = base_slug
    suffix = 1
    while (
        await db.execute(select(Organization.id).where(Organization.slug == slug))
    ).scalar_one_or_none():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    org = Organization(
        name=data.name,
        slug=slug,
        plan=data.plan,
        settings={
            "country": data.country.upper(),
            "use_cases": data.use_cases,
            "features_enabled": data.features_enabled,
            "environment_assignments": data.environment_assignments,
            "verified": False,
            "environment_provisioned": False,
        },
    )
    db.add(org)
    await db.flush()
    db.add(OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role=OrgRole.OWNER,
        is_default=False,
    ))
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "tenant.create",
        "organization",
        org.id,
        details={"name": org.name, "environment_assignments": data.environment_assignments},
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return _tenant_view(org)


@router.get("/{tenant_id}/environments", summary="Get Tenant Environment assignments")
async def get_tenant_environments(
    tenant_id: str,
    current_org: Organization = Depends(get_current_organization),
) -> dict[str, Any]:
    if tenant_id != current_org.id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    settings = dict(current_org.settings or {})
    return {
        "tenant_id": current_org.id,
        "environment_assignments": list(settings.get("environment_assignments") or []),
        "environment_provisioned": bool(settings.get("environment_provisioned", False)),
        "deployment_mode": "managed" if settings.get("environment_provisioned") else "local_or_pending",
    }
