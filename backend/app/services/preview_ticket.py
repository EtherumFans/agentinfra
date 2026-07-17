"""Phase 7 Gate 13A-1 — Preview Bootstrap Ticket.

Short-lived HMAC-signed ticket that the Console issues and the iframe
exchanges for a scoped Runtime Token. Per Gate 13A architecture
(reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md):

- Ticket TTL = 60 seconds (compared to TraceToken's 24h)
- Single-use: marked EXCHANGED in DB on first successful exchange;
  replay attempts return TICKET_ALREADY_USED
- Bound to (preview_session_id, organization_id, user_id,
  expected_parent_origin, nonce, jti)
- Constant-time signature comparison via secrets.compare_digest

Ticket format (URL-safe base64 of JSON ``{v,s,o,u,p,n,j,e}``):
- ``v``  → token_version, currently 1
- ``s``  → preview_session_id (opaque UUID; appears in iframe URL)
- ``o``  → organization_id
- ``u``  → user_id
- ``p``  → expected_parent_origin (Console origin)
- ``f``  → expected_iframe_origin (backend origin)
- ``n``  → nonce (random hex; MessageChannel handshake proof)
- ``j``  → jti (unique per ticket)
- ``e``  → exp epoch seconds
- ``a``  → allowed_agent_ids list (empty = all)
- ``c``  → allowed_scopes list

Signature: HMAC-SHA256 of payload_b64, base64url, appended after ``.``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings


# ── public constants ────────────────────────────────────────────────

DEFAULT_TTL_SECONDS = 60  # PDF §3 specifies 30–60s; we use the upper bound
RUNTIME_TOKEN_TTL_SECONDS = 10 * 60  # 10 minutes
TOKEN_VERSION = 1


class PreviewTicketError(Exception):
    """Base for all preview ticket verification failures."""


class PreviewTicketExpired(PreviewTicketError):
    pass


class PreviewTicketInvalidSignature(PreviewTicketError):
    pass


class PreviewTicketMalformed(PreviewTicketError):
    pass


class PreviewTicketOriginMismatch(PreviewTicketError):
    """Ticket bound to a different parent origin."""


class PreviewTicketNonceMismatch(PreviewTicketError):
    """Ticket bound to a different nonce."""


# ── internals ───────────────────────────────────────────────────────


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret_bytes() -> bytes:
    """HMAC key — derived from settings.SECRET_KEY (SHA-256 for fixed length)."""
    raw = (settings.SECRET_KEY or "").encode("utf-8") or b"icoder-preview-fallback"
    # Domain-separate from trace_token key by prefixing (prevents cross-use).
    return hashlib.sha256(b"icoder-preview-ticket|" + raw).digest()


def _sign(payload_b64: str) -> str:
    mac = hmac.new(_secret_bytes(), payload_b64.encode("ascii"), hashlib.sha256)
    return _b64url_encode(mac.digest())


# ── public API ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreviewTicketClaims:
    preview_session_id: str
    organization_id: str
    user_id: str
    expected_parent_origin: str
    expected_iframe_origin: str
    nonce: str
    jti: str
    exp: int  # epoch seconds
    allowed_agent_ids: list = field(default_factory=list)
    allowed_scopes: list = field(default_factory=lambda: ["agents:run", "runs:read", "traces:read", "contexts:write"])


def generate_nonce() -> str:
    """Random 16-byte hex nonce for MessageChannel handshake proof."""
    return secrets.token_hex(16)


def generate_preview_session_id() -> str:
    """Random opaque UUID-like ID for the iframe URL (NOT a JWT)."""
    return secrets.token_urlsafe(24)


def generate_jti() -> str:
    """Random JWT ID for the ticket."""
    return secrets.token_urlsafe(16)


def issue_preview_ticket(
    *,
    preview_session_id: str,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
    expected_parent_origin: str,
    expected_iframe_origin: str,
    nonce: str,
    jti: Optional[str] = None,
    allowed_agent_ids: Optional[list] = None,
    allowed_scopes: Optional[list] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Issue an HMAC-signed Preview Bootstrap Ticket.

    The ticket grants the iframe the right to exchange for a scoped
    Runtime Token within ``ttl_seconds`` (default 60s). Bound to
    (preview_session_id, organization_id, user_id, parent_origin, nonce).
    """
    if not preview_session_id:
        raise ValueError("preview_session_id is required")
    if not expected_parent_origin or not expected_iframe_origin:
        raise ValueError("expected_parent_origin and expected_iframe_origin are required")
    if not nonce:
        raise ValueError("nonce is required")

    now = int(time.time())
    payload = {
        "v": TOKEN_VERSION,
        "s": preview_session_id,
        "o": organization_id or "",
        "u": user_id or "",
        "p": expected_parent_origin,
        "f": expected_iframe_origin,
        "n": nonce,
        "j": jti or generate_jti(),
        "e": now + int(ttl_seconds),
        "a": allowed_agent_ids or [],
        "c": allowed_scopes or ["agents:run", "runs:read", "traces:read", "contexts:write"],
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_preview_ticket(
    token: str,
    *,
    expected_parent_origin: Optional[str] = None,
    expected_iframe_origin: Optional[str] = None,
    expected_nonce: Optional[str] = None,
) -> PreviewTicketClaims:
    """Verify a preview ticket's signature, expiry, origin, and nonce.

    Raises ``PreviewTicketMalformed`` if the format is wrong,
    ``PreviewTicketInvalidSignature`` if the signature doesn't match,
    ``PreviewTicketExpired`` if past exp,
    ``PreviewTicketOriginMismatch`` / ``PreviewTicketNonceMismatch`` if
    bound to a different identifier than expected.
    """
    if not token or "." not in token:
        raise PreviewTicketMalformed("missing or malformed ticket")
    payload_b64, sig = token.rsplit(".", 1)
    expected_sig = _sign(payload_b64)
    if not secrets.compare_digest(sig, expected_sig):
        raise PreviewTicketInvalidSignature("signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as e:
        raise PreviewTicketMalformed(f"payload decode failed: {e}") from e

    if not isinstance(payload, dict):
        raise PreviewTicketMalformed("payload not a dict")
    if payload.get("v") != TOKEN_VERSION:
        raise PreviewTicketMalformed(f"unsupported ticket version {payload.get('v')!r}")

    preview_session_id = str(payload.get("s") or "")
    org_id = str(payload.get("o") or "")
    user_id = str(payload.get("u") or "")
    parent_origin = str(payload.get("p") or "")
    iframe_origin = str(payload.get("f") or "")
    nonce = str(payload.get("n") or "")
    jti = str(payload.get("j") or "")
    try:
        exp = int(payload.get("e") or 0)
    except (TypeError, ValueError):
        raise PreviewTicketMalformed("exp not an int")
    allowed_agents = payload.get("a") or []
    allowed_scopes = payload.get("c") or ["agents:run", "runs:read", "traces:read", "contexts:write"]

    if not preview_session_id or not parent_origin or not nonce or not jti:
        raise PreviewTicketMalformed("missing required claim")

    if exp <= int(time.time()):
        raise PreviewTicketExpired(f"ticket expired at {exp}")

    if expected_parent_origin is not None and parent_origin != expected_parent_origin:
        raise PreviewTicketOriginMismatch(
            f"ticket bound to parent_origin={parent_origin!r}, expected {expected_parent_origin!r}"
        )
    if expected_iframe_origin is not None and iframe_origin != expected_iframe_origin:
        raise PreviewTicketOriginMismatch(
            f"ticket bound to iframe_origin={iframe_origin!r}, expected {expected_iframe_origin!r}"
        )
    if expected_nonce is not None and nonce != expected_nonce:
        raise PreviewTicketNonceMismatch(
            f"ticket nonce={nonce!r}, expected {expected_nonce!r}"
        )

    return PreviewTicketClaims(
        preview_session_id=preview_session_id,
        organization_id=org_id,
        user_id=user_id,
        expected_parent_origin=parent_origin,
        expected_iframe_origin=iframe_origin,
        nonce=nonce,
        jti=jti,
        exp=exp,
        allowed_agent_ids=list(allowed_agents),
        allowed_scopes=list(allowed_scopes),
    )


def issue_runtime_token(
    *,
    preview_session_id: str,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
    allowed_scopes: Optional[list] = None,
    ttl_seconds: int = RUNTIME_TOKEN_TTL_SECONDS,
) -> str:
    """Issue a scoped Runtime Token after a successful ticket exchange.

    The Runtime Token is what the widget uses as its bearer token for
    `/api/v1/agents/{id}/run` etc. It's a separate signed token (not the
    Console JWT) so the iframe never sees the user's full-scope JWT.

    Token format mirrors preview_ticket but with type marker 'rt'.
    """
    now = int(time.time())
    payload = {
        "v": TOKEN_VERSION,
        "t": "rt",  # runtime token (vs 'pt' preview ticket)
        "s": preview_session_id,
        "o": organization_id or "",
        "u": user_id or "",
        "e": now + int(ttl_seconds),
        "c": allowed_scopes or ["agents:run", "runs:read", "traces:read", "contexts:write"],
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_runtime_token(token: str) -> dict:
    """Verify a Runtime Token signature and expiry. Returns claims dict."""
    if not token or "." not in token:
        raise PreviewTicketMalformed("missing or malformed runtime token")
    payload_b64, sig = token.rsplit(".", 1)
    expected_sig = _sign(payload_b64)
    if not secrets.compare_digest(sig, expected_sig):
        raise PreviewTicketInvalidSignature("runtime token signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as e:
        raise PreviewTicketMalformed(f"runtime token payload decode failed: {e}") from e

    if payload.get("v") != TOKEN_VERSION:
        raise PreviewTicketMalformed(f"unsupported runtime token version {payload.get('v')!r}")
    if payload.get("t") != "rt":
        raise PreviewTicketMalformed(f"not a runtime token (type={payload.get('t')!r})")

    try:
        exp = int(payload.get("e") or 0)
    except (TypeError, ValueError):
        raise PreviewTicketMalformed("runtime token exp not an int")
    if exp <= int(time.time()):
        raise PreviewTicketExpired(f"runtime token expired at {exp}")

    return payload
