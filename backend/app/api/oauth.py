"""OAuth 2.0 endpoints — Client Credentials + Authorization Code + PKCE"""
import hashlib
import base64
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.oauth import OAuthClient, OAuthToken
from app.models.user import User

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

# In-memory authorization code store (production: use DB)
_auth_codes: dict[str, dict] = {}


def _pkce_challenge(verifier: str) -> str:
    """Compute PKCE S256 code_challenge from code_verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _create_oauth_token(client_id: str, scopes: str, owner_id: str, expires_seconds: int) -> str:
    """Create a JWT for OAuth client_credentials grant."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    payload = {
        "sub": client_id,
        "type": "client_credentials",
        "scopes": scopes,
        "owner_id": owner_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/token")
async def token_endpoint(
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
    """
    # Find client first
    result = await db.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id, OAuthClient.is_active == True)
    )
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=401, detail="invalid_client")

    if grant_type == "client_credentials":
        # RFC 6749 §4.4 — Client Credentials
        if not client_secret or not OAuthClient.verify_secret(client_secret, client.client_secret_hash):
            raise HTTPException(status_code=401, detail="invalid_client")
        return await _handle_client_credentials(client, scope, db)

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

        # Generate token for the user
        access_token = _create_oauth_token(
            client_id, stored.get("scope", scope), client.owner_id, client.token_expires_seconds
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": client.token_expires_seconds,
            "scope": stored.get("scope", scope),
            "refresh_token": secrets.token_urlsafe(32),  # For SPA refresh
        }

    raise HTTPException(status_code=400, detail="unsupported_grant_type")


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


async def _handle_client_credentials(client: OAuthClient, scope: str, db: AsyncSession):
    """Internal: handle client_credentials grant."""
    access_token = _create_oauth_token(client.client_id, scope, client.owner_id, client.token_expires_seconds)
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=client.token_expires_seconds)
    db.add(OAuthToken(client_id=client.client_id, token_hash=token_hash, scopes=scope, expires_at=expires_at))
    client.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": client.token_expires_seconds, "scope": scope}


@router.post("/clients")
async def create_client(
    name: str = Form(...),
    description: str = Form(""),
    scopes: str = Form("api:read api:write"),
    token_expires_seconds: int = Form(3600),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new OAuth 2.0 client (requires user auth)."""
    client_id = OAuthClient.generate_client_id()
    secret_plaintext, secret_hash = OAuthClient.generate_client_secret()

    client = OAuthClient(
        name=name,
        client_id=client_id,
        client_secret_hash=secret_hash,
        description=description,
        scopes=scopes,
        owner_id=current_user.id,
        token_expires_seconds=token_expires_seconds,
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List OAuth clients for the current user."""
    result = await db.execute(
        select(OAuthClient).where(
            OAuthClient.owner_id == current_user.id,
            OAuthClient.is_active == True,
        ).order_by(OAuthClient.created_at.desc())
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
