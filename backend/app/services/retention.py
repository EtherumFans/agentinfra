"""Phase A1A Gate 4.7 — Retention + deletion policy and purge primitives.

Healthcare compliance regimes (China's 网络安全法 + PIPL, ISO 27001,
HIPAA-style minimum-necessary) require that audit logs and run
history do not live forever. The charter §4.7 deliverable is:

1. A dataclass describing the per-table TTLs.
2. ``purge_expired_*`` primitives that delete rows older than the TTL.
3. An audit emit helper that records each purge event in the audit
   log so a Security Admin can answer "what was deleted when?".

The purge primitives do NOT auto-schedule. Operators wire them to
their scheduler of choice (cron, systemd timer, Kubernetes CronJob).
A future gate may ship an in-process scheduler; the charter forbids
that for Gate 4.7 (out of scope).

Design:

- TTLs default to conservative values (audit logs: 7 years / 2557
  days; run history: 90 days; run trace events: 90 days). The
  defaults can be overridden via env vars.
- ``dry_run=True`` returns the count of rows that WOULD be deleted
  without modifying anything.
- Every successful purge emits a ``retention.purge`` audit row via
  ``tenant_owned_system_audit`` so the deletion itself is auditable.
  The audit row carries the table name, rows deleted, and cutoff
  timestamp.
- Purges are tenant-scoped when ``organization_id`` is supplied
  (per-tenant retention windows are a future deliverable; for now
  all tenants share the global TTL).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy import delete, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Defaults ────────────────────────────────────────────────────────
# Audit logs: 7 years (2557 days). Aligns with China's cybersecurity
# law §21 (network logs ≥ 6 months) and the more conservative medical
# record retention norm (病历 ≥ 30 years; audit trail at least as
# long as the underlying record). Hospitals can extend via env.
DEFAULT_AUDIT_LOG_TTL_DAYS = 2557

# Run history: 90 days. Run history is operational, not compliance —
# 90 days covers any reasonable "go back and figure out what happened"
# investigation while bounding DB growth.
DEFAULT_RUN_HISTORY_TTL_DAYS = 90

# Run trace events: 90 days (same rationale as run_history).
DEFAULT_RUN_TRACE_EVENTS_TTL_DAYS = 90


@dataclass(frozen=True)
class RetentionPolicy:
    """Per-table retention windows (in days)."""

    audit_log_ttl_days: int = DEFAULT_AUDIT_LOG_TTL_DAYS
    run_history_ttl_days: int = DEFAULT_RUN_HISTORY_TTL_DAYS
    run_trace_events_ttl_days: int = DEFAULT_RUN_TRACE_EVENTS_TTL_DAYS

    @classmethod
    def from_env(cls) -> "RetentionPolicy":
        """Read TTLs from env vars.

        Local development falls back to conservative defaults. Cloud mode
        fails closed on an invalid value so an operator typo cannot silently
        change the published retention contract.
        """

        cloud_mode = (
            os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower()
            == "cloud"
        )

        def _positive_int(name: str, default: int) -> int:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return default
            try:
                v = int(raw)
                if v > 0:
                    return v
            except ValueError:
                pass
            if cloud_mode:
                raise ValueError(
                    f"{name} must be a positive integer in cloud mode"
                )
            logger.warning(
                "retention: invalid %s=%r, falling back to %d", name, raw, default,
            )
            return default

        policy = cls(
            audit_log_ttl_days=_positive_int("ICODER_AUDIT_LOG_TTL_DAYS", DEFAULT_AUDIT_LOG_TTL_DAYS),
            run_history_ttl_days=_positive_int("ICODER_RUN_HISTORY_TTL_DAYS", DEFAULT_RUN_HISTORY_TTL_DAYS),
            run_trace_events_ttl_days=_positive_int("ICODER_RUN_TRACE_EVENTS_TTL_DAYS", DEFAULT_RUN_TRACE_EVENTS_TTL_DAYS),
        )
        if policy.run_trace_events_ttl_days > policy.run_history_ttl_days:
            if cloud_mode:
                raise ValueError(
                    "ICODER_RUN_TRACE_EVENTS_TTL_DAYS must not exceed "
                    "ICODER_RUN_HISTORY_TTL_DAYS in cloud mode"
                )
            logger.warning(
                "retention: trace TTL exceeds RunHistory TTL; clamping %d to %d",
                policy.run_trace_events_ttl_days,
                policy.run_history_ttl_days,
            )
            return cls(
                audit_log_ttl_days=policy.audit_log_ttl_days,
                run_history_ttl_days=policy.run_history_ttl_days,
                run_trace_events_ttl_days=policy.run_history_ttl_days,
            )
        return policy


# ── Purge primitives ────────────────────────────────────────────────


async def purge_expired_audit_logs(
    db: AsyncSession,
    policy: RetentionPolicy,
    *,
    dry_run: bool = False,
    organization_id: Optional[str] = None,
) -> int:
    """Delete audit_logs rows older than ``policy.audit_log_ttl_days``.

    If ``organization_id`` is supplied, only that tenant's rows are
    purged (useful for tenant offboarding). Otherwise all tenants'
    expired rows are purged.

    Returns the count of rows deleted (or would-be-deleted in dry_run).
    """
    from app.models.audit_log import AuditLog

    cutoff = datetime.now(UTC) - timedelta(days=policy.audit_log_ttl_days)
    stmt = select(func.count(AuditLog.id)).where(AuditLog.created_at < cutoff)
    if organization_id is not None:
        stmt = stmt.where(AuditLog.organization_id == organization_id)
    count = (await db.execute(stmt)).scalar_one()

    if dry_run or count == 0:
        logger.info(
            "retention: audit_logs purge dry_run=%s cutoff=%s org=%s count=%d",
            dry_run, cutoff.isoformat(), organization_id, count,
        )
        return count

    # Execute the delete.
    del_stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
    if organization_id is not None:
        del_stmt = del_stmt.where(AuditLog.organization_id == organization_id)
    result = await db.execute(del_stmt)
    deleted = result.rowcount or 0
    logger.info(
        "retention: audit_logs purge cutoff=%s org=%s deleted=%d",
        cutoff.isoformat(), organization_id, deleted,
    )
    await db.commit()
    return deleted


async def purge_expired_run_history(
    db: AsyncSession,
    policy: RetentionPolicy,
    *,
    dry_run: bool = False,
    organization_id: Optional[str] = None,
) -> dict[str, int]:
    """Delete run_history rows older than the TTL, cascading to trace events.

    Returns a dict ``{"run_history": N, "run_trace_events": M}`` with
    per-table deletion counts.
    """
    from app.models.run_history import RunHistoryModel

    try:
        from app.models.run_trace import RunTraceEventModel
    except ImportError:
        RunTraceEventModel = None  # type: ignore[assignment]

    cutoff = datetime.now(UTC) - timedelta(days=policy.run_history_ttl_days)

    # Count run_history rows first.
    count_stmt = select(func.count(RunHistoryModel.id)).where(RunHistoryModel.created_at < cutoff)
    if organization_id is not None:
        count_stmt = count_stmt.where(RunHistoryModel.organization_id == organization_id)
    rh_count = (await db.execute(count_stmt)).scalar_one()

    if dry_run:
        # Count trace events that WOULD be cascaded.
        rt_count = 0
        if RunTraceEventModel is not None:
            old_run_ids_stmt = select(RunHistoryModel.run_id).where(
                RunHistoryModel.created_at < cutoff,
            )
            if organization_id is not None:
                old_run_ids_stmt = old_run_ids_stmt.where(
                    RunHistoryModel.organization_id == organization_id,
                )
            old_run_ids = [r for (r,) in (await db.execute(old_run_ids_stmt)).all()]
            if old_run_ids:
                rt_count_stmt = select(func.count(RunTraceEventModel.id)).where(
                    RunTraceEventModel.run_id.in_(old_run_ids),
                )
                rt_count = (await db.execute(rt_count_stmt)).scalar_one()
        logger.info(
            "retention: run_history purge dry_run cutoff=%s org=%s rh=%d rt=%d",
            cutoff.isoformat(), organization_id, rh_count, rt_count,
        )
        return {"run_history": rh_count, "run_trace_events": rt_count}

    if rh_count == 0:
        logger.info(
            "retention: run_history purge no-op cutoff=%s org=%s",
            cutoff.isoformat(), organization_id,
        )
        return {"run_history": 0, "run_trace_events": 0}

    # Cascade to trace events first (FK).
    rt_deleted = 0
    if RunTraceEventModel is not None:
        old_run_ids_stmt = select(RunHistoryModel.run_id).where(
            RunHistoryModel.created_at < cutoff,
        )
        if organization_id is not None:
            old_run_ids_stmt = old_run_ids_stmt.where(
                RunHistoryModel.organization_id == organization_id,
            )
        old_run_ids = [r for (r,) in (await db.execute(old_run_ids_stmt)).all()]
        if old_run_ids:
            rt_del = delete(RunTraceEventModel).where(
                RunTraceEventModel.run_id.in_(old_run_ids),
            )
            rt_result = await db.execute(rt_del)
            rt_deleted = rt_result.rowcount or 0

    # Then delete run_history.
    rh_del = delete(RunHistoryModel).where(RunHistoryModel.created_at < cutoff)
    if organization_id is not None:
        rh_del = rh_del.where(RunHistoryModel.organization_id == organization_id)
    rh_result = await db.execute(rh_del)
    rh_deleted = rh_result.rowcount or 0

    logger.info(
        "retention: run_history purge cutoff=%s org=%s rh=%d rt=%d",
        cutoff.isoformat(), organization_id, rh_deleted, rt_deleted,
    )
    await db.commit()
    return {"run_history": rh_deleted, "run_trace_events": rt_deleted}


async def purge_expired_run_trace_events(
    db: AsyncSession,
    policy: RetentionPolicy,
    *,
    dry_run: bool = False,
    organization_id: Optional[str] = None,
) -> dict[str, int]:
    """Purge retained trace events without deleting their RunHistory rows.

    Only terminal runs are eligible. This prevents an operator schedule from
    deleting the prefix of a legitimately long-running stream. Each affected
    RunHistory row receives a durable purge timestamp and cumulative count so
    subsequent SSE resume attempts can return 410 instead of conflating an
    expired cursor with a cursor that never belonged to the run.
    """
    from app.models.run_history import RunHistoryModel
    from app.models.run_trace import RunTraceEventModel
    from app.services.run_lifecycle import RunStatus

    cutoff = datetime.now(UTC) - timedelta(
        days=policy.run_trace_events_ttl_days
    )
    terminal_statuses = (
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.COMPLETED_AFTER_CLIENT_ABORT,
    )
    conditions = [
        RunTraceEventModel.created_at < cutoff,
        RunHistoryModel.status.in_(terminal_statuses),
    ]
    if organization_id is not None:
        conditions.append(RunHistoryModel.organization_id == organization_id)

    grouped_stmt = (
        select(RunTraceEventModel.run_id, func.count(RunTraceEventModel.id))
        .join(
            RunHistoryModel,
            RunHistoryModel.run_id == RunTraceEventModel.run_id,
        )
        .where(*conditions)
        .group_by(RunTraceEventModel.run_id)
    )
    grouped = [
        (str(run_id), int(count))
        for run_id, count in (await db.execute(grouped_stmt)).all()
    ]
    total = sum(count for _, count in grouped)
    result = {"run_trace_events": total, "runs_affected": len(grouped)}
    if dry_run or total == 0:
        logger.info(
            "retention: run_trace_events purge dry_run=%s cutoff=%s org=%s events=%d runs=%d",
            dry_run,
            cutoff.isoformat(),
            organization_id,
            total,
            len(grouped),
        )
        return result

    purged_at = datetime.now(UTC)
    for run_id, count in grouped:
        await db.execute(
            update(RunHistoryModel)
            .where(RunHistoryModel.run_id == run_id)
            .values(
                trace_events_purged_at=purged_at,
                trace_events_purged_count=(
                    func.coalesce(RunHistoryModel.trace_events_purged_count, 0)
                    + count
                ),
            )
        )

    eligible_ids = (
        select(RunTraceEventModel.id)
        .join(
            RunHistoryModel,
            RunHistoryModel.run_id == RunTraceEventModel.run_id,
        )
        .where(*conditions)
    )
    delete_result = await db.execute(
        delete(RunTraceEventModel).where(
            RunTraceEventModel.id.in_(eligible_ids)
        )
    )
    deleted = int(delete_result.rowcount or 0)
    if deleted != total:
        await db.rollback()
        raise RuntimeError(
            "run_trace retention count changed during purge; transaction rolled back"
        )

    await emit_purge_audit(
        db,
        table_name="run_trace_events",
        rows_deleted=deleted,
        cutoff=cutoff,
        organization_id=organization_id,
    )
    await db.commit()
    logger.info(
        "retention: run_trace_events purge cutoff=%s org=%s events=%d runs=%d",
        cutoff.isoformat(),
        organization_id,
        deleted,
        len(grouped),
    )
    return {"run_trace_events": deleted, "runs_affected": len(grouped)}


# ── Purge audit emit ────────────────────────────────────────────────


async def emit_purge_audit(
    db: AsyncSession,
    *,
    table_name: str,
    rows_deleted: int,
    cutoff: datetime,
    organization_id: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """Record a ``retention.purge`` audit event.

    Use after every successful purge so the deletion itself is
    auditable. The event uses ``tenant_owned_system_audit`` when
    ``organization_id`` is set, else falls back to ``system_audit``.
    """
    from app.services.system_audit import system_audit, tenant_owned_system_audit

    details = {
        "table": table_name,
        "rows_deleted": rows_deleted,
        "cutoff": cutoff.isoformat(),
        "dry_run": dry_run,
    }
    if organization_id:
        await tenant_owned_system_audit(
            db,
            organization_id=organization_id,
            action="retention.purge",
            resource_type="retention",
            resource_id=table_name,
            details=details,
        )
    else:
        await system_audit(
            db,
            action="retention.purge",
            resource_type="retention",
            resource_id=table_name,
            details=details,
        )


async def purge_expired_agent_feedback(
    db: AsyncSession,
    *,
    dry_run: bool = False,
    organization_id: Optional[str] = None,
    now: datetime | None = None,
) -> int:
    """Physically remove Task feedback after each row's bounded deadline."""
    from app.models.agent_feedback import (
        AgentTaskFeedback,
        FeedbackTrainingAuthorization,
    )

    cutoff = now or datetime.now(UTC)
    count_stmt = select(func.count(AgentTaskFeedback.id)).where(
        AgentTaskFeedback.retention_until <= cutoff
    )
    if organization_id is not None:
        count_stmt = count_stmt.where(
            AgentTaskFeedback.organization_id == organization_id
        )
    count = int((await db.execute(count_stmt)).scalar_one())
    if dry_run or count == 0:
        return count
    feedback_ids = select(AgentTaskFeedback.id).where(
        AgentTaskFeedback.retention_until <= cutoff
    )
    if organization_id is not None:
        feedback_ids = feedback_ids.where(
            AgentTaskFeedback.organization_id == organization_id
        )
    await db.execute(delete(FeedbackTrainingAuthorization).where(
        FeedbackTrainingAuthorization.feedback_id.in_(feedback_ids)
    ))
    delete_stmt = delete(AgentTaskFeedback).where(
        AgentTaskFeedback.retention_until <= cutoff
    )
    if organization_id is not None:
        delete_stmt = delete_stmt.where(
            AgentTaskFeedback.organization_id == organization_id
        )
    result = await db.execute(delete_stmt)
    deleted = int(result.rowcount or 0)
    await emit_purge_audit(
        db,
        table_name="agent_task_feedback",
        rows_deleted=deleted,
        cutoff=cutoff,
        organization_id=organization_id,
    )
    await db.commit()
    return deleted


async def purge_expired_conversation_memory(
    db: AsyncSession,
    *,
    dry_run: bool = False,
    organization_id: Optional[str] = None,
    now: datetime | None = None,
) -> int:
    """Hard-delete governed memory at its row-specific consent deadline.

    Legacy ConversationMemory rows have no ``retention_until`` and are outside
    this primitive; their older context lifecycle remains unchanged.
    """
    from app.models.memory import ConversationMemory, MemoryConsent

    cutoff = now or datetime.now(UTC)
    conditions = [
        ConversationMemory.consent_id.is_not(None),
        ConversationMemory.retention_until.is_not(None),
        ConversationMemory.retention_until <= cutoff,
    ]
    if organization_id is not None:
        conditions.append(ConversationMemory.organization_id == organization_id)
    count = int((await db.execute(
        select(func.count(ConversationMemory.id)).where(*conditions)
    )).scalar_one())
    if dry_run:
        return count

    consent_conditions = [
        MemoryConsent.status == "active",
        MemoryConsent.expires_at <= cutoff,
    ]
    if organization_id is not None:
        consent_conditions.append(MemoryConsent.organization_id == organization_id)
    await db.execute(
        update(MemoryConsent)
        .where(*consent_conditions)
        .values(status="expired")
        .execution_options(synchronize_session=False)
    )
    if count == 0:
        await db.commit()
        return 0
    result = await db.execute(
        delete(ConversationMemory)
        .where(*conditions)
        .execution_options(synchronize_session=False)
    )
    deleted = int(result.rowcount or 0)
    await emit_purge_audit(
        db,
        table_name="conversation_memories",
        rows_deleted=deleted,
        cutoff=cutoff,
        organization_id=organization_id,
    )
    await db.commit()
    return deleted


__all__ = [
    "RetentionPolicy",
    "purge_expired_audit_logs",
    "purge_expired_run_history",
    "purge_expired_run_trace_events",
    "purge_expired_agent_feedback",
    "purge_expired_conversation_memory",
    "emit_purge_audit",
    "DEFAULT_AUDIT_LOG_TTL_DAYS",
    "DEFAULT_RUN_HISTORY_TTL_DAYS",
    "DEFAULT_RUN_TRACE_EVENTS_TTL_DAYS",
]
