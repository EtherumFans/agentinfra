from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
)
from app.icoder.agent_runtime.provider_a2a_handler import ProviderA2AHandler
from icoder_runtime.backends.contracts import BackendResponse
from official_agents.clinical_guidelines.agent import (
    build_clinical_guidelines,
    to_pack_output,
)


BACKEND_ROOT = Path(__file__).resolve().parents[3]
TRIAGE_PACK = json.loads(
    (BACKEND_ROOT / "official_agents" / "triage" / "agent_pack.json").read_text(
        encoding="utf-8"
    )
)
TRIAGE_EXAMPLE = TRIAGE_PACK["example_outputs"][0]
TRIAGE_INPUT = TRIAGE_PACK["example_inputs"][0]["input_text"]
CLINICAL_GUIDELINES_PACK = json.loads(
    (BACKEND_ROOT / "official_agents" / "clinical-guidelines" / "agent_pack.json").read_text(
        encoding="utf-8"
    )
)
CLINICAL_GUIDELINES_INPUT = CLINICAL_GUIDELINES_PACK["example_inputs"][0]["input_text"]


class _StreamingProvider:
    supports_streaming = True

    async def stream(self, req, ctx, *, request=None):
        yield {
            "step": "provider_text_delta",
            "payload": {
                "delta": "provisional model output",
                "native": True,
                "provisional": True,
            },
        }
        domain_result = json.loads(json.dumps(TRIAGE_EXAMPLE))
        domain_result["manual_review_required"] = False
        domain_result["supporting_evidence"] = "validated"
        response = BackendResponse(
            status="pass",
            summary="validated",
            markdown=json.dumps(domain_result),
            backend_provider="icoder.pure-llm.v1",
            backend_type="pure_llm",
            finish_state="completed",
            trace_refs=[ctx.run_id],
        )
        yield {"step": "backend_invoked", "payload": response}
        yield {"step": "finished", "payload": {"state": "completed"}}


class _Registry:
    def resolve_from_agent_pack(self, pack):
        return _StreamingProvider()

    def get_backend_config(self, pack):
        return pack.get("backend_config") or {}


@pytest.mark.asyncio
async def test_provider_a2a_handler_uses_stream_and_returns_validated_terminal(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    monkeypatch.setattr(module, "get_default_registry", lambda: _Registry())
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    agent_id = "triage"
    assert agent_id in handler.agent_ids
    events: list[dict] = []
    request = InboundRequest(
        message=InboundMessage(
            parts=[{"kind": "text", "text": TRIAGE_INPUT}],
            context_id="context-test",
        ),
        metadata={"organization_id": "org-test"},
        stream_sink=events.append,
    )

    response = await handler._handle_async(agent_id, request)

    assert response.kind == "message"
    data = response.parts[0]["data"]
    assert data["supporting_evidence"] == "validated"
    assert "structured_extraction" not in data
    assert "backend_provider" not in data
    assert "tool_calls" not in data
    # Pack human_review=required overrides the model's false value.
    assert data["manual_review_required"] is True
    assert response.metadata["manual_review_required"] is True
    assert response.metadata["backend_provider"] == "icoder.pure-llm.v1"
    assert [event["step"] for event in events] == [
        "provider_text_delta",
        "backend_invoked",
        "finished",
    ]


@pytest.mark.asyncio
async def test_provider_a2a_handler_fails_closed_on_pack_contract_violation(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    monkeypatch.setattr(module, "get_default_registry", lambda: _Registry())
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    request = InboundRequest(
        message=InboundMessage(
            parts=[{"kind": "text", "text": "de-identified note"}],
            context_id="context-contract-fail",
        ),
        metadata={"organization_id": "org-test"},
    )

    class _InvalidProvider:
        supports_streaming = False

        async def invoke(self, req, ctx, *, request=None):
            return BackendResponse(
                status="pass",
                summary="generic shell only",
                markdown='{"summary":"generic shell only"}',
                backend_provider="icoder.pure-llm.v1",
                backend_type="pure_llm",
                finish_state="completed",
                trace_refs=[ctx.run_id],
            )

    class _InvalidRegistry(_Registry):
        def resolve_from_agent_pack(self, pack):
            return _InvalidProvider()

    monkeypatch.setattr(
        module, "get_default_registry", lambda: _InvalidRegistry(),
    )
    response = await handler._handle_async("triage", request)

    assert response.kind == "error"
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.http_status == 503
    assert "acuity_level" in response.metadata["missing_required_fields"]
    assert response.metadata["invalid_field_types"] == []
    assert response.metadata["undeclared_output_fields"] == ["<redacted>"]
    assert response.metadata["manual_review_required"] is True


@pytest.mark.asyncio
async def test_provider_a2a_handler_fails_closed_on_wrong_contract_type(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    class _WrongTypeProvider:
        supports_streaming = False

        async def invoke(self, req, ctx, *, request=None):
            payload = json.loads(json.dumps(TRIAGE_EXAMPLE))
            payload["acuity_level"] = []
            payload["debug_payload"] = "patient-secret-marker"
            return BackendResponse(
                status="pass",
                summary="wrong type",
                markdown=json.dumps(payload),
                backend_provider="icoder.pure-llm.v1",
                backend_type="pure_llm",
                finish_state="completed",
            )

    class _WrongTypeRegistry(_Registry):
        def resolve_from_agent_pack(self, pack):
            return _WrongTypeProvider()

    monkeypatch.setattr(
        module, "get_default_registry", lambda: _WrongTypeRegistry(),
    )
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    response = await handler._handle_async(
        "triage",
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": TRIAGE_INPUT}],
                context_id="context-contract-wrong-type",
            ),
            metadata={"organization_id": "org-test"},
        ),
    )

    assert response.kind == "error"
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["missing_required_fields"] == []
    assert response.metadata["invalid_field_types"] == [
        {"field": "acuity_level", "expected": "string", "actual": "array"}
    ]
    assert response.metadata["undeclared_output_fields"] == ["<redacted>"]
    assert response.metadata["undeclared_output_field_count"] == 1
    assert "patient-secret-marker" not in repr(response)


@pytest.mark.asyncio
async def test_provider_a2a_handler_fails_closed_on_nested_schema_violation(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    secret = "patient-secret-marker"

    class _NestedInvalidProvider:
        supports_streaming = False

        async def invoke(self, req, ctx, *, request=None):
            payload = json.loads(json.dumps(TRIAGE_EXAMPLE))
            payload["red_flags"][0] = {"value": secret}
            return BackendResponse(
                status="pass",
                summary="nested invalid",
                markdown=json.dumps(payload),
                backend_provider="icoder.pure-llm.v1",
                backend_type="pure_llm",
                finish_state="completed",
                trace_refs=[ctx.run_id],
            )

    class _NestedInvalidRegistry(_Registry):
        def resolve_from_agent_pack(self, pack):
            return _NestedInvalidProvider()

    monkeypatch.setattr(
        module, "get_default_registry", lambda: _NestedInvalidRegistry(),
    )
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    response = await handler._handle_async(
        "triage",
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": TRIAGE_INPUT}],
                context_id="context-contract-nested-invalid",
            ),
            metadata={"organization_id": "org-test"},
        ),
    )

    assert response.kind == "error"
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["invalid_field_schemas"] == [{
        "path": "red_flags[]",
        "keyword": "type",
        "expected": "string",
        "actual": "object",
    }]
    assert secret not in repr(response)


@pytest.mark.asyncio
async def test_provider_a2a_handler_fails_closed_on_semantic_schema_violation(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    class _SemanticInvalidProvider:
        supports_streaming = False

        async def invoke(self, req, ctx, *, request=None):
            payload = json.loads(json.dumps(TRIAGE_EXAMPLE))
            payload["red_flags"] = [f"flag-{index}" for index in range(65)]
            return BackendResponse(
                status="pass",
                summary="semantic invalid",
                markdown=json.dumps(payload),
                backend_provider="icoder.pure-llm.v1",
                backend_type="pure_llm",
                finish_state="completed",
                trace_refs=[ctx.run_id],
            )

    class _SemanticInvalidRegistry(_Registry):
        def resolve_from_agent_pack(self, pack):
            return _SemanticInvalidProvider()

    monkeypatch.setattr(module, "get_default_registry", lambda: _SemanticInvalidRegistry())
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    response = await handler._handle_async(
        "triage",
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": TRIAGE_INPUT}],
                context_id="context-contract-semantic-invalid",
            ),
            metadata={"organization_id": "org-test"},
        ),
    )

    assert response.kind == "error"
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["invalid_field_schemas"] == [{
        "path": "red_flags",
        "keyword": "maxItems",
        "expected": "at_or_below_max_items",
        "actual": "too_many_items",
    }]


@pytest.mark.asyncio
async def test_provider_a2a_handler_fails_closed_on_cross_field_relation(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as module

    class _RelationInvalidProvider:
        supports_streaming = False

        async def invoke(self, req, ctx, *, request=None):
            payload = to_pack_output(
                build_clinical_guidelines(req.input["text"], run_id=ctx.run_id)
            )
            payload["deviations"] = []
            return BackendResponse(
                status="pass",
                summary="cross-field invalid",
                markdown=json.dumps(payload),
                backend_provider="icoder.pure-llm.v1",
                backend_type="pure_llm",
                finish_state="completed",
            )

    class _RelationInvalidRegistry(_Registry):
        def resolve_from_agent_pack(self, pack):
            return _RelationInvalidProvider()

    monkeypatch.setattr(module, "get_default_registry", lambda: _RelationInvalidRegistry())
    handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    response = await handler._handle_async(
        "clinical-guidelines",
        InboundRequest(
            message=InboundMessage(
                parts=[{"kind": "text", "text": CLINICAL_GUIDELINES_INPUT}],
                context_id="context-contract-relation-invalid",
            ),
            metadata={"organization_id": "org-test"},
        ),
    )

    assert response.kind == "error"
    assert response.error["code"] == "OUTPUT_CONTRACT_VIOLATION"
    assert response.metadata["invalid_field_schemas"] == [{
        "path": "deviations",
        "keyword": "fieldRelation",
        "expected": "unmet_guideline_requires_deviation",
        "actual": "non_empty_violated",
    }]
