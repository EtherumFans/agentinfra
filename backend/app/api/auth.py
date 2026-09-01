# iCoDer - Auth API Router (Multi-Tenant)
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.models.organization import Organization, OrganizationMember, OrgRole
from app.schemas.user import (
    UserCreate, UserLogin, UserResponse, UserMeResponse,
    TokenResponse, TokenRefresh, SwitchOrgRequest, OrgInfo,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
    RevokeTokensRequest,
)
from app.middleware.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user, get_current_organization,
)
from app.middleware.audit import log_action
from app.services.database_tenancy import bind_tenant_to_transaction

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Generate a URL-friendly slug from an organization name."""
    import re
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:64]


async def _get_user_orgs(db: AsyncSession, user_id: str) -> list[OrgInfo]:
    """Get all organizations for a user with membership info."""
    orgs = []
    organizations = (
        await db.execute(
            select(Organization).where(Organization.is_active.is_(True))
        )
    ).scalars().all()
    for org in organizations:
        await bind_tenant_to_transaction(db, org.id)
        member = (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org.id,
                    OrganizationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            continue
        orgs.append(OrgInfo(
            id=org.id,
            name=org.name,
            slug=org.slug,
            plan=org.plan,
            role=member.role.value,
            is_default=member.is_default,
        ))
    return orgs


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    # Public sign-up creates an organization owner, but never a privileged
    # platform principal. Elevated clinical/platform roles require an
    # authenticated administrative assignment flow.
    if data.role != UserRole.CODER:
        try:
            from app.services.system_audit import system_audit

            await system_audit(
                db,
                action="auth.register.denied.role_escalation",
                resource_type="user_registration",
                details={"requested_role": data.role.value},
                status="failure",
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            await db.commit()
        except Exception as audit_error:  # pragma: no cover - defensive
            await db.rollback()
            logger.error("registration role-escalation audit failed: %s", audit_error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "SELF_ASSIGNED_ROLE_FORBIDDEN",
                "message": "Public registration cannot assign a privileged role.",
            },
        )

    # Check uniqueness
    existing = await db.execute(select(User).where(
        (User.username == data.username) | (User.email == data.email)
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already exists")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole.CODER,
        department=data.department,
    )
    db.add(user)
    await db.flush()

    # Auto-create organization for the new user
    base_org_name = (data.organization_name or f"{data.full_name}'s Organization")[:256]
    org_name = base_org_name
    base_slug = _slugify(base_org_name)
    slug = base_slug
    # Both columns are database-unique. Different users can legitimately
    # choose the same display name, so advance one shared deterministic suffix
    # until the name/slug pair is available instead of surfacing a 500.
    counter = 1
    while True:
        existing_org = await db.execute(
            select(Organization.id).where(
                (Organization.name == org_name) | (Organization.slug == slug)
            )
        )
        if existing_org.scalar_one_or_none() is None:
            break
        suffix = f"-{counter}"
        org_name = f"{base_org_name[:256 - len(suffix)]}{suffix}"
        slug = f"{base_slug[:64 - len(suffix)]}{suffix}"
        counter += 1

    org = Organization(name=org_name, slug=slug, plan="free")
    db.add(org)
    await db.flush()
    await bind_tenant_to_transaction(db, org.id)

    # Creator becomes owner
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=OrgRole.OWNER,
        is_default=True,
    )
    db.add(member)

    await log_action(db, user.id, user.username, "user.register", "user", user.id,
                     ip_address=request.client.host if request.client else None,
                     details={"org_id": org.id, "org_name": org.name},
                     organization_id=org.id)

    orgs = [OrgInfo(id=org.id, name=org.name, slug=org.slug, plan=org.plan,
                    role="owner", is_default=True)]
    access_token = create_access_token(user.id, user.username, user.role.value, org.id, token_version=0)
    refresh_token = create_refresh_token(user.id, org.id, token_version=0)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
        organizations=orgs,
        current_org_id=org.id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"login:{client_ip}"
    if not login_limiter.check(rate_key):
        retry_after = 300
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Try again in {retry_after} seconds.",
        )

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    login_limiter.record(rate_key)

    if not user or not verify_password(data.password, user.hashed_password):
        await log_action(db, None, data.username, "user.login_failed", "user",
                         ip_address=request.client.host if request.client else None, status="failure")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Auto-upgrade legacy SHA-256 passwords to bcrypt
    from app.middleware.auth import _needs_rehash
    if _needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(data.password)
        await db.commit()
        logger.info(f"Password hash upgraded to bcrypt for user: {user.username}")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Get user's organizations
    orgs = await _get_user_orgs(db, user.id)
    default_org_id = ""
    for org in orgs:
        if org.is_default:
            default_org_id = org.id
            break
    if not default_org_id and orgs:
        default_org_id = orgs[0].id

    if default_org_id:
        await bind_tenant_to_transaction(db, default_org_id)
    await log_action(db, user.id, user.username, "user.login", "user", user.id,
                     ip_address=request.client.host if request.client else None,
                     details={"org_count": len(orgs), "current_org_id": default_org_id},
                     organization_id=default_org_id or None)

    access_token = create_access_token(user.id, user.username, user.role.value, default_org_id, token_version=user.token_version)
    refresh_token = create_refresh_token(user.id, default_org_id, token_version=user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
        organizations=orgs,
        current_org_id=default_org_id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    org_id = payload.get("org_id", "")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if user.token_version != payload.get("token_version", 0):
        raise HTTPException(status_code=401, detail="Refresh token revoked. Please re-authenticate.")

    orgs = await _get_user_orgs(db, user.id)
    # Verify org_id still valid
    if org_id and not any(o.id == org_id for o in orgs):
        org_id = orgs[0].id if orgs else ""

    access_token = create_access_token(user.id, user.username, user.role.value, org_id, token_version=user.token_version)
    new_refresh = create_refresh_token(user.id, org_id, token_version=user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        user=UserResponse.model_validate(user),
        organizations=orgs,
        current_org_id=org_id,
    )


@router.post("/switch-org", response_model=TokenResponse)
async def switch_org(data: SwitchOrgRequest, request: Request,
                     current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Switch to a different organization. Returns new JWT with new org_id."""
    # Verify membership
    await bind_tenant_to_transaction(db, data.org_id)
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == data.org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=403, detail="You are not a member of this organization")

    # Verify org is active
    result = await db.execute(select(Organization).where(Organization.id == data.org_id))
    org = result.scalar_one_or_none()
    if not org or not org.is_active:
        raise HTTPException(status_code=400, detail="Organization not found or suspended")

    orgs = await _get_user_orgs(db, current_user.id)
    await bind_tenant_to_transaction(db, data.org_id)

    await log_action(db, current_user.id, current_user.username, "org.switch", "organization",
                     data.org_id, details={"org_name": org.name},
                     ip_address=request.client.host if request.client else None)

    access_token = create_access_token(current_user.id, current_user.username,
                                       current_user.role.value, org.id,
                                       token_version=current_user.token_version)
    refresh_token = create_refresh_token(current_user.id, org.id, token_version=current_user.token_version)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(current_user),
        organizations=orgs,
        current_org_id=org.id,
    )


@router.get("/me", response_model=UserMeResponse)
async def get_me(current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    orgs = await _get_user_orgs(db, current_user.id)
    # Try to get current org from token
    current_org_id = ""
    return UserMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        department=current_user.department,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        organizations=orgs,
        current_org_id=current_org_id,
    )


# ── Account Security Endpoints ──────────────────────────────────────────

@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(data: ForgotPasswordRequest, request: Request,
                           db: AsyncSession = Depends(get_db)):
    """Request a password reset. Always returns 202 to avoid user enumeration."""
    import hashlib
    from app.models.oauth import PasswordResetToken

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # Generate reset token (valid 1 hour)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(reset)

        # Delivery belongs to the configured out-of-band email provider. The
        # raw reset credential is never returned or written to application logs.
        logger.info("password reset credential created for out-of-band delivery")

    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest, request: Request,
                          db: AsyncSession = Depends(get_db)):
    """Reset password using a valid reset token."""
    import hashlib
    from app.models.oauth import PasswordResetToken

    token_hash = hashlib.sha256(data.token.encode()).hexdigest()
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.is_used == False,
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )
    reset = result.scalar_one_or_none()
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Update password
    result = await db.execute(select(User).where(User.id == reset.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    reset.is_used = True

    # Revoke all existing tokens for this user
    await _revoke_user_tokens(db, user.id, "password_change")

    await log_action(db, user.id, user.username, "user.password_reset", "user", user.id,
                     ip_address=request.client.host if request.client else None)

    return {"message": "Password reset successful. All sessions have been revoked."}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password (requires current password)."""
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(data.new_password)

    # A password change is a security-boundary event. Existing access,
    # refresh, and user-owned OAuth tokens must not survive it.
    await _revoke_user_tokens(db, current_user.id, "password_change")

    await log_action(db, current_user.id, current_user.username, "user.password_change",
                     "user", current_user.id,
                     ip_address=request.client.host if request.client else None)

    return {"message": "Password changed successfully."}


@router.post("/revoke-tokens")
async def revoke_tokens(
    data: RevokeTokensRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke all active tokens for the current user (logout all devices)."""
    count = await _revoke_user_tokens(db, current_user.id, data.reason)

    await log_action(db, current_user.id, current_user.username, "user.revoke_tokens",
                     "user", current_user.id,
                     details={"count": count, "reason": data.reason},
                     ip_address=request.client.host if request.client else None)

    return {"message": f"Revoked {count} active tokens.", "count": count}


async def _revoke_user_tokens(db: AsyncSession, user_id: str, reason: str = "logout") -> int:
    """Revoke all active tokens for a user — increments token_version to invalidate all JWTs."""
    # Increment token_version to invalidate all existing JWTs immediately
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.token_version += 1
        logger.info(f"User {user.username} token_version incremented to {user.token_version} (reason: {reason})")
    # Also revoke OAuth tokens
    from app.models.oauth import OAuthClient, OAuthToken
    oauth_result = await db.execute(
        select(OAuthToken)
        .join(OAuthClient, OAuthClient.client_id == OAuthToken.client_id)
        .where(OAuthClient.owner_id == user_id, OAuthToken.is_revoked.is_(False))
    )
    tokens = oauth_result.scalars().all()
    for t in tokens:
        t.is_revoked = True
    return len(tokens) + (1 if user else 0)


# ── Login Rate Limiter ───────────────────────────────────────────────────

from collections import defaultdict
import time

class LoginRateLimiter:
    """Simple in-memory rate limiter for login attempts.

    Production: use Redis with sliding window.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """Returns True if allowed, False if rate limited."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        return len(self._attempts[key]) < self.max_attempts

    def record(self, key: str) -> None:
        self._attempts[key].append(time.time())

    def remaining(self, key: str) -> int:
        self.check(key)  # cleanup stale entries
        return max(0, self.max_attempts - len(self._attempts[key]))


login_limiter = LoginRateLimiter(max_attempts=5, window_seconds=300)
