from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpcore
import httpx
import pytest

from app.services.connector_executor import (
    ConnectorTransportError,
    ConnectorTransportRequest,
)
from app.services.connector_http_transport import (
    GovernedConnectorHTTPTransport,
    PinnedAsyncHTTPTransport,
    PinnedDNSNetworkBackend,
    canonical_agent_card_digest,
)
from app.services.ssrf_guard import SSRFError


def _request(
    connector_type: str,
    *,
    operation: str,
    binding: str,
    arguments: dict | None = None,
    **overrides,
) -> ConnectorTransportRequest:
    values = {
        "connector_type": connector_type,
        "url": "https://connector.example/a2a" if connector_type == "a2a" else "https://connector.example/mcp",
        "operation": operation,
        "arguments": arguments or {},
        "protocol_binding": binding,
        "connect_timeout_seconds": 1.0,
        "total_timeout_seconds": 2.0,
        "max_response_bytes": 4096,
        "session_scope": "org-test:con-test:1",
    }
    values.update(overrides)
    return ConnectorTransportRequest(**values)


def _public_resolver(_host: str, _port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_pinned_transport_does_not_require_optional_http2_runtime():
    transport = PinnedAsyncHTTPTransport(resolver=_public_resolver)
    assert transport._pool._http1 is True
    assert transport._pool._http2 is False


@pytest.mark.asyncio
async def test_mcp_streamable_http_initializes_once_and_propagates_session():
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content or b"{}")
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": "session-safe-1",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"protocolVersion": "2025-03-26", "capabilities": {}},
                },
            )
        if body.get("method") == "notifications/initialized":
            assert request.headers["Mcp-Session-Id"] == "session-safe-1"
            return httpx.Response(202, content=b"")
        assert body["method"] == "tools/call"
        assert request.headers["Mcp-Session-Id"] == "session-safe-1"
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    request = _request(
        "mcp",
        operation="lookup",
        binding="streamable-http",
        arguments={"code": "I21"},
        headers={"Authorization": "Bearer test-token"},
    )
    first = await transport(request)
    second = await transport(request)
    isolated = await transport(replace(request, session_scope="org-other:con-test:1"))
    await client.aclose()

    assert first["content"][0]["text"] == "ok"
    assert second == first
    assert isolated == first
    assert len(calls) == 7  # each security scope owns its own MCP session


@pytest.mark.asyncio
async def test_a2a_jsonrpc_and_http_json_bindings_are_real_protocol_requests():
    seen: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        seen.append((request.method, str(request.url), body))
        assert request.headers["A2A-Version"] == "1.0"
        if body.get("jsonrpc") == "2.0":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/a2a+json"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"kind": "message", "messageId": "msg-1"},
                },
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"kind": "task", "id": "task-1", "status": {"state": "completed"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    rpc = await transport(
        _request(
            "a2a",
            operation="SendMessage",
            binding="JSONRPC",
            arguments={"message": {"role": "ROLE_USER", "parts": [{"text": "hi"}]}},
        )
    )
    rest = await transport(
        _request(
            "a2a",
            operation="GetTask",
            binding="HTTP+JSON",
            arguments={"taskId": "task/1", "historyLength": 2, "ignored": "no"},
        )
    )
    await client.aclose()

    assert rpc["messageId"] == "msg-1"
    assert rest["id"] == "task-1"
    assert seen[0][2]["method"] == "SendMessage"
    assert seen[1][0] == "GET"
    assert seen[1][1].endswith("/a2a/tasks/task%2F1?historyLength=2")


@pytest.mark.asyncio
async def test_redirects_default_deny_and_same_origin_is_bounded():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content or b"{}")
        if request.url.path.endswith("/a2a"):
            return httpx.Response(307, headers={"Location": "/a2a-v2"})
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"ok": True}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    with pytest.raises(ConnectorTransportError) as denied:
        await transport(_request("a2a", operation="GetTask", binding="JSONRPC"))
    assert denied.value.code == "CONNECTOR_REDIRECT_FORBIDDEN"
    assert calls == 1

    result = await transport(
        _request(
            "a2a",
            operation="GetTask",
            binding="JSONRPC",
            redirect_policy="same-origin",
            max_redirects=1,
        )
    )
    await client.aclose()
    assert result == {"ok": True}
    assert calls == 3


@pytest.mark.asyncio
async def test_cross_origin_redirect_response_limit_and_content_type_fail_closed():
    mode = "cross-origin"

    async def handler(request: httpx.Request) -> httpx.Response:
        if mode == "cross-origin":
            return httpx.Response(308, headers={"Location": "https://evil.example/a2a"})
        if mode == "oversized":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b"x" * 2048,
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"{}",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    request = _request(
        "a2a",
        operation="GetTask",
        binding="JSONRPC",
        redirect_policy="same-origin",
        max_redirects=1,
        max_response_bytes=1024,
    )
    with pytest.raises(ConnectorTransportError) as cross_origin:
        await transport(request)
    assert cross_origin.value.code == "CONNECTOR_REDIRECT_ORIGIN_FORBIDDEN"

    mode = "oversized"
    with pytest.raises(ConnectorTransportError) as oversized:
        await transport(request)
    assert oversized.value.code == "CONNECTOR_RESPONSE_TOO_LARGE"

    mode = "content-type"
    with pytest.raises(ConnectorTransportError) as content_type:
        await transport(request)
    assert content_type.value.code == "CONNECTOR_RESPONSE_CONTENT_TYPE_INVALID"
    await client.aclose()


@pytest.mark.asyncio
async def test_public_registry_json_get_owns_host_encoding_and_bounds():
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"ok": True},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
        host_authorizer=lambda host: host == "registry.example",
    )
    result = await transport.get_json(
        base_url="https://registry.example/v2/search",
        expected_host="registry.example",
        params={"query.term": "heart failure & diabetes", "pageSize": 5},
        max_response_bytes=4096,
    )
    assert result == {"ok": True}
    assert seen[0].method == "GET"
    assert seen[0].url.params["query.term"] == "heart failure & diabetes"
    assert seen[0].url.params["pageSize"] == "5"
    assert seen[0].headers["Accept"] == "application/json"

    with pytest.raises(ConnectorTransportError) as host_mismatch:
        await transport.get_json(
            base_url="https://evil.example/v2/search",
            expected_host="registry.example",
            params={},
        )
    assert host_mismatch.value.code == "CONNECTOR_EGRESS_NOT_APPROVED"
    await client.aclose()


@pytest.mark.asyncio
async def test_public_registry_json_get_denies_redirect_size_and_total_timeout():
    mode = "redirect"

    async def handler(request: httpx.Request) -> httpx.Response:
        if mode == "redirect":
            return httpx.Response(307, headers={"Location": "/other"})
        if mode == "oversized":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                content=b"{" + b'"x":"' + b"a" * 2048 + b'"}',
            )
        await asyncio.sleep(0.2)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"ok": True},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    request = {
        "base_url": "https://registry.example/search",
        "expected_host": "registry.example",
        "params": {"query": "safe"},
        "max_response_bytes": 1024,
    }
    with pytest.raises(ConnectorTransportError) as redirect:
        await transport.get_json(**request)
    assert redirect.value.code == "CONNECTOR_REDIRECT_FORBIDDEN"

    mode = "oversized"
    with pytest.raises(ConnectorTransportError) as oversized:
        await transport.get_json(**request)
    assert oversized.value.code == "CONNECTOR_RESPONSE_TOO_LARGE"

    mode = "timeout"
    with pytest.raises(ConnectorTransportError) as timeout:
        await transport.get_json(**request, total_timeout_seconds=0.1)
    assert timeout.value.code == "CONNECTOR_UPSTREAM_TIMEOUT"
    assert timeout.value.retryable is True
    await client.aclose()


class _ObservedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.hosts.append(host)
        return object()

    async def connect_unix_socket(self, *args, **kwargs):
        raise AssertionError("unexpected unix socket")

    async def sleep(self, seconds):
        return None


@pytest.mark.asyncio
async def test_dns_result_is_the_actual_tcp_destination_and_denial_prevents_connect():
    backend = _ObservedBackend()
    pinned = PinnedDNSNetworkBackend(
        resolver=lambda host, port: ("93.184.216.34",),
        backend=backend,
    )
    stream = await pinned.connect_tcp("connector.example", 443)
    assert stream is not None
    assert backend.hosts == ["93.184.216.34"]

    def deny(host: str, port: int) -> tuple[str, ...]:
        raise SSRFError(host, "private target")

    pinned = PinnedDNSNetworkBackend(resolver=deny, backend=backend)
    with pytest.raises(httpcore.ConnectError):
        await pinned.connect_tcp("connector.example", 443)
    assert backend.hosts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_upstream_status_and_jsonrpc_error_are_stable_and_redacted():
    mode = "status"

    async def handler(request: httpx.Request) -> httpx.Response:
        if mode == "status":
            return httpx.Response(503, content=b"patient payload must never escape")
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": "x",
                "error": {"code": -32000, "message": "patient payload"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    request = _request("a2a", operation="GetTask", binding="JSONRPC")
    with pytest.raises(ConnectorTransportError) as status:
        await transport(request)
    assert status.value.code == "CONNECTOR_UPSTREAM_503"
    assert status.value.retryable is True
    assert status.value.http_status_class == "5xx"
    assert "patient" not in str(status.value)

    mode = "rpc"
    with pytest.raises(ConnectorTransportError) as rpc:
        await transport(request)
    assert rpc.value.code == "CONNECTOR_UPSTREAM_RPC_ERROR"
    assert "patient" not in str(rpc.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_streaming_a2a_accepts_bounded_multiline_sse_event():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            content=(
                b"event: task-status-update\n"
                b"data: {\"kind\":\"task\",\n"
                b"data: \"id\":\"task-1\"}\n\n"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    result = await transport(
        _request(
            "a2a",
            operation="SubscribeToTask",
            binding="HTTP+JSON",
            arguments={"taskId": "task-1"},
        )
    )
    assert result == {"kind": "task", "id": "task-1"}
    await client.aclose()


@pytest.mark.asyncio
async def test_pinned_agent_card_is_verified_before_a2a_payload_and_cached():
    get_calls = 0
    post_calls = 0
    card = {
        "name": "Pinned Agent",
        "description": "Synthetic",
        "version": "1.0.0",
        "supportedInterfaces": [{
            "url": "https://connector.example/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }],
        "capabilities": {},
        "skills": [],
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_calls, post_calls
        if request.method == "GET":
            get_calls += 1
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json=card,
            )
        post_calls += 1
        body = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"ok": True}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    request = _request(
        "a2a",
        operation="GetTask",
        binding="JSONRPC",
        agent_card_url="https://connector.example/.well-known/agent-card.json",
        agent_card_digest=canonical_agent_card_digest(card),
    )
    assert await transport(request) == {"ok": True}
    assert await transport(request) == {"ok": True}
    assert (get_calls, post_calls) == (1, 2)

    with pytest.raises(ConnectorTransportError) as mismatch:
        await transport(replace(request, agent_card_digest="0" * 64))
    assert mismatch.value.code == "CONNECTOR_AGENT_CARD_DIGEST_MISMATCH"
    assert (get_calls, post_calls) == (2, 2)
    await client.aclose()


@pytest.mark.asyncio
async def test_network_timeout_maps_to_retryable_stable_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("raw destination details")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=_public_resolver,
        client=client,
    )
    with pytest.raises(ConnectorTransportError) as raised:
        await transport(_request("a2a", operation="GetTask", binding="JSONRPC"))
    assert raised.value.code == "CONNECTOR_UPSTREAM_TIMEOUT"
    assert raised.value.retryable is True
    assert "destination" not in str(raised.value)
    await client.aclose()
