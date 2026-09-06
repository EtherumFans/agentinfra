"""A2A fast-path audit ownership must exist without test-seeded run rows."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app import database
from app.api import run_trace as trace_api
from app.coding_runtime.base import CodingResult
from app.icoder.agent_runtime import a2a_facade as facade
from app.icoder.agent_runtime.orchestrator import run_trace
from app.models.run_history import RunHistoryModel
from app.services import run_lifecycle
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


@pytest_asyncio.fixture
async def audit_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(RunHistoryModel.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", sessions)
    store = run_trace.RunTraceStore()
    monkeypatch.setattr(run_trace, "get_default_store", lambda: store)
    monkeypatch.setattr(trace_api, "get_default_store", lambda: store)
    monkeypatch.setattr(trace_api, "_emit_console_system_audit", AsyncMock())
    monkeypatch.setenv("ICODER_RESULT_ATTESTATION_KEY", "test-only-attestation-key-32-bytes-minimum")
    yield sessions
    await engine.dispose()


def _input():
    return {
        "dispatch_input": {
            "agent_id": "medical-coding-agent", "input_text": "synthetic evidence",
            "extra": None, "runtime_mode": "corti_like_fast",
            "include_trace": True, "include_evidence": True,
            "run_id": "run-audit-test", "trace_id": "trace-audit-test",
            "user_id": "user-a", "tenant_id": "org-a",
        },
        "context_id": "context-audit-test", "source_text": "synthetic evidence",
    }


def _result(error=False):
    return CodingResult(
        codes=[], run_id="run-audit-test", trace_id="trace-audit-test",
        llm_provider="mock", cost={"amount": 0.125},
        raw_schema=MedicalCodingOutputSchema(
            review_conclusion="WARNING", manual_review_required=True,
            confidence=0.0, provider="mock", model="mock",
        ).to_dict(),
        error=error, error_reason="provider_failure" if error else "",
        trace_events=[{"step": "llm_call", "status": "failed" if error else "ok"}],
    )


async def _row(sessions):
    async with sessions() as db:
        return await run_lifecycle.get_run_status(db, run_id="run-audit-test")


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [False, True])
async def test_committed_owned_run_before_dispatch_and_scoped_trace(audit_db, monkeypatch, error):
    async def dispatch(**kwargs):
        row = await _row(audit_db)
        assert row.status == "RUNNING"
        assert row.organization_id == kwargs["tenant_id"] == "org-a"
        assert row.user_id == "user-a"
        assert row.tenancy_classification == "MODERN"
        return _result(error), kwargs["run_id"], kwargs["trace_id"]

    monkeypatch.setattr(facade, "dispatch_medical_coding_fast", dispatch)
    response = await facade.run_medical_coding_a2a(**_input())
    assert response.kind == ("error" if error else "message")
    row = await _row(audit_db)
    assert row.status == ("FAILED" if error else "COMPLETED")
    assert row.error is error
    assert row.cost_usd == 0.125
    assert row.context_id == "context-audit-test"

    request = Request({"type": "http", "headers": []})
    monkeypatch.setattr(trace_api, "get_request_tenant", lambda _: "org-a")
    trace = await trace_api._get_run_trace_impl(row.run_id, "raw", request)
    assert trace["run_id"] == row.run_id
    assert trace["trace_attestation"]
    assert any(event["step"] == "llm_call" for event in trace["events"])
    monkeypatch.setattr(trace_api, "get_request_tenant", lambda _: "org-b")
    with pytest.raises(HTTPException) as caught:
        await trace_api._get_run_trace_impl(row.run_id, "raw", request)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_start_failure_prevents_provider_call(audit_db, monkeypatch):
    dispatch = AsyncMock()
    monkeypatch.setattr(facade, "dispatch_medical_coding_fast", dispatch)
    monkeypatch.setattr(run_lifecycle, "record_run_start", AsyncMock(side_effect=RuntimeError("db unavailable")))
    response = await facade.run_medical_coding_a2a(**_input())
    assert response.kind == "error"
    assert response.error["code"] == "RUN_AUDIT_UNAVAILABLE"
    dispatch.assert_not_awaited()
    assert await _row(audit_db) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["dispatch", "projection", "changed_run_id"])
async def test_execution_failures_finalize_failed(audit_db, monkeypatch, failure):
    dispatch = AsyncMock(return_value=(_result(), "run-audit-test", "trace-audit-test"))
    if failure == "dispatch":
        dispatch.side_effect = RuntimeError("sensitive provider error")
    elif failure == "projection":
        monkeypatch.setattr(facade, "build_medical_coding_inbound_response", lambda **_: (_ for _ in ()).throw(ValueError("sensitive output")))
    else:
        dispatch.return_value = (_result(), "run-wrong", "trace-audit-test")
    monkeypatch.setattr(facade, "dispatch_medical_coding_fast", dispatch)
    response = await facade.run_medical_coding_a2a(**_input())
    assert response.kind == "error"
    assert "sensitive" not in str(response.error)
    assert (await _row(audit_db)).status == "FAILED"


@pytest.mark.asyncio
async def test_finalization_failure_withholds_success(audit_db, monkeypatch):
    monkeypatch.setattr(facade, "dispatch_medical_coding_fast", AsyncMock(
        return_value=(_result(), "run-audit-test", "trace-audit-test")))
    real_set_status = run_lifecycle.set_status

    async def unavailable_finalization(db, **kwargs):
        if kwargs["status"] != "RUNNING":
            raise RuntimeError("db unavailable")
        return await real_set_status(db, **kwargs)

    monkeypatch.setattr(run_lifecycle, "set_status", unavailable_finalization)
    response = await facade.run_medical_coding_a2a(**_input())
    assert response.kind == "error"
    assert response.http_status == 503
    assert response.error["code"] == "RUN_AUDIT_UNAVAILABLE"
    assert not response.parts
    assert (await _row(audit_db)).status == "RUNNING"
