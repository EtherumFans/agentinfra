"""Phase 7 Gate 7 §12 — signed trace URL tokens.

The existing ``trace_url`` (Phase 6 Gate 5) returns a relative frontend
path ``/ai-studio/runs/{run_id}/trace``. That URL only works inside
the Console SPA (the user has to be logged in). Partners embedding the
widget don't have a Console session, so we need a way for them to
deep-link into a trace view without logging in.

This module issues HMAC-signed tokens that grant read-only access to
``GET /api/v1/runs/{run_id}/trace?token=...`` for a single ``run_id``
within a single ``organization_id``, expiring after a TTL (default 24h).

Design (§12.1-§12.4):

- The token is a URL-safe base64 string carrying ``{run_id, org_id,
  api_client_id, exp}`` plus an HMAC-SHA256 signature derived from
  ``settings.SECRET_KEY``.
- Verification is constant-time on the signature (``secrets.compare_digest``)
  to prevent timing attacks.
- Tokens are **revocable** by rotating ``SECRET_KEY`` (existing runs
  become inaccessible). We don't currently track issued tokens in the
  DB — that would let us revoke per-token, but §12 doesn't require it.
- Tokens never embed the run payload — they're just an authorization
  bearer; the actual trace events are read from the RunTraceStore on
  verification.

Token format (URL-safe base64 of JSON ``{i,r,o,c,e}``):
- ``i``  → version, currently 1
- ``r``  → run_id (string)
- ``o``  → organization_id (string; may be empty in single-tenant dev)
- ``c``  → api_client_id (string; identifies the partner who requested)
- ``e``  → exp epoch seconds (int)

Signature is HMAC-SHA256 of the payload bytes, base64url, appended
after ``.`` separator: ``<payload>.<sig>``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings


# ── public constants ────────────────────────────────────────────────

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours
TOKEN_VERSION = 1


class TraceTokenError(Exception):
    """Base for all trace token verification failures."""


class TraceTokenExpired(TraceTokenError):
    pass


class TraceTokenInvalidSignature(TraceTokenError):
    pass


class TraceTokenMalformed(TraceTokenError):
    pass


class TraceTokenRunMismatch(TraceTokenError):
    """Token is valid but was issued for a different run_id."""


class TraceTokenOrgMismatch(TraceTokenError):
    """Token is valid but was issued for a different organization."""


# ── internals ───────────────────────────────────────────────────────


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _secret_bytes() -> bytes:
    """HMAC key — derived from settings.SECRET_KEY (SHA-256 to get a
    fixed-length key regardless of input length)."""
    raw = (settings.SECRET_KEY or "").encode("utf-8") or b"icoder-trace-fallback"
    return hashlib.sha256(raw).digest()


def _sign(payload_b64: str) -> str:
    mac = hmac.new(_secret_bytes(), payload_b64.encode("ascii"), hashlib.sha256)
    return _b64url_encode(mac.digest())


# ── public API ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TraceTokenClaims:
    run_id: str
    organization_id: str
    api_client_id: str
    exp: int  # epoch seconds


def issue_trace_token(
    *,
    run_id: str,
    organization_id: Optional[str] = None,
    api_client_id: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Issue an HMAC-signed trace URL token.

    The token grants read-only access to ``GET /api/v1/runs/{run_id}/trace``
    for ``ttl_seconds`` (default 24h). The token is bound to
    ``run_id`` and ``organization_id`` — verification will reject it
    for any other run/org.
    """
    if not run_id:
        raise ValueError("run_id is required")
    now = int(time.time())
    payload = {
        "i": TOKEN_VERSION,
        "r": run_id,
        "o": organization_id or "",
        "c": api_client_id or "",
        "e": now + int(ttl_seconds),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_trace_token(
    token: str,
    *,
    expected_run_id: Optional[str] = None,
    expected_organization_id: Optional[str] = None,
) -> TraceTokenClaims:
    """Verify a trace token's signature, expiry, and (optionally)
    run_id/org binding.

    Raises ``TraceTokenMalformed`` if the format is wrong,
    ``TraceTokenInvalidSignature`` if the signature doesn't match,
    ``TraceTokenExpired`` if past exp, ``TraceTokenRunMismatch`` /
    ``TraceTokenOrgMismatch`` if bound to a different identifier than
    expected.

    Returns the decoded claims on success.
    """
    if not token or "." not in token:
        raise TraceTokenMalformed("missing or malformed token")
    payload_b64, sig = token.rsplit(".", 1)
    expected_sig = _sign(payload_b64)
    if not secrets.compare_digest(sig, expected_sig):
        raise TraceTokenInvalidSignature("signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as e:
        raise TraceTokenMalformed(f"payload decode failed: {e}") from e

    if not isinstance(payload, dict):
        raise TraceTokenMalformed("payload not a dict")
    if payload.get("i") != TOKEN_VERSION:
        raise TraceTokenMalformed(f"unsupported token version {payload.get('i')!r}")

    run_id = str(payload.get("r") or "")
    org_id = str(payload.get("o") or "")
    api_client_id = str(payload.get("c") or "")
    try:
        exp = int(payload.get("e") or 0)
    except (TypeError, ValueError):
        raise TraceTokenMalformed("exp not an int")

    if exp <= int(time.time()):
        raise TraceTokenExpired(f"token expired at {exp}")

    if expected_run_id is not None and run_id != expected_run_id:
        raise TraceTokenRunMismatch(
            f"token bound to run_id={run_id!r}, expected {expected_run_id!r}"
        )

    # Org check: only enforce if BOTH the token and the caller specify
    # an org. In single-tenant dev the org may legitimately be "".
    if (
        expected_organization_id is not None
        and org_id
        and expected_organization_id
        and org_id != expected_organization_id
    ):
        raise TraceTokenOrgMismatch(
            f"token bound to org={org_id!r}, expected {expected_organization_id!r}"
        )

    return TraceTokenClaims(
        run_id=run_id,
        organization_id=org_id,
        api_client_id=api_client_id,
        exp=exp,
    )


def build_trace_url(
    base_url: str,
    *,
    run_id: str,
    organization_id: Optional[str] = None,
    api_client_id: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Compose the full partner-accessible trace URL.

    ``base_url`` is the backend base (e.g. https://api.icoder.cloud).
    Returns a URL of the form::

        {base_url}/api/v1/runs/{run_id}/trace?token=<signed>

    The token is bound to ``run_id`` + ``organization_id`` and expires
    after ``ttl_seconds``.
    """
    if not run_id:
        return ""
    token = issue_trace_token(
        run_id=run_id,
        organization_id=organization_id,
        api_client_id=api_client_id,
        ttl_seconds=ttl_seconds,
    )
    base = (base_url or "").rstrip("/")
    return f"{base}/api/v1/runs/{run_id}/trace?token={token}"
