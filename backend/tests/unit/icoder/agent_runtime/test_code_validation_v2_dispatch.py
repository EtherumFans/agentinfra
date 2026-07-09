"""Phase 4-D (D-5) — code-validation-agent v2 A2A dispatch wiring.

Verifies that POST /api/icoder/agents/code-validation-agent/v1/message:send
routes to the v2 path (LLMWithToolsProvider + 4 MCP tools) directly,
bypassing the v1 validate_codes MCP tool.

Acceptance criteria (from plan):
  - Response has v2 shape (validated_codes + cross_code_issues + markdown)
  - agent_ref in response = @2.0.0
  - backend_provider marker = icoder.llm-with-tools.v1
  - RunTrace backend_provider event emitted (icoder.llm-with-tools.v1)
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p11")
os.environ.setdefault("ICODER_PHASE1_STUB_LLM", "0")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _send(client: TestClient, input_text: str):
    payload = {
        "jsonrpc": "2.0",
        "id": f"cv2-{uuid.uuid4().hex[:8]}",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": input_text}],
                "metadata": {},
            }
        },
    }
    r = client.post(
        "/api/icoder/agents/code-validation-agent/v1/message:send",
        json=payload,
        headers={"A2A-Protocol-Version": "0.3", "Content-Type": "application/json"},
    )
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    body = r.json()
    assert "result" in body
    return body["result"]


def test_v2_dispatch_returns_v2_shape(client):
    """A2A response contains v2 fields (validated_codes / cross_code_issues)."""
    input_text = (
        '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,'
        '"evidence":["心衰证据"],"category":"primary"},'
        '"secondary_diagnoses":[],"procedures":[]}'
    )
    result = _send(client, input_text)
    assert result["kind"] == "message"
    data_part = next((p for p in result["parts"] if p.get("kind") == "data"), None)
    assert data_part is not None
    data = data_part["data"]
    # v2 schema fields
    assert "validated_codes" in data
    assert "cross_code_issues" in data
    assert "markdown" in data
    assert "summary" in data
    assert data["rule_set"] == "medical_coding"
    # v1-only fields absent
    assert "fired_rules" not in data, "v2 path should not emit v1 fired_rules"
    assert "code_assignment_summary" not in data, "v2 path should not emit v1 code_assignment_summary"


def test_v2_dispatch_agent_ref_is_v2(client):
    """agent_ref in response = @2.0.0 (D-5 wiring overrides legacy fallback)."""
    input_text = '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,"evidence":["x"]}}'
    result = _send(client, input_text)
    data_part = next((p for p in result["parts"] if p.get("kind") == "data"), None)
    data = data_part["data"]
    assert data.get("agent_ref") == "icoder/code-validation-agent@2.0.0"
    assert data["trace_refs"].get("agent_ref") == "icoder/code-validation-agent@2.0.0"


def test_v2_dispatch_backend_provider_marker(client):
    """DataPart metadata carries backend_provider=icoder.llm-with-tools.v1."""
    input_text = '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,"evidence":["x"]}}'
    result = _send(client, input_text)
    data_part = next((p for p in result["parts"] if p.get("kind") == "data"), None)
    assert data_part["metadata"].get("backend_provider") == "icoder.llm-with-tools.v1"
    # Top-level metadata also carries the marker
    assert result["metadata"].get("backend_provider") == "icoder.llm-with-tools.v1"


def test_v2_dispatch_run_trace_emits_backend_provider(client):
    """RunTrace COMPLETION event emits backend_provider=icoder.llm-with-tools.v1."""
    input_text = '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,"evidence":["x"]}}'
    result = _send(client, input_text)
    run_id = result["metadata"].get("run_id")
    assert run_id, "missing run_id in response metadata"

    # Fetch the RunTrace and verify backend_provider was emitted.
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        get_default_store,
    )
    store = get_default_store()
    events = store.get_run(run_id)
    assert events, f"no RunTrace events found for run_id={run_id}"
    # Find COMPLETION event
    completion = next(
        (e for e in events if e.step == "completion"), None,
    )
    assert completion is not None, "no COMPLETION event in RunTrace timeline"
    assert (
        completion.safe_metadata.get("backend_provider")
        == "icoder.llm-with-tools.v1"
    ), f"expected backend_provider=icoder.llm-with-tools.v1, got {completion.safe_metadata}"


def test_validate_codes_mcp_tool_stays_v1(client):
    """Regression: the validate_codes MCP tool itself still returns v1 shape
    (with fired_rules / code_assignment_summary), so other MCP consumers
    are unaffected by D-5. Invokes dispatch_tool directly with proper auth
    to bypass the HTTP auth layer (which requires coding:validate scope).
    """
    import asyncio
    from types import SimpleNamespace as _NS
    from app.icoder.mcp.server import dispatch_tool
    from app.icoder.mcp.auth import AuthHeader
    from app.main import app as _app  # already constructed by the client fixture

    fake_state = _NS()
    fake_state.context_id = str(uuid.uuid4())
    fake_state.run_id = str(uuid.uuid4())
    fake_state.mcp_run_auth_context = None
    fake_state.auth_header = AuthHeader(
        kind="none",
        granted_scopes=["coding:validate"],
        redacted_view="(test, coding:validate granted)",
    )
    fake_request = _NS()
    fake_request.app = _app
    fake_request.state = fake_state

    coding_set = {
        "primary_diagnosis": {
            "code": "I50.9",
            "confidence": 0.95,
            "evidence": ["心衰证据"],
        },
        "secondary_diagnoses": [],
        "procedures": [],
    }
    result = asyncio.new_event_loop().run_until_complete(
        dispatch_tool(
            "validate_codes",
            {"coding_set": coding_set},
            fake_request,
            run_id=fake_state.run_id,
        )
    )
    # MCP returns {"content": <handler result>, "isError": False}
    assert not result.get("isError"), f"validate_codes returned isError: {result}"
    content = result.get("content") or {}
    # v1 marker fields — these are absent in the v2 schema. Their presence
    # confirms the MCP tool still routes through the legacy RuleEngine.
    v1_keys = list(content.keys())
    assert "fired_rules" in v1_keys or "code_assignment_summary" in v1_keys, (
        f"validate_codes MCP tool should still return v1 shape with fired_rules/"
        f"code_assignment_summary; got keys: {v1_keys}"
    )
    # trace_refs.agent_ref should still be @1.0.0 (v1 MCP tool unchanged)
    tr = content.get("trace_refs") or {}
    assert tr.get("agent_ref") == "icoder/code-validation-agent@1.0.0", (
        f"validate_codes MCP tool trace_refs.agent_ref should be @1.0.0; got: {tr.get('agent_ref')}"
    )
