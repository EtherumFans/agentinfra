import json

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_agents_resource_uses_definition_crud_and_a2a_execution_mainline():
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        calls.append((request.method, raw_path, request.headers, body))
        if raw_path.endswith("/v1/message%3Asend") or raw_path.endswith("/v1/message:send"):
            return httpx.Response(200, json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "kind": "message",
                    "role": "agent",
                    "messageId": "result-1",
                    "contextId": "context-1",
                    "parts": [{"kind": "text", "text": "done"}],
                    "metadata": {},
                },
            })
        return httpx.Response(200, json={"agents": []})

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        client.agents.list()
        result = client.agents.run("medical/coding", "de-identified note")
    finally:
        client.close()

    assert calls[0][1] == "/api/rest/v1/agent_definitions"
    assert calls[1][1] == "/api/icoder/agents/medical%2Fcoding/v1/message:send"
    assert calls[1][3]["method"] == "message/send"
    assert calls[1][2]["A2A-Protocol-Version"] == "0.3"
    assert result["contextId"] == "context-1"
    assert all(not path.startswith("/api/agents") for _, path, _, _ in calls)


def test_agents_resource_stream_uses_a2a_sse_contract():
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append((request, body))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            content=b'event: data-json\ndata: {"jsonrpc":"2.0"}\n\nevent: done\ndata: {}\n\n',
        )

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        chunks = list(client.agents.stream("note completeness", "safe input"))
    finally:
        client.close()

    request, body = captured[0]
    assert request.url.raw_path.decode() == (
        "/api/icoder/agents/note%20completeness/v1/message:stream"
    )
    assert request.headers["A2A-Protocol-Version"] == "0.3"
    assert request.headers["Authorization"] == "Bearer token"
    assert body["method"] == "message/stream"
    assert body["params"]["message"]["parts"][0]["text"] == "safe input"
    assert chunks == ['{"jsonrpc":"2.0"}', "{}"]


def test_agents_resource_exposes_hub_and_card_contract_routes():
    calls = []
    card = {
        "agent_id": "claim-check",
        "agent_ref": "icoder/claim-check@1.0.0",
        "name": "Claim Check",
        "execution_path": "provider_registry",
        "execution_target": "icoder.pure-llm.v1",
        "runtime_readiness": {
            "structural_status": "ready",
            "configuration_status": "not_checked",
            "run_action_enabled": False,
            "reason": "tenant_runtime_readiness_requires_authentication",
            "runtime_dependencies": ["external_llm_gateway"],
            "external_llm_required": True,
            "live_health_verified": False,
            "semantic_validation_status": "not_verified",
            "production_approval_status": "not_approved",
        },
        "output_contract": {
            "schema_ref": "icoder/ClaimCheckOutput/v1",
            "required_fields": ["summary"],
            "optional_fields": ["details"],
            "field_types": {"summary": "string", "details": "array"},
            "field_schemas": {
                "summary": {"type": "string", "maxLength": 32768},
                "details": {
                    "type": "array",
                    "maxItems": 100,
                    "uniqueItems": True,
                    "items": {"type": "string", "enum": ["a", "b"]},
                },
            },
              "field_relations": [{
                  "id": "details_require_summary",
                  "for_each": "candidates",
                  "when": [{"path": "details", "operator": "non_empty"}],
                  "must": [{"path": "confidence", "operator": "gte", "value": 0.7}],
              }],
              "evidence_bindings": [{
                  "id": "candidate_evidence_matches_input",
                  "for_each": "candidates",
                  "text_path": "evidence_text",
                  "span_path": "char_span",
              }],
              "cross_agent_relations": [{
                  "id": "candidate_matches_upstream",
                  "local_path": "summary",
                  "upstream_agent_id": "upstream-agent",
                  "upstream_path": "items",
                  "upstream_item_path": "code",
                  "operator": "scalar_in_upstream_items",
                  "normalization": "medical_code",
                  "required": False,
              }],
        },
    }
    discovery_card = {
        "name": "Claim Check",
        "description": "A2A discovery card",
        "url": "https://api.cn.icoder.cloud/api/icoder/agents/claim-check/v1/message:send",
        "version": "1.0.0",
        "provider": "iCoDer",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "skills": [{
            "id": "claim-check",
            "name": "Claim Check",
            "description": "Validate claims",
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object"},
        }],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["application/json"],
        "securitySchemes": {},
    }
    tenant_readiness = {
        "schema_version": "1.0",
        "generated_at": "2026-08-23T00:00:00Z",
        "total": 1,
        "agents": [{
            "agent_id": "claim-check",
            "execution_target": "icoder.pure-llm.v1",
            "runtime_readiness": {
                "structural_status": "ready",
                "configuration_status": "configured",
                "run_action_enabled": True,
                "reason": "tenant_model_configuration_present",
                "runtime_dependencies": ["external_llm_gateway"],
                "llm_required": True,
                "live_health_verified": True,
                "connectivity_status": "verified",
                "semantic_validation_status": "not_verified",
                "production_approval_status": "not_approved",
            },
            "evidence": {
                "scope": "tenant_configuration_and_connectivity",
                "selection_mode": "pinned",
                "selection_version": 2,
                "deployment_id": "deepseek",
                "provider_id": "deepseek",
                "configuration_probe_status": "not_run",
                "canary_checked_at": "2026-08-23T00:00:00Z",
                "canary_expires_at": "2026-08-23T00:15:00Z",
            },
        }],
    }

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/card"):
            return httpx.Response(200, json=discovery_card)
        if request.url.path.endswith("/hub/readiness"):
            return httpx.Response(200, json=tenant_readiness)
        return httpx.Response(200, json={
            "agents": [card], "total": 1, "source": "packs", "schema_version": "1.3",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        hub = client.agents.hub("coding_revenue_cycle")
        legacy_hub_resource = client.agent_hub.list("coding_revenue_cycle")
        readiness = client.agents.hub_readiness()
        legacy_readiness = client.agent_hub.readiness()
        discovered = client.agents.card("claim/check")
    finally:
        client.close()

    assert calls[0].url.path == "/api/icoder/agents/hub"
    assert calls[0].url.params["use_case"] == "coding_revenue_cycle"
    assert calls[1].url.path == "/api/icoder/agents/hub"
    assert calls[2].url.path == "/api/icoder/agents/hub/readiness"
    assert calls[3].url.path == "/api/icoder/agents/hub/readiness"
    assert calls[4].url.raw_path.decode() == "/api/icoder/agents/claim%2Fcheck/card"
    assert hub["agents"][0]["output_contract"]["optional_fields"] == ["details"]
    assert discovered["capabilities"]["streaming"] is True
    assert discovered["skills"][0]["outputSchema"]["type"] == "object"
    assert hub["agents"][0]["output_contract"]["field_types"]["details"] == "array"
    assert hub["agents"][0]["output_contract"]["field_schemas"]["details"]["items"]["type"] == "string"
    assert hub["agents"][0]["output_contract"]["field_schemas"]["summary"]["maxLength"] == 32768
    assert hub["agents"][0]["output_contract"]["field_relations"][0]["id"] == "details_require_summary"
    assert hub["agents"][0]["output_contract"]["evidence_bindings"][0]["span_path"] == "char_span"
    assert hub["agents"][0]["runtime_readiness"]["configuration_status"] == (
        "not_checked"
    )
    assert hub["agents"][0]["runtime_readiness"]["live_health_verified"] is False
    assert readiness["agents"][0]["runtime_readiness"]["configuration_status"] == (
        "configured"
    )
    assert readiness["agents"][0]["runtime_readiness"]["connectivity_status"] == (
        "verified"
    )
    assert readiness["agents"][0]["runtime_readiness"]["live_health_verified"] is True
    assert readiness["agents"][0]["evidence"]["deployment_id"] == "deepseek"
    assert legacy_readiness["schema_version"] == "1.0"
    assert legacy_hub_resource["schema_version"] == "1.3"


def test_agents_resource_clones_hub_agent_with_project_runtime_identity():
    calls = []
    clone = {
        "project_agent_id": "project-agent-1",
        "runtime_agent_id": "project-agent-1",
        "source_runtime_agent_id": "claim-check",
        "source_agent_ref": "icoder/claim-check@1.0.0",
        "chat_url": "/ai-studio/agents/project-agent-1/chat",
        "customize_url": "/ai-studio/agents/project-agent-1",
        "run_url": "/api/icoder/agents/project-agent-1/v1/message:send",
        "cloned": True,
    }

    def handler(request):
        calls.append((request, json.loads(request.content)))
        return httpx.Response(201, json=clone)

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        result = client.agents.clone(
            "claim/check",
            name="Project Claim Check",
            project_id="project-cn-1",
        )
    finally:
        client.close()

    request, body = calls[0]
    assert request.url.raw_path.decode() == "/api/icoder/agents/claim%2Fcheck/clone"
    assert body == {
        "open_after_clone": True,
        "name": "Project Claim Check",
        "project_id": "project-cn-1",
    }
    assert result["runtime_agent_id"] == result["project_agent_id"]
    assert result["source_runtime_agent_id"] == "claim-check"


def test_agents_resource_rejects_clone_that_bypasses_project_identity():
    def handler(_request):
        return httpx.Response(200, json={
            "project_agent_id": "project-agent-1",
            "runtime_agent_id": "claim-check",
            "source_runtime_agent_id": "claim-check",
            "source_agent_ref": "icoder/claim-check@1.0.0",
            "chat_url": "/chat",
            "customize_url": "/customize",
            "run_url": "/api/icoder/agents/claim-check/v1/message:send",
            "cloned": False,
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="bypass the project runtime identity"):
            client.agents.clone("claim-check")
    finally:
        client.close()


def test_agents_resource_rejects_hub_that_enables_unavailable_agent():
    def handler(_request):
        return httpx.Response(200, json={
            "agents": [{
                "agent_id": "claim-check",
                "runtime_readiness": {
                    "structural_status": "ready",
                    "configuration_status": "unavailable",
                    "run_action_enabled": True,
                    "reason": "mock_provider",
                    "runtime_dependencies": ["external_llm_gateway"],
                    "external_llm_required": True,
                    "live_health_verified": False,
                    "semantic_validation_status": "not_verified",
                    "production_approval_status": "not_approved",
                },
            }],
            "total": 1,
            "source": "packs",
            "schema_version": "1.3",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(ValueError, match="enables an unavailable Agent"):
            client.agents.hub()
    finally:
        client.close()


def test_agents_resource_rejects_unverified_tenant_live_health_claim():
    def handler(_request):
        return httpx.Response(200, json={
            "schema_version": "1.0",
            "generated_at": "2026-08-23T00:00:00Z",
            "total": 1,
            "agents": [{
                "agent_id": "claim-check",
                "execution_target": "icoder.pure-llm.v1",
                "runtime_readiness": {
                    "structural_status": "ready",
                    "configuration_status": "configured",
                    "run_action_enabled": True,
                    "reason": "configured",
                    "runtime_dependencies": ["external_llm_gateway"],
                    "llm_required": True,
                    "live_health_verified": True,
                    "connectivity_status": "not_run",
                    "semantic_validation_status": "not_verified",
                    "production_approval_status": "not_approved",
                },
                "evidence": {
                    "scope": "tenant_configuration_and_connectivity",
                    "selection_mode": "pinned",
                    "selection_version": 1,
                    "deployment_id": "deepseek",
                    "provider_id": "deepseek",
                    "configuration_probe_status": "not_run",
                    "canary_checked_at": None,
                    "canary_expires_at": None,
                },
            }],
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(
            ValueError,
            match="claims live health without verified connectivity",
        ):
            client.agents.hub_readiness()
    finally:
        client.close()


def test_agents_resource_manages_connectors_and_optimistic_graph_revisions():
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request, body))
        if request.url.path.endswith("/connector-graph"):
            return httpx.Response(200, json={
                "version": "1.0",
                "enabled": True,
                "execution_mode": "sequential",
                "nodes": (body or {}).get("nodes", []),
                "revision": 1,
            })
        return httpx.Response(200, json={
            "id": "con-1",
            "agent_id": "agent/one",
            "type": "registry",
            "name": "Memory",
            "enabled": False,
            "config": {"registry_key": "memory"},
            "version": 1,
            "credential": {"present": False},
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        client.agents.create_connector(
            "agent/one",
            connector_type="registry",
            name="Memory",
            config={"registry_key": "memory", "capabilities": ["lookup"]},
        )
        client.agents.bind_connector_credential(
            "agent/one",
            "con/1",
            provider="vault",
            secret_ref="vault://tenant/connectors/memory",
            secret_type="bearer",
        )
        client.agents.put_connector_graph(
            "agent/one",
            expected_revision=0,
            enabled=True,
            execution_mode="parallel",
            max_concurrency=2,
            nodes=[{
                "id": "lookup",
                "connector_id": "con-1",
                "operation": "lookup",
                "when": {
                    "input_key": "codingSystem",
                    "operator": "equals",
                    "value": "ICD-10-CN",
                },
            }],
        )
        client.agents.delete_connector_graph("agent/one", expected_revision=1)
        client.agents.grant_memory_consent(
            "agent/one", acknowledgement=True, purpose_of_use="treatment",
        )
        client.agents.memory_consent("agent/one", purpose_of_use="treatment")
        client.agents.memory_readiness("agent/one", purpose_of_use="treatment")
        client.agents.revoke_memory_consent("agent/one", purpose_of_use="treatment")
    finally:
        client.close()

    assert calls[0][0].url.raw_path.decode() == (
        "/api/v2/agentic/agents/agent%2Fone/connectors"
    )
    assert calls[0][1]["config"]["registry_key"] == "memory"
    assert calls[1][0].url.raw_path.decode() == (
        "/api/v2/agentic/agents/agent%2Fone/connectors/con%2F1/credential"
    )
    assert calls[1][1]["secret_ref"] == "vault://tenant/connectors/memory"
    assert calls[2][1]["expected_revision"] == 0
    assert calls[2][1]["execution_mode"] == "parallel"
    assert calls[2][1]["max_concurrency"] == 2
    assert calls[3][0].method == "DELETE"
    assert calls[3][0].url.params["expected_revision"] == "1"
    assert calls[4][0].url.raw_path.decode() == (
        "/api/v2/agentic/agents/agent%2Fone/memory-consent"
    )
    assert calls[4][1]["acknowledgement"] is True
    assert calls[5][0].url.params["purpose_of_use"] == "treatment"
    assert calls[6][0].url.path.endswith("/memory-readiness")
    assert calls[6][0].url.params["purpose_of_use"] == "treatment"
    assert calls[7][0].method == "DELETE"
    assert calls[7][0].url.params["purpose_of_use"] == "treatment"
