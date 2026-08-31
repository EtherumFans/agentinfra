"""Tenant-bound, secret-free model readiness evidence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def tenant_deployment_cache_key(
    organization_id: object,
    deployment_id: str,
) -> str:
    """Bind process-local probe evidence to the tenant that authorized it."""
    return f"{str(organization_id)}:{deployment_id.strip().lower()}"


def tenant_cached_probe(
    cache: dict[str, object],
    organization_id: object,
    deployment_id: str,
) -> dict[str, object] | None:
    value = cache.get(tenant_deployment_cache_key(organization_id, deployment_id))
    return dict(value) if isinstance(value, dict) else None


@dataclass(frozen=True)
class TenantCanaryEvidence:
    status: Literal["not_run", "verified", "expired", "failed"]
    live_health_verified: bool
    checked_at: str | None
    expires_at: str | None


async def latest_tenant_canary_evidence(
    db: AsyncSession,
    *,
    organization_id: object,
    deployment_id: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> TenantCanaryEvidence:
    """Resolve durable canary evidence for this exact tenant and deployment."""
    deployment_id = deployment_id.strip().lower()
    if not deployment_id:
        return TenantCanaryEvidence("not_run", False, None, None)
    row = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.action == "model.live_canary.completed",
                AuditLog.resource_id == deployment_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return TenantCanaryEvidence("not_run", False, None, None)

    checked = row.created_at
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    else:
        checked = checked.astimezone(UTC)
    ttl_seconds = max(60, min(int(ttl_seconds), 86400))
    expires = checked + timedelta(seconds=ttl_seconds)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)
    details = row.details if isinstance(row.details, dict) else {}
    valid = (
        details.get("status") == "reachable"
        and details.get("reason_code") == "ok"
        and details.get("expected_token_matched") is True
        and details.get("patient_data_sent") is False
    )
    if not valid:
        status: Literal["not_run", "verified", "expired", "failed"] = "failed"
    elif current > expires:
        status = "expired"
    else:
        status = "verified"
    return TenantCanaryEvidence(
        status=status,
        live_health_verified=status == "verified",
        checked_at=checked.isoformat(),
        expires_at=expires.isoformat(),
    )


__all__ = [
    "TenantCanaryEvidence",
    "latest_tenant_canary_evidence",
    "tenant_cached_probe",
    "tenant_deployment_cache_key",
]
