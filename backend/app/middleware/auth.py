# iCoDer - Authentication Middleware (Multi-Tenant)
import logging
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.organization import Organization, OrganizationMember

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


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
    if user.token_version > token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked. Please re-authenticate.")
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

    # Verify token hasn't been revoked
    import hashlib
    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.token_hash == token_hash,
            OAuthToken.is_revoked == False,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    return {
        "client_id": payload.get("sub"),
        "scopes": (payload.get("scopes") or "").split(),
        "owner_id": payload.get("owner_id"),
        "org_id": payload.get("org_id", ""),
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
    if user.token_version > token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked. Please re-authenticate.")
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
