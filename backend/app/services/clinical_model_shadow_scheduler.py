"""Database-fenced scheduler and persistent aggregate alert evaluation."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_model_package import (
    ClinicalModelShadowAlertState,
    ClinicalModelShadowDeadLetter,
    ClinicalModelShadowEvaluationJob,
    ClinicalModelShadowSchedulerLease,
)
from app.services.clinical_model_shadow_job import (
    database_utc_now,
    summarize_shadow_job_health,
)
from app.services.clinical_model_shadow_observability import get_clinical_shadow_metrics


SCHEDULER_NAME = "clinical-shadow-maintenance"
_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_ALERT_CODES = frozenset({
    "queue_backlog", "queue_age_exceeded", "expired_leases",
    "exhausted_jobs", "dead_letter_backlog",
})


@dataclass(frozen=True, slots=True)
class ShadowSchedulerLease:
    scheduler_name: str
    owner: str
    token: str
    generation: int
    expires_at: datetime


def _owner(value: str) -> str:
    result = value.strip()
    if _OWNER.fullmatch(result) is None:
        raise ValueError("SHADOW_SCHEDULER_OWNER_INVALID")
    return result


async def acquire_shadow_scheduler_lease(
    db: AsyncSession,
    *,
    owner: str,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> ShadowSchedulerLease | None:
    current = now or await database_utc_now(db)
    validated_owner = _owner(owner)
    seconds = max(5, min(int(lease_seconds), 300))
    token = str(uuid.uuid4())
    row = await db.get(ClinicalModelShadowSchedulerLease, SCHEDULER_NAME)
    if row is None:
        row = ClinicalModelShadowSchedulerLease(
            scheduler_name=SCHEDULER_NAME,
            lease_owner=validated_owner,
            lease_token=token,
            lease_expires_at=current + timedelta(seconds=seconds),
            generation=1,
            last_cycle_started_at=current,
            created_at=current,
            updated_at=current,
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            get_clinical_shadow_metrics().record("scheduler_lease_contended")
            return None
        return ShadowSchedulerLease(
            SCHEDULER_NAME, validated_owner, token, 1, row.lease_expires_at,
        )
    expires = row.lease_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires > current and row.lease_owner != validated_owner:
        await db.rollback()
        get_clinical_shadow_metrics().record("scheduler_lease_contended")
        return None
    generation = row.generation + 1
    changed = await db.execute(
        update(ClinicalModelShadowSchedulerLease)
        .where(
            ClinicalModelShadowSchedulerLease.scheduler_name == SCHEDULER_NAME,
            or_(
                ClinicalModelShadowSchedulerLease.lease_expires_at <= current,
                ClinicalModelShadowSchedulerLease.lease_owner == validated_owner,
            ),
        )
        .values(
            lease_owner=validated_owner,
            lease_token=token,
            lease_expires_at=current + timedelta(seconds=seconds),
            generation=generation,
            last_cycle_started_at=current,
            last_cycle_status=None,
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    if not changed.rowcount:
        await db.rollback()
        get_clinical_shadow_metrics().record("scheduler_lease_contended")
        return None
    await db.commit()
    return ShadowSchedulerLease(
        SCHEDULER_NAME, validated_owner, token, generation,
        current + timedelta(seconds=seconds),
    )


async def renew_shadow_scheduler_lease(
    db: AsyncSession,
    lease: ShadowSchedulerLease,
    *,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> bool:
    current = now or await database_utc_now(db)
    seconds = max(5, min(int(lease_seconds), 300))
    changed = await db.execute(
        update(ClinicalModelShadowSchedulerLease)
        .where(
            ClinicalModelShadowSchedulerLease.scheduler_name == lease.scheduler_name,
            ClinicalModelShadowSchedulerLease.lease_owner == lease.owner,
            ClinicalModelShadowSchedulerLease.lease_token == lease.token,
            ClinicalModelShadowSchedulerLease.generation == lease.generation,
            ClinicalModelShadowSchedulerLease.lease_expires_at > current,
        )
        .values(
            lease_expires_at=current + timedelta(seconds=seconds),
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return bool(changed.rowcount)


async def complete_shadow_scheduler_cycle(
    db: AsyncSession,
    lease: ShadowSchedulerLease,
    *,
    succeeded: bool,
    now: datetime | None = None,
) -> bool:
    current = now or await database_utc_now(db)
    changed = await db.execute(
        update(ClinicalModelShadowSchedulerLease)
        .where(
            ClinicalModelShadowSchedulerLease.scheduler_name == lease.scheduler_name,
            ClinicalModelShadowSchedulerLease.lease_owner == lease.owner,
            ClinicalModelShadowSchedulerLease.lease_token == lease.token,
            ClinicalModelShadowSchedulerLease.generation == lease.generation,
            ClinicalModelShadowSchedulerLease.lease_expires_at > current,
        )
        .values(
            lease_expires_at=current,
            last_cycle_completed_at=current,
            last_cycle_status="succeeded" if succeeded else "failed",
            updated_at=current,
        )
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    completed = bool(changed.rowcount)
    if completed:
        get_clinical_shadow_metrics().record(
            "scheduler_cycle_succeeded" if succeeded else "scheduler_cycle_failed"
        )
    return completed


async def evaluate_persistent_shadow_alerts(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    queue_alert_count: int = 10,
    max_queue_age_seconds: int = 300,
    expired_lease_alert_count: int = 1,
    dead_letter_alert_count: int = 1,
) -> dict[str, int]:
    """Persist only aggregate alert episodes and return aggregate transitions."""

    current = now or await database_utc_now(db)
    organization_ids = set((await db.scalars(
        select(ClinicalModelShadowEvaluationJob.organization_id).distinct()
    )).all())
    organization_ids.update((await db.scalars(
        select(ClinicalModelShadowDeadLetter.organization_id).distinct()
    )).all())
    organization_ids.update((await db.scalars(
        select(ClinicalModelShadowAlertState.organization_id).distinct()
    )).all())
    fired = resolved = evaluated = 0
    for organization_id in sorted(organization_ids):
        health = await summarize_shadow_job_health(
            db,
            organization_id=organization_id,
            now=current,
            queue_alert_count=queue_alert_count,
            max_queue_age_seconds=max_queue_age_seconds,
            expired_lease_alert_count=expired_lease_alert_count,
            dead_letter_alert_count=dead_letter_alert_count,
        )
        firing_codes = set(health["alert_codes"])
        states = {
            row.alert_code: row
            for row in (await db.scalars(
                select(ClinicalModelShadowAlertState).where(
                    ClinicalModelShadowAlertState.organization_id == organization_id,
                )
            )).all()
        }
        for code in sorted(_ALERT_CODES):
            row = states.get(code)
            should_fire = code in firing_codes
            if row is None and should_fire:
                db.add(ClinicalModelShadowAlertState(
                    id=str(uuid.uuid4()),
                    organization_id=organization_id,
                    alert_code=code,
                    state="firing",
                    occurrence_count=1,
                    opened_at=current,
                    last_evaluated_at=current,
                    last_transition_at=current,
                    resolved_at=None,
                    created_at=current,
                    updated_at=current,
                ))
                fired += 1
                get_clinical_shadow_metrics().record("alert_fired")
            elif row is not None:
                row.last_evaluated_at = current
                row.updated_at = current
                if should_fire and row.state == "resolved":
                    row.state = "firing"
                    row.occurrence_count += 1
                    row.opened_at = current
                    row.last_transition_at = current
                    row.resolved_at = None
                    fired += 1
                    get_clinical_shadow_metrics().record("alert_fired")
                elif not should_fire and row.state == "firing":
                    row.state = "resolved"
                    row.last_transition_at = current
                    row.resolved_at = current
                    resolved += 1
                    get_clinical_shadow_metrics().record("alert_resolved")
        evaluated += 1
    await db.commit()
    return {
        "organizations_evaluated": evaluated,
        "alerts_fired": fired,
        "alerts_resolved": resolved,
        "aggregate_only": 1,
    }


__all__ = [
    "SCHEDULER_NAME",
    "ShadowSchedulerLease",
    "acquire_shadow_scheduler_lease",
    "complete_shadow_scheduler_cycle",
    "evaluate_persistent_shadow_alerts",
    "renew_shadow_scheduler_lease",
]
