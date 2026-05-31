"""Admin API — programmatic console management (Multi-Tenant).

Enables programmatic creation of customers, users, API clients,
and agent lifecycle management for platform integrators.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.agent import Agent
from app.models.oauth import OAuthClient
from app.models.organization import Organization, OrganizationMember
from app.middleware.auth import get_admin_user
from app.config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., min_length=1)
    plan: str = "free"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=4)
    full_name: str = ""
    role: str = "user"
    customer_id: str = ""


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

    from app.api.agents import _agent_to_dict
    items = []
    for a in agents:
        items.append(await _agent_to_dict(a))
    return {"agents": items, "total": len(items)}


@router.get("/users")
async def list_users(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return {
        "users": [
            {"id": u.id, "username": u.username, "full_name": u.full_name,
             "role": u.role.value if hasattr(u.role, 'value') else str(u.role),
             "is_active": u.is_active, "created_at": u.created_at.isoformat()}
            for u in users
        ],
        "total": len(users),
    }


@router.get("/api-clients")
async def list_api_clients(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all OAuth API clients."""
    result = await db.execute(select(OAuthClient))
    clients = result.scalars().all()
    return {
        "clients": [
            {"client_id": c.client_id, "name": c.name,
             "scopes": c.scopes, "is_active": c.is_active,
             "created_at": c.created_at.isoformat()}
            for c in clients
        ],
    }


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
    is_active: bool = Query(...),
    plan: str = Query(""),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform-level: suspend/unsuspend organization or change plan."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.is_active = is_active
    if plan:
        org.plan = plan
    await db.flush()

    return {"id": org.id, "name": org.name, "is_active": org.is_active, "plan": org.plan}


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
