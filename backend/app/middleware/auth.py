# iCoDer - Authentication Middleware (Multi-Tenant)
import logging
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.database_tenancy import bind_tenant_to_transaction
from app.models.user import User
from app.models.organization import Organization, OrganizationMember

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def _bind_live_user_membership(
    db: AsyncSession,
    *,
    user_id: str,
    organization_id: str | None,
    required: bool = False,
) -> bool:
    """Bind only a currently active organization membership.

    User-only dependencies are common across older routes.  A JWT org claim
    is not authority, so the claim is promoted to PostgreSQL RLS context only
    after this live membership and organization-status check.
    """
    org_id = str(organization_id or "").strip()
    if not org_id:
        if required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization selected.",
            )
        return False
    # The asserted tenant narrows RLS visibility; the live membership query
    # remains the authorization decision and rejects a forged JWT claim.
    await bind_tenant_to_transaction(db, org_id)
    membership = (
        await db.execute(
            select(OrganizationMember.id)
            .join(
                Organization,
                Organization.id == OrganizationMember.organization_id,
            )
            .where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
                Organization.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization membership required",
            )
        return False
    return True


def hash_password(password: str) -> str:
    """Hash password using bcrypt (production default)."""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _needs_rehash(hashed_password: str) -> bool:
    """Check if a password hash should be upgraded to bcrypt."""
    return hashed_password.startswith("$sha256$")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored hash. Supports bcrypt ($2b$/$2a$) and legacy SHA-256."""
    try:
        if hashed_password.startswith("$sha256$"):
            parts = hashed_password.split("$")
            if len(parts) >= 4:
                salt = parts[2]
                stored_hash = parts[3]
                computed_hash = hashlib.sha256(f"{salt}{plain_password}".encode()).hexdigest()
                return hmac.compare_digest(computed_hash, stored_hash)
        elif hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
            import bcrypt
            return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        return False
    except Exception:
        return False


def create_access_token(user_id: str, username: str, role: str, org_id: str = "", token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "org_id": org_id,
        "token_version": token_version,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str, org_id: str = "", token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "token_version": token_version,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_delegation_token(
    user_id: str,
    username: str,
    agent_id: str,
    agent_account_id: str,
    scopes: list[str] | None = None,
    org_id: str = "",
) -> str:
    """Create a delegation JWT — user delegates authority to an Agent.

    This JWT carries both user identity (who authorized) and agent identity
    (which Agent is executing). External systems verify this token to audit:
    "User X via Agent Y performed operation Z."
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)  # Short-lived
    payload = {
        "sub": user_id,
        "username": username,
        "agent": agent_id,
        "agent_account_id": agent_account_id,
        "scopes": scopes or [],
        "org_id": org_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "delegation",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    # B-007 fix: Console preview iframe exchanges a Bootstrap Ticket for a
    # Runtime Token (trace_token format: payload.signature, 2 segments,
    # type='rt'). The widget then uses it as a Bearer for
    # /api/v1/agents/{id}/run. PyJWT expects 3 segments and raises
    # "Not enough segments" — route 2-segment tokens through
    # verify_runtime_token and translate to a JWT-like payload so the
    # rest of the auth pipeline (get_current_user_or_oauth_client,
    # get_current_organization) works unchanged.
    if token and token.count(".") == 1:
        from app.services.preview_ticket import verify_runtime_token, PreviewTicketError
        try:
            claims = verify_runtime_token(token)
        except PreviewTicketError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid runtime token: {e}",
            )
        return {
            "type": "runtime_token",
            "sub": claims.get("u") or None,
            "org_id": claims.get("o") or None,
            "scopes": claims.get("c") or [],
            "exp": claims.get("e"),
            "preview_session_id": claims.get("s"),
        }
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please provide a valid Bearer token.",
        )
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token required",
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")
    # Check token_version: if user's tokens have been revoked, reject
    token_version = payload.get("token_version", 0)
    if user.token_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked. Please re-authenticate.")
    await _bind_live_user_membership(
        db,
        user_id=user.id,
        organization_id=payload.get("org_id"),
    )
    return user


async def get_current_organization(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from JWT token. Requires valid org_id in token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    payload = decode_token(credentials.credentials)
    token_type = payload.get("type")
    if token_type not in {"access", "runtime_token", "client_credentials"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Organization access token required",
        )
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No organization selected. Please select or create an organization.",
        )

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if not org.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is suspended")

    # An org_id claim is context, not proof of tenant membership. Binding it
    # first only narrows RLS visibility; the checks below remain authoritative.
    await bind_tenant_to_transaction(db, org.id)

    # Validate the
    # principal here so organization-only dependencies cannot be used after
    # membership removal or with a refresh token.
    if token_type in {"access", "runtime_token"}:
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        if token_type == "access" and user.token_version != payload.get("token_version", 0):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked. Please re-authenticate.")
        membership_result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user_id,
            )
        )
        if membership_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization membership required")
    else:
        client = await get_current_client(credentials, db)
        if client.get("org_id") != org.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context mismatch")
    return org


async def require_org_membership(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> OrganizationMember:
    """Verify current user is a member of the current organization."""
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == current_org.id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return member


def require_org_role(*roles: str):
    """Dependency factory: require specific org role(s)."""
    async def checker(
        current_user: User = Depends(get_current_user),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationMember:
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == current_org.id,
                OrganizationMember.user_id == current_user.id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None or member.role.value not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of these organization roles: {', '.join(roles)}",
            )
        return member
    return checker


async def get_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get current authenticated OAuth client from client_credentials token.

    Returns dict with client_id, scopes, owner_id, org_id for M2M auth.
    Falls back to user auth if token type is not client_credentials.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    token_type = payload.get("type")
    if token_type != "client_credentials":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Client credentials required")

    # Verify token hasn't been revoked and still belongs to the asserted
    # tenant. JWT claims are attribution hints; the current database rows are
    # the authority for client state, owner and scopes.
    import hashlib
    from app.models.oauth import OAuthClient
    from app.services.oauth_delegation import (
        OAuthDelegationValidationError,
        normalize_agent_grants,
        normalize_purpose_grants,
    )

    client_id = str(payload.get("sub") or "")
    org_id = str(payload.get("org_id") or "")
    owner_id = str(payload.get("owner_id") or "")
    if not client_id or not org_id or not owner_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credential attribution",
        )
    # Enter the asserted tenant before touching protected OAuth state. The
    # token/client/owner checks below prove whether that assertion is valid.
    await bind_tenant_to_transaction(db, org_id)
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.token_hash == token_hash,
            OAuthToken.is_revoked == False,
            OAuthToken.client_id == client_id,
            OAuthToken.organization_id == org_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    client = (
        await db.execute(
            select(OAuthClient).where(
                OAuthClient.client_id == client_id,
                OAuthClient.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if client is None or not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Client is disabled or unavailable",
        )
    if client.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Client owner attribution mismatch",
        )
    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Delegated subject is inactive",
        )
    membership = (
        await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == owner_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Delegated subject organization membership required",
        )
    token_scopes = {
        str(item).strip()
        for item in (payload.get("scopes") or "").split()
        if str(item).strip()
    }
    current_scopes = client.granted_scopes()
    if not token_scopes.issubset(current_scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "CLIENT_SCOPE_REVOKED",
                "revoked_scopes": sorted(token_scopes - current_scopes),
            },
        )

    try:
        allowed_agent_ids = normalize_agent_grants(
            list(client.allowed_agent_ids or [])
        )
        allowed_purposes = normalize_purpose_grants(
            list(client.allowed_purposes or [])
        )
    except OAuthDelegationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLIENT_DELEGATION_INVALID"},
        ) from exc

    return {
        "client_id": client_id,
        "scopes": sorted(token_scopes),
        "owner_id": owner_id,
        "delegated_subject_id": owner_id,
        "org_id": org_id,
        "allowed_agent_ids": allowed_agent_ids,
        "allowed_purposes": allowed_purposes,
        "token_type": "client_credentials",
    }


async def get_current_user_or_oauth_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> tuple[Optional[User], Optional[dict]]:
    """Phase 7 Gate 12 — hybrid auth for partner-invoke routes.

    Partner HIS/EMR backends exchange ``client_credentials`` for a token
    and pass it to the browser widget. The widget then calls
    ``POST /api/v1/agents/{id}/run`` with that token. This dependency
    accepts BOTH user JWTs (Console flow) and client_credentials tokens
    (partner flow), returning ``(user, client)`` — exactly one will be
    non-None.

    Routes using this dependency must read identity from whichever value
    is set. ``get_current_organization_compat`` below resolves org_id
    from either side.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please provide a valid Bearer token.",
        )
    payload = decode_token(credentials.credentials)
    token_type = payload.get("type")

    if token_type == "client_credentials":
        # Reuse the existing client auth path (checks revocation, returns dict).
        client = await get_current_client(credentials, db)
        return None, client

    if token_type == "runtime_token":
        # B-007 fix: Console preview iframe Runtime Token (Bootstrap Ticket
        # exchange). Identity is the Console user who triggered the preview;
        # scopes are limited to agents:run / runs:read / traces:read /
        # contexts:write and expire in 10min. Skip token_version check —
        # Runtime Token is itself HMAC-signed + short-lived, so it does
        # not need the long-lived JWT revocation gate.
        user_id = payload.get("sub")
        user = None
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")
            await _bind_live_user_membership(
                db,
                user_id=user_id,
                organization_id=payload.get("org_id"),
                required=True,
            )
        return user, {
            "type": "runtime_token",
            "token_type": "runtime_token",
            "preview_session_id": payload.get("preview_session_id"),
            "scopes": payload.get("scopes") or [],
            "organization_id": payload.get("org_id"),
            "org_id": payload.get("org_id") or "",
            "user_id": user_id,
            # agent_run.py partner path reads client_id for audit; use a
            # sentinel so the preview-session origin shows up in run rows
            # without colliding with real API Client IDs.
            "client_id": f"console-preview:{payload.get('preview_session_id') or 'unknown'}",
        }

    if token_type != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required")

    # User JWT path — same logic as get_current_user.
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")
    token_version = payload.get("token_version", 0)
    if user.token_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked. Please re-authenticate.")
    await _bind_live_user_membership(
        db,
        user_id=user.id,
        organization_id=payload.get("org_id"),
    )
    return user, None


def require_scopes(*required_scopes: str):
    """Dependency factory that enforces token-side scope grants.

    Corti parity (2026-06-30, Phase 1.0): implements the limited-scope
    credential check documented in
    ``docs/corti-reverse-engineered/SUMMARY.md`` §13.2 — when an SDK
    requests a token with ``scope=openid transcribe``, that token must be
    rejected from any non-transcribe endpoint even if the underlying client
    has full ``api:read api:write`` grants.

    Usage::

        @router.get("/api/v2/stt/transcripts")
        async def upload_transcript(
            client: dict = Depends(require_scopes("transcribe", "api:read")),
        ):
            ...

    The token's granted scopes must intersect with the required scopes
    subset (i.e. every required scope is satisfied). A token carrying
    only ``transcribe`` will satisfy ``require_scopes("transcribe")``
    but be rejected by ``require_scopes("api:read", "transcribe")``
    because ``api:read`` is missing.
    """
    async def _checker(client: dict = Depends(get_current_client)) -> dict:
        granted = set(client.get("scopes") or [])
        missing = [s for s in required_scopes if s not in granted]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_scope",
                    "required_scopes": list(required_scopes),
                    "missing_scopes": missing,
                    "granted_scopes": sorted(granted),
                },
            )
        return client
    return _checker


# Capability-to-endpoint alias mapping. Lets handlers use friendly names like
# ``require_corti_capability("transcribe")`` without having to invent
# scope strings ad hoc. Corresponds to docs §13.2 (limited-scope credentials).
CAPABILITY_SCOPE_ALIASES: dict[str, tuple[str, ...]] = {
    "transcribe": ("transcribe",),
    "streams": ("streams",),
    "textgen": ("textgen",),
    "facts": ("facts",),
}


def require_corti_capability(capability: str):
    """Shorthand for ``require_scopes(*CAPABILITY_SCOPE_ALIASES[capability])``."""
    try:
        scopes = CAPABILITY_SCOPE_ALIASES[capability]
    except KeyError as e:
        raise ValueError(f"Unknown capability {capability!r}; expected one of {sorted(CAPABILITY_SCOPE_ALIASES)}") from e
    return require_scopes(*scopes)


# Import at bottom to avoid circular
from app.models.oauth import OAuthToken


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_coder_or_above(
    current_user: User = Depends(get_current_user),
) -> User:
    """Any authenticated user with coder role or higher."""
    return current_user
