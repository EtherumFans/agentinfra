"""Backward-compatible team routes backed by organization membership.

The former TeamMember table was a global, unscoped authorization surface.
These routes retain the frontend contract while delegating all writes to the
authoritative OrganizationMember/OrganizationInvite policy.
"""
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.organizations import (
    invite_member as organization_invite_member,
    list_invites as organization_list_invites,
    remove_member as organization_remove_member,
    update_member_role as organization_update_member_role,
)
from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user, require_org_membership
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.organization import InviteMemberRequest, UpdateMemberRoleRequest

router = APIRouter(prefix="/api/team", tags=["team"])


def _avatar(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@router.get("/members")
async def list_members(
    current_org: Organization = Depends(get_current_organization),
    _membership: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == current_org.id)
            .order_by(OrganizationMember.created_at)
        )
    ).all()
    return {
        "members": [
            {
                "id": member.id,
                "user_id": user.id,
                "name": user.full_name or user.username,
                "email": user.email,
                "role": member.role.value,
                "avatar": _avatar(user.full_name or user.username),
            }
            for member, user in rows
        ]
    }


@router.get("/invitations")
async def list_invitations(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    invites = await organization_list_invites(
        current_org.id, current_user, current_org, db
    )
    return {
        "invitations": [
            {
                "id": invite.id,
                "email": str(invite.email),
                "role": invite.role,
                "status": invite.status,
                "invited_at": invite.created_at.isoformat(),
                "expires_at": invite.expires_at.isoformat(),
            }
            for invite in invites
            if invite.status == "pending"
        ]
    }


@router.post("/invite")
async def invite_member(
    request: Request,
    response: Response,
    email: str,
    role: str = Query("member", pattern="^(admin|member|viewer)$"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return await organization_invite_member(
        current_org.id,
        InviteMemberRequest(email=email, role=role),
        request,
        response,
        current_user,
        current_org,
        db,
    )


@router.put("/members/{member_id}")
async def update_member_role(
    member_id: str,
    request: Request,
    role: str = Query(..., pattern="^(admin|member|viewer)$"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.organization_id == current_org.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Member not found")
    updated = await organization_update_member_role(
        current_org.id,
        member.user_id,
        UpdateMemberRoleRequest(role=role),
        request,
        current_user,
        current_org,
        db,
    )
    return {"status": "updated", "member_id": member_id, "role": updated.role}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.id == member_id,
                OrganizationMember.organization_id == current_org.id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Member not found")
    await organization_remove_member(
        current_org.id,
        member.user_id,
        request,
        current_user,
        current_org,
        db,
    )
    return {"status": "removed", "member_id": member_id}
