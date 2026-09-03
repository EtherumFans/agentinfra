"""Tamper-evident attestations for chaining Agent results.

An upstream result is clinical decision input.  Accepting a caller-supplied
``agent_id``/``run_id``/``schema_ref`` without proving that the server issued
the accompanying result would make cross-Agent consistency checks cosmetic.
This module signs a canonical SHA-256 digest of the public result together
with its tenant, run, Agent, and schema identity.

The token contains no clinical content, only identifiers and a digest.  It is
short-lived and is invalidated when ``SECRET_KEY`` rotates.
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
_KEY_DOMAIN = b"icoder:agent-result-attestation:v1\x00"


class ResultAttestationError(ValueError):
    """Base class for fail-closed attestation verification failures."""


class ResultAttestationExpired(ResultAttestationError):
    pass


class ResultAttestationMalformed(ResultAttestationError):
    pass


class ResultAttestationMismatch(ResultAttestationError):
    pass


@dataclass(frozen=True)
class ResultAttestationClaims:
    run_id: str
    agent_id: str
    schema_ref: str
    organization_id: str
    result_sha256: str
    exp: int


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def _key() -> bytes:
    raw = (settings.SECRET_KEY or "").encode("utf-8")
    if not raw:
        raise ResultAttestationMalformed("server signing key is unavailable")
    return hashlib.sha256(_KEY_DOMAIN + raw).digest()


def _canonical_result(result: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResultAttestationMalformed("result is not canonical JSON") from exc


def _result_digest(result: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_result(result)).hexdigest()


def _sign(payload_b64: str) -> str:
    return _b64url_encode(
        hmac.new(_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    )


def issue_result_attestation(
    *,
    run_id: str,
    agent_id: str,
    schema_ref: str,
    organization_id: str,
    result: dict[str, Any],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Issue a tenant-bound proof for one exact public Agent result."""
    required = {
        "run_id": run_id,
        "agent_id": agent_id,
        "schema_ref": schema_ref,
        "organization_id": organization_id,
    }
    if any(not str(value or "").strip() for value in required.values()):
        missing = ",".join(key for key, value in required.items() if not str(value or "").strip())
        raise ResultAttestationMalformed(f"missing attestation identity: {missing}")
    if not isinstance(result, dict):
        raise ResultAttestationMalformed("result must be an object")
    ttl = int(ttl_seconds)
    if ttl <= 0:
        raise ResultAttestationMalformed("ttl_seconds must be positive")
    payload = {
        "v": TOKEN_VERSION,
        "r": run_id,
        "a": agent_id,
        "s": schema_ref,
        "o": organization_id,
        "d": _result_digest(result),
        "e": int(time.time()) + ttl,
    }
    payload_b64 = _b64url_encode(json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_result_attestation(
    token: str,
    *,
    expected_run_id: str,
    expected_agent_id: str,
    expected_schema_ref: str,
    expected_organization_id: str,
    result: dict[str, Any],
) -> ResultAttestationClaims:
    """Verify signature, expiry, tenant, identities, and exact result digest."""
    if not isinstance(token, str) or token.count(".") != 1:
        raise ResultAttestationMalformed("missing or malformed result attestation")
    payload_b64, signature = token.split(".", 1)
    if not secrets.compare_digest(signature, _sign(payload_b64)):
        raise ResultAttestationMismatch("result attestation signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise ResultAttestationMalformed("result attestation payload is invalid") from exc
    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise ResultAttestationMalformed("unsupported result attestation version")
    try:
        exp = int(payload.get("e"))
    except (TypeError, ValueError) as exc:
        raise ResultAttestationMalformed("result attestation expiry is invalid") from exc
    if exp <= int(time.time()):
        raise ResultAttestationExpired("result attestation expired")

    expected = {
        "r": expected_run_id,
        "a": expected_agent_id,
        "s": expected_schema_ref,
        "o": expected_organization_id,
        "d": _result_digest(result),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ResultAttestationMismatch("result attestation identity or digest mismatch")
    return ResultAttestationClaims(
        run_id=str(payload["r"]),
        agent_id=str(payload["a"]),
        schema_ref=str(payload["s"]),
        organization_id=str(payload["o"]),
        result_sha256=str(payload["d"]),
        exp=exp,
    )


def verify_upstream_result_attestations(
    upstream_results: list[dict[str, Any]],
    *,
    organization_id: str,
) -> None:
    """Validate every supplied upstream result before it reaches a runtime."""
    for item in upstream_results:
        if not isinstance(item, dict):
            raise ResultAttestationMalformed("upstream result must be an object")
        result = item.get("result")
        if not isinstance(result, dict):
            raise ResultAttestationMalformed("upstream result payload must be an object")
        verify_result_attestation(
            str(item.get("attestation") or ""),
            expected_run_id=str(item.get("run_id") or ""),
            expected_agent_id=str(item.get("agent_id") or ""),
            expected_schema_ref=str(item.get("schema_ref") or ""),
            expected_organization_id=organization_id,
            result=result,
        )


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ResultAttestationClaims",
    "ResultAttestationError",
    "ResultAttestationExpired",
    "ResultAttestationMalformed",
    "ResultAttestationMismatch",
    "issue_result_attestation",
    "verify_result_attestation",
    "verify_upstream_result_attestations",
]
