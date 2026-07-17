"""Phase 7 Gate 13A-1 — Preview Session & Bootstrap Ticket endpoints.

Two-step handshake that replaces JWT-in-iframe-URL:

1. Console (with JWT) POSTs here to mint a 60s single-use ticket bound to
   (preview_session_id, org, user, parent_origin, iframe_origin, nonce,
   agent_allowlist, scopes). The DB row mirrors the ticket claims so we
   can revoke, mark USED, and audit.

2. iframe (no JWT) POSTs the ticket to /exchange. We verify HMAC signature,
   expiry, origin binding, nonce, AND that the DB status is PENDING.
   Atomically transition PENDING → EXCHANGED, issue a 10-minute scoped
   Runtime Token. The iframe uses the Runtime Token (not the user's JWT)
   as Bearer for /api/v1/agents/{id}/run etc.

Per reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.middleware.audit import log_action
from app.models.preview_session import PreviewSession
from app.models.user import User
from app.models.organization import Organization
from app.services.preview_ticket import (
    DEFAULT_TTL_SECONDS,
    PreviewTicketError,
    PreviewTicketExpired,
    PreviewTicketInvalidSignature,
    PreviewTicketMalformed,
    PreviewTicketNonceMismatch,
    PreviewTicketOriginMismatch,
    RUNTIME_TOKEN_TTL_SECONDS,
    generate_jti,
    generate_nonce,
    generate_preview_session_id,
    issue_preview_ticket,
    issue_runtime_token,
    verify_preview_ticket,
)


router = APIRouter(prefix="/api/embedded/preview-sessions", tags=["embedded-preview"])


_DEFAULT_SCOPES = ["agents:run", "runs:read", "traces:read", "contexts:write"]


# ── request / response schemas ────────────────────────────────────────


class PreviewSessionCreate(BaseModel):
    """Body of POST /api/embedded/preview-sessions.

    The Console sends the parent origin (its own origin) so we can bind
    the ticket to it. Patient context is NOT included — that flows via
    MessageChannel after the handshake.
    """
    expected_parent_origin: str = Field(
        ..., description="Console origin, e.g. http://localhost:3000",
    )
    allowed_agent_ids: Optional[list[str]] = Field(
        default=None, description="Agent refs to allow; empty/None = all",
    )
    allowed_scopes: Optional[list[str]] = Field(
        default=None, description="Scopes for the Runtime Token",
    )
    ttl_seconds: int = Field(
        default=DEFAULT_TTL_SECONDS, ge=5, le=300,
        description="Ticket TTL (5–300s). Default 60s per PDF §3.",
    )


class PreviewSessionResponse(BaseModel):
    preview_session_id: str
    ticket: str
    nonce: str
    expires_at: datetime
    iframe_url: str


class TicketExchangeRequest(BaseModel):
    ticket: str = Field(..., description="The HMAC-signed bootstrap ticket")


class TicketExchangeResponse(BaseModel):
    runtime_token: str
    expires_at: datetime
    preview_session_id: str
    scopes: list[str]
    token_type: str = "bearer"


class PreviewSessionStatus(BaseModel):
    preview_session_id: str
    status: str
    issued_at: datetime
    expires_at: datetime
    exchanged_at: Optional[datetime] = None
    exchanged_from_ip: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────


def _iframe_origin_from_request(request: Request) -> str:
    """The iframe is same-origin with the backend; this returns its origin."""
    # Prefer forwarded host (cloud), fall back to direct host.
    fwd = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8000"
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    return f"{scheme}://{fwd}"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── endpoints ─────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=PreviewSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Preview Session and mint a 60s bootstrap ticket",
)
async def create_preview_session(
    body: PreviewSessionCreate,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> PreviewSessionResponse:
    """Console calls this with its JWT to mint a single-use ticket.

    The ticket is bound to (org, user, parent_origin, iframe_origin,
    nonce, agent_allowlist, scopes). TTL is 60s per PDF §3.
    """
    iframe_origin = _iframe_origin_from_request(request)
    parent_origin = body.expected_parent_origin.rstrip("/")

    preview_session_id = generate_preview_session_id()
    nonce = generate_nonce()
    jti = generate_jti()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=body.ttl_seconds)

    scopes = body.allowed_scopes if body.allowed_scopes is not None else _DEFAULT_SCOPES

    # Persist DB row FIRST (jti is UNIQUE — guarantees no collision).
    session_row = PreviewSession(
        preview_session_id=preview_session_id,
        organization_id=org.id,
        user_id=user.id,
        api_client_id=None,
        expected_parent_origin=parent_origin,
        expected_iframe_origin=iframe_origin,
        nonce=nonce,
        allowed_agent_ids=body.allowed_agent_ids or [],
        allowed_scopes=scopes,
        jti=jti,
        single_use=1,
        token_version=1,
        status="PENDING",
        issued_at=now,
        expires_at=expires_at,
    )
    db.add(session_row)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="jti collision — please retry",
        ) from e

    # Now mint the HMAC-signed ticket — claims mirror the DB row.
    ticket = issue_preview_ticket(
        preview_session_id=preview_session_id,
        organization_id=org.id,
        user_id=user.id,
        expected_parent_origin=parent_origin,
        expected_iframe_origin=iframe_origin,
        nonce=nonce,
        jti=jti,
        allowed_agent_ids=body.allowed_agent_ids or [],
        allowed_scopes=scopes,
        ttl_seconds=body.ttl_seconds,
    )

    iframe_url = (
        f"{iframe_origin}/api/embedded/preview.html?psid={preview_session_id}"
    )

    # Audit: Console issued a bootstrap ticket (no PHI recorded — the
    # resource_id is the opaque preview_session_id, not the patient).
    await log_action(
        db=db,
        user_id=user.id,
        username=getattr(user, "username", None),
        action="preview_session.create",
        resource_type="preview_session",
        resource_id=preview_session_id,
        details={
            "jti": jti,
            "expected_parent_origin": parent_origin,
            "expected_iframe_origin": iframe_origin,
            "allowed_scopes": scopes,
            "allowed_agent_ids": body.allowed_agent_ids or [],
            "ttl_seconds": body.ttl_seconds,
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        organization_id=org.id,
    )
    # The create's log_action is in the same session-flush boundary;
    # commit was already done above. For safety we re-flush so the
    # audit row is persisted alongside.
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    return PreviewSessionResponse(
        preview_session_id=preview_session_id,
        ticket=ticket,
        nonce=nonce,
        expires_at=expires_at,
        iframe_url=iframe_url,
    )


@router.post(
    "/exchange",
    response_model=TicketExchangeResponse,
    summary="Exchange a bootstrap ticket for a scoped Runtime Token",
)
async def exchange_ticket(
    body: TicketExchangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TicketExchangeResponse:
    """iframe POSTs the ticket here. We verify signature, expiry, origin,
    and nonce; check the DB row is still PENDING; atomically transition
    to EXCHANGED; return a scoped 10-minute Runtime Token.

    Single-use is enforced by the status transition: a second call with
    the same ticket sees status=EXCHANGED and gets 410 TICKET_ALREADY_USED.
    """
    iframe_origin = _iframe_origin_from_request(request)
    client_ip = _client_ip(request)

    # 1. HMAC verify + expiry + origin + nonce binding
    try:
        claims = verify_preview_ticket(
            body.ticket,
            expected_iframe_origin=iframe_origin,
        )
    except PreviewTicketExpired as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"TICKET_EXPIRED: {e}",
        ) from e
    except PreviewTicketInvalidSignature as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TICKET_INVALID_SIGNATURE",
        ) from e
    except PreviewTicketOriginMismatch as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"TICKET_ORIGIN_MISMATCH: {e}",
        ) from e
    except PreviewTicketNonceMismatch as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"TICKET_NONCE_MISMATCH: {e}",
        ) from e
    except PreviewTicketMalformed as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TICKET_MALFORMED: {e}",
        ) from e
    except PreviewTicketError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TICKET_ERROR: {e}",
        ) from e

    # 2. Look up DB row by jti (the unique constraint makes this safe).
    result = await db.execute(
        select(PreviewSession).where(PreviewSession.jti == claims.jti)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # Signature verified but no DB row — either pre-migration or
        # the row was hard-deleted. Refuse.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="TICKET_NOT_FOUND: preview session not in DB",
        )

    # 3. Verify the on-the-wire claims still match the DB row.
    # Prevents a forged ticket (same jti, swapped origin) from passing.
    if row.preview_session_id != claims.preview_session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TICKET_BINDING_MISMATCH: preview_session_id",
        )
    if row.nonce != claims.nonce:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TICKET_BINDING_MISMATCH: nonce",
        )
    if row.expected_parent_origin != claims.expected_parent_origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TICKET_BINDING_MISMATCH: parent_origin",
        )

    # 4. Enforce single-use via status transition.
    if row.status == "EXCHANGED":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="TICKET_ALREADY_USED",
        )
    if row.status == "REVOKED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TICKET_REVOKED",
        )
    if row.status == "EXPIRED":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="TICKET_EXPIRED",
        )
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"TICKET_BAD_STATE: {row.status}",
        )

    # 5. Atomically transition PENDING → EXCHANGED.
    row.status = "EXCHANGED"
    row.exchanged_at = datetime.now(timezone.utc)
    row.exchanged_from_ip = client_ip
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        # Concurrent exchange races to here; re-read to confirm.
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="TICKET_ALREADY_USED (race)",
        ) from e

    # Audit: ticket successfully exchanged (no PHI).
    await log_action(
        db=db,
        user_id=row.user_id,
        username=None,
        action="preview_session.exchange",
        resource_type="preview_session",
        resource_id=row.preview_session_id,
        details={
            "jti": row.jti,
            "organization_id": row.organization_id,
            "ip": client_ip,
        },
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
        organization_id=row.organization_id,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    # 6. Mint the 10-minute Runtime Token with narrow scope.
    runtime_token = issue_runtime_token(
        preview_session_id=row.preview_session_id,
        organization_id=row.organization_id,
        user_id=row.user_id,
        allowed_scopes=row.allowed_scopes or _DEFAULT_SCOPES,
        ttl_seconds=RUNTIME_TOKEN_TTL_SECONDS,
    )

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=RUNTIME_TOKEN_TTL_SECONDS
    )

    return TicketExchangeResponse(
        runtime_token=runtime_token,
        expires_at=expires_at,
        preview_session_id=row.preview_session_id,
        scopes=list(row.allowed_scopes or _DEFAULT_SCOPES),
        token_type="bearer",
    )


@router.get(
    "/{preview_session_id}",
    response_model=PreviewSessionStatus,
    summary="Get the status of a Preview Session (no ticket, no auth)",
)
async def get_preview_session_status(
    preview_session_id: str,
    db: AsyncSession = Depends(get_db),
) -> PreviewSessionStatus:
    """Status lookup by opaque preview_session_id (NOT the jti).

    Returns no secrets — used by the Console to check whether the iframe
    exchanged the ticket yet. Statuses: PENDING, EXCHANGED, REVOKED,
    EXPIRED.
    """
    result = await db.execute(
        select(PreviewSession).where(
            PreviewSession.preview_session_id == preview_session_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PREVIEW_SESSION_NOT_FOUND",
        )
    return PreviewSessionStatus(
        preview_session_id=row.preview_session_id,
        status=row.status,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        exchanged_at=row.exchanged_at,
        exchanged_from_ip=row.exchanged_from_ip,
    )


@router.post(
    "/{preview_session_id}/revoke",
    response_model=PreviewSessionStatus,
    summary="Revoke a pending Preview Session (admin/user kill-switch)",
)
async def revoke_preview_session(
    preview_session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PreviewSessionStatus:
    """Console user revokes a session (e.g. they closed the page).

    Only the session owner or an org admin can revoke. Pending sessions
    transition to REVOKED; already-EXCHANGED sessions also get revoked
    (the Runtime Token's HMAC signature can't be unissued, but the row
    is marked and future code can refuse tokens whose DB row is REVOKED).
    """
    result = await db.execute(
        select(PreviewSession).where(
            PreviewSession.preview_session_id == preview_session_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PREVIEW_SESSION_NOT_FOUND",
        )
    # Ownership: only the original user can revoke (org admin handled elsewhere).
    if row.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="NOT_SESSION_OWNER",
        )
    if row.status in ("EXPIRED", "REVOKED"):
        # Already terminal — idempotent no-op.
        pass
    else:
        row.status = "REVOKED"
        await db.commit()
        # Audit: user revoked the session.
        await log_action(
            db=db,
            user_id=user.id,
            username=getattr(user, "username", None),
            action="preview_session.revoke",
            resource_type="preview_session",
            resource_id=row.preview_session_id,
            details={"jti": row.jti, "previous_status": "PENDING"},
            ip_address=None,
            user_agent=None,
            organization_id=row.organization_id,
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()

    return PreviewSessionStatus(
        preview_session_id=row.preview_session_id,
        status=row.status,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        exchanged_at=row.exchanged_at,
        exchanged_from_ip=row.exchanged_from_ip,
    )
