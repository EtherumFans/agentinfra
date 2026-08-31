from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation
from app.services.connector_external_registry import (
    GATEWAY_REQUEST_CONTRACT,
    GATEWAY_RESPONSE_CONTRACT,
    GovernedExternalRegistryProvider,
)
from app.services.connector_http_transport import GovernedConnectorHTTPTransport


def _invocation(
    key: str,
    query: str = "aspirin",
    *,
    organization_id: str = "org-approved",
) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id=organization_id,
        agent_id="agt-test",
        connector_id="con-test",
        operation={"drugbank": "lookup", "posos": "guide", "web-search": "search"}[key],
        arguments={"query": query, "max_results": 3},
        run_id="run-test",
        data_classification="deidentified",
        purpose_of_use="treatment",
    )


class _FakeTransport:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    async def post_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses[kwargs["base_url"]]


def _provider(transport, **overrides) -> GovernedExternalRegistryProvider:
    arguments = {
        "credential_resolver": lambda service: f"secret-{service}",
        "host_authorizer": lambda host: host == "gateway.example.org",
        "endpoints": {
            "drugbank": "https://gateway.example.org/drugbank/query",
            "posos": "https://gateway.example.org/posos/query",
            "web-search": "https://gateway.example.org/search/query",
        },
        "region": "CN",
        "web_provider_opt_in": True,
        "web_tenant_opt_in_organizations": frozenset({"org-approved"}),
    }
    arguments.update(overrides)
    return GovernedExternalRegistryProvider(transport, **arguments)


@pytest.mark.asyncio
async def test_drugbank_gateway_executes_contract_and_projects_minimum_fields():
    endpoint = "https://gateway.example.org/drugbank/query"
    transport = _FakeTransport({endpoint: {
        "contract": GATEWAY_RESPONSE_CONTRACT,
        "provider": "drugbank",
        "total_available": 1,
        "results": [{
            "drugbank_id": "DB00945",
            "name": "Aspirin",
            "description": "An antiplatelet medicine",
            "indication": "Licensed indication text",
            "interactions": [{
                "drug": "Warfarin",
                "severity": "major",
                "description": "Bleeding risk may increase",
                "source_url": "https://go.drugbank.com/drugs/DB00945",
                "ignored_vendor_field": "not projected",
            }],
            "source_url": "https://go.drugbank.com/drugs/DB00945",
            "raw_vendor_payload": "not projected",
        }],
    }})

    result = await _provider(transport)("drugbank", _invocation("drugbank"))

    assert result["returned"] == 1
    assert result["drugs"][0]["drugbank_id"] == "DB00945"
    assert "raw_vendor_payload" not in repr(result)
    assert "ignored_vendor_field" not in repr(result)
    assert result["live_external_performed"] is True
    call = transport.calls[0]
    assert call["expected_host"] == "gateway.example.org"
    assert call["body"] == {
        "contract": GATEWAY_REQUEST_CONTRACT,
        "provider": "drugbank",
        "operation": "lookup",
        "query": "aspirin",
        "max_results": 3,
        "region": "CN",
    }
    assert call["headers"] == {"Authorization": "Bearer secret-drugbank"}
    assert "secret-drugbank" not in repr(result)


@pytest.mark.asyncio
async def test_posos_and_web_search_gateway_outputs_are_bounded_and_review_only():
    transport = _FakeTransport({
        "https://gateway.example.org/posos/query": {
            "contract": GATEWAY_RESPONSE_CONTRACT,
            "provider": "posos",
            "total_available": 1,
            "results": [{
                "medication": "Metformin",
                "summary": "Reference guidance",
                "contraindications": ["Severe renal impairment"],
                "interactions": ["Review concomitant therapy"],
                "citations": [{
                    "title": "Licensed monograph",
                    "url": "https://reference.example/monograph",
                }],
            }],
        },
        "https://gateway.example.org/search/query": {
            "contract": GATEWAY_RESPONSE_CONTRACT,
            "provider": "web-search",
            "total_available": 1,
            "results": [{
                "title": "National clinical guidance",
                "url": "https://health.example/guidance?q=asthma#tracking",
                "snippet": "Guidance summary",
                "source": "Health authority",
                "published": "2026-01-01",
            }],
        },
    })
    provider = _provider(transport)

    posos = await provider("posos", _invocation("posos", "metformin"))
    web = await provider("web-search", _invocation("web-search", "asthma guidance"))

    assert posos["guidance"][0]["medication"] == "Metformin"
    assert "clinician_review_required" in posos["clinical_use"]
    assert web["results"][0]["url"] == "https://health.example/guidance?q=asthma"
    assert web["authoritative"] is False


@pytest.mark.asyncio
async def test_external_gate_fails_closed_before_transport_for_policy_and_phi():
    transport = _FakeTransport({})
    cases = [
        (
            _provider(transport, endpoints={}),
            "drugbank",
            _invocation("drugbank"),
            "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED",
        ),
        (
            _provider(transport, credential_resolver=lambda _service: None),
            "drugbank",
            _invocation("drugbank"),
            "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED",
        ),
        (
            _provider(transport, web_provider_opt_in=False),
            "web-search",
            _invocation("web-search"),
            "CONNECTOR_REGISTRY_OPT_IN_REQUIRED",
        ),
        (
            _provider(transport),
            "web-search",
            _invocation("web-search", organization_id="org-not-approved"),
            "CONNECTOR_REGISTRY_OPT_IN_REQUIRED",
        ),
        (
            _provider(transport),
            "drugbank",
            replace(_invocation("drugbank"), data_classification="phi"),
            "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED",
        ),
        (
            _provider(transport),
            "drugbank",
            _invocation("drugbank", "患者张三正在服用阿司匹林"),
            "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED",
        ),
        (
            _provider(transport, region="APAC"),
            "drugbank",
            _invocation("drugbank"),
            "CONNECTOR_REGISTRY_REGION_BLOCKED",
        ),
    ]
    for provider, key, invocation, expected in cases:
        with pytest.raises(ConnectorExecutionError) as raised:
            await provider(key, invocation)
        assert raised.value.code == expected
    assert transport.calls == []


@pytest.mark.asyncio
async def test_external_gateway_rejects_wrong_contract_provider_and_unsafe_url():
    endpoint = "https://gateway.example.org/drugbank/query"
    bad_responses = [
        {"contract": "wrong", "provider": "drugbank", "total_available": 0, "results": []},
        {"contract": GATEWAY_RESPONSE_CONTRACT, "provider": "posos", "total_available": 0, "results": []},
        {
            "contract": GATEWAY_RESPONSE_CONTRACT,
            "provider": "drugbank",
            "total_available": 1,
            "results": [{
                "drugbank_id": "DB00945",
                "name": "Aspirin",
                "source_url": "http://unsafe.example/drug",
            }],
        },
    ]
    for response in bad_responses:
        transport = _FakeTransport({endpoint: response})
        with pytest.raises(ConnectorExecutionError) as raised:
            await _provider(transport)("drugbank", _invocation("drugbank"))
        assert raised.value.code == "CONNECTOR_REGISTRY_RESPONSE_INVALID"


def test_external_registry_status_is_truthful_and_secret_free():
    secret = "secret-value-must-never-leak"
    provider = _provider(
        _FakeTransport({}), credential_resolver=lambda _service: secret,
    )

    status = provider.status()

    assert status["providers"]["drugbank"]["configured"] is True
    assert status["providers"]["web-search"]["tenant_opt_in_count"] == 1
    assert secret not in repr(status)
    assert "gateway.example.org" not in repr(status)


@pytest.mark.asyncio
async def test_expert_async_compatibility_apis_use_governed_provider_outputs():
    from app.agents.experts.drugbank_expert import lookup_async
    from app.agents.experts.posos_expert import guide_async
    from app.agents.experts.web_search_expert import search_async

    async def provider(key, _invocation):
        if key == "drugbank":
            return {
                "drugs": [{
                    "drugbank_id": "DB00945", "name": "Aspirin",
                    "interactions": [{"drug": "Warfarin"}],
                }],
                "live_external_performed": True,
            }
        if key == "posos":
            return {
                "guidance": [{"medication": "Metformin", "summary": "Review"}],
                "live_external_performed": True,
            }
        return {
            "results": [{"title": "Guidance", "url": "https://health.example"}],
            "live_external_performed": True,
        }

    drugbank = await lookup_async(
        "aspirin", organization_id="org-approved", provider=provider,
    )
    posos = await guide_async(
        "metformin", organization_id="org-approved", provider=provider,
    )
    web = await search_async(
        "guidance", organization_id="org-approved", provider=provider,
    )

    assert drugbank.live_lookup_performed is True
    assert drugbank.drug_info["drugbank_id"] == "DB00945"
    assert posos.live_lookup_performed is True
    assert posos.guidance["medication"] == "Metformin"
    assert web.live_search_performed is True
    assert web.results[0]["title"] == "Guidance"


@pytest.mark.asyncio
async def test_governed_transport_post_json_enforces_origin_and_request_bounds():
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"ok": True},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=False, trust_env=False,
    )
    transport = GovernedConnectorHTTPTransport(
        client=client,
        resolver=lambda _host, _port: ("203.0.113.10",),
        host_authorizer=lambda host: host == "gateway.example.org",
    )
    try:
        result = await transport.post_json(
            base_url="https://gateway.example.org/query",
            expected_host="gateway.example.org",
            headers={"Authorization": "Bearer opaque"},
            body={"query": "aspirin"},
        )
        assert result == {"ok": True}
        assert captured[0].headers["authorization"] == "Bearer opaque"

        with pytest.raises(ConnectorExecutionError) as wrong_host:
            await transport.post_json(
                base_url="https://evil.example/query",
                expected_host="gateway.example.org",
                headers={},
                body={},
            )
        assert wrong_host.value.code == "CONNECTOR_EGRESS_NOT_APPROVED"

        with pytest.raises(ConnectorExecutionError) as plain_http:
            await transport.post_json(
                base_url="http://127.0.0.1:9000/query",
                expected_host="127.0.0.1",
                headers={},
                body={},
            )
        assert plain_http.value.code == "CONNECTOR_EGRESS_NOT_APPROVED"

        with pytest.raises(ConnectorExecutionError) as injected:
            await transport.post_json(
                base_url="https://gateway.example.org/query",
                expected_host="gateway.example.org",
                headers={"Authorization": "Bearer ok\r\nX-Evil: yes"},
                body={},
            )
        assert injected.value.code == "CONNECTOR_ARGUMENTS_INVALID"
    finally:
        await transport.aclose()
        await client.aclose()
