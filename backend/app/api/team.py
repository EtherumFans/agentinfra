"""Team management endpoints with database persistence"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.team import TeamMember, TeamRole

router = APIRouter(prefix="/api/team", tags=["team"])


def _avatar(name: str) -> str:
    """Generate initials avatar from name."""
    parts = name.strip().split()
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@router.get("/members")
async def list_members(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List team members"""
    result = await db.execute(
        select(TeamMember).where(TeamMember.status == "active")
        .order_by(TeamMember.role, TeamMember.created_at)
    )
    members = result.scalars().all()
    return {
        "members": [
            {
                "id": m.id,
                "name": m.name,
                "email": m.email,
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "avatar": _avatar(m.name),
            }
            for m in members
        ]
    }


@router.get("/invitations")
async def list_invitations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending team invitations"""
    result = await db.execute(
        select(TeamMember).where(TeamMember.status == "pending")
        .order_by(TeamMember.created_at.desc())
    )
    members = result.scalars().all()
    return {
        "invitations": [
            {
                "id": m.id,
                "email": m.email,
                "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                "status": m.status,
                "invited_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in members
        ]
    }


@router.post("/invite")
async def invite_member(
    email: str,
    role: str = Query("coder", enum=["coder", "dept_head", "viewer"]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new team member"""
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.email == email,
            TeamMember.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Member already in team")

    team_role = TeamRole(role)
    member = TeamMember(
        user_id="",
        email=email,
        name=email.split("@")[0],
        role=team_role,
        status="pending",
        invited_by=user.id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return {"status": "invited", "email": email, "role": role}


@router.put("/members/{member_id}")
async def update_member_role(
    member_id: str,
    role: str = Query(..., enum=["coder", "dept_head", "viewer"]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a team member's role"""
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.status == "active")
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = TeamRole(role)
    await db.commit()
    return {"status": "updated", "member_id": member_id, "role": role}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a team member"""
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.status == "active")
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.role == TeamRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot remove owner")
    member.status = "removed"
    await db.commit()
    return {"status": "removed", "member_id": member_id}
