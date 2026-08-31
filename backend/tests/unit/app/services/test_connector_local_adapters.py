from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation
from app.services.connector_local_adapters import (
    GovernedInternalAgentAdapter,
    GovernedRegistryAdapter,
)


def _invocation(
    operation: str,
    arguments: dict,
    *,
    agent_id: str = "agt-source",
) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id="org-test",
        agent_id=agent_id,
        connector_id="con-test",
        operation=operation,
        arguments=arguments,
        run_id="run-parent",
        task_id="task-parent",
        data_classification="deidentified",
        purpose_of_use="treatment",
    )


@pytest.mark.asyncio
async def test_registry_adapter_executes_local_deterministic_capabilities():
    adapter = GovernedRegistryAdapter(SimpleNamespace(state=SimpleNamespace()))
    connector = SimpleNamespace()

    bmi = await adapter(
        None,
        connector,
        _invocation("calculate", {
            "calculator": "bmi",
            "inputs": {"weight_kg": 70.0, "height_m": 1.75},
        }),
        "medical-calculator",
    )
    assert bmi["output"]["bmi"] == 22.86
    assert bmi["clinical_use"] == "licensed_clinician_review_required"

    memory = await adapter(
        None,
        connector,
        _invocation("retrieve", {
            "query": "胸痛 入院",
            "thread_messages": [{
                "parts": [{"kind": "text", "text": "患者胸痛后入院"}],
            }],
            "top_k": 3,
        }),
        "memory",
    )
    assert memory["retrieval_mode"] == "LEXICAL_ONLY"
    assert memory["authoritative"] is False

    started = await adapter(
        None,
        connector,
        _invocation("start", {
            "questionnaire_key": "intake-v1",
            "questions": [{"key": "chief", "prompt": "主诉？"}],
        }),
        "interviewing",
    )
    assert started["next_question"]["key"] == "chief"
    assert started["state"]["questionnaire_key"] == "intake-v1"


@pytest.mark.asyncio
async def test_registry_adapter_runs_governed_medical_coding_handler():
    app = SimpleNamespace(state=SimpleNamespace())
    adapter = GovernedRegistryAdapter(app)
    result = await adapter(
        None,
        SimpleNamespace(),
        _invocation("verify_code", {"code": "I21.001"}),
        "medical-coding",
    )
    assert result["code"] == "I21.001"
    assert result["in_catalog"] is True


@pytest.mark.asyncio
async def test_registry_adapter_rejects_invalid_handler_output(monkeypatch):
    import app.icoder.mcp.server as mcp_server

    async def invalid_output(_arguments, _request):
        return {"code": 123}

    monkeypatch.setattr(mcp_server, "resolve_handler", lambda _ref: invalid_output)
    adapter = GovernedRegistryAdapter(SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(ConnectorExecutionError) as raised:
        await adapter(
            None,
            SimpleNamespace(),
            _invocation("verify_code", {"code": "I21.001"}),
            "medical-coding",
        )
    assert raised.value.code == "CONNECTOR_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_registry_public_dispatch_and_scoped_operations_use_server_grants():
    calls = []

    async def public_provider(registry_key, invocation):
        calls.append((registry_key, invocation.operation))
        return {"provider": registry_key, "returned": 0}

    public_provider.status = lambda: {"configured": True}
    adapter = GovernedRegistryAdapter(
        SimpleNamespace(state=SimpleNamespace()),
        public_registry_provider=public_provider,
    )
    result = await adapter(
        None,
        SimpleNamespace(),
        _invocation("search", {"query": "trial"}),
        "pubmed",
    )
    assert result == {"provider": "pubmed", "returned": 0}
    assert calls == [("pubmed", "search")]

    with pytest.raises(ConnectorExecutionError) as external:
        await adapter(
            None,
            SimpleNamespace(),
            _invocation("lookup", {"drug": "x"}),
            "drugbank",
        )
    assert external.value.code == "CONNECTOR_REGISTRY_PROVIDER_UNAVAILABLE"

    with pytest.raises(ConnectorExecutionError) as scoped:
        await adapter(
            None,
            SimpleNamespace(),
            _invocation("validate_codes", {"coding_set": {}}),
            "medical-coding",
        )
    assert scoped.value.code == "CONNECTOR_REGISTRY_SCOPE_FORBIDDEN"

    invocation = _invocation("validate_codes", {"coding_set": {}})
    invocation = ConnectorInvocation(
        **{
            **invocation.__dict__,
            "actor_type": "api_client",
            "actor_id": "client-1",
            "delegated_subject_id": "user-owner-1",
            "granted_scopes": frozenset({"coding:validate"}),
        }
    )
    allowed = await adapter(
        None, SimpleNamespace(), invocation, "medical-coding",
    )
    assert allowed["manual_review_required"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,scope,arguments,output_key",
    [
        ("validate_codes", "coding:validate", {"coding_set": {}}, "review_conclusion"),
        ("evaluate_compliance", "compliance:evaluate", {"coding_set": {}}, "review_conclusion"),
        (
            "check_documentation_gaps",
            "documentation:check",
            {"encounter_text": "主诉：胸痛。现病史：今日发作。"},
            "completeness_score",
        ),
    ],
)
async def test_all_declared_medical_coding_scopes_are_enforced_and_executable(
    operation, scope, arguments, output_key,
):
    adapter = GovernedRegistryAdapter(SimpleNamespace(state=SimpleNamespace()))
    base = _invocation(operation, arguments)
    wrong = ConnectorInvocation(
        **{**base.__dict__, "granted_scopes": frozenset({"agents:run"})}
    )
    with pytest.raises(ConnectorExecutionError) as denied:
        await adapter(None, SimpleNamespace(), wrong, "medical-coding")
    assert denied.value.code == "CONNECTOR_REGISTRY_SCOPE_FORBIDDEN"

    allowed = ConnectorInvocation(
        **{
            **base.__dict__,
            "actor_type": "api_client",
            "actor_id": "client-1",
            "delegated_subject_id": "user-owner-1",
            "granted_scopes": frozenset({"agents:run", scope}),
        }
    )
    result = await adapter(None, SimpleNamespace(), allowed, "medical-coding")
    assert output_key in result


class _SuccessHandler:
    async def handle_async(self, target_agent_id, request):
        return SimpleNamespace(
            kind="message",
            parts=[{"kind": "data", "data": {"target": target_agent_id}}],
            metadata={
                "result_attestation": "signed",
                "manual_review_required": True,
            },
        )


@pytest.mark.asyncio
async def test_internal_agent_adapter_preserves_tenant_and_returns_child_run():
    app = SimpleNamespace(state=SimpleNamespace())
    adapter = GovernedInternalAgentAdapter(app, handler=_SuccessHandler())
    result = await adapter(
        None,
        SimpleNamespace(),
        _invocation("delegate", {"text": "脱敏病例", "case": {"age": 65}}),
        "agt-target",
    )
    assert result["target_agent_id"] == "agt-target"
    assert result["child_run_id"].startswith("run-")
    assert result["result_attestation"] == "signed"
    assert result["parts"][0]["data"]["target"] == "agt-target"


@pytest.mark.asyncio
async def test_internal_agent_adapter_accepts_only_graph_owned_dependency_channel():
    app = SimpleNamespace(state=SimpleNamespace())

    class InspectHandler:
        async def handle_async(self, target_agent_id, request):
            data = next(part["data"] for part in request.message.parts if part["kind"] == "data")
            assert "_dependencies" not in data
            assert data["connector_dependencies"] == {"prior": {"status": "success"}}
            return await _SuccessHandler().handle_async(target_agent_id, request)

    adapter = GovernedInternalAgentAdapter(app, handler=InspectHandler())
    invocation = _invocation("delegate", {
        "text": "脱敏病例",
        "_dependencies": {"prior": {"status": "success"}},
    })
    invocation = ConnectorInvocation(
        **{
            **invocation.__dict__,
            "trusted_server_channels": frozenset({"_dependencies"}),
        }
    )
    result = await adapter(None, SimpleNamespace(), invocation, "agt-target")
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_internal_agent_adapter_rejects_reserved_input_and_runtime_cycle():
    app = SimpleNamespace(state=SimpleNamespace())
    holder = {}

    class NestedHandler:
        async def handle_async(self, _target_agent_id, _request):
            return await holder["adapter"](
                None,
                SimpleNamespace(),
                _invocation("delegate", {"text": "nested"}, agent_id="agt-target"),
                "agt-source",
            )

    adapter = GovernedInternalAgentAdapter(app, handler=NestedHandler())
    holder["adapter"] = adapter
    with pytest.raises(ConnectorExecutionError) as reserved:
        await adapter(
            None,
            SimpleNamespace(),
            _invocation("run", {"text": "x", "_connector_results": {}}),
            "agt-target",
        )
    assert reserved.value.code == "CONNECTOR_AGENT_ARGUMENTS_FORBIDDEN"

    with pytest.raises(ConnectorExecutionError) as cycle:
        await adapter(
            None,
            SimpleNamespace(),
            _invocation("delegate", {"text": "outer"}),
            "agt-target",
        )
    assert cycle.value.code == "CONNECTOR_AGENT_RUNTIME_CYCLE"
