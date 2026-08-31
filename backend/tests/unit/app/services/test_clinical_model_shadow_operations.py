from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.clinical_model_shadow_observability import ClinicalShadowMetrics
from app.services.clinical_model_shadow_queue import (
    DatabasePollingShadowQueue,
    ShadowQueueConfigurationError,
    build_shadow_queue_adapter,
)
from app.services.clinical_model_shadow_job import database_utc_now


@pytest.mark.asyncio
async def test_database_queue_is_phi_free_durable_fallback() -> None:
    adapter = build_shadow_queue_adapter(backend="database")
    assert isinstance(adapter, DatabasePollingShadowQueue)
    assert await adapter.notify("11111111-1111-1111-1111-111111111111") is True
    with pytest.raises(ValueError, match="SHADOW_QUEUE_JOB_ID_INVALID"):
        await adapter.notify("patient-name")
    await adapter.close()


def test_queue_configuration_fails_closed() -> None:
    with pytest.raises(ShadowQueueConfigurationError, match="BACKEND_INVALID"):
        build_shadow_queue_adapter(backend="unknown")
    with pytest.raises(ShadowQueueConfigurationError, match="URL_REQUIRED"):
        build_shadow_queue_adapter(backend="redis_signal")
    with pytest.raises(ShadowQueueConfigurationError, match="TLS_REQUIRED"):
        build_shadow_queue_adapter(
            backend="redis_signal",
            redis_url="redis://localhost:6379/0",
        )


def test_shadow_metrics_are_bounded_and_low_cardinality() -> None:
    metrics = ClinicalShadowMetrics()
    metrics.record("queued")
    metrics.record("dead_lettered", 2)
    snapshot = metrics.snapshot()
    assert snapshot["events_total"] == 3
    assert snapshot["events"]["queued"] == 1
    assert snapshot["events"]["dead_lettered"] == 2
    assert snapshot["patient_labels_present"] is False
    assert snapshot["tenant_labels_present"] is False
    assert snapshot["job_labels_present"] is False
    with pytest.raises(ValueError, match="EVENT_INVALID"):
        metrics.record("patient-123")


@pytest.mark.asyncio
async def test_lease_clock_is_database_authoritative_and_utc() -> None:
    import app.database as database

    before = datetime.now(UTC) - timedelta(seconds=2)
    async with database.AsyncSessionLocal() as db:
        observed = await database_utc_now(db)
    after = datetime.now(UTC) + timedelta(seconds=2)
    assert observed.tzinfo is not None
    assert before <= observed <= after
