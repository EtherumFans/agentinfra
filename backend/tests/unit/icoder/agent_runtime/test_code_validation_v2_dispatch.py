"""Phase 4-D (D-5) — code-validation-agent v2 A2A dispatch wiring.

Verifies that POST /api/icoder/agents/code-validation-agent/v1/message:send
routes to the governed catalog v2 path with optional LLM/tool review,
bypassing the v1 validate_codes MCP tool.

Acceptance criteria (from plan):
  - Response has v2 shape (validated_codes + cross_code_issues + markdown)
  - agent_ref in response = @2.0.0
  - backend_provider marker = icoder.governed-code-validation.v1
  - RunTrace backend/provider and catalog provenance are emitted
"""

from __future__ import annotations

import os
import uuid
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from icoder_runtime.backends.output_contract_validation import (
    validate_declared_field_schemas,
    validate_required_field_types,
)

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.pop("ICODER_CREDENTIAL_LLM", None)
os.environ.setdefault("ICODER_PHASE1_STUB_LLM", "0")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _send_agent(client: TestClient, agent_id: str, input_text: str):
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
        f"/api/icoder/agents/{agent_id}/v1/message:send",
        json=payload,
        headers={"A2A-Protocol-Version": "0.3", "Content-Type": "application/json"},
    )
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    body = r.json()
    assert "result" in body
    return body["result"]


def _send(client: TestClient, input_text: str):
    return _send_agent(client, "code-validation-agent", input_text)


def _assert_current_pack_contract(data: dict, pack_dir: str) -> dict:
    pack_path = (
        Path(__file__).resolve().parents[4]
        / "official_agents"
        / pack_dir
        / "agent_pack.json"
    )
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    contract = pack["output_contract"]
    declared = set(contract.get("required_fields") or []) | set(
        contract.get("optional_fields") or []
    )
    domain = {field: data[field] for field in declared if field in data}
    missing = sorted(set(contract.get("required_fields") or []) - set(domain))
    assert missing == [], (pack_dir, missing)
    invalid_types = validate_required_field_types(domain, contract)
    invalid_schemas = validate_declared_field_schemas(domain, contract)
    assert invalid_types == [], (pack_dir, [item.to_dict() for item in invalid_types])
    assert invalid_schemas == [], (
        pack_dir,
        [item.to_dict() for item in invalid_schemas],
    )
    return pack


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
    _assert_current_pack_contract(data, "code-validation")
    # Internal/legacy fields are not part of the current public Pack.
    assert "rule_set" not in data
    assert "agent_ref" not in data
    assert "trace_refs" not in data
    # v1-only fields absent
    assert "fired_rules" not in data, "v2 path should not emit v1 fired_rules"
    assert "code_assignment_summary" not in data, "v2 path should not emit v1 code_assignment_summary"


def test_v2_dispatch_agent_ref_is_v2(client):
    """Version identity is metadata, not an undeclared domain field."""
    input_text = '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,"evidence":["x"]}}'
    result = _send(client, input_text)
    data_part = next((p for p in result["parts"] if p.get("kind") == "data"), None)
    data = data_part["data"]
    assert data_part["metadata"].get("agent_ref") == (
        "icoder/code-validation-agent@2.0.0"
    )
    assert "agent_ref" not in data
    assert "trace_refs" not in data


def test_v2_dispatch_backend_provider_marker(client):
    """DataPart metadata carries the governed hybrid Provider identity."""
    input_text = '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,"evidence":["x"]}}'
    result = _send(client, input_text)
    data_part = next((p for p in result["parts"] if p.get("kind") == "data"), None)
    assert data_part["metadata"].get("backend_provider") == (
        "icoder.governed-code-validation.v1"
    )
    assert data_part["metadata"].get("backend_type") == "hybrid"
    # Top-level metadata also carries the marker
    assert result["metadata"].get("backend_provider") == (
        "icoder.governed-code-validation.v1"
    )


def test_v2_dispatch_run_trace_emits_backend_provider(client):
    """RunTrace emits governed Provider identity and catalog provenance."""
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
    completion = next((e for e in events if e.step == "completion"), None)
    assert completion is not None, "no COMPLETION event in RunTrace timeline"
    assert (
        completion.safe_metadata.get("backend_provider")
        == "icoder.governed-code-validation.v1"
    ), completion.safe_metadata
    output = next((e for e in events if e.step == "output_generated"), None)
    assert output is not None
    assert output.safe_metadata["clinical_asset_integrity_verified"] is True
    assert "cn.icd10cn.catalog" in output.safe_metadata["clinical_asset_ids"]
    assert output.safe_metadata["semantic_enhancement_used"] is False


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


@pytest.mark.parametrize(
    ("agent_id", "pack_dir", "input_text"),
    [
        (
            "compliance-guardrail-agent",
            "compliance-guardrail",
            '{"primary_diagnosis":{"code":"I50.9","confidence":0.95,'
            '"evidence":["de-identified evidence"]},"procedures":[]}',
        ),
        (
            "note-completeness-agent",
            "note-completeness",
            "主诉：胸闷。现病史：三天。既往史：高血压。体格检查：无异常。"
            "辅助检查：心电图。诊断：心力衰竭。治疗经过：对症治疗。",
        ),
    ],
)
def test_other_dedicated_a2a_routes_emit_their_pack_contract(
    client, agent_id: str, pack_dir: str, input_text: str,
):
    result = _send_agent(client, agent_id, input_text)
    data_part = next(part for part in result["parts"] if part.get("kind") == "data")
    pack = _assert_current_pack_contract(data_part["data"], pack_dir)
    assert data_part["metadata"]["schema_ref"] == (
        pack["output_contract"]["schema_ref"]
    )
    assert result["metadata"]["production_writeback_blocked"] is True
