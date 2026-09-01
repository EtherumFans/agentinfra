"""Organization membership, role, and invitation APIs.

The JWT ``org_id`` is an enforced tenant boundary. Path-addressed operations
must match it; organization roles are independent from platform roles.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_user_orgs, _slugify
from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import get_current_organization, get_current_user, require_org_membership
from app.models.organization import (
    Organization,
    OrganizationInvite,
    OrganizationInviteDelivery,
    OrganizationMember,
    OrgRole,
)
from app.models.user import User
from app.schemas.organization import (
    AcceptOrganizationInviteRequest,
    InviteMemberRequest,
    OrganizationCreate,
    OrganizationInviteResponse,
    OrganizationInviteCreateResponse,
    OrganizationResponse,
    OrganizationUpdate,
    OrgMemberResponse,
    UpdateMemberRoleRequest,
)
from app.services.invite_delivery import (
    InviteDeliveryConfigurationError,
    cancel_invite_delivery,
    enqueue_invite_delivery,
    invite_delivery_mode,
    recipient_domain_allowed,
    requeue_dead_letter,
)
from app.services.database_tenancy import bind_tenant_to_transaction

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

_RESERVED_SETTINGS = {
    "_model_routing",
    "plan",
    "verified",
    "environment_provisioned",
    "environment_assignments",
}


def _org_response(org: Organization) -> OrganizationResponse:
    return OrganizationResponse.model_validate(org)


def _invite_response(
    invite: OrganizationInvite,
    delivery_status: str | None = None,
) -> OrganizationInviteResponse:
    return OrganizationInviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role.value,
        status=invite.status,
        delivery_status=delivery_status,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


def _token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _require_path_context(org_id: str, current_org: Organization) -> None:
    # Use 404 to avoid confirming the existence of another tenant.
    if org_id != current_org.id:
        raise HTTPException(status_code=404, detail="Organization not found")


async def _actor_member(db: AsyncSession, org_id: str, user_id: str) -> OrganizationMember:
    member = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if member is None or member.role not in {OrgRole.OWNER, OrgRole.ADMIN}:
        raise HTTPException(status_code=403, detail="Owner or admin role required")
    return member


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a free organization; paid plans require the billing/admin flow."""
    if data.plan != "free":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PLAN_ASSIGNMENT_FORBIDDEN",
                "message": "Paid plans cannot be self-assigned.",
            },
        )
    base_slug = _slugify(data.name)
    slug = base_slug
    counter = 1
    while (await db.execute(select(Organization.id).where(Organization.slug == slug))).scalar_one_or_none():
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organization(name=data.name, slug=slug, plan="free")
    db.add(org)
    await db.flush()
    await bind_tenant_to_transaction(db, org.id)
    db.add(OrganizationMember(
        organization_id=org.id,
        user_id=current_user.id,
        role=OrgRole.OWNER,
        is_default=False,
    ))
    await log_action(
        db, current_user.id, current_user.username, "org.create", "organization", org.id,
        details={"plan": "free"}, organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    return _org_response(org)


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memberships = await _get_user_orgs(db, current_user.id)
    if not memberships:
        return []
    organizations = (
        await db.execute(
            select(Organization).where(
                Organization.id.in_([membership.id for membership in memberships])
            )
        )
    ).scalars().all()
    by_id = {organization.id: organization for organization in organizations}
    return [
        _org_response(by_id[membership.id])
        for membership in memberships
        if membership.id in by_id
    ]


@router.get("/current", response_model=OrganizationResponse)
async def get_current_org(current_org: Organization = Depends(get_current_organization)):
    return _org_response(current_org)


@router.post("/invites/accept", response_model=OrganizationResponse)
async def accept_invite(
    data: AcceptOrganizationInviteRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Consume a one-time invitation whose normalized email matches the user."""
    membership_count = (
        await db.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.user_id == current_user.id
            )
        )
    ).scalar_one()
    token_digest = _token_digest(data.token)
    if db.get_bind().dialect.name == "postgresql":
        invite_org_id = (
            await db.execute(
                text("SELECT icoder_resolve_invite_tenant(:token)"),
                {"token": token_digest},
            )
        ).scalar_one_or_none()
        if invite_org_id:
            await bind_tenant_to_transaction(db, str(invite_org_id))
    invite = (
        await db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.token == token_digest)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    if _as_utc(invite.expires_at) <= datetime.now(timezone.utc):
        invite.status = "expired"
        await cancel_invite_delivery(db, invite_id=invite.id)
        await db.commit()
        raise HTTPException(status_code=410, detail="Invitation expired")
    if invite.email.strip().casefold() != current_user.email.strip().casefold():
        raise HTTPException(status_code=403, detail="Invitation email does not match the authenticated user")

    existing = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == invite.organization_id,
                OrganizationMember.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        invite.status = "accepted"
        await cancel_invite_delivery(db, invite_id=invite.id)
        await db.commit()
        raise HTTPException(status_code=409, detail="User is already a member")

    org = (
        await db.execute(select(Organization).where(Organization.id == invite.organization_id))
    ).scalar_one_or_none()
    if org is None or not org.is_active:
        raise HTTPException(status_code=410, detail="Invited organization is unavailable")

    db.add(OrganizationMember(
        organization_id=invite.organization_id,
        user_id=current_user.id,
        role=invite.role,
        is_default=membership_count == 0,
    ))
    invite.status = "accepted"
    await cancel_invite_delivery(db, invite_id=invite.id)
    await log_action(
        db, current_user.id, current_user.username, "org.invite.accept", "organization_invite", invite.id,
        details={"role": invite.role.value}, organization_id=invite.organization_id,
        ip_address=request.client.host if request.client else None,
    )
    return _org_response(org)


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
):
    _require_path_context(org_id, current_org)
    return _org_response(current_org)


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    await _actor_member(db, org_id, current_user.id)
    if data.settings is not None:
        reserved = sorted(_RESERVED_SETTINGS.intersection(data.settings))
        if reserved:
            raise HTTPException(
                status_code=403,
                detail={"code": "RESERVED_ORG_SETTINGS", "fields": reserved},
            )
        current_org.settings = data.settings
    if data.name is not None:
        current_org.name = data.name
    await log_action(
        db, current_user.id, current_user.username, "org.update", "organization", org_id,
        organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return _org_response(current_org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    actor = await _actor_member(db, org_id, current_user.id)
    if actor.role != OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Only the owner can delete an organization")
    current_org.is_active = False
    users = (
        await db.execute(
            select(User).join(OrganizationMember, OrganizationMember.user_id == User.id).where(
                OrganizationMember.organization_id == org_id
            )
        )
    ).scalars().all()
    for user in users:
        user.token_version += 1
    await log_action(
        db, current_user.id, current_user.username, "org.delete", "organization", org_id,
        organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/{org_id}/members", response_model=list[OrgMemberResponse])
async def list_members(
    org_id: str,
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    rows = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id)
            .order_by(OrganizationMember.created_at)
        )
    ).all()
    return [
        OrgMemberResponse(
            id=member.id, user_id=member.user_id, username=user.username,
            email=user.email, full_name=user.full_name, role=member.role.value,
            is_default=member.is_default, created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.get("/{org_id}/invites", response_model=list[OrganizationInviteResponse])
async def list_invites(
    org_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    await _actor_member(db, org_id, current_user.id)
    invites = (
        await db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.organization_id == org_id)
            .order_by(OrganizationInvite.created_at.desc())
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    delivery_by_invite = {
        delivery.invite_id: delivery
        for delivery in (
            await db.execute(
                select(OrganizationInviteDelivery).where(
                    OrganizationInviteDelivery.organization_id == org_id
                )
            )
        ).scalars().all()
    }
    for invite in invites:
        if invite.status == "pending" and _as_utc(invite.expires_at) <= now:
            invite.status = "expired"
            await cancel_invite_delivery(db, invite_id=invite.id)
    return [
        _invite_response(
            invite,
            delivery_by_invite.get(invite.id).status if delivery_by_invite.get(invite.id) else None,
        )
        for invite in invites
    ]


@router.post(
    "/{org_id}/invites",
    response_model=OrganizationInviteCreateResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    org_id: str,
    data: InviteMemberRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create an invite; webhook mode never returns the raw credential."""
    _require_path_context(org_id, current_org)
    actor = await _actor_member(db, org_id, current_user.id)
    requested_role = OrgRole(data.role)
    if requested_role == OrgRole.ADMIN and actor.role != OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Only the owner can invite administrators")

    normalized_email = str(data.email).strip().casefold()
    delivery_mode = invite_delivery_mode()
    if delivery_mode == "webhook" and not recipient_domain_allowed(normalized_email):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVITE_EMAIL_DOMAIN_FORBIDDEN",
                "message": "Invitation recipient domain is not allowed.",
            },
        )
    user = (
        await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    ).scalar_one_or_none()
    if user is not None:
        existing_member = (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing_member is not None:
            raise HTTPException(status_code=409, detail="User is already a member")

    existing_invite = (
        await db.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.organization_id == org_id,
                func.lower(OrganizationInvite.email) == normalized_email,
                OrganizationInvite.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing_invite is not None and _as_utc(existing_invite.expires_at) > datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="An active invitation already exists for this email")
    if existing_invite is not None:
        existing_invite.status = "expired"
        await cancel_invite_delivery(db, invite_id=existing_invite.id)

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invite = OrganizationInvite(
        organization_id=org_id,
        email=normalized_email,
        role=requested_role,
        token=_token_digest(raw_token),
        status="pending",
        expires_at=expires_at,
        invited_by=current_user.id,
    )
    db.add(invite)
    await db.flush()
    delivery = None
    if delivery_mode == "webhook":
        try:
            delivery = await enqueue_invite_delivery(
                db,
                invite=invite,
                organization=current_org,
                raw_token=raw_token,
            )
        except InviteDeliveryConfigurationError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "INVITE_DELIVERY_UNAVAILABLE",
                    "message": "Invitation delivery is not safely configured.",
                },
            ) from exc
    await log_action(
        db, current_user.id, current_user.username, "org.invite.create", "organization_invite", invite.id,
        details={"role": requested_role.value}, organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )
    response.headers["Cache-Control"] = "no-store"
    result = {
        "invite_id": invite.id,
        "expires_at": expires_at,
        "delivery": delivery.status if delivery is not None else "manual",
        "message": (
            "Invitation queued for delivery."
            if delivery is not None
            else "Invitation created; external email delivery remains required."
        ),
    }
    if delivery is None:
        result["invite_token"] = raw_token
    return result


@router.delete("/{org_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    org_id: str,
    invite_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    await _actor_member(db, org_id, current_user.id)
    invite = (
        await db.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.id == invite_id,
                OrganizationInvite.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    invite.status = "revoked"
    await cancel_invite_delivery(db, invite_id=invite.id)
    await log_action(
        db, current_user.id, current_user.username, "org.invite.revoke", "organization_invite", invite.id,
        organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )


@router.post("/{org_id}/invites/{invite_id}/retry", response_model=OrganizationInviteResponse)
async def retry_invite_delivery(
    org_id: str,
    invite_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Requeue a dead-letter delivery without exposing its credential."""
    _require_path_context(org_id, current_org)
    await _actor_member(db, org_id, current_user.id)
    invite = (
        await db.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.id == invite_id,
                OrganizationInvite.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invite.status != "pending" or _as_utc(invite.expires_at) <= datetime.now(timezone.utc):
        if invite.status == "pending":
            invite.status = "expired"
            await cancel_invite_delivery(db, invite_id=invite.id)
            await db.commit()
        raise HTTPException(status_code=409, detail="Invitation is no longer active")
    delivery = await requeue_dead_letter(db, invite_id=invite.id)
    if delivery is None:
        raise HTTPException(status_code=409, detail="Invitation delivery is not retryable")
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "org.invite.delivery_requeued",
        "organization_invite_delivery",
        delivery.id,
        details={"invite_id": invite.id},
        organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )
    return _invite_response(invite, delivery.status)


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: str,
    user_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    actor = await _actor_member(db, org_id, current_user.id)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    target = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot remove the organization owner")
    if target.role == OrgRole.ADMIN and actor.role != OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Only the owner can remove administrators")

    target_user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    target_user.token_version += 1
    await db.delete(target)
    await log_action(
        db, current_user.id, current_user.username, "org.member.remove", "organization_member", target.id,
        details={"target_user_id": user_id}, organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )


@router.patch("/{org_id}/members/{user_id}", response_model=OrgMemberResponse)
async def update_member_role(
    org_id: str,
    user_id: str,
    data: UpdateMemberRoleRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    _require_path_context(org_id, current_org)
    actor = await _actor_member(db, org_id, current_user.id)
    target = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == OrgRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot change the owner's role")
    requested_role = OrgRole(data.role)
    if actor.role != OrgRole.OWNER and (target.role == OrgRole.ADMIN or requested_role == OrgRole.ADMIN):
        raise HTTPException(status_code=403, detail="Only the owner can grant or change administrator access")

    old_role = target.role.value
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    if target.role != requested_role:
        target.role = requested_role
        user.token_version += 1
        await log_action(
            db, current_user.id, current_user.username, "org.member.role_update", "organization_member", target.id,
            details={"target_user_id": user_id, "old_role": old_role, "new_role": requested_role.value},
            organization_id=org_id,
            ip_address=request.client.host if request.client else None,
        )
    await db.flush()
    return OrgMemberResponse(
        id=target.id, user_id=target.user_id, username=user.username,
        email=user.email, full_name=user.full_name, role=target.role.value,
        is_default=target.is_default, created_at=target.created_at,
    )
