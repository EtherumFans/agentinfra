"""Phase 7 Gate 3 — Server-side Idempotency-Key dedup service.

Per Phase 7 §8: server is the final security boundary for dedup. The
client already sends `Idempotency-Key` + `X-Attempt` headers (Phase 6
Gate 3); this service enforces server-side dedup against the
`idempotency_records` table.

Concurrency model (§8.3):
- INSERT-with-UNIQUE is the dedup primitive. Two concurrent requests
  with the same key attempt INSERT; the loser raises IntegrityError,
  which we catch and convert to a SELECT of the winning row.
- "SELECT then INSERT" without a UNIQUE constraint is FORBIDDEN (§8.3).
- We rely on the UNIQUE constraint `uq_idempotency_org_client_key`
  (alembic 012) for correctness.

Semantic (§8.2):
- First request (no existing record) → INSERT PENDING + return None
  (caller proceeds with the actual run).
- Same key + same request_hash + COMPLETED → return the saved snapshot.
- Same key + same request_hash + IN_PROGRESS → return the run_id with
  status IN_PROGRESS (caller returns 200 with status=IN_PROGRESS).
- Same key + DIFFERENT request_hash → raise IdempotencyKeyReusedError
  (caller returns 409).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.tenancy_guard import (
    assert_tenancy_for_write,
    classify_modern_write,
)
from app.models.idempotency_record import IdempotencyRecord

logger = logging.getLogger(__name__)

# Phase 7 §8.1: status constants
STATUS_PENDING = "PENDING"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

# Records expire after 24h — clients should not retry days-old requests.
DEFAULT_TTL_SECONDS = 24 * 60 * 60


class IdempotencyKeyReusedError(HTTPException):
    """409 — same Idempotency-Key was reused with a different request body."""

    def __init__(self, idempotency_key: str, agent_ref: str) -> None:
        super().__init__(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST",
                "message": (
                    "Idempotency-Key was already used for a different request body. "
                    "Each unique request MUST use a new Idempotency-Key."
                ),
                "idempotency_key": idempotency_key,
                "agent_ref": agent_ref,
            },
        )


@dataclass
class DedupResult:
    """Outcome of a dedup check.

    - `should_run=True` → no prior record; caller proceeds with the run.
      `record` is the freshly-created PENDING row (caller MUST call
      `mark_completed()` or `mark_failed()` after the run).
    - `should_run=False` → prior record exists. Caller returns
      `response_snapshot` directly (if COMPLETED) or returns
      `run_id` + IN_PROGRESS indicator (if PENDING/IN_PROGRESS).
    """

    should_run: bool
    record: IdempotencyRecord
    response_snapshot: Optional[dict] = None
    in_progress: bool = False


def compute_request_hash(
    *,
    agent_id: str,
    input_text: str,
    runtime_mode: str = "",
    extra: Optional[dict] = None,
) -> str:
    """SHA-256 of the normalized request body.

    The hash is what tells "same request" apart from "different request
    reusing same key" (Phase 7 §8.2 mismatch case → 409).

    Normalization:
    - agent_id lowercased
    - input_text UTF-8 encoded, stripped
    - runtime_mode default to "" if None
    - extra dict JSON-serialized with sort_keys=True
    """
    payload = {
        "agent_id": agent_id.lower().strip(),
        "input_text": (input_text or "").strip(),
        "runtime_mode": runtime_mode or "",
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def acquire_or_replay(
    db: AsyncSession,
    *,
    idempotency_key: str,
    request_hash: str,
    agent_ref: str,
    organization_id: Optional[str] = None,
    api_client_id: Optional[str] = None,
    context_id: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> DedupResult:
    """Atomic INSERT-or-SELECT against idempotency_records.

    Returns a DedupResult — caller branches on `should_run`:
    - True → run the agent, then call mark_completed() / mark_failed()
    - False → return response_snapshot (COMPLETED) or IN_PROGRESS

    Raises IdempotencyKeyReusedError on key+hash mismatch (409).

    NOTE on NULL semantics: SQLite AND PostgreSQL treat NULLs as
    distinct under UNIQUE constraints, which would silently defeat
    dedup when ``organization_id`` or ``api_client_id`` is unset
    (local-dev single-org mode, Console JWT without an API client).
    We normalize None → "" sentinel at the service boundary so the
    constraint always has a comparable value to match on.
    """
    if not idempotency_key:
        # Empty key — caller should bypass dedup entirely (not call us).
        raise ValueError("idempotency_key must be non-empty")

    # Phase A1A Gate 2 §3: cloud-mode fail-closed tenancy guard.
    # In cloud mode, every partner request MUST have a resolved org
    # identity — otherwise dedup keys aren't tenant-scoped.
    assert_tenancy_for_write(organization_id, "idempotency_records")

    # Normalize NULL → "" so the UNIQUE constraint matches rows that
    # belong to "no org / no API client" partners. SQLite AND PostgreSQL
    # treat NULL as distinct under UNIQUE, which would silently defeat
    # dedup in single-org mode or for Console-JWT callers. The empty-
    # string sentinel normalizes both to "no partner" identity.
    org_id_norm = (organization_id or "").strip()
    api_client_id_norm = (api_client_id or "").strip()

    # Try INSERT first (the winner path). On UNIQUE violation, fall back
    # to SELECT. This is the canonical pattern for safe concurrency —
    # the loser never observes a half-written row.
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    record = IdempotencyRecord(
        organization_id=org_id_norm,
        api_client_id=api_client_id_norm,
        idempotency_key=idempotency_key,
        agent_ref=agent_ref,
        context_id=context_id,
        request_hash=request_hash,
        status=STATUS_PENDING,
        expires_at=expires_at,
    )
    db.add(record)
    try:
        await db.flush()  # Issues INSERT; UNIQUE violation raises here.
        logger.info(
            "idempotency: ACQUIRED key=%s agent=%s req_hash=%s record_id=%s",
            idempotency_key[:8], agent_ref, request_hash[:8], record.id,
        )
        return DedupResult(should_run=True, record=record)
    except IntegrityError as ie:
        # UNIQUE violation — another request won the race (or this is a
        # replay). Roll back the failed INSERT and SELECT the winner.
        await db.rollback()
        existing = await _fetch_by_key(
            db,
            idempotency_key=idempotency_key,
            organization_id=org_id_norm,
            api_client_id=api_client_id_norm,
        )
        if existing is None:
            # Extremely unlikely — INSERT failed but row not found.
            # Could be a check constraint violation or other DB issue.
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "IDEMPOTENCY_INTERNAL_ERROR",
                    "message": (
                        "IntegrityError on idempotency INSERT but no existing "
                        "row found; database may be inconsistent"
                    ),
                },
            ) from ie
        # Hash mismatch → 409
        if existing.request_hash != request_hash:
            logger.warning(
                "idempotency: REUSED key=%s agent=%s existing_hash=%s new_hash=%s",
                idempotency_key[:8], agent_ref,
                existing.request_hash[:8], request_hash[:8],
            )
            raise IdempotencyKeyReusedError(idempotency_key, agent_ref)
        # Same key + same hash — replay path.
        if existing.status == STATUS_COMPLETED and existing.response_snapshot:
            logger.info(
                "idempotency: REPLAY key=%s run_id=%s → returning snapshot",
                idempotency_key[:8], existing.run_id,
            )
            return DedupResult(
                should_run=False,
                record=existing,
                response_snapshot=existing.response_snapshot,
                in_progress=False,
            )
        # PENDING / IN_PROGRESS — caller returns the run_id.
        logger.info(
            "idempotency: IN_PROGRESS key=%s run_id=%s status=%s",
            idempotency_key[:8], existing.run_id, existing.status,
        )
        return DedupResult(
            should_run=False,
            record=existing,
            response_snapshot=None,
            in_progress=True,
        )


async def mark_in_progress(
    db: AsyncSession,
    record: IdempotencyRecord,
    *,
    run_id: str,
) -> None:
    """Transition a PENDING record to IN_PROGRESS with the bound run_id."""
    record.status = STATUS_IN_PROGRESS
    record.run_id = run_id
    await db.flush()


async def mark_completed(
    db: AsyncSession,
    record: IdempotencyRecord,
    *,
    response_snapshot: dict[str, Any],
) -> None:
    """Persist the completed response snapshot.

    The snapshot is what future replays will return verbatim (Phase 7
    §8.2 "Run 已完成 → 返回原 run_id 和原响应").
    """
    record.status = STATUS_COMPLETED
    record.response_snapshot = response_snapshot
    await db.flush()


async def mark_failed(
    db: AsyncSession,
    record: IdempotencyRecord,
) -> None:
    """Mark the record as FAILED — next replay will re-attempt (not return snapshot)."""
    record.status = STATUS_FAILED
    await db.flush()


async def _fetch_by_key(
    db: AsyncSession,
    *,
    idempotency_key: str,
    organization_id: Optional[str],
    api_client_id: Optional[str],
) -> Optional[IdempotencyRecord]:
    """SELECT existing record by (org, client, key)."""
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.idempotency_key == idempotency_key,
        IdempotencyRecord.organization_id.is_(organization_id)
        if organization_id is None
        else IdempotencyRecord.organization_id == organization_id,
        IdempotencyRecord.api_client_id.is_(api_client_id)
        if api_client_id is None
        else IdempotencyRecord.api_client_id == api_client_id,
    )
    result = await db.execute(stmt)
    return result.scalars().one_or_none()
