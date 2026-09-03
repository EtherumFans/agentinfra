"""Phase 3-D2.5 Part A3 — Tool Dispatch Detail tests.

Verifies the 15-field ``dispatch_detail`` metadata emitted under
``TOOLS_CALL.safe_metadata.dispatch_detail`` covers the full dispatch
lifecycle (schema / phi / auth / scope / handler / duration / result /
error) and never leaks raw token / Authorization / client_secret /
secret_ref / PHI.

7 tests:
  1. success emits dispatch_detail with all 15 fields, handler_status=ok
  2. schema validation failure emits dispatch_detail with
     input_schema_validation=failed, error_stage=schema
  3. scope failure emits dispatch_detail with scope_check=failed,
     error_stage=scope, error_code=-32012
  4. handler failure emits dispatch_detail with handler_status=failed,
     error_stage=handler_invoke
  5. dispatch_detail contains no token/secret/Authorization/PHI
  6. RunTrace API returns dispatch_detail under tools_call step
  7. (frontend vitest, separate file) RunTracePage renders Tool
     Dispatch Detail
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.icoder.mcp.auth import AuthHeader
from app.icoder.mcp.errors import MCPAuthError, MCPError, MCPErrorCode
from app.icoder.mcp.server import dispatch_tool
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    RunTraceStore,
    emit_trace_event,
)


def _seed_modern_row(run_id: str, org_id: str) -> None:
    """Seed an authoritative MODERN RunHistory row so the Phase A1A
    Gate 3R.1 orphan-run guard does not deny the trace read.

    Synchronous wrapper around the async DB work; safe to call from
    sync test bodies. Async tests should call ``_aseed_modern_row``
    instead to avoid ``asyncio.run() inside a running loop``.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async def _go() -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("DELETE FROM run_history WHERE run_id = :rid"),
                {"rid": run_id},
            )
            db.add(
                RunHistoryModel(
                    run_id=run_id,
                    agent_id="medical-coding-agent",
                    user_id="u-test-bypass",
                    cost_usd=0.0,
                    latency_ms=0,
                    runtime_mode="a2a_pure_llm",
                    status="COMPLETED",
                    organization_id=org_id,
                    tenancy_classification="MODERN",
                )
            )
            await db.commit()

    asyncio.run(_go())


async def _aseed_modern_row(run_id: str, org_id: str) -> None:
    """Async variant of ``_seed_modern_row`` for use inside ``async def``
    test bodies where ``asyncio.run()`` would collide with the running
    event loop.
    """
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM run_history WHERE run_id = :rid"),
            {"rid": run_id},
        )
        db.add(
            RunHistoryModel(
                run_id=run_id,
                agent_id="medical-coding-agent",
                user_id="u-test-bypass",
                cost_usd=0.0,
                latency_ms=0,
                runtime_mode="a2a_pure_llm",
                status="COMPLETED",
                organization_id=org_id,
                tenancy_classification="MODERN",
            )
        )
        await db.commit()


async def _aclear_run_history(run_id: str) -> None:
    """Async variant of ``_clear_run_history``."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM run_history WHERE run_id = :rid"),
            {"rid": run_id},
        )
        await db.commit()


# ── Fixtures ───────────────────────────────────────────────────────


def _build_app_state(*, phi_redactor=None) -> SimpleNamespace:
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.phi_redactor = phi_redactor
    app.state.mcp_secret_resolver = None
    app.state.mcp_http_client_factory = None
    app.state.mcp_clock = None
    return app


def _build_request(*, run_id: str, auth_header: AuthHeader | None = None,
                   app_state=None, context_id=None) -> SimpleNamespace:
    state = SimpleNamespace()
    state.run_id = run_id
    state.context_id = context_id
    state.mcp_run_auth_context = None
    state.auth_header = auth_header
    req = SimpleNamespace()
    req.state = state
    req.app = app_state or _build_app_state()
    return req


def _coding_set_dict() -> dict:
    return {
        "primary_diagnosis": {
            "code": "I50.9",
            "description": "心力衰竭",
            "confidence": 0.95,
            "category": "primary",
            "evidence": ["患者出现呼吸困难"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
    }


def _full_scopes_auth() -> AuthHeader:
    return AuthHeader(
        kind="none",
        granted_scopes=["coding:validate"],
        redacted_view="(test, coding:validate granted)",
    )


def _no_scopes_auth() -> AuthHeader:
    return AuthHeader(
        kind="none",
        granted_scopes=[],
        redacted_view="(test, no scopes)",
    )


# ── Helpers ────────────────────────────────────────────────────────


def _get_dispatch_detail(events: list, step=RunTraceStep.TOOLS_CALL) -> dict | None:
    """Extract dispatch_detail dict from the first matching step event."""
    for e in events:
        if e.step == step and "dispatch_detail" in e.safe_metadata:
            return e.safe_metadata["dispatch_detail"]
    return None


DISPATCH_DETAIL_KEYS = {
    "tool_name", "dispatch_mode",
    "round_index", "caller",
    "handler_ref",
    "input_schema_validation", "phi_redaction",
    "auth_type", "auth_resolved",
    "required_scopes", "granted_scopes",
    "scope_check", "handler_status",
    "duration_ms", "result_shape",
    "error_code", "error_stage",
}

SECRET_KEY_PATTERNS = (
    "token", "secret", "authorization", "client_secret",
    "secret_ref", "password", "bearer_token",
    "access_token", "refresh_token", "api_key",
)


def _iter_dict_values(d: Any):
    """Yield (key, value) pairs recursively for nested dict/list."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield k, v
            yield from _iter_dict_values(v)
    elif isinstance(d, list):
        for item in d:
            yield from _iter_dict_values(item)


def _is_token_blob(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if value.startswith("Bearer "):
        return True
    if value.startswith("eyJ") and value.count(".") == 2:
        return True
    if len(value) >= 40 and all(c.isalnum() or c in "-_" for c in value):
        return True
    return False


# ── Test 1: success emits dispatch_detail with all 15 fields ───────


@pytest.mark.asyncio
async def test_dispatch_tool_success_emits_dispatch_detail():
    """dispatch_tool success → TOOLS_CALL carries dispatch_detail with
    all 15 fields; handler_status=ok, error_stage=None."""
    run_id = "tdd-1"
    fake_result = {
        "review_conclusion": "PASS",
        "issues_found": [],
        "fired_rules": ["R001"],
    }
    async def _fake_run(input_text, *, run_id=""):
        return fake_result

    store = RunTraceStore()
    with patch("official_agents.code_validation.agent.run", new=_fake_run), \
         patch(
             "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
             return_value=store,
         ):
        await dispatch_tool(
            "validate_codes",
            {"coding_set": _coding_set_dict()},
            _build_request(run_id=run_id, auth_header=_full_scopes_auth()),
            run_id=run_id,
        )

    events = store.get_run(run_id)
    detail = _get_dispatch_detail(events)
    assert detail is not None, "TOOLS_CALL must carry dispatch_detail"
    # All 15 fields present
    assert set(detail.keys()) == DISPATCH_DETAIL_KEYS, (
        f"missing keys: {DISPATCH_DETAIL_KEYS - set(detail.keys())}; "
        f"extra: {set(detail.keys()) - DISPATCH_DETAIL_KEYS}"
    )
    # Success-path field values
    assert detail["tool_name"] == "validate_codes"
    assert detail["dispatch_mode"] == "in_process"  # SimpleNamespace request
    assert detail["handler_ref"] == "app.icoder.mcp.handlers.validate_codes:handle"
    assert detail["input_schema_validation"] == "passed"
    assert detail["phi_redaction"] == "skipped"  # no redactor registered
    assert detail["auth_type"] == "in-process"  # auth_config is None
    assert detail["auth_resolved"] is True
    assert detail["required_scopes"] == ["coding:validate"]
    assert detail["granted_scopes"] == ["coding:validate"]
    assert detail["scope_check"] == "passed"
    assert detail["handler_status"] == "ok"
    assert isinstance(detail["duration_ms"], (int, float))
    assert detail["duration_ms"] >= 0
    assert detail["result_shape"] is not None
    assert "dict" in detail["result_shape"]
    assert detail["error_code"] is None
    assert detail["error_stage"] is None


# ── Test 2: schema validation failure ──────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_tool_schema_validation_failure_emits_dispatch_detail():
    """Invalid args (missing required `coding_set`) → dispatch_detail
    with input_schema_validation=failed, error_stage=schema,
    error_code=INVALID_PARAMS (-32602), TOOLS_CALL=FAILED."""
    run_id = "tdd-2"
    store = RunTraceStore()
    with patch(
        "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
        return_value=store,
    ):
        with pytest.raises(MCPError) as exc_info:
            await dispatch_tool(
                "validate_codes",
                # missing coding_set → ValidationError
                {"encounter_text": "患者男，66岁"},
                _build_request(run_id=run_id, auth_header=_full_scopes_auth()),
                run_id=run_id,
            )
        assert exc_info.value.code == MCPErrorCode.INVALID_PARAMS

    events = store.get_run(run_id)
    # TOOLS_CALL=FAILED must be present with dispatch_detail
    tools_call_events = [e for e in events if e.step == RunTraceStep.TOOLS_CALL]
    assert len(tools_call_events) == 1
    assert tools_call_events[0].status == RunTraceStatus.FAILED
    detail = tools_call_events[0].safe_metadata.get("dispatch_detail")
    assert detail is not None
    assert detail["input_schema_validation"] == "failed"
    assert detail["error_stage"] == "schema"
    assert detail["error_code"] == MCPErrorCode.INVALID_PARAMS
    assert detail["handler_status"] == "ok"  # handler never ran


# ── Test 3: scope failure ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_tool_scope_failure_emits_dispatch_detail():
    """Missing scope → dispatch_detail with scope_check=failed,
    error_stage=scope, error_code=MCP_AUTH_FORBIDDEN (-32012)."""
    run_id = "tdd-3"
    store = RunTraceStore()
    with patch(
        "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
        return_value=store,
    ):
        with pytest.raises(MCPAuthError) as exc_info:
            await dispatch_tool(
                "validate_codes",
                {"coding_set": _coding_set_dict()},
                _build_request(run_id=run_id, auth_header=_no_scopes_auth()),
                run_id=run_id,
            )
        assert exc_info.value.code == MCPErrorCode.MCP_AUTH_FORBIDDEN

    events = store.get_run(run_id)
    tools_call_events = [e for e in events if e.step == RunTraceStep.TOOLS_CALL]
    assert len(tools_call_events) == 1
    assert tools_call_events[0].status == RunTraceStatus.FAILED
    detail = tools_call_events[0].safe_metadata.get("dispatch_detail")
    assert detail is not None
    assert detail["scope_check"] == "failed"
    assert detail["error_stage"] == "scope"
    assert detail["error_code"] == MCPErrorCode.MCP_AUTH_FORBIDDEN
    assert detail["required_scopes"] == ["coding:validate"]
    assert detail["granted_scopes"] == []


# ── Test 4: handler failure ────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_tool_handler_failure_emits_dispatch_detail():
    """Handler raises Exception → dispatch_detail with
    handler_status=failed, error_stage=handler_invoke."""
    run_id = "tdd-4"
    store = RunTraceStore()

    async def _boom_handler(arguments, request):
        raise RuntimeError("simulated handler crash")

    with patch(
        "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
        return_value=store,
    ), patch(
        "app.icoder.mcp.handlers.validate_codes.handle",
        new=_boom_handler,
    ):
        with pytest.raises(MCPError) as exc_info:
            await dispatch_tool(
                "validate_codes",
                {"coding_set": _coding_set_dict()},
                _build_request(run_id=run_id, auth_header=_full_scopes_auth()),
                run_id=run_id,
            )
        assert exc_info.value.code == MCPErrorCode.INTERNAL_ERROR

    events = store.get_run(run_id)
    tools_call_events = [e for e in events if e.step == RunTraceStep.TOOLS_CALL]
    assert len(tools_call_events) == 1
    assert tools_call_events[0].status == RunTraceStatus.FAILED
    detail = tools_call_events[0].safe_metadata.get("dispatch_detail")
    assert detail is not None
    assert detail["handler_status"] == "failed"
    assert detail["error_stage"] == "handler_invoke"
    assert detail["error_code"] == MCPErrorCode.INTERNAL_ERROR
    assert detail["handler_ref"] == "app.icoder.mcp.handlers.validate_codes:handle"


# ── Test 5: no token/secret/Authorization/PHI leak ─────────────────


@pytest.mark.asyncio
async def test_dispatch_detail_contains_no_token_secret_authorization_phi():
    """Sweep dispatch_detail recursively; assert no key matches
    secret pattern and no value matches token-blob heuristic."""
    run_id = "tdd-5"
    fake_result = {"review_conclusion": "PASS", "issues_found": []}
    async def _fake_run(input_text, *, run_id=""):
        return fake_result

    store = RunTraceStore()
    with patch("official_agents.code_validation.agent.run", new=_fake_run), \
         patch(
             "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
             return_value=store,
         ):
        await dispatch_tool(
            "validate_codes",
            {"coding_set": _coding_set_dict()},
            _build_request(run_id=run_id, auth_header=_full_scopes_auth()),
            run_id=run_id,
        )

    events = store.get_run(run_id)
    detail = _get_dispatch_detail(events)
    assert detail is not None

    # Recursively sweep all keys + values
    for key, value in _iter_dict_values(detail):
        key_lower = str(key).lower()
        for pat in SECRET_KEY_PATTERNS:
            assert pat not in key_lower, (
                f"secret key pattern {pat!r} found in dispatch_detail key {key!r}"
            )
        assert not _is_token_blob(value), (
            f"token-blob value found in dispatch_detail key {key!r}: "
            f"{str(value)[:40]}..."
        )

    # Specifically assert no PHI原文: the input contained "患者出现呼吸困难"
    # (in coding_set.evidence). The dispatch_detail must NOT contain it.
    detail_json = json.dumps(detail, ensure_ascii=False, default=str)
    assert "患者" not in detail_json, "PHI leaked into dispatch_detail"
    assert "呼吸困难" not in detail_json, "PHI leaked into dispatch_detail"


# ── Test 6: RunTrace API returns dispatch_detail ───────────────────


@pytest.mark.asyncio
async def test_run_trace_api_returns_dispatch_detail():
    """GET /api/runtime/runs/{run_id}/trace response includes
    dispatch_detail under tools_call step."""
    run_id = "tdd-6"
    fake_result = {"review_conclusion": "PASS", "issues_found": []}
    async def _fake_run(input_text, *, run_id=""):
        return fake_result

    # Phase A1A Gate 3R.1 — seed authoritative MODERN row so the orphan-run
    # guard does not deny. Resolved tenant is ICODER_SINGLE_TENANT_ORG_ID.
    await _aseed_modern_row(run_id, "org_default1")
    store = RunTraceStore()
    try:
        with patch("official_agents.code_validation.agent.run", new=_fake_run), \
             patch(
                 "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
                 return_value=store,
             ):
            await dispatch_tool(
                "validate_codes",
                {"coding_set": _coding_set_dict()},
                _build_request(run_id=run_id, auth_header=_full_scopes_auth()),
                run_id=run_id,
            )

        # Now call the API endpoint directly with TestClient
        from fastapi.testclient import TestClient
        from app.main import app

        # Override the API store to our in-memory store so the API reads
        # what we just wrote.
        with patch(
            "app.api.run_trace.get_default_store",
            return_value=store,
        ), patch(
            "app.api.run_trace.get_request_tenant",
            return_value=None,  # in-memory store doesn't filter by org
        ):
            client = TestClient(app)
            resp = client.get(f"/api/runtime/runs/{run_id}/trace")
        assert resp.status_code == 200
        body = resp.json()
        assert "timeline" in body
        tools_call_events = [
            e for e in body["timeline"] if e.get("step") == RunTraceStep.TOOLS_CALL
        ]
        assert len(tools_call_events) >= 1
        detail = tools_call_events[0].get("safe_metadata", {}).get("dispatch_detail")
        assert detail is not None
        assert detail["tool_name"] == "validate_codes"
        assert detail["handler_status"] == "ok"
    finally:
        await _aclear_run_history(run_id)
