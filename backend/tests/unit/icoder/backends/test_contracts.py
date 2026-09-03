"""Tests for ``icoder_runtime.backends.contracts`` — Phase 4-A Task 1.

Verifies:
  - ``AgentBackendProvider`` is a runtime-checkable Protocol.
  - ``BackendResponse.to_output_contract()`` normalizes correctly.
  - ``OutputContract`` validates the 9-state status enum.
  - ``BackendRequest.with_extra_context`` is immutable.
  - ``ProviderCapability`` / ``ProviderHealth`` round-trip.

Per Phase 4-A Task 9: "ProviderRegistry register / get / list / unknown
provider" + "agent_pack backend_provider schema validation" + "RuleEngineProvider
invoke returns BackendResponse" + "PureLLMProvider skeleton can build
request and handle mock response" + "LLMWithToolsProvider skeleton can
translate tool call to MCP compat layer" + "ToolMCPCompatLayer calls
dispatch_tool, not handler directly" + "RunTrace includes backend_provider
metadata" + "Existing 4 runnable agents no regression" + "TypeScript 0
error".
"""
from __future__ import annotations

import pytest

from icoder_runtime.backends import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    OutputContract,
    OutputIssue,
    ProviderCapability,
    ProviderHealth,
    ToolCallRecord,
)


# ── BackendResponse.to_output_contract ─────────────────────────────


def test_backend_response_to_output_contract_basic():
    """BackendResponse normalizes to OutputContract with all fields."""
    resp = BackendResponse(
        status="pass",
        summary="ok",
        issues=[OutputIssue(code="R001", severity="info", message="m")],
        backend_provider="icoder.rule-engine.v1",
        backend_type="rule_engine",
        latency_ms=42,
        raw_provider_response={"fired": ["R001"]},
        markdown="# summary",
        evidence_refs=["R001"],
        trace_refs=["run-1:rule-engine:1"],
    )
    contract = resp.to_output_contract(agent_id="ag", run_id="run-1")
    assert contract.agent_id == "ag"
    assert contract.run_id == "run-1"
    assert contract.backend_provider == "icoder.rule-engine.v1"
    assert contract.status == "pass"
    assert contract.summary == "ok"
    assert len(contract.issues) == 1
    assert contract.issues[0].code == "R001"
    assert contract.latency_ms == 42
    assert contract.raw == {"fired": ["R001"]}
    assert contract.schema_ref == "icoder/OutputContract/v1"


def test_backend_response_to_output_contract_with_custom_schema_ref():
    """to_output_contract accepts a custom schema_ref."""
    resp = BackendResponse(status="warning", backend_provider="x")
    contract = resp.to_output_contract(schema_ref="icoder/RuleEngineOutput/v1")
    assert contract.schema_ref == "icoder/RuleEngineOutput/v1"


# ── OutputContract enum validation ──────────────────────────────────


@pytest.mark.parametrize("status", [
    "pass", "warning", "fail", "complete", "incomplete",
    "unclear", "compliant", "non_compliant", "requires_review",
])
def test_output_contract_accepts_9_state_enum(status):
    """All 9 Corti-observed status values are valid."""
    c = OutputContract(backend_provider="x", status=status)  # type: ignore[arg-type]
    assert c.status == status


def test_output_contract_rejects_invalid_status():
    """Invalid status values are rejected by Pydantic."""
    with pytest.raises(Exception):
        OutputContract(backend_provider="x", status="bogus")  # type: ignore[arg-type]


# ── BackendRequest.with_extra_context immutability ─────────────────


def test_backend_request_with_extra_context_does_not_mutate_original():
    """with_extra_context returns a new instance; original is unchanged."""
    req = BackendRequest(
        input={"text": "hello"},
        system_prompt="sys",
        user_input="hello",
        tool_scope=["verify"],
    )
    new_req = req.with_extra_context({"rule_verdict": "pass"})
    assert new_req.extra_context == {"rule_verdict": "pass"}
    # Original is unchanged.
    assert req.extra_context == {}
    # Other fields are preserved (deep-copied where mutable).
    assert new_req.tool_scope == ["verify"]
    assert new_req.input == {"text": "hello"}
    # Mutating new_req.tool_scope doesn't affect req.tool_scope.
    new_req.tool_scope.append("guidelines")
    assert req.tool_scope == ["verify"]


# ── ProviderHealth / ProviderCapability ─────────────────────────────


def test_provider_health_defaults():
    h = ProviderHealth()
    assert h.state == "ok"
    assert h.latency_ms == 0
    assert h.details == {}


def test_provider_capability_round_trip():
    cap = ProviderCapability(
        provider_id="icoder.rule-engine.v1",
        backend_type="rule_engine",
        supports_tool_calling=False,
        supports_streaming=False,
        deterministic=True,
        default_output_contract="icoder/RuleEngineOutput/v1",
        supported_tools=[],
        description="deterministic rules",
    )
    assert cap.provider_id == "icoder.rule-engine.v1"
    assert cap.deterministic is True


# ── AgentBackendProvider is runtime_checkable ───────────────────────


def test_agent_backend_provider_protocol_runtime_checkable():
    """The Protocol is runtime_checkable — instances of classes that
    implement the right shape pass isinstance."""

    class _FakeProvider:
        provider_id = "icoder.fake.v1"
        backend_type = "rule_engine"
        supports_tool_calling = False
        supports_streaming = False
        deterministic = True

        async def health(self):
            return ProviderHealth()

        async def invoke(self, req, ctx):
            return BackendResponse(status="pass", backend_provider=self.provider_id)

        async def stream(self, req, ctx):
            yield {"step": "finished"}

        def output_contract(self):
            return "icoder/Fake/v1"

        def fallback_chain(self):
            return None

        def capabilities(self):
            return ProviderCapability(
                provider_id=self.provider_id,
                backend_type=self.backend_type,
                supports_tool_calling=self.supports_tool_calling,
                supports_streaming=self.supports_streaming,
                deterministic=self.deterministic,
            )

    # Instance passes the runtime check (Protocol is structural).
    instance = _FakeProvider()
    assert isinstance(instance, AgentBackendProvider)


# ── AgentRunContext shape ───────────────────────────────────────────


def test_agent_run_context_minimal():
    ctx = AgentRunContext(
        run_id="run-1",
        context_id="ctx-1",
        agent_id="ag-1",
    )
    assert ctx.tenant_id == "default"
    assert ctx.region == "cn"
    assert ctx.redacted_input == ""
    assert ctx.backend_config == {}
