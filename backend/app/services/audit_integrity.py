"""Cryptographic audit chaining and append-only archive helpers.

Production writes use PostgreSQL revision 070's security-definer append
function.  The signing interface is deliberately small so a cloud KMS MAC or
asymmetric signer can replace the local HMAC implementation without changing
the archive format.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.audit_log import AuditLog


GENESIS_HASH = "0" * 64
SYSTEM_STREAM_ID = "system"
SCHEMA_VERSION = "icoder.audit-archive.v1"


def immutable_audit_archive_enabled() -> bool:
    """Return whether the optional advanced audit archive is enabled."""
    return bool(settings.ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED)


class AuditSigner(Protocol):
    algorithm: str
    key_id: str

    def sign(self, message: bytes) -> str: ...

    def verify(self, message: bytes, signature: str) -> bool: ...


class HMACAuditSigner:
    algorithm = "HMAC-SHA256"

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if len(key) < 32:
            raise ValueError("audit signing key must contain at least 32 bytes")
        if not key_id or len(key_id) > 128:
            raise ValueError("audit signing key id is required and must be <= 128 chars")
        self._key = key
        self.key_id = key_id

    def sign(self, message: bytes) -> str:
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def verify(self, message: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(message), signature)


def configured_audit_signer() -> HMACAuditSigner:
    """Resolve the active signer, failing closed in cloud mode.

    ``ICODER_AUDIT_SIGNING_KEY`` is the current bootstrap integration point.
    Production orchestration must inject it from a secrets/KMS system.  Local
    mode derives a domain-separated development key from ``SECRET_KEY``.
    """
    raw = os.environ.get("ICODER_AUDIT_SIGNING_KEY", "").encode("utf-8")
    key_id = os.environ.get("ICODER_AUDIT_SIGNING_KEY_ID", "").strip()
    if not raw:
        if settings.ICODER_DEPLOYMENT_MODE == "cloud":
            raise RuntimeError("ICODER_AUDIT_SIGNING_KEY is required in cloud mode")
        raw = hashlib.sha256(
            b"icoder/audit-integrity/local/v1\x00" + settings.SECRET_KEY.encode("utf-8")
        ).digest()
        key_id = key_id or "local-derived-v1"
    return HMACAuditSigner(raw, key_id=key_id or "env-v1")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def audit_payload(entry: AuditLog) -> dict[str, Any]:
    """Return the stable, minimum-necessary event representation to seal."""
    return {
        "schema": SCHEMA_VERSION,
        "audit_log_id": entry.id,
        "organization_id": entry.organization_id,
        "user_id": entry.user_id,
        "username": entry.username,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "details": entry.details,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "status": entry.status,
        "error_message": entry.error_message,
        "model_input_summary": entry.model_input_summary,
        "model_output_summary": entry.model_output_summary,
        "model_version": entry.model_version,
        "tool_calls_made": entry.tool_calls_made,
        "tokens_used": entry.tokens_used,
        "tenancy_classification": entry.tenancy_classification,
        "tenancy_attribution_source": entry.tenancy_attribution_source,
        "tenancy_attribution_confidence": entry.tenancy_attribution_confidence,
    }


@dataclass(frozen=True)
class AuditEnvelope:
    stream_id: str
    sequence: int
    payload: dict[str, Any]
    payload_hash: str
    previous_hash: str
    chain_hash: str
    signature: str
    signing_algorithm: str
    signing_key_id: str
    archived_at: datetime


def create_envelope(
    payload: dict[str, Any], *, stream_id: str, sequence: int,
    previous_hash: str, signer: AuditSigner,
) -> AuditEnvelope:
    if sequence < 1:
        raise ValueError("audit archive sequence must be positive")
    if len(previous_hash) != 64:
        raise ValueError("previous_hash must be a SHA-256 hex digest")
    payload_hash = hashlib.sha256(canonical_json(payload)).hexdigest()
    chain_input = canonical_json({
        "stream_id": stream_id,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "payload_hash": payload_hash,
    })
    chain_hash = hashlib.sha256(chain_input).hexdigest()
    signature = signer.sign(chain_hash.encode("ascii"))
    return AuditEnvelope(
        stream_id=stream_id, sequence=sequence, payload=payload,
        payload_hash=payload_hash, previous_hash=previous_hash,
        chain_hash=chain_hash, signature=signature,
        signing_algorithm=signer.algorithm, signing_key_id=signer.key_id,
        archived_at=datetime.now(UTC),
    )


def verify_envelopes(
    envelopes: Iterable[AuditEnvelope], *, signer: AuditSigner,
) -> None:
    """Raise ``ValueError`` on the first discontinuity, mutation or bad MAC."""
    previous = GENESIS_HASH
    expected_sequence = 1
    stream_id: str | None = None
    for envelope in envelopes:
        stream_id = stream_id or envelope.stream_id
        if envelope.stream_id != stream_id:
            raise ValueError("archive contains multiple streams")
        expected = create_envelope(
            envelope.payload, stream_id=envelope.stream_id,
            sequence=expected_sequence, previous_hash=previous, signer=signer,
        )
        if envelope.sequence != expected_sequence:
            raise ValueError("audit archive sequence gap")
        if envelope.previous_hash != previous:
            raise ValueError("audit archive previous hash mismatch")
        if envelope.payload_hash != expected.payload_hash:
            raise ValueError("audit archive payload was modified")
        if envelope.chain_hash != expected.chain_hash:
            raise ValueError("audit archive chain hash mismatch")
        if envelope.signing_key_id != signer.key_id or not signer.verify(
            envelope.chain_hash.encode("ascii"), envelope.signature,
        ):
            raise ValueError("audit archive signature verification failed")
        previous = envelope.chain_hash
        expected_sequence += 1


async def archive_audit_log(
    db: AsyncSession, entry: AuditLog, *, signer: AuditSigner | None = None,
) -> AuditEnvelope | None:
    """Append to the optional integrity stream when the advanced feature is on."""
    if not immutable_audit_archive_enabled():
        return None
    if db.get_bind().dialect.name != "postgresql":
        return None
    if not entry.id:
        raise ValueError("audit log must be flushed before it can be archived")
    signer = signer or configured_audit_signer()
    stream_id = entry.organization_id or SYSTEM_STREAM_ID
    head = (
        await db.execute(
            text("SELECT sequence, chain_hash FROM icoder_audit_archive_head(:org)"),
            {"org": entry.organization_id},
        )
    ).one()
    envelope = create_envelope(
        audit_payload(entry), stream_id=stream_id,
        sequence=int(head.sequence) + 1,
        previous_hash=str(head.chain_hash or GENESIS_HASH), signer=signer,
    )
    await db.execute(
        text("SELECT icoder_append_audit_archive(CAST(:record AS jsonb))"),
        {"record": json.dumps({
            "id": __import__("uuid").uuid4().hex[:12],
            "audit_log_id": entry.id,
            "organization_id": entry.organization_id,
            "stream_id": envelope.stream_id,
            "sequence": envelope.sequence,
            "payload": envelope.payload,
            "payload_hash": envelope.payload_hash,
            "previous_hash": envelope.previous_hash,
            "chain_hash": envelope.chain_hash,
            "signature": envelope.signature,
            "signing_algorithm": envelope.signing_algorithm,
            "signing_key_id": envelope.signing_key_id,
            "archived_at": envelope.archived_at.isoformat(),
        }, ensure_ascii=False)},
    )
    return envelope


__all__ = [
    "AuditEnvelope", "AuditSigner", "GENESIS_HASH", "HMACAuditSigner",
    "archive_audit_log", "audit_payload", "canonical_json",
    "configured_audit_signer", "create_envelope", "immutable_audit_archive_enabled",
    "verify_envelopes",
]
