from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation
from app.services.connector_http_transport import GovernedConnectorHTTPTransport
from app.services.connector_runtime import (
    ConnectorCredentialAdapter,
    build_connector_runtime,
    connector_data_policy_authorizer,
    connector_host_authorizer,
)


def _credential(secret_type: str = "bearer", *, version: int = 1):
    return SimpleNamespace(
        fingerprint="0123456789abcdef",
        version=version,
        secret_type=secret_type,
    )


def _invocation(classification: str, purpose: str = "treatment"):
    return ConnectorInvocation(
        organization_id="org-test",
        agent_id="agt-test",
        connector_id="con-test",
        operation="lookup",
        arguments={},
        data_classification=classification,
        purpose_of_use=purpose,
    )


def test_host_policy_requires_exact_allowlist_in_cloud_and_cn(monkeypatch):
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("ICODER_ENVIRONMENT", "eu")
    monkeypatch.delenv("ICODER_CONNECTOR_EGRESS_ALLOWLIST", raising=False)
    assert connector_host_authorizer("public.example") is True

    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv(
        "ICODER_CONNECTOR_EGRESS_ALLOWLIST",
        "approved.example, api.cn.example",
    )
    assert connector_host_authorizer("approved.example") is True
    assert connector_host_authorizer("sub.approved.example") is False

    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("ICODER_ENVIRONMENT", "cn")
    assert connector_host_authorizer("api.cn.example") is True
    assert connector_host_authorizer("unlisted.example") is False


def test_data_policy_defaults_phi_to_deny_and_requires_dedicated_host(monkeypatch):
    connector = SimpleNamespace(normalized_url="https://approved.example/a2a")
    monkeypatch.delenv("ICODER_CONNECTOR_ALLOW_PHI", raising=False)
    monkeypatch.delenv("ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST", raising=False)

    assert connector_data_policy_authorizer(
        connector, _invocation("deidentified"),
    ) is True
    assert connector_data_policy_authorizer(
        connector, _invocation("phi"),
    ) is False
    assert connector_data_policy_authorizer(
        connector, _invocation("non_phi", "research"),
    ) is False

    monkeypatch.setenv("ICODER_CONNECTOR_ALLOW_PHI", "1")
    monkeypatch.setenv(
        "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST", "approved.example",
    )
    assert connector_data_policy_authorizer(
        connector, _invocation("phi"),
    ) is True
    connector.normalized_url = "https://other.example/a2a"
    assert connector_data_policy_authorizer(
        connector, _invocation("phi"),
    ) is False


@pytest.mark.asyncio
async def test_static_credentials_use_fingerprint_service_and_reject_header_injection():
    resolved: list[str] = []

    def secret_resolver(service: str) -> str:
        resolved.append(service)
        return "safe-secret"

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None))
    transport = GovernedConnectorHTTPTransport(
        resolver=lambda host, port: ("93.184.216.34",),
        client=client,
    )
    adapter = ConnectorCredentialAdapter(
        transport,
        secret_resolver=secret_resolver,
    )
    assert await adapter(_credential("bearer")) == {
        "Authorization": "Bearer safe-secret"
    }
    assert await adapter(_credential("api-key")) == {"X-API-Key": "safe-secret"}
    assert resolved == [
        "connector_0123456789abcdef",
        "connector_0123456789abcdef",
    ]

    bad = ConnectorCredentialAdapter(
        transport,
        secret_resolver=lambda service: "value\r\nX-Evil: yes",
    )
    with pytest.raises(ConnectorExecutionError) as raised:
        await bad(_credential("bearer"))
    assert raised.value.code == "CONNECTOR_CREDENTIAL_RESOLUTION_FAILED"
    await client.aclose()


@pytest.mark.asyncio
async def test_oauth_client_credentials_are_pinned_bounded_and_cached():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url == httpx.URL("https://auth.example/token")
        assert b"client_secret=client-secret" in request.content
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
            },
        )

    raw = json.dumps({
        "token_url": "https://auth.example/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scope": "read:clinical",
    })
    now = 1000.0
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=lambda host, port: ("93.184.216.34",),
        client=client,
    )
    adapter = ConnectorCredentialAdapter(
        transport,
        secret_resolver=lambda service: raw,
        clock=lambda: now,
    )
    first = await adapter(_credential("oauth2-client"))
    second = await adapter(_credential("oauth2-client"))
    assert first == second == {"Authorization": "Bearer access-token"}
    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_runtime_builder_wires_transport_credentials_and_policy_without_io(monkeypatch):
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    runtime = build_connector_runtime()
    assert runtime.executor._remote_transport is runtime.transport
    assert runtime.executor._credential_resolver is not None
    assert runtime.executor._contextual_registry_invoker is runtime.registry_adapter
    assert runtime.registry_adapter._public_registry_provider is runtime.public_registry_provider
    assert runtime.agent_adapter is None
    assert runtime.executor._policy_authorizer is connector_data_policy_authorizer
    await runtime.aclose()


@pytest.mark.asyncio
async def test_runtime_builder_wires_internal_agent_adapter_when_app_is_available():
    app = SimpleNamespace(state=SimpleNamespace())
    runtime = build_connector_runtime(app)
    assert runtime.agent_adapter is not None
    assert runtime.executor._contextual_agent_invoker is runtime.agent_adapter
    assert runtime.status()["internal_agent_adapter"]["cycle_guard"] is True
    assert runtime.status()["registry_adapter"]["public_provider"][
        "deidentified_queries_only"
    ] is True
    await runtime.aclose()
