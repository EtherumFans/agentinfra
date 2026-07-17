"""Platform API Clients API — Phase 7 Gate 5 §10.2 partner CRUD.

Real implementation replacing the Phase 1 cloud-flip stub. Partners
(Tenant admins) use these endpoints to:

  - Create an OAuth client (returns plaintext secret ONCE)
  - List / view clients in their organization
  - Disable / enable a client (immediate revocation on disable)
  - Rotate the secret (old hash replaced; old tokens invalidated on
    next refresh — RFC 6749 doesn't auto-revoke issued tokens, but
    short 5-min TTL bounds the blast radius)
  - Update granted scopes
  - Configure allowed_origins (Phase 7 §11.1 — exact Origin strings,
    no wildcard, exact match enforced at request time)
  - Test connection (validates the client can mint a token)

§10.3 Secret rules (enforced here):
  - Plaintext shown ONLY on create/rotate response
  - DB stores sha256(client_secret) — never the plaintext
  - Endpoint responses never echo the secret back
  - Disable flips is_active=False; subsequent /token calls return 401

§10.4 Scope enforcement: not done here — done in agent_run / runs /
trace endpoints via the get_current_oauth_client dependency that
checks the JWT's scopes claim against the required scope.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.oauth import OAuthClient
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["phase7-api-clients"])


# ── Request / response schemas ─────────────────────────────────────


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    scopes: str = "agents:run runs:read traces:read usage:read"
    allowed_origins: list[str] = Field(
        default_factory=list,
        description=(
            "Exact Origin strings permitted to embed this client's "
            "widget. No wildcards (Phase 7 §11.1)."
        ),
    )
    embedded_app_id: Optional[str] = None
    token_expires_seconds: int = Field(default=300, ge=60, le=3600)


class ClientUpdateScopes(BaseModel):
    scopes: str = Field(..., description="Space-separated scope list.")


class ClientUpdateOrigins(BaseModel):
    allowed_origins: list[str] = Field(
        ..., description="Exact Origin strings. Empty list = deny all embeds.",
    )


class ClientRotate(BaseModel):
    """Rotate the client secret. The response carries the new plaintext
    secret exactly once."""


class ClientSummary(BaseModel):
    """Public view of an OAuthClient. Never includes the secret hash."""
    client_id: str
    name: str
    description: str
    scopes: str
    is_active: bool
    organization_id: Optional[str]
    owner_id: str
    last_used_at: Optional[datetime]
    allowed_origins: list[str]
    embedded_app_id: Optional[str]
    token_expires_seconds: int
    created_at: datetime
    updated_at: datetime


class ClientCreateResponse(ClientSummary):
    """Create + Rotate responses carry the plaintext secret ONCE.

    §10.3: the partner MUST capture this immediately — it is never
    retrievable again. Front-end MUST NOT save it to localStorage
    (Phase 7 §11.3 / §10.3).
    """
    client_secret: str = Field(
        ..., description="Plaintext secret — shown ONCE. Store in a secret manager.",
    )
    secret_shown_at: datetime


class ClientTestResponse(BaseModel):
    """POST /api/clients/{id}/test result."""
    ok: bool
    client_id: str
    is_active: bool
    granted_scopes: list[str]
    message: str


# ── Helpers ────────────────────────────────────────────────────────


_VALID_SCOPES = {
    "agents:run", "runs:read", "traces:read", "usage:read",
    "contexts:write", "cdi:run", "medical-coding:run", "drg-dip:run",
    # Legacy / capability scopes (kept for backward compat with Phase 1.0 clients):
    "api:read", "api:write",
    "transcribe", "streams", "textgen", "facts", "openid",
}


def _validate_scopes(scopes: str) -> str:
    """Reject unknown scopes — typo protection (§10.4)."""
    parts = [s for s in (scopes or "").split() if s]
    unknown = [s for s in parts if s not in _VALID_SCOPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNKNOWN_SCOPE",
                "message": f"Unknown scope(s): {unknown}. Allowed: {sorted(_VALID_SCOPES)}",
                "unknown": unknown,
                "allowed": sorted(_VALID_SCOPES),
            },
        )
    return " ".join(parts)


def _validate_origins(origins: list[str]) -> list[str]:
    """Phase 7 §11.1: exact Origin strings, no wildcards."""
    cleaned: list[str] = []
    for o in origins or []:
        if not isinstance(o, str):
            raise HTTPException(
                status_code=400,
                detail={"code": "BAD_ORIGIN", "message": f"Origin must be string: {o!r}"},
            )
        o = o.strip()
        if not o:
            continue
        if o == "*":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "WILDCARD_ORIGIN_FORBIDDEN",
                    "message": (
                        "Wildcard '*' is forbidden when client_credentials "
                        "is enabled (Phase 7 §11.1)."
                    ),
                },
            )
        if not (o.startswith("http://") or o.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "BAD_ORIGIN",
                    "message": f"Origin must include scheme (http/https): {o!r}",
                },
            )
        cleaned.append(o)
    return cleaned


def _to_summary(c: OAuthClient) -> ClientSummary:
    return ClientSummary(
        client_id=c.client_id,
        name=c.name,
        description=c.description or "",
        scopes=c.scopes or "",
        is_active=bool(c.is_active),
        organization_id=c.organization_id,
        owner_id=c.owner_id,
        last_used_at=c.last_used_at,
        allowed_origins=list(c.allowed_origins or []),
        embedded_app_id=c.embedded_app_id,
        token_expires_seconds=int(c.token_expires_seconds or 300),
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _get_owned(
    db: AsyncSession, *, client_id: str, org_id: str,
) -> OAuthClient:
    """Fetch a client scoped to the current org; 404 if not found or
    cross-org (don't leak existence)."""
    stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
    result = await db.execute(stmt)
    c = result.scalars().one_or_none()
    if c is None or (c.organization_id and org_id and c.organization_id != org_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "CLIENT_NOT_FOUND", "message": f"Client {client_id} not found."},
        )
    return c


# ── CRUD endpoints ─────────────────────────────────────────────────


@router.get("", response_model=list[ClientSummary], operation_id="phase7_list_api_clients")
async def list_clients(
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> list[ClientSummary]:
    """List all API Clients in the current organization (§10.2)."""
    stmt = (
        select(OAuthClient)
        .where(OAuthClient.organization_id == current_org.id)
        .order_by(OAuthClient.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_to_summary(c) for c in result.scalars().all()]


@router.post(
    "",
    response_model=ClientCreateResponse,
    operation_id="phase7_create_api_client",
    status_code=201,
)
async def create_client(
    body: ClientCreate,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientCreateResponse:
    """Create an API Client (§10.2). Returns the plaintext secret ONCE.

    §10.3: the secret is shown only here. The DB stores sha256(secret).
    Front-end MUST NOT save it to localStorage (Phase 7 §11.3).
    """
    scopes = _validate_scopes(body.scopes)
    origins = _validate_origins(body.allowed_origins)
    client_id = OAuthClient.generate_client_id("icoder")
    plaintext, secret_hash = OAuthClient.generate_client_secret()
    owner_id = str(getattr(current_user, "id", "") or "")
    client = OAuthClient(
        organization_id=current_org.id,
        name=body.name.strip(),
        client_id=client_id,
        client_secret_hash=secret_hash,
        description=body.description or "",
        scopes=scopes,
        is_active=True,
        owner_id=owner_id,
        token_expires_seconds=int(body.token_expires_seconds),
        allowed_origins=origins,
        embedded_app_id=body.embedded_app_id,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    logger.info(
        "phase7: API Client created client_id=%s org=%s owner=%s scopes=%s origins=%d",
        client_id, current_org.id, owner_id, scopes, len(origins),
    )
    base = _to_summary(client)
    return ClientCreateResponse(
        **base.model_dump(),
        client_secret=plaintext,
        secret_shown_at=datetime.now(timezone.utc),
    )


@router.get(
    "/{client_id}",
    response_model=ClientSummary,
    operation_id="phase7_get_api_client",
)
async def get_client(
    client_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    """View one API Client (§10.2). Never returns the secret."""
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    return _to_summary(c)


@router.post(
    "/{client_id}/disable",
    response_model=ClientSummary,
    operation_id="phase7_disable_api_client",
)
async def disable_client(
    client_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    """Disable a client (§10.2 + §10.3 immediate-revoke rule).

    Flips ``is_active=False``; the /token endpoint will reject future
    token requests. Issued tokens remain valid until their 5-min TTL
    expires (RFC 6749 doesn't auto-revoke)."""
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    c.is_active = False
    await db.commit()
    await db.refresh(c)
    logger.info("phase7: API Client disabled client_id=%s", client_id)
    return _to_summary(c)


@router.post(
    "/{client_id}/enable",
    response_model=ClientSummary,
    operation_id="phase7_enable_api_client",
)
async def enable_client(
    client_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    """Re-enable a disabled client (§10.2)."""
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    c.is_active = True
    await db.commit()
    await db.refresh(c)
    logger.info("phase7: API Client enabled client_id=%s", client_id)
    return _to_summary(c)


@router.post(
    "/{client_id}/rotate",
    response_model=ClientCreateResponse,
    operation_id="phase7_rotate_api_client_secret",
)
async def rotate_secret(
    client_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientCreateResponse:
    """Rotate the client secret (§10.3). Returns the new plaintext ONCE.

    The previous hash is replaced. Old tokens remain valid until their
    short TTL expires; partners using the old secret will get 401 on
    their next /token refresh. Recommended rotation cadence: 90 days.
    """
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    plaintext, secret_hash = OAuthClient.generate_client_secret()
    c.client_secret_hash = secret_hash
    await db.commit()
    await db.refresh(c)
    logger.info("phase7: API Client secret rotated client_id=%s", client_id)
    base = _to_summary(c)
    return ClientCreateResponse(
        **base.model_dump(),
        client_secret=plaintext,
        secret_shown_at=datetime.now(timezone.utc),
    )


@router.patch(
    "/{client_id}/scopes",
    response_model=ClientSummary,
    operation_id="phase7_update_api_client_scopes",
)
async def update_scopes(
    client_id: str,
    body: ClientUpdateScopes,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    """Update granted scopes (§10.2 + §10.4 — actually enforced)."""
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    c.scopes = _validate_scopes(body.scopes)
    await db.commit()
    await db.refresh(c)
    return _to_summary(c)


@router.patch(
    "/{client_id}/allowed-origins",
    response_model=ClientSummary,
    operation_id="phase7_update_api_client_origins",
)
async def update_origins(
    client_id: str,
    body: ClientUpdateOrigins,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientSummary:
    """Update allowed Origins for embedded widget embedding (§11.1)."""
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    c.allowed_origins = _validate_origins(body.allowed_origins)
    await db.commit()
    await db.refresh(c)
    return _to_summary(c)


@router.post(
    "/{client_id}/test",
    response_model=ClientTestResponse,
    operation_id="phase7_test_api_client",
)
async def test_connection(
    client_id: str,
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ClientTestResponse:
    """Test connection (§10.2). Returns ok=True iff the client exists,
    is active, and has at least one granted scope.

    This does NOT mint a token (that would require the secret). It's a
    quick "is this client configured correctly" probe for the UI.
    """
    c = await _get_owned(db, client_id=client_id, org_id=current_org.id)
    granted = sorted(c.granted_scopes())
    return ClientTestResponse(
        ok=bool(c.is_active and granted),
        client_id=c.client_id,
        is_active=bool(c.is_active),
        granted_scopes=granted,
        message=(
            "Client is active and has scopes." if c.is_active and granted
            else "Client is disabled." if not c.is_active
            else "Client has no granted scopes."
        ),
    )


__all__ = ["router"]
