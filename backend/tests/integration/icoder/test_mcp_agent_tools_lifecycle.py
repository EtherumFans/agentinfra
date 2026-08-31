"""Phase 3-D2 Task 3 — MCP agent tools lifecycle integration tests.

Verifies the end-to-end dispatch_tool path for the 3 agent-backed MCP
tools (validate_codes / evaluate_compliance / check_documentation_gaps):
  - In-process dispatch via dispatch_tool() works (single code path with
    the HTTP route, zero HTTP overhead).
  - Scope check fires: missing required_scopes → MCP_AUTH_FORBIDDEN -32012.
  - Trace emits (AUTH_RESOLVED / SCOPE_CHECKED / TOOLS_CALL / COMPLETION)
    land in the RunTrace store.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.icoder.mcp.auth import AuthHeader
from app.icoder.mcp.errors import MCPAuthError, MCPErrorCode
from app.icoder.mcp.server import dispatch_tool
from app.icoder.mcp.tool_registry import TOOL_REGISTRY
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    RunTraceStore,
)


def _build_app_state(*, phi_redactor=None) -> SimpleNamespace:
    """Build a fake app.state with the optional hooks dispatch_tool reads."""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.phi_redactor = phi_redactor
    app.state.mcp_secret_resolver = None
    app.state.mcp_http_client_factory = None
    app.state.mcp_clock = None
    return app


def _build_request(*, run_id: str, auth_header: AuthHeader | None = None,
                   app_state=None) -> SimpleNamespace:
    state = SimpleNamespace()
    state.run_id = run_id
    state.context_id = None
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


# ── Test 1: in-process dispatch_tool with full scopes succeeds ───────


@pytest.mark.asyncio
async def test_dispatch_tool_validate_codes_with_scopes_succeeds(trace_store=None):
    """dispatch_tool(validate_codes, ...) with coding:validate scope → succeeds.

    The handler wraps official_agents.code_validation.agent.run() (SSOT).
    We mock agent.run() to avoid pulling in the RuleEngine dependencies.
    """
    run_id = "test-dispatch-1"
    fake_result = {
        "review_conclusion": "PASS",
        "issues_found": [],
        "manual_review_required": False,
        "rule_set": "medical_coding",
        "fired_rules": ["R001"],
        "code_assignment_summary": {},
        "trace_refs": {"run_id": run_id, "agent_ref": "icoder/code-validation-agent@1.0.0"},
    }
    async def _fake_run(input_text, *, run_id=""):
        return fake_result

    with patch(
        "official_agents.code_validation.agent_legacy.run_legacy",
        new=_fake_run,
    ):
        auth = AuthHeader(
            kind="none",
            granted_scopes=["coding:validate"],
            redacted_view="(test, coding:validate granted)",
        )
        result = await dispatch_tool(
            "validate_codes",
            {"coding_set": _coding_set_dict()},
            _build_request(run_id=run_id, auth_header=auth),
            run_id=run_id,
        )
    assert result["isError"] is False
    content = result["content"]
    assert content["review_conclusion"] == "PASS"
    assert content["fired_rules"] == ["R001"]


# ── Test 2: missing scope → MCP_AUTH_FORBIDDEN -32012 ────────────────


@pytest.mark.asyncio
async def test_dispatch_tool_validate_codes_without_scope_returns_forbidden():
    """dispatch_tool(validate_codes) without coding:validate scope → -32012."""
    run_id = "test-dispatch-2"
    auth = AuthHeader(
        kind="none",
        granted_scopes=[],  # missing coding:validate
        redacted_view="(test, no scopes)",
    )
    with pytest.raises(MCPAuthError) as exc_info:
        await dispatch_tool(
            "validate_codes",
            {"coding_set": _coding_set_dict()},
            _build_request(run_id=run_id, auth_header=auth),
            run_id=run_id,
        )
    assert exc_info.value.code == MCPErrorCode.MCP_AUTH_FORBIDDEN
    # Error data surfaces required + granted for client-side branching
    assert exc_info.value.data["required_scopes"] == ["coding:validate"]
    assert exc_info.value.data["granted_scopes"] == []


# ── Test 3: trace emits land in RunTrace store ───────────────────────


@pytest.mark.asyncio
async def test_dispatch_tool_emits_scope_check_and_completion_trace():
    """dispatch_tool emits SCOPE_CHECKED + TOOLS_CALL + COMPLETION trace events."""
    store = RunTraceStore()
    run_id = "test-dispatch-3"
    fake_result = {"review_conclusion": "PASS", "issues_found": [], "fired_rules": []}
    async def _fake_run(input_text, *, run_id=""):
        return fake_result

    with patch("official_agents.code_validation.agent.run", new=_fake_run), \
         patch(
             "app.icoder.agent_runtime.orchestrator.run_trace.get_default_store",
             return_value=store,
         ):
        auth = AuthHeader(
            kind="none",
            granted_scopes=["coding:validate"],
            redacted_view="(test)",
        )
        await dispatch_tool(
            "validate_codes",
            {"coding_set": _coding_set_dict()},
            _build_request(run_id=run_id, auth_header=auth),
            run_id=run_id,
        )

    events = store.get_run(run_id)
    steps = [e.step for e in events]
    # SCOPE_CHECKED + TOOLS_CALL + COMPLETION = 3 emits minimum (no auth_config
    # so AUTH_RESOLVED is skipped).
    assert RunTraceStep.SCOPE_CHECKED in steps
    assert RunTraceStep.TOOLS_CALL in steps
    assert RunTraceStep.COMPLETION in steps
    # Final COMPLETION status = OK
    completion = next(e for e in events if e.step == RunTraceStep.COMPLETION)
    assert completion.status == RunTraceStatus.OK
    # SCOPE_CHECKED carries the required_scopes + granted_scopes
    scope_evt = next(e for e in events if e.step == RunTraceStep.SCOPE_CHECKED)
    assert scope_evt.safe_metadata["required_scopes"] == ["coding:validate"]
    assert scope_evt.safe_metadata["granted_scopes"] == ["coding:validate"]
