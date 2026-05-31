# iCoDer - Organization CRUD API (Multi-Tenant)
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization, OrganizationMember, OrganizationInvite, OrgRole
from app.schemas.organization import (
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    OrgMemberResponse, InviteMemberRequest, UpdateMemberRoleRequest,
)
from app.middleware.auth import (
    get_current_user, get_current_organization,
    require_org_role, require_org_membership,
)
from app.middleware.audit import log_action
from app.api.auth import _slugify

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization. Creator automatically becomes owner."""
    base_slug = _slugify(data.name)
    slug = base_slug
    counter = 1
    while True:
        existing = await db.execute(select(Organization).where(Organization.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(name=data.name, slug=slug, plan=data.plan)
    db.add(org)
    await db.flush()

    member = OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role=OrgRole.OWNER,
        is_default=False,
    )
    db.add(member)

    await log_action(db, current_user.id, current_user.username, "org.create", "organization",
                     org.id, details={"name": org.name, "plan": org.plan},
                     ip_address=request.client.host if request.client else None)

    return OrganizationResponse(
        id=org.id, name=org.name, slug=org.slug, plan=org.plan,
        is_active=org.is_active, created_at=org.created_at, updated_at=org.updated_at,
    )


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all organizations the current user belongs to."""
    result = await db.execute(
        select(Organization).join(
            OrganizationMember, OrganizationMember.organization_id == Organization.id
        ).where(OrganizationMember.user_id == current_user.id)
    )
    orgs = result.scalars().all()
    return [
        OrganizationResponse(
            id=o.id, name=o.name, slug=o.slug, plan=o.plan,
            is_active=o.is_active, created_at=o.created_at, updated_at=o.updated_at,
        )
        for o in orgs
    ]


@router.get("/current", response_model=OrganizationResponse)
async def get_current_org(
    current_org: Organization = Depends(get_current_organization),
):
    """Get the currently active organization."""
    return OrganizationResponse(
        id=current_org.id, name=current_org.name, slug=current_org.slug,
        plan=current_org.plan, is_active=current_org.is_active,
        created_at=current_org.created_at, updated_at=current_org.updated_at,
    )


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
):
    """Get organization details. Requires membership."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationResponse(
        id=org.id, name=org.name, slug=org.slug, plan=org.plan,
        is_active=org.is_active, created_at=org.created_at, updated_at=org.updated_at,
    )


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update organization. Requires owner or admin role."""
    # Verify role
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member or member.role.value not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Owner or admin role required")

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if data.name is not None:
        org.name = data.name
    if data.settings is not None:
        org.settings = data.settings

    await db.flush()
    return OrganizationResponse(
        id=org.id, name=org.name, slug=org.slug, plan=org.plan,
        is_active=org.is_active, created_at=org.created_at, updated_at=org.updated_at,
    )


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete an organization. Owner only."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.role == OrgRole.OWNER,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Only the owner can delete an organization")

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.is_active = False
    await db.flush()


@router.get("/{org_id}/members", response_model=list[OrgMemberResponse])
async def list_members(
    org_id: str,
    member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
):
    """List all members of an organization."""
    result = await db.execute(
        select(OrganizationMember, User).join(
            User, User.id == OrganizationMember.user_id
        ).where(OrganizationMember.organization_id == org_id)
    )
    rows = result.all()
    return [
        OrgMemberResponse(
            id=mem.id, user_id=mem.user_id,
            username=user.username, email=user.email, full_name=user.full_name,
            role=mem.role.value, is_default=mem.is_default,
            created_at=mem.created_at,
        )
        for mem, user in rows
    ]


@router.post("/{org_id}/invites", status_code=status.HTTP_201_CREATED)
async def invite_member(
    org_id: str,
    data: InviteMemberRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to the organization by email."""
    # Verify inviter has permission
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    inviter = result.scalar_one_or_none()
    if not inviter or inviter.role.value not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Owner or admin role required")

    # Check if already a member
    existing_user = await db.execute(select(User).where(User.email == data.email))
    user = existing_user.scalar_one_or_none()
    if user:
        existing_member = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user.id,
            )
        )
        if existing_member.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a member")

    # Check for existing pending invite
    existing_invite = await db.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.organization_id == org_id,
            OrganizationInvite.email == data.email,
            OrganizationInvite.status == "pending",
        )
    )
    if existing_invite.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An active invitation already exists for this email")

    token = secrets.token_urlsafe(32)
    invite = OrganizationInvite(
        organization_id=org_id,
        email=data.email,
        role=OrgRole(data.role),
        token=token,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by=current_user.id,
    )
    db.add(invite)

    await log_action(db, current_user.id, current_user.username, "org.invite", "organization",
                     org_id, details={"email": data.email, "role": data.role},
                     ip_address=request.client.host if request.client else None)

    return {"invite_token": token, "message": f"Invitation sent to {data.email}"}


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: str,
    user_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the organization."""
    # Verify remover has permission
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    remover = result.scalar_one_or_none()
    if not remover or remover.role.value not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Owner or admin role required")

    # Cannot remove yourself
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself. Use delete organization instead.")

    # Cannot remove an owner
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot remove the organization owner")

    await db.delete(target)

    await log_action(db, current_user.id, current_user.username, "org.remove_member",
                     "organization", org_id,
                     details={"removed_user_id": user_id},
                     ip_address=request.client.host if request.client else None)


@router.patch("/{org_id}/members/{user_id}", response_model=OrgMemberResponse)
async def update_member_role(
    org_id: str,
    user_id: str,
    data: UpdateMemberRoleRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role. Requires owner or admin."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    updater = result.scalar_one_or_none()
    if not updater or updater.role.value not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Owner or admin role required")

    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == OrgRole.OWNER and data.role != "owner":
        raise HTTPException(status_code=403, detail="Cannot change the owner's role")

    old_role = target.role.value
    target.role = OrgRole(data.role)
    await db.flush()

    # Get user info
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    await log_action(db, current_user.id, current_user.username, "org.update_role",
                     "organization", org_id,
                     details={"target_user_id": user_id, "old_role": old_role, "new_role": data.role},
                     ip_address=request.client.host if request.client else None)

    return OrgMemberResponse(
        id=target.id, user_id=target.user_id,
        username=user.username if user else "", email=user.email if user else "",
        full_name=user.full_name if user else "",
        role=target.role.value, is_default=target.is_default,
        created_at=target.created_at,
    )
