from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.model_readiness import (
    latest_tenant_canary_evidence,
    tenant_cached_probe,
    tenant_deployment_cache_key,
)


class _Result:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class _Db:
    def __init__(self, row):
        self.row = row

    async def execute(self, _statement):
        return _Result(self.row)


def test_process_probe_cache_is_tenant_and_deployment_bound() -> None:
    cache = {
        tenant_deployment_cache_key("org-a", "deepseek"): {"status": "reachable"},
    }

    assert tenant_cached_probe(cache, "org-a", "deepseek") == {
        "status": "reachable"
    }
    assert tenant_cached_probe(cache, "org-b", "deepseek") is None
    assert tenant_cached_probe(cache, "org-a", "qwen") is None


@pytest.mark.asyncio
async def test_durable_canary_evidence_is_verified_only_inside_ttl() -> None:
    checked = datetime(2026, 8, 23, 1, 0, tzinfo=UTC)
    row = SimpleNamespace(
        created_at=checked.replace(tzinfo=None),
        details={
            "status": "reachable",
            "reason_code": "ok",
            "expected_token_matched": True,
            "patient_data_sent": False,
        },
    )

    fresh = await latest_tenant_canary_evidence(
        _Db(row),
        organization_id="org-a",
        deployment_id="deepseek",
        ttl_seconds=900,
        now=checked + timedelta(seconds=899),
    )
    expired = await latest_tenant_canary_evidence(
        _Db(row),
        organization_id="org-a",
        deployment_id="deepseek",
        ttl_seconds=900,
        now=checked + timedelta(seconds=901),
    )

    assert fresh.status == "verified"
    assert fresh.live_health_verified is True
    assert expired.status == "expired"
    assert expired.live_health_verified is False
    assert fresh.checked_at == "2026-08-23T01:00:00+00:00"
    assert fresh.expires_at == "2026-08-23T01:15:00+00:00"


@pytest.mark.asyncio
async def test_failed_or_missing_canary_never_becomes_live_health() -> None:
    failed_row = SimpleNamespace(
        created_at=datetime(2026, 8, 23, 1, 0),
        details={
            "status": "reachable",
            "reason_code": "ok",
            "expected_token_matched": True,
            "patient_data_sent": True,
        },
    )
    failed = await latest_tenant_canary_evidence(
        _Db(failed_row),
        organization_id="org-a",
        deployment_id="deepseek",
        ttl_seconds=900,
        now=datetime(2026, 8, 23, 1, 1, tzinfo=UTC),
    )
    missing = await latest_tenant_canary_evidence(
        _Db(None),
        organization_id="org-a",
        deployment_id="deepseek",
        ttl_seconds=900,
    )

    assert failed.status == "failed"
    assert failed.live_health_verified is False
    assert missing.status == "not_run"
    assert missing.checked_at is None

