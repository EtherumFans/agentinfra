"""OAuth 2.0 endpoints — Client Credentials + Authorization Code + PKCE.

Corti parity (2026-06-30, Phase 1.0): implements the four enforcement points
documented in ``docs/corti-reverse-engineered/SUMMARY.md`` §13.2:

1. **5-minute short-lived tokens** — ``OAUTH_CLIENT_EXPIRE_SECONDS`` config
   (default ``300``) replaces the legacy 1-hour TTL for client_credentials.
2. **Tenant-Name header enforcement** — handled by
   ``app.middleware.tenant_extractor`` (mounted in ``main.py``). The token
   endpoint itself is exempt so first-time callers can bootstrap.
3. **Capability scope intersection** — request scope must be a subset of the
   client's granted scopes (uniform across both endpoints below).
4. **Realm-based URL** — ``POST /api/oauth/realms/{realm}/token`` mirrors
   the ``https://auth.{env}.corti.app/realms/{tenant}/protocol/...`` pattern.

A1A Gate 1 Step 5 (2026-07-17): every 401 ``invalid_client`` is now
preceded by an ``api_client.authentication_rejected`` audit log entry
containing ``client_id``, ``reason``, source IP, and user-agent. Audit
failure is swallowed (never blocks the rejection).
"""
import hashlib
import base64
import logging
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Form, Request, Query
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import get_current_user
from app.models.oauth import OAuthClient, OAuthToken
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oauth", tags=["oauth"])


async def _emit_auth_rejection(
    db: AsyncSession,
    *,
    client_id: str,
    reason: str,
    request: Request | None = None,
    realm: str | None = None,
) -> None:
    """A1A Gate 1 Step 5 — record api_client.authentication_rejected audit event.

    Best-effort: if DB write fails, log the error and continue (the 401
    response MUST still be returned). Commits immediately so the audit row
    survives the HTTPException that the caller is about to raise.
    """
    try:
        ip = None
        ua = None
        if request is not None:
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")
        await log_action(
            db,
            user_id=None,
            username=None,
            action="api_client.authentication_rejected",
            resource_type="api_client",
            resource_id=client_id or None,
            details={
                "client_id": client_id or None,
                "reason": reason,
                "realm": realm,
                "endpoint": "token_endpoint" if realm is None else "realm_token_endpoint",
            },
            ip_address=ip,
            user_agent=ua,
            status="failure",
            error_message=reason,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "audit emit failed for api_client.authentication_rejected "
            "(client_id=%s reason=%s): %s",
            client_id, reason, e,
        )
        try:
            await db.rollback()
        except Exception:
            pass

# In-memory authorization code store (production: use DB)
_auth_codes: dict[str, dict] = {}


def _pkce_challenge(verifier: str) -> str:
    """Compute PKCE S256 code_challenge from code_verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _create_oauth_token(
    client_id: str,
    scopes: str,
    owner_id: str,
    expires_seconds: int,
    realm: str = "",
    org_id: str = "",
) -> str:
    """Create a JWT for OAuth client_credentials grant.

    ``realm`` is the path-based tenant slug (Corti realm-name parity) and is
    emitted both as a top-level ``realm`` claim and (when no explicit
    ``org_id`` was attached to the client) as the ``org_id`` claim so that
    downstream tenant-header cross-checks succeed.

    A unique ``jti`` (RFC 7519 §4.1.7) is included so back-to-back mints in
    the same second do not collide on the ``oauth_tokens.token_hash``
    unique constraint — the same JWT body can otherwise repeat when exp,
    iat, sub, scopes and realm all line up.
    """
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    payload = {
        "sub": client_id,
        "type": "client_credentials",
        "scopes": scopes,
        "owner_id": owner_id,
        "realm": realm,
        "org_id": org_id or realm,
        "jti": secrets.token_urlsafe(16),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _intersect_scopes(requested: str, granted: set[str]) -> str:
    """Return the subset of ``requested`` allowed by ``granted``.

    Corti-style capability scope tokens are honored when the client's
    declaration explicitly enumerates a capability (e.g. ``transcribe``).
    The intersection rule still holds: requesting ``api:read transcribe``
    against a client declared as ``transcribe`` yields only ``transcribe``.
    """
    requested_set = {s for s in (requested or "").split() if s}
    effective = sorted(requested_set & granted)
    if not effective:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_scope",
                "message": "Requested scope is not granted by this client.",
                "requested": sorted(requested_set),
                "granted": sorted(granted),
            },
        )
    return " ".join(effective)


def _default_oauth_ttl() -> int:
    """Read TTL from settings; this indirection keeps tests able to override."""
    return int(getattr(settings, "OAUTH_CLIENT_EXPIRE_SECONDS", 300) or 300)


@router.post("/token")
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(""),
    code: str = Form(""),
    code_verifier: str = Form(""),
    redirect_uri: str = Form(""),
    scope: str = Form("api:read api:write"),
    db: AsyncSession = Depends(get_db),
):
    """OAuth 2.0 Token Endpoint.

    Supports three grant types:
    - client_credentials (RFC 6749 §4.4): M2M authentication
    - authorization_code (RFC 6749 §4.1): SPA/user authentication
    - authorization_code + PKCE (RFC 7636): SPA with code challenge

    The ``Tenant-Name`` (or ``X-Tenant``) header is honored when present;
    mismatches with the bearer JWT's ``org_id`` claim return HTTP 400
    ``tenant_header_mismatch`` (see ``TenantHeaderMiddleware``).
    """
    # Find client first
    result = await db.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.is_active == True)
    )
    client = result.scalar_one_or_none()
    if not client:
        await _emit_auth_rejection(
            db, client_id=client_id, reason="client_not_found_or_inactive", request=request,
        )
        raise HTTPException(status_code=401, detail="invalid_client")

    if grant_type == "client_credentials":
        # RFC 6749 §4.4 — Client Credentials
        if not client_secret or not OAuthClient.verify_secret(client_secret, client.client_secret_hash):
            await _emit_auth_rejection(
                db, client_id=client_id, reason="secret_mismatch_or_empty", request=request,
            )
            raise HTTPException(status_code=401, detail="invalid_client")
        return await _handle_client_credentials(client, scope, db, realm="")

    elif grant_type == "authorization_code":
        # RFC 6749 §4.1 + RFC 7636 PKCE
        if not code or code not in _auth_codes:
            raise HTTPException(status_code=400, detail="invalid_grant")

        stored = _auth_codes.pop(code)

        # Verify client match
        if stored["client_id"] != client_id:
            raise HTTPException(status_code=400, detail="invalid_grant")

        # PKCE verification (if code_challenge was used)
        if stored.get("code_challenge"):
            if not code_verifier:
                raise HTTPException(status_code=400, detail="code_verifier_required")
            expected = _pkce_challenge(code_verifier)
            if expected != stored["code_challenge"]:
                raise HTTPException(status_code=400, detail="invalid_grant")

        # Generate token for the user (also uses the short-lived TTL)
        ttl = _default_oauth_ttl()
        effective_scope = _intersect_scopes(stored.get("scope", scope), client.granted_scopes())
        access_token = _create_oauth_token(
            client_id, effective_scope, client.owner_id, ttl
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "scope": effective_scope,
            "refresh_token": secrets.token_urlsafe(32),  # For SPA refresh
        }

    raise HTTPException(status_code=400, detail="unsupported_grant_type")


# === Realm-based token URL (Corti parity) =====================================
# https://auth.{env}.corti.app/realms/{tenant}/protocol/openid-connect/token
# iCoDer parity exposes the same pattern under
# ``/api/oauth/realms/{realm}/token``. The realm is recorded on the token
# (claim ``realm`` plus ``org_id``) so subsequent API calls can be matched
# against the ``Tenant-Name`` header without an extra DB hop.


@router.post("/realms/{realm}/token")
async def realm_token_endpoint(
    realm: str,
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(""),
    scope: str = Form("api:read api:write"),
    db: AsyncSession = Depends(get_db),
):
    """OAuth 2.0 Token Endpoint, realm-routed (Corti parity).

    The ``realm`` path parameter is the tenant slug (e.g. ``base`` or a custom
    hospital slug). The token is minted with ``realm`` recorded as both the
    ``realm`` and ``org_id`` claims so that the resulting bearer can be
    cross-checked against the ``Tenant-Name`` header on protected endpoints.
    """
    if not realm or not realm.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid_realm")

    result = await db.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.is_active == True)
    )
    client = result.scalar_one_or_none()
    if not client:
        await _emit_auth_rejection(
            db, client_id=client_id, reason="client_not_found_or_inactive",
            request=request, realm=realm,
        )
        raise HTTPException(status_code=401, detail="invalid_client")

    if grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="realm_token_supports_client_credentials_only")

    if not client_secret or not OAuthClient.verify_secret(client_secret, client.client_secret_hash):
        await _emit_auth_rejection(
            db, client_id=client_id, reason="secret_mismatch_or_empty",
            request=request, realm=realm,
        )
        raise HTTPException(status_code=401, detail="invalid_client")

    return await _handle_client_credentials(client, scope, db, realm=realm)


@router.get("/realms/{realm}/.well-known/openid-configuration")
async def realm_discovery(realm: str):
    """Discovery doc scaffold for the realm-routed endpoint (Corti parity).

    Mirrors the URL of https://auth.{env}.corti.app/realms/{tenant}/.well-known/openid-configuration
    — even when only client_credentials is implemented locally, returning the
    shape lets SDKs pre-fetch the endpoint without branching on auth mode.
    """
    if not realm:
        raise HTTPException(status_code=400, detail="invalid_realm")
    return {
        "issuer": f"local://icoder/realms/{realm}",
        "token_endpoint": f"/api/oauth/realms/{realm}/token",
        "revocation_endpoint": "/api/oauth/token/revoke",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "scopes_supported": sorted({"api:read", "api:write", *getattr(settings, "OAUTH_CAPABILITY_SCOPES", [])}),
    }


@router.get("/authorize")
async def authorize_endpoint(
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "api:read",
    code_challenge: str = "",  # PKCE S256
    code_challenge_method: str = "S256",
    state: str = "",
):
    """OAuth 2.0 Authorization Endpoint.

    For SPAs: redirects user to login, then back with authorization code.
    PKCE: client sends code_challenge, later exchanges code with code_verifier.
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")

    # Generate authorization code
    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # In production, redirect to a login page. Here we return the code directly.
    redirect = f"{redirect_uri or '/callback'}?code={code}"
    if state:
        redirect += f"&state={state}"

    return {
        "authorization_code": code,
        "redirect": redirect,
        "expires_in": 600,  # 10 minutes
        "pkce_enabled": bool(code_challenge),
    }


async def _handle_client_credentials(
    client: OAuthClient, scope: str, db: AsyncSession, realm: str = "",
) -> dict:
    """Internal: handle client_credentials grant.

    Resolves the effective token TTL from the request (when the caller asks
    for a specific lifetime via the per-client ``token_expires_seconds``
    override) or falls back to the global ``OAUTH_CLIENT_EXPIRE_SECONDS``
    config (5-minute default — Corti parity). The requested scope is
    intersected with the client's granted scopes so that
    ``scope=transcribe`` against a client declared as ``api:read api:write``
    fails with ``invalid_scope`` rather than minting an over-broad token.
    """
    effective_scope = _intersect_scopes(scope, client.granted_scopes())
    # Per-client override wins when explicitly smaller; otherwise default.
    per_client = int(client.token_expires_seconds or _default_oauth_ttl())
    ttl = min(per_client, _default_oauth_ttl()) if per_client > 0 else _default_oauth_ttl()

    access_token = _create_oauth_token(
        client.client_id,
        effective_scope,
        client.owner_id,
        ttl,
        realm=realm,
        org_id=client.organization_id or "",
    )
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    db.add(
        OAuthToken(
            client_id=client.client_id,
            token_hash=token_hash,
            scopes=effective_scope,
            expires_at=expires_at,
            organization_id=client.organization_id,
        )
    )
    client.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": ttl,
        "scope": effective_scope,
        "realm": realm or None,
    }


@router.post("/clients")
async def create_client(
    name: str = Form(...),
    description: str = Form(""),
    scopes: str = Form("api:read api:write"),
    token_expires_seconds: int | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new OAuth 2.0 client (requires user auth).

    ``token_expires_seconds`` is optional — when omitted, the global
    ``OAUTH_CLIENT_EXPIRE_SECONDS`` config (5-minute Corti-parity default)
    is used. Callers may explicitly set a longer TTL only when the value is
    not larger than the config ceiling.
    """
    client_id = OAuthClient.generate_client_id()
    secret_plaintext, secret_hash = OAuthClient.generate_client_secret()

    default_ttl = _default_oauth_ttl()
    if token_expires_seconds is None:
        effective_ttl = default_ttl
    else:
        # Cap to config ceiling — never silently leak 8h tokens from a stale
        # client form.
        effective_ttl = min(int(token_expires_seconds), default_ttl) if int(token_expires_seconds) > 0 else default_ttl

    client = OAuthClient(
        name=name,
        client_id=client_id,
        client_secret_hash=secret_hash,
        description=description,
        scopes=scopes,
        owner_id=current_user.id,
        token_expires_seconds=effective_ttl,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)

    return {
        "id": client.id,
        "name": client.name,
        "client_id": client.client_id,
        "client_secret": secret_plaintext,  # Only returned once!
        "description": client.description,
        "scopes": client.scopes,
        "token_expires_seconds": client.token_expires_seconds,
        "created_at": client.created_at.isoformat(),
    }


@router.get("/clients")
async def list_clients(
    include_disabled: bool = Query(
        True,
        description="Include disabled (is_active=False) clients in the response. "
                    "Default True so Console can render the disabled badge + re-enable "
                    "action. Pass ?include_disabled=false for partner-facing listings.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List OAuth clients for the current user.

    B-005 follow-up: previously this endpoint filtered ``is_active == True``
    unconditionally, so once a client was disabled it disappeared from Console.
    The frontend (APIClientsPage.tsx:180-181) already had a disabled badge
    ready, but the backend hid the row — making the only re-enable path a
    direct DB UPDATE. Now we surface disabled clients by default so the
    Console can show them with their badge + enable action.
    """
    filters = [OAuthClient.owner_id == current_user.id]
    if not include_disabled:
        filters.append(OAuthClient.is_active == True)
    result = await db.execute(
        select(OAuthClient).where(*filters).order_by(OAuthClient.created_at.desc())
    )
    clients = result.scalars().all()
    return {
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "client_id": c.client_id,
                "description": c.description,
                "scopes": c.scopes,
                "is_active": c.is_active,
                "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
                "created_at": c.created_at.isoformat(),
            }
            for c in clients
        ]
    }


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an OAuth client."""
    result = await db.execute(
        select(OAuthClient).where(
            OAuthClient.client_id == client_id,
            OAuthClient.owner_id == current_user.id,
        )
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = False
    await db.commit()
    return {"status": "revoked"}


@router.post("/token/revoke")
async def revoke_token(
    token: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an access token (RFC 7009)."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.token_hash == token_hash,
            OAuthToken.is_revoked == False,
        )
    )
    oauth_token = result.scalar_one_or_none()
    if oauth_token:
        oauth_token.is_revoked = True
        await db.commit()
    return {"status": "revoked"}
