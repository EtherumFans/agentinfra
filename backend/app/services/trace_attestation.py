"""Tamper-evident proofs for display-safe RunTrace artifacts.

The token binds the exact serialized safe event list to its tenant and run.
It contains no prompt, response body, credential, or clinical text—only
identifiers, a SHA-256 digest, and an expiry.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings


DEFAULT_TTL_SECONDS = 24 * 60 * 60
TOKEN_VERSION = 1
_KEY_DOMAIN = b"icoder:run-trace-attestation:v1\x00"


class TraceAttestationError(ValueError):
    pass


class TraceAttestationExpired(TraceAttestationError):
    pass


class TraceAttestationMalformed(TraceAttestationError):
    pass


class TraceAttestationMismatch(TraceAttestationError):
    pass


@dataclass(frozen=True)
class TraceAttestationClaims:
    run_id: str
    organization_id: str
    events_sha256: str
    exp: int


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _key() -> bytes:
    raw = (settings.SECRET_KEY or "").encode("utf-8")
    if not raw:
        raise TraceAttestationMalformed("server signing key is unavailable")
    return hashlib.sha256(_KEY_DOMAIN + raw).digest()


def _canonical_events(events: list[dict[str, Any]]) -> bytes:
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise TraceAttestationMalformed("events must be a list of objects")
    try:
        return json.dumps(
            events,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TraceAttestationMalformed("events are not canonical JSON") from exc


def _events_digest(events: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_events(events)).hexdigest()


def _sign(payload_b64: str) -> str:
    return _b64url_encode(
        hmac.new(_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    )


def issue_trace_attestation(
    *,
    run_id: str,
    organization_id: str,
    events: list[dict[str, Any]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    if not str(run_id or "").strip() or not str(organization_id or "").strip():
        raise TraceAttestationMalformed("run and organization identities are required")
    ttl = int(ttl_seconds)
    if ttl <= 0:
        raise TraceAttestationMalformed("ttl_seconds must be positive")
    payload = {
        "v": TOKEN_VERSION,
        "r": run_id,
        "o": organization_id,
        "d": _events_digest(events),
        "e": int(time.time()) + ttl,
    }
    payload_b64 = _b64url_encode(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_trace_attestation(
    token: str,
    *,
    expected_run_id: str,
    expected_organization_id: str,
    events: list[dict[str, Any]],
) -> TraceAttestationClaims:
    if not isinstance(token, str) or token.count(".") != 1:
        raise TraceAttestationMalformed("missing or malformed trace attestation")
    payload_b64, signature = token.split(".", 1)
    if not secrets.compare_digest(signature, _sign(payload_b64)):
        raise TraceAttestationMismatch("trace attestation signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise TraceAttestationMalformed("trace attestation payload is invalid") from exc
    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise TraceAttestationMalformed("unsupported trace attestation version")
    try:
        exp = int(payload.get("e"))
    except (TypeError, ValueError) as exc:
        raise TraceAttestationMalformed("trace attestation expiry is invalid") from exc
    if exp <= int(time.time()):
        raise TraceAttestationExpired("trace attestation expired")
    expected = {
        "r": expected_run_id,
        "o": expected_organization_id,
        "d": _events_digest(events),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise TraceAttestationMismatch("trace attestation identity or digest mismatch")
    return TraceAttestationClaims(
        run_id=str(payload["r"]),
        organization_id=str(payload["o"]),
        events_sha256=str(payload["d"]),
        exp=exp,
    )


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "TraceAttestationClaims",
    "TraceAttestationError",
    "TraceAttestationExpired",
    "TraceAttestationMalformed",
    "TraceAttestationMismatch",
    "issue_trace_attestation",
    "verify_trace_attestation",
]

