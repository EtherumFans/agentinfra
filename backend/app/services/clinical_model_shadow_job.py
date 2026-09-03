"""Fenced asynchronous execution for aggregate-only clinical shadow jobs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import database
from app.middleware.audit import log_action
from app.models.clinical_model_package import (
    ClinicalModelArtifactAttestation,
    ClinicalModelPackage,
    ClinicalModelShadowBinding,
    ClinicalModelShadowDeadLetter,
    ClinicalModelShadowEvaluation,
    ClinicalModelShadowEvaluationJob,
)
from app.models.organization import Organization
from app.models.user import User
from app.services.clinical_model_bundle import (
    ClinicalModelBundleError,
    validate_verification_report,
    verify_bundle_directory,
)
from app.services.clinical_model_shadow_observation import (
    ClinicalModelShadowObservationError,
    build_fault_observation,
    run_verified_shadow_suite,
    validate_shadow_observation,
)
from app.services.clinical_model_shadow_probe import ClinicalModelShadowProbeError
from app.services.clinical_model_shadow_observability import get_clinical_shadow_metrics


DEFAULT_LEASE_SECONDS = 30
MINIMUM_LEASE_SECONDS = 5
MAXIMUM_LEASE_SECONDS = 300
MAXIMUM_WORKER_ID_LENGTH = 64
DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "clinical_model_bundle_v1"
)
TERMINAL_STATUSES = {"passed", "stopped", "failed", "cancelled"}
SAFE_RETRY_ERROR_CODES = {
    "ARTIFACT_RESOLUTION_FAILED",
    "BINDING_CHANGED",
    "INTERNAL_WORKER_ERROR",
    "LEASE_EXPIRED",
    "OBSERVATION_INVALID",
}
SHADOW_JOB_CANCELLATION_REASONS = {
    "operator_request",
    "maintenance",
    "safety_stop",
}


class ClinicalModelShadowJobError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimedShadowJob:
    job_id: str
    organization_id: str
    binding_id: str
    package_id: str
    attestation_id: str
    binding_record_version: int
    fault_mode: str
    worker_id: str
    lease_token: str
    attempt_count: int
    lease_expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


async def database_utc_now(db: AsyncSession) -> datetime:
    """Read the lease clock from the database, not from a worker host.

    Explicit ``now`` arguments remain available for deterministic tests and
    controlled fault injection.  Production callers omit them, which makes
    lease ownership independent of application-host clock skew.
    """

    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        # SQLite CURRENT_TIMESTAMP truncates fractional seconds.  That can
        # make a job inserted in the current second appear not-yet-due.
        value = await db.scalar(select(func.strftime("%Y-%m-%d %H:%M:%f", "now")))
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
    else:
        value = await db.scalar(select(func.current_timestamp()))
    if not isinstance(value, datetime):
        raise ClinicalModelShadowJobError("SHADOW_JOB_DATABASE_CLOCK_INVALID")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _validated_worker_id(worker_id: str) -> str:
    value = worker_id.strip()
    if (
        not value
        or len(value) > MAXIMUM_WORKER_ID_LENGTH
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None
    ):
        raise ClinicalModelShadowJobError("SHADOW_JOB_WORKER_ID_INVALID")
    return value


def _validated_lease_seconds(lease_seconds: int) -> int:
    if isinstance(lease_seconds, bool) or not (
        MINIMUM_LEASE_SECONDS <= lease_seconds <= MAXIMUM_LEASE_SECONDS
    ):
        raise ClinicalModelShadowJobError("SHADOW_JOB_LEASE_DURATION_INVALID")
    return lease_seconds


def _claimable(now: datetime):
    return or_(
        and_(
            ClinicalModelShadowEvaluationJob.status == "queued",
            ClinicalModelShadowEvaluationJob.next_attempt_at <= now,
        ),
        and_(
            ClinicalModelShadowEvaluationJob.status == "running",
            ClinicalModelShadowEvaluationJob.lease_expires_at <= now,
        ),
    )


def _claim_from_row(row: ClinicalModelShadowEvaluationJob) -> ClaimedShadowJob:
    if row.lease_token is None or row.lease_owner is None or row.lease_expires_at is None:
        raise ClinicalModelShadowJobError("SHADOW_JOB_LEASE_SHAPE_INVALID")
    return ClaimedShadowJob(
        job_id=row.id,
        organization_id=row.organization_id,
        binding_id=row.binding_id,
        package_id=row.package_id,
        attestation_id=row.attestation_id,
        binding_record_version=row.binding_record_version,
        fault_mode=row.fault_mode,
        worker_id=row.lease_owner,
        lease_token=row.lease_token,
        attempt_count=row.attempt_count,
        lease_expires_at=row.lease_expires_at,
    )


async def _ensure_dead_letter(
    db: AsyncSession,
    row: ClinicalModelShadowEvaluationJob,
    *,
    error_code: str,
    now: datetime,
) -> ClinicalModelShadowDeadLetter:
    existing = (
        await db.execute(
            select(ClinicalModelShadowDeadLetter).where(
                ClinicalModelShadowDeadLetter.source_job_id == row.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    dead_letter = ClinicalModelShadowDeadLetter(
        id=str(uuid.uuid4()),
        organization_id=row.organization_id,
        source_job_id=row.id,
        binding_id=row.binding_id,
        use_case=row.use_case,
        package_id=row.package_id,
        attestation_id=row.attestation_id,
        binding_record_version=row.binding_record_version,
        error_code=error_code,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        status="available",
        created_at=now,
        updated_at=now,
    )
    db.add(dead_letter)
    await log_action(
        db, row.created_by_user_id, "shadow-worker",
        "clinical_model_shadow_job.dead_lettered",
        "clinical_model_shadow_dead_letter", dead_letter.id,
        details={
            "job_id": row.id,
            "binding_id": row.binding_id,
            "use_case": row.use_case,
            "error_code": error_code,
            "attempt_count": row.attempt_count,
            "max_attempts": row.max_attempts,
            "dead_letter_status": "available",
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
        },
        organization_id=row.organization_id,
        status="error",
    )
    get_clinical_shadow_metrics().record("dead_lettered")
    return dead_letter


async def finalize_exhausted_shadow_jobs(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    organization_id: str | None = None,
    limit: int = 100,
) -> int:
    """Fail expired work that has no remaining attempt and free its slot."""

    current = now or await database_utc_now(db)
    bounded_limit = max(1, min(int(limit), 1000))
    statement = select(ClinicalModelShadowEvaluationJob).where(
            or_(
                and_(
                    ClinicalModelShadowEvaluationJob.status == "running",
                    ClinicalModelShadowEvaluationJob.lease_expires_at <= current,
                ),
                and_(
                    ClinicalModelShadowEvaluationJob.status == "queued",
                    ClinicalModelShadowEvaluationJob.next_attempt_at <= current,
                ),
            ),
            ClinicalModelShadowEvaluationJob.attempt_count
            >= ClinicalModelShadowEvaluationJob.max_attempts,
        )
    if organization_id is not None:
        statement = statement.where(
            ClinicalModelShadowEvaluationJob.organization_id == organization_id,
        )
    rows = list((await db.scalars(statement.limit(bounded_limit))).all())
    completed = 0
    for row in rows:
        changed = await db.execute(
            update(ClinicalModelShadowEvaluationJob)
            .where(
                ClinicalModelShadowEvaluationJob.id == row.id,
                ClinicalModelShadowEvaluationJob.status.in_(["queued", "running"]),
                ClinicalModelShadowEvaluationJob.attempt_count
                >= ClinicalModelShadowEvaluationJob.max_attempts,
            )
            .values(
                status="failed",
                active_binding_id=None,
                lease_owner=None,
                lease_token=None,
                lease_expires_at=None,
                error_code="LEASE_EXPIRED",
                completed_at=current,
                updated_at=current,
            )
        )
        if not changed.rowcount:
            continue
        completed += 1
        await _ensure_dead_letter(
            db, row, error_code="LEASE_EXPIRED", now=current,
        )
        await log_action(
            db, row.created_by_user_id, "shadow-worker",
            "clinical_model_shadow_job.failed",
            "clinical_model_shadow_evaluation_job", row.id,
            details={
                "error_code": "LEASE_EXPIRED",
                "attempt_count": row.attempt_count,
                "max_attempts": row.max_attempts,
                "retry_scheduled": False,
                "aggregate_only": True,
                "patient_data_used": False,
                "predictions_emitted": False,
            },
            organization_id=row.organization_id,
            status="error",
        )
    if completed:
        await db.commit()
    else:
        await db.rollback()
    return completed


async def cancel_shadow_job(
    db: AsyncSession,
    *,
    organization_id: str,
    job_id: str,
    cancelled_by_user_id: str,
    cancelled_by_username: str,
    reason: str,
    now: datetime | None = None,
) -> tuple[str, ClinicalModelShadowEvaluationJob | None]:
    """Cancel active work and atomically invalidate any outstanding fence."""

    if reason not in SHADOW_JOB_CANCELLATION_REASONS:
        raise ClinicalModelShadowJobError("SHADOW_JOB_CANCELLATION_REASON_INVALID")
    current = now or await database_utc_now(db)
    row = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob)
            .where(
                ClinicalModelShadowEvaluationJob.id == job_id,
                ClinicalModelShadowEvaluationJob.organization_id == organization_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        await db.rollback()
        return "not_found", None
    if row.status == "cancelled":
        return "already_cancelled", row
    if row.status not in {"queued", "running"}:
        return "terminal", row
    changed = await db.execute(
        update(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.id == job_id,
            ClinicalModelShadowEvaluationJob.organization_id == organization_id,
            ClinicalModelShadowEvaluationJob.status.in_(["queued", "running"]),
        )
        .values(
            status="cancelled",
            active_binding_id=None,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            error_code=None,
            cancellation_reason=reason,
            cancelled_at=current,
            cancelled_by_user_id=cancelled_by_user_id,
            completed_at=current,
            updated_at=current,
        )
    )
    if not changed.rowcount:
        await db.rollback()
        return "race_lost", None
    await log_action(
        db,
        cancelled_by_user_id,
        cancelled_by_username,
        "clinical_model_shadow_job.cancelled",
        "clinical_model_shadow_evaluation_job",
        job_id,
        details={
            "binding_id": row.binding_id,
            "use_case": row.use_case,
            "cancellation_reason": reason,
            "attempt_count": row.attempt_count,
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
            "production_inference_enabled": False,
        },
        organization_id=organization_id,
    )
    await db.commit()
    get_clinical_shadow_metrics().record("cancelled")
    cancelled = await db.get(ClinicalModelShadowEvaluationJob, job_id)
    return "cancelled", cancelled


async def summarize_shadow_job_health(
    db: AsyncSession,
    *,
    organization_id: str,
    now: datetime | None = None,
    queue_alert_count: int = 10,
    max_queue_age_seconds: int = 300,
    expired_lease_alert_count: int = 1,
    dead_letter_alert_count: int = 1,
) -> dict[str, Any]:
    """Return tenant-safe aggregate queue health without job identifiers."""

    current = now or await database_utc_now(db)
    queue_threshold = max(1, min(int(queue_alert_count), 100000))
    age_threshold = max(1, min(int(max_queue_age_seconds), 86400))
    lease_threshold = max(1, min(int(expired_lease_alert_count), 100000))
    dead_letter_threshold = max(1, min(int(dead_letter_alert_count), 100000))
    counts = {status: 0 for status in (
        "queued", "running", "passed", "stopped", "failed", "cancelled",
    )}
    for status, count in (
        await db.execute(
            select(
                ClinicalModelShadowEvaluationJob.status,
                func.count(ClinicalModelShadowEvaluationJob.id),
            )
            .where(ClinicalModelShadowEvaluationJob.organization_id == organization_id)
            .group_by(ClinicalModelShadowEvaluationJob.status)
        )
    ).all():
        counts[str(status)] = int(count)

    due_filter = and_(
        ClinicalModelShadowEvaluationJob.organization_id == organization_id,
        ClinicalModelShadowEvaluationJob.status == "queued",
        ClinicalModelShadowEvaluationJob.next_attempt_at <= current,
    )
    due_queued_count, oldest_due_at = (
        await db.execute(
            select(
                func.count(ClinicalModelShadowEvaluationJob.id),
                func.min(ClinicalModelShadowEvaluationJob.next_attempt_at),
            ).where(due_filter)
        )
    ).one()
    expired_lease_count = int(
        await db.scalar(
            select(func.count(ClinicalModelShadowEvaluationJob.id)).where(
                ClinicalModelShadowEvaluationJob.organization_id == organization_id,
                ClinicalModelShadowEvaluationJob.status == "running",
                ClinicalModelShadowEvaluationJob.lease_expires_at <= current,
            )
        ) or 0
    )
    exhausted_count = int(
        await db.scalar(
            select(func.count(ClinicalModelShadowEvaluationJob.id)).where(
                ClinicalModelShadowEvaluationJob.organization_id == organization_id,
                ClinicalModelShadowEvaluationJob.status.in_(["queued", "running"]),
                ClinicalModelShadowEvaluationJob.attempt_count
                >= ClinicalModelShadowEvaluationJob.max_attempts,
                or_(
                    and_(
                        ClinicalModelShadowEvaluationJob.status == "queued",
                        ClinicalModelShadowEvaluationJob.next_attempt_at <= current,
                    ),
                    and_(
                        ClinicalModelShadowEvaluationJob.status == "running",
                        ClinicalModelShadowEvaluationJob.lease_expires_at <= current,
                    ),
                ),
            )
        ) or 0
    )
    dead_letter_count = int(
        await db.scalar(
            select(func.count(ClinicalModelShadowDeadLetter.id)).where(
                ClinicalModelShadowDeadLetter.organization_id == organization_id,
                ClinicalModelShadowDeadLetter.status == "available",
            )
        ) or 0
    )
    oldest_age = 0
    if oldest_due_at is not None:
        if oldest_due_at.tzinfo is None:
            oldest_due_at = oldest_due_at.replace(tzinfo=UTC)
        oldest_age = max(0, int((current - oldest_due_at).total_seconds()))
    alerts: list[str] = []
    if int(due_queued_count) >= queue_threshold:
        alerts.append("queue_backlog")
    if oldest_age >= age_threshold and int(due_queued_count) > 0:
        alerts.append("queue_age_exceeded")
    if expired_lease_count >= lease_threshold:
        alerts.append("expired_leases")
    if exhausted_count:
        alerts.append("exhausted_jobs")
    if dead_letter_count >= dead_letter_threshold:
        alerts.append("dead_letter_backlog")
    return {
        "status": "degraded" if alerts else "healthy",
        "status_counts": counts,
        "due_queued_count": int(due_queued_count),
        "active_lease_count": counts["running"] - expired_lease_count,
        "expired_lease_count": expired_lease_count,
        "exhausted_count": exhausted_count,
        "dead_letter_count": dead_letter_count,
        "oldest_due_age_seconds": oldest_age,
        "alert_codes": alerts,
        "evaluated_at": current,
        "aggregate_only": True,
        "patient_data_used": False,
        "identifiers_emitted": False,
    }


async def claim_next_shadow_job(
    db: AsyncSession,
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> ClaimedShadowJob | None:
    """Atomically claim one due or expired job and issue a new fence token."""

    owner = _validated_worker_id(worker_id)
    seconds = _validated_lease_seconds(lease_seconds)
    current = now or await database_utc_now(db)
    await finalize_exhausted_shadow_jobs(db, now=current)
    candidate_ids = list((await db.scalars(
        select(ClinicalModelShadowEvaluationJob.id)
        .where(_claimable(current))
        .order_by(
            ClinicalModelShadowEvaluationJob.next_attempt_at,
            ClinicalModelShadowEvaluationJob.created_at,
            ClinicalModelShadowEvaluationJob.id,
        )
        .limit(16)
    )).all())
    for job_id in candidate_ids:
        token = str(uuid.uuid4())
        claimed = await db.execute(
            update(ClinicalModelShadowEvaluationJob)
            .where(
                ClinicalModelShadowEvaluationJob.id == job_id,
                _claimable(current),
                ClinicalModelShadowEvaluationJob.attempt_count
                < ClinicalModelShadowEvaluationJob.max_attempts,
            )
            .values(
                status="running",
                lease_owner=owner,
                lease_token=token,
                lease_expires_at=current + timedelta(seconds=seconds),
                attempt_count=ClinicalModelShadowEvaluationJob.attempt_count + 1,
                started_at=func.coalesce(
                    ClinicalModelShadowEvaluationJob.started_at, current,
                ),
                error_code=None,
                updated_at=current,
            )
        )
        if not claimed.rowcount:
            await db.rollback()
            continue
        row = await db.get(ClinicalModelShadowEvaluationJob, job_id)
        if row is None:
            raise ClinicalModelShadowJobError("SHADOW_JOB_DISAPPEARED")
        await log_action(
            db, row.created_by_user_id, "shadow-worker",
            "clinical_model_shadow_job.claimed",
            "clinical_model_shadow_evaluation_job", row.id,
            details={
                "attempt_count": row.attempt_count,
                "recovered_after_expiry": row.attempt_count > 1,
                "lease_seconds": seconds,
                "aggregate_only": True,
                "patient_data_used": False,
                "predictions_emitted": False,
            },
            organization_id=row.organization_id,
        )
        await db.commit()
        get_clinical_shadow_metrics().record("claimed")
        if row.attempt_count > 1:
            get_clinical_shadow_metrics().record("recovered")
        await db.refresh(row)
        return _claim_from_row(row)
    await db.rollback()
    return None


async def claim_shadow_job(
    db: AsyncSession,
    job_id: str,
    worker_id: str,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> ClaimedShadowJob | None:
    """Claim a specific job for the explicit development executor."""

    owner = _validated_worker_id(worker_id)
    seconds = _validated_lease_seconds(lease_seconds)
    current = now or await database_utc_now(db)
    await finalize_exhausted_shadow_jobs(db, now=current)
    token = str(uuid.uuid4())
    claimed = await db.execute(
        update(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.id == job_id,
            _claimable(current),
            ClinicalModelShadowEvaluationJob.attempt_count
            < ClinicalModelShadowEvaluationJob.max_attempts,
        )
        .values(
            status="running",
            lease_owner=owner,
            lease_token=token,
            lease_expires_at=current + timedelta(seconds=seconds),
            attempt_count=ClinicalModelShadowEvaluationJob.attempt_count + 1,
            started_at=func.coalesce(ClinicalModelShadowEvaluationJob.started_at, current),
            error_code=None,
            updated_at=current,
        )
    )
    if not claimed.rowcount:
        await db.rollback()
        return None
    row = await db.get(ClinicalModelShadowEvaluationJob, job_id)
    if row is None:
        await db.rollback()
        return None
    await log_action(
        db, row.created_by_user_id, "shadow-worker",
        "clinical_model_shadow_job.claimed",
        "clinical_model_shadow_evaluation_job", row.id,
        details={
            "attempt_count": row.attempt_count,
            "recovered_after_expiry": row.attempt_count > 1,
            "lease_seconds": seconds,
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
        },
        organization_id=row.organization_id,
    )
    await db.commit()
    get_clinical_shadow_metrics().record("claimed")
    if row.attempt_count > 1:
        get_clinical_shadow_metrics().record("recovered")
    await db.refresh(row)
    return _claim_from_row(row)


async def renew_shadow_job_lease(
    db: AsyncSession,
    claim: ClaimedShadowJob,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> bool:
    seconds = _validated_lease_seconds(lease_seconds)
    current = now or await database_utc_now(db)
    renewed = await db.execute(
        update(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.id == claim.job_id,
            ClinicalModelShadowEvaluationJob.status == "running",
            ClinicalModelShadowEvaluationJob.lease_owner == claim.worker_id,
            ClinicalModelShadowEvaluationJob.lease_token == claim.lease_token,
            ClinicalModelShadowEvaluationJob.lease_expires_at > current,
        )
        .values(
            lease_expires_at=current + timedelta(seconds=seconds),
            updated_at=current,
        )
    )
    await db.commit()
    return bool(renewed.rowcount)


async def fail_claimed_shadow_job(
    db: AsyncSession,
    claim: ClaimedShadowJob,
    *,
    error_code: str,
    retryable: bool,
    retry_delay_seconds: int = 0,
    now: datetime | None = None,
) -> str | None:
    if error_code not in SAFE_RETRY_ERROR_CODES:
        raise ClinicalModelShadowJobError("SHADOW_JOB_ERROR_CODE_INVALID")
    if retry_delay_seconds < 0 or retry_delay_seconds > 3600:
        raise ClinicalModelShadowJobError("SHADOW_JOB_RETRY_DELAY_INVALID")
    current = now or await database_utc_now(db)
    row = await db.get(ClinicalModelShadowEvaluationJob, claim.job_id)
    if (
        row is None
        or row.status != "running"
        or row.lease_owner != claim.worker_id
        or row.lease_token != claim.lease_token
    ):
        await db.rollback()
        return None
    retry = retryable and row.attempt_count < row.max_attempts
    target = "queued" if retry else "failed"
    changed = await db.execute(
        update(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.id == claim.job_id,
            ClinicalModelShadowEvaluationJob.status == "running",
            ClinicalModelShadowEvaluationJob.lease_owner == claim.worker_id,
            ClinicalModelShadowEvaluationJob.lease_token == claim.lease_token,
        )
        .values(
            status=target,
            active_binding_id=row.binding_id if retry else None,
            lease_owner=None,
            lease_token=None,
            lease_expires_at=None,
            next_attempt_at=current + timedelta(seconds=retry_delay_seconds),
            error_code=error_code,
            completed_at=None if retry else current,
            updated_at=current,
        )
    )
    if not changed.rowcount:
        await db.rollback()
        return None
    if not retry:
        await _ensure_dead_letter(db, row, error_code=error_code, now=current)
    await log_action(
        db, row.created_by_user_id, "shadow-worker",
        (
            "clinical_model_shadow_job.retry_scheduled"
            if retry else "clinical_model_shadow_job.failed"
        ),
        "clinical_model_shadow_evaluation_job", row.id,
        details={
            "error_code": error_code,
            "attempt_count": row.attempt_count,
            "max_attempts": row.max_attempts,
            "retry_scheduled": retry,
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
        },
        organization_id=row.organization_id,
        status="error" if not retry else "success",
    )
    await db.commit()
    get_clinical_shadow_metrics().record(
        "retry_scheduled" if retry else "failed"
    )
    return target


async def settle_claimed_shadow_job(
    db: AsyncSession,
    claim: ClaimedShadowJob,
    observation: dict[str, Any],
    *,
    now: datetime | None = None,
) -> ClinicalModelShadowEvaluation | None:
    """Fence terminal mutation, persist aggregate evaluation and roll back once."""

    validate_shadow_observation(observation)
    current = now or await database_utc_now(db)
    fenced = await db.execute(
        update(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.id == claim.job_id,
            ClinicalModelShadowEvaluationJob.status == "running",
            ClinicalModelShadowEvaluationJob.lease_owner == claim.worker_id,
            ClinicalModelShadowEvaluationJob.lease_token == claim.lease_token,
            ClinicalModelShadowEvaluationJob.lease_expires_at > current,
        )
        .values(updated_at=current)
    )
    if not fenced.rowcount:
        await db.rollback()
        return None
    job = await db.get(ClinicalModelShadowEvaluationJob, claim.job_id)
    if job is None:
        await db.rollback()
        return None
    await db.execute(
        select(Organization).where(
            Organization.id == job.organization_id,
        ).with_for_update()
    )
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding)
            .where(
                ClinicalModelShadowBinding.id == job.binding_id,
                ClinicalModelShadowBinding.organization_id == job.organization_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        binding is None
        or binding.record_version != job.binding_record_version
        or binding.package_id != job.package_id
        or binding.attestation_id != job.attestation_id
    ):
        job.status = "failed"
        job.active_binding_id = None
        job.error_code = "BINDING_CHANGED"
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        job.completed_at = current
        await _ensure_dead_letter(
            db, job, error_code="BINDING_CHANGED", now=current,
        )
        user = await db.get(User, job.created_by_user_id)
        username = user.username if user is not None else "shadow-job-requester"
        await log_action(
            db, job.created_by_user_id, username,
            "clinical_model_shadow_job.failed",
            "clinical_model_shadow_evaluation_job", job.id,
            details={
                "binding_id": job.binding_id,
                "use_case": job.use_case,
                "error_code": "BINDING_CHANGED",
                "attempt_count": job.attempt_count,
                "aggregate_only": True,
                "patient_data_used": False,
                "predictions_emitted": False,
                "production_inference_enabled": False,
            },
            organization_id=job.organization_id,
        )
        await db.commit()
        return None

    before_version = binding.record_version
    rollback_performed = False
    if observation["result"] == "passed":
        binding.evaluation_gate_status = "passed"
    else:
        binding.evaluation_gate_status = "stopped"
        if binding.previous_package_id and binding.previous_attestation_id:
            target_attestation = (
                await db.execute(
                    select(ClinicalModelArtifactAttestation).where(
                        ClinicalModelArtifactAttestation.id
                        == binding.previous_attestation_id,
                        ClinicalModelArtifactAttestation.organization_id
                        == job.organization_id,
                        ClinicalModelArtifactAttestation.package_id
                        == binding.previous_package_id,
                    )
                )
            ).scalar_one_or_none()
            target_package = (
                await db.execute(
                    select(ClinicalModelPackage).where(
                        ClinicalModelPackage.id == binding.previous_package_id,
                        ClinicalModelPackage.organization_id == job.organization_id,
                        ClinicalModelPackage.use_case == job.use_case,
                        ClinicalModelPackage.status.in_(["approved", "active"]),
                    )
                )
            ).scalar_one_or_none()
            if target_attestation is not None and target_package is not None:
                failed_package_id = binding.package_id
                failed_attestation_id = binding.attestation_id
                binding.package_id = target_package.id
                binding.attestation_id = target_attestation.id
                binding.previous_package_id = failed_package_id
                binding.previous_attestation_id = failed_attestation_id
                binding.evaluation_gate_status = "not_evaluated"
                rollback_performed = True
    binding.record_version += 1
    binding.bound_by_user_id = job.created_by_user_id
    evaluation_id = str(uuid.uuid4())
    binding.last_evaluation_id = evaluation_id
    binding.last_evaluated_at = current
    evaluation = ClinicalModelShadowEvaluation(
        id=evaluation_id,
        organization_id=job.organization_id,
        binding_id=binding.id,
        use_case=job.use_case,
        package_id=job.package_id,
        attestation_id=job.attestation_id,
        source=observation["source"],
        suite_id=observation["suite_id"],
        suite_sha256=observation["suite_sha256"],
        artifact_sha256=observation["artifact_sha256"],
        observation_report_sha256=observation["observation_report_sha256"],
        result=observation["result"],
        reason_code=observation["reason_code"],
        fault_mode=observation["fault_mode"],
        run_count=observation["run_count"],
        vector_observation_count=observation["vector_observation_count"],
        success_count=observation["success_count"],
        mismatch_count=observation["mismatch_count"],
        error_count=observation["error_count"],
        latency_p50_ms=observation["latency_p50_ms"],
        latency_p95_ms=observation["latency_p95_ms"],
        artifact_reverified=observation["artifact_reverified"],
        rollback_performed=rollback_performed,
        binding_version_before=before_version,
        binding_version_after=binding.record_version,
        evaluated_by_user_id=job.created_by_user_id,
        created_at=current,
    )
    db.add(evaluation)
    job.status = observation["result"]
    job.active_binding_id = None
    job.evaluation_id = evaluation_id
    job.error_code = None
    job.rollback_performed = rollback_performed
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.completed_at = current
    user = await db.get(User, job.created_by_user_id)
    username = user.username if user is not None else "shadow-job-requester"
    await log_action(
        db, job.created_by_user_id, username,
        "clinical_model_shadow_job.completed",
        "clinical_model_shadow_evaluation_job", job.id,
        details={
            "binding_id": binding.id,
            "evaluation_id": evaluation_id,
            "use_case": job.use_case,
            "result": observation["result"],
            "reason_code": observation["reason_code"],
            "fault_mode": observation["fault_mode"],
            "attempt_count": job.attempt_count,
            "rollback_performed": rollback_performed,
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
            "network_used": False,
            "production_inference_enabled": False,
        },
        organization_id=job.organization_id,
    )
    if rollback_performed:
        await log_action(
            db, job.created_by_user_id, username,
            "clinical_model_shadow_job.auto_rolled_back",
            "clinical_model_shadow_binding", binding.id,
            details={
                "job_id": job.id,
                "evaluation_id": evaluation_id,
                "failed_package_id": job.package_id,
                "failed_attestation_id": job.attestation_id,
                "restored_package_id": binding.package_id,
                "restored_attestation_id": binding.attestation_id,
                "binding_version_after": binding.record_version,
                "aggregate_only": True,
                "patient_data_used": False,
                "predictions_emitted": False,
                "production_inference_enabled": False,
            },
            organization_id=job.organization_id,
        )
    await db.commit()
    get_clinical_shadow_metrics().record(observation["result"])
    await db.refresh(evaluation)
    return evaluation


async def _load_claim_artifact_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    claim: ClaimedShadowJob,
) -> tuple[dict[str, object], dict[str, object]]:
    async with session_factory() as db:
        job = await db.get(ClinicalModelShadowEvaluationJob, claim.job_id)
        package = await db.get(ClinicalModelPackage, claim.package_id)
        attestation = await db.get(
            ClinicalModelArtifactAttestation, claim.attestation_id,
        )
        if (
            job is None
            or package is None
            or attestation is None
            or job.status != "running"
            or job.lease_owner != claim.worker_id
            or job.lease_token != claim.lease_token
            or package.organization_id != claim.organization_id
            or attestation.organization_id != claim.organization_id
            or attestation.package_id != package.id
            or package.model_kind != "synthetic-shadow-fixture"
        ):
            raise ClinicalModelShadowJobError("SHADOW_JOB_ARTIFACT_SNAPSHOT_INVALID")
        return (
            {
                "package_key": package.package_key,
                "package_version": package.package_version,
                "package_sha256": package.package_sha256,
                "use_case": package.use_case,
                "runtime_contract": package.runtime_contract,
                "training_dataset_sha256": package.training_dataset_sha256,
                "training_case_count": package.training_case_count,
            },
            {
                "bundle_content_sha256": attestation.bundle_content_sha256,
                "manifest_sha256": attestation.manifest_sha256,
                "verification_report_sha256": attestation.verification_report_sha256,
                "trust_key_id": attestation.trust_key_id,
                "trust_store_sha256": attestation.trust_store_sha256,
                "sbom_sha256": attestation.sbom_sha256,
                "model_sha256": attestation.model_sha256,
            },
        )


async def execute_claimed_repository_shadow_job(
    claim: ClaimedShadowJob,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    fixture: Path = DEFAULT_FIXTURE,
) -> str:
    """Execute one repository-only claim and settle through its fence token."""

    factory = session_factory or database.AsyncSessionLocal
    try:
        package, attestation = await _load_claim_artifact_snapshot(factory, claim)
        if claim.fault_mode == "none":
            verified = await asyncio.to_thread(
                verify_bundle_directory, fixture, environment="test",
            )
            validate_verification_report(verified.report)
            expected = {
                "bundle_id": package["package_key"],
                "bundle_version": package["package_version"],
                "bundle_content_sha256": package["package_sha256"],
                "use_case": package["use_case"],
                "runtime_contract": package["runtime_contract"],
                "training_dataset_sha256": package["training_dataset_sha256"],
                "training_case_count": package["training_case_count"],
                "manifest_sha256": attestation["manifest_sha256"],
                "verification_report_sha256": attestation["verification_report_sha256"],
                "trust_key_id": attestation["trust_key_id"],
                "trust_store_sha256": attestation["trust_store_sha256"],
                "sbom_sha256": attestation["sbom_sha256"],
            }
            if any(verified.report.get(key) != value for key, value in expected.items()):
                raise ClinicalModelShadowJobError("SHADOW_JOB_ARTIFACT_SNAPSHOT_INVALID")
            observation = await asyncio.to_thread(run_verified_shadow_suite, verified)
            if (
                observation["artifact_sha256"]
                != attestation["bundle_content_sha256"]
                or observation["model_sha256"] != attestation["model_sha256"]
            ):
                raise ClinicalModelShadowJobError("SHADOW_JOB_ARTIFACT_SNAPSHOT_INVALID")
        else:
            observation = build_fault_observation(
                claim.fault_mode,
                artifact_sha256=str(attestation["bundle_content_sha256"]),
                model_sha256=str(attestation["model_sha256"]),
            )
        async with factory() as db:
            evaluation = await settle_claimed_shadow_job(db, claim, observation)
        if evaluation is None:
            get_clinical_shadow_metrics().record("fence_lost")
            return "fence_lost"
        return "settled"
    except (
        ClinicalModelBundleError,
        ClinicalModelShadowObservationError,
        ClinicalModelShadowProbeError,
        ClinicalModelShadowJobError,
    ):
        async with factory() as db:
            failed = await fail_claimed_shadow_job(
                db, claim,
                error_code="ARTIFACT_RESOLUTION_FAILED",
                retryable=False,
            )
        return "failed" if failed is not None else "fence_lost"
    except Exception:
        async with factory() as db:
            failed = await fail_claimed_shadow_job(
                db, claim,
                error_code="INTERNAL_WORKER_ERROR",
                retryable=True,
            )
        if failed is None:
            get_clinical_shadow_metrics().record("fence_lost")
            return "fence_lost"
        return "retry_queued" if failed == "queued" else "failed"


async def replay_shadow_dead_letter(
    db: AsyncSession,
    *,
    organization_id: str,
    dead_letter_id: str,
    idempotency_key: str,
    replayed_by_user_id: str,
    replayed_by_username: str,
    now: datetime | None = None,
) -> tuple[str, ClinicalModelShadowEvaluationJob | None]:
    """Create one new fenced job from an eligible metadata-only dead letter."""

    current = now or await database_utc_now(db)
    dead_letter = (
        await db.execute(
            select(ClinicalModelShadowDeadLetter)
            .where(
                ClinicalModelShadowDeadLetter.id == dead_letter_id,
                ClinicalModelShadowDeadLetter.organization_id == organization_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if dead_letter is None:
        await db.rollback()
        return "not_found", None
    if dead_letter.status == "replayed":
        if dead_letter.replay_idempotency_key != idempotency_key:
            return "idempotency_conflict", None
        row = await db.get(
            ClinicalModelShadowEvaluationJob, dead_letter.replayed_job_id,
        )
        return "already_replayed", row
    if dead_letter.status != "available":
        return "not_available", None
    source = await db.get(
        ClinicalModelShadowEvaluationJob, dead_letter.source_job_id,
    )
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.id == dead_letter.binding_id,
                ClinicalModelShadowBinding.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if source is None or binding is None:
        return "stale_snapshot", None
    if (
        binding.record_version != dead_letter.binding_record_version
        or binding.package_id != dead_letter.package_id
        or binding.attestation_id != dead_letter.attestation_id
    ):
        return "stale_snapshot", None
    active = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob.id).where(
                ClinicalModelShadowEvaluationJob.organization_id == organization_id,
                ClinicalModelShadowEvaluationJob.active_binding_id == binding.id,
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        return "active_conflict", None
    request_sha256 = hashlib.sha256(json.dumps(
        {
            "dead_letter_id": dead_letter.id,
            "source_job_id": dead_letter.source_job_id,
            "binding_record_version": dead_letter.binding_record_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    existing = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob).where(
                ClinicalModelShadowEvaluationJob.organization_id == organization_id,
                ClinicalModelShadowEvaluationJob.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_sha256 != request_sha256:
            return "idempotency_conflict", None
        return "already_replayed", existing
    job = ClinicalModelShadowEvaluationJob(
        id=str(uuid.uuid4()),
        organization_id=organization_id,
        binding_id=binding.id,
        active_binding_id=binding.id,
        use_case=dead_letter.use_case,
        package_id=dead_letter.package_id,
        attestation_id=dead_letter.attestation_id,
        binding_record_version=dead_letter.binding_record_version,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
        fault_mode=source.fault_mode,
        status="queued",
        attempt_count=0,
        max_attempts=source.max_attempts,
        next_attempt_at=current,
        rollback_performed=False,
        created_by_user_id=replayed_by_user_id,
        created_at=current,
        updated_at=current,
    )
    db.add(job)
    dead_letter.status = "replayed"
    dead_letter.replayed_job_id = job.id
    dead_letter.replay_idempotency_key = idempotency_key
    dead_letter.replayed_at = current
    dead_letter.replayed_by_user_id = replayed_by_user_id
    dead_letter.updated_at = current
    await log_action(
        db, replayed_by_user_id, replayed_by_username,
        "clinical_model_shadow_job.dead_letter_replayed",
        "clinical_model_shadow_dead_letter", dead_letter.id,
        details={
            "job_id": job.id,
            "source_job_id": dead_letter.source_job_id,
            "binding_id": binding.id,
            "use_case": dead_letter.use_case,
            "dead_letter_status": "replayed",
            "request_sha256": request_sha256,
            "aggregate_only": True,
            "patient_data_used": False,
            "predictions_emitted": False,
            "production_inference_enabled": False,
        },
        organization_id=organization_id,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "race_lost", None
    await db.refresh(job)
    get_clinical_shadow_metrics().record("replayed")
    get_clinical_shadow_metrics().record("queued")
    return "replayed", job


__all__ = [
    "ClaimedShadowJob",
    "ClinicalModelShadowJobError",
    "DEFAULT_FIXTURE",
    "DEFAULT_LEASE_SECONDS",
    "MAXIMUM_LEASE_SECONDS",
    "MINIMUM_LEASE_SECONDS",
    "claim_next_shadow_job",
    "claim_shadow_job",
    "cancel_shadow_job",
    "execute_claimed_repository_shadow_job",
    "fail_claimed_shadow_job",
    "finalize_exhausted_shadow_jobs",
    "renew_shadow_job_lease",
    "replay_shadow_dead_letter",
    "settle_claimed_shadow_job",
    "summarize_shadow_job_health",
    "utc_now",
]
