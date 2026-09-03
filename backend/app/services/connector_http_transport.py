"""Governed outbound HTTP transport for MCP and A2A connectors.

The transport owns the last network boundary.  It does not inherit operating
system proxy settings, resolves and validates every hostname, pins the TCP
socket to an approved literal IP while preserving TLS SNI, refuses unsafe
redirects, and bounds response bytes before JSON parsing.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, urlencode, urljoin, urlsplit

import httpcore
import httpx

from app.services.connector_executor import (
    ConnectorTransportError,
    ConnectorTransportRequest,
)
from app.services.ssrf_guard import SSRFError, resolve_safe_addresses


AddressResolver = Callable[[str, int], tuple[str, ...]]
HostAuthorizer = Callable[[str], bool]


def canonical_agent_card_digest(card: dict[str, Any]) -> str:
    """Return the pinned digest contract used by A2A Connector configs."""

    encoded = json.dumps(
        card,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PinnedDNSNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve, approve, then connect to the exact approved IP literal."""

    def __init__(
        self,
        *,
        resolver: AddressResolver = resolve_safe_addresses,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[tuple] | None = None,
    ):
        try:
            addresses = self._resolver(host, port)
        except SSRFError as exc:
            raise httpcore.ConnectError("outbound destination denied") from exc
        if not addresses:
            raise httpcore.ConnectError("outbound destination unresolved")

        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    host=address,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("outbound connection failed")

    async def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.UnsupportedProtocol("unix sockets are forbidden")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _CoreResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream) -> None:
        self._stream = stream

    async def __aiter__(self):
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        if hasattr(self._stream, "aclose"):
            await self._stream.aclose()


class PinnedAsyncHTTPTransport(httpx.AsyncBaseTransport):
    """Small httpx/httpcore bridge accepting a pinned network backend."""

    def __init__(
        self,
        *,
        resolver: AddressResolver = resolve_safe_addresses,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        # Match httpx's isolated trust model instead of inheriting the Windows
        # system certificate store. This keeps proxy/enterprise roots out of
        # the Connector boundary and avoids provider-specific TLS rejection.
        ssl_context = httpx.create_ssl_context(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context,
            max_connections=32,
            max_keepalive_connections=8,
            keepalive_expiry=10.0,
            http1=True,
            # Keep the security transport independent of the optional ``h2``
            # package. Both governed public registries and the supported
            # MCP/A2A HTTP bindings work over HTTP/1.1.
            http2=False,
            retries=0,
            network_backend=PinnedDNSNetworkBackend(
                resolver=resolver,
                backend=network_backend,
            ),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_CoreResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


@dataclass(frozen=True)
class _BoundedDocument:
    status_code: int
    headers: dict[str, str]
    value: dict[str, Any] | None


_A2A_HTTP_PATHS = {
    "SendMessage": ("POST", "message:send"),
    "SendStreamingMessage": ("POST", "message:stream"),
    "ListTasks": ("GET", "tasks"),
    "GetTask": ("GET", "tasks/{task_id}"),
    "CancelTask": ("POST", "tasks/{task_id}:cancel"),
    "SubscribeToTask": ("POST", "tasks/{task_id}:subscribe"),
}


class GovernedConnectorHTTPTransport:
    """Callable adapter consumed by :class:`ConnectorExecutor`."""

    def __init__(
        self,
        *,
        resolver: AddressResolver = resolve_safe_addresses,
        client: httpx.AsyncClient | None = None,
        host_authorizer: HostAuthorizer | None = None,
        allow_loopback_http_for_testing: bool = False,
    ) -> None:
        self._resolver = resolver
        self._host_authorizer = host_authorizer
        self._allow_loopback_http_for_testing = bool(
            allow_loopback_http_for_testing
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            transport=PinnedAsyncHTTPTransport(resolver=resolver),
            follow_redirects=False,
            trust_env=False,
        )
        self._mcp_sessions: dict[tuple[str, str], str] = {}
        self._mcp_initialized: set[tuple[str, str]] = set()
        self._mcp_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._verified_a2a_cards: set[tuple[str, str, str, str]] = set()

    async def __call__(self, request: ConnectorTransportRequest) -> dict[str, Any]:
        self._validate_request(request)
        if request.connector_type == "mcp":
            return await self._call_mcp(request)
        if request.connector_type == "a2a":
            return await self._call_a2a(request)
        raise ConnectorTransportError("CONNECTOR_TRANSPORT_TYPE_UNSUPPORTED")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_json(
        self,
        *,
        base_url: str,
        expected_host: str,
        params: Mapping[str, str | int],
        connect_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 15.0,
        max_response_bytes: int = 512 * 1024,
    ) -> dict[str, Any]:
        """Perform a fixed-host, bounded JSON GET for approved registries.

        The caller owns the provider-specific path and parameter allowlist. This
        method owns URL encoding, exact-host verification, the pinned network
        backend, proxy isolation, redirect denial, timeouts and response bounds.
        """

        canonical_host = expected_host.strip().rstrip(".").casefold()
        try:
            parsed = urlsplit(base_url)
            actual_host = (parsed.hostname or "").rstrip(".").casefold()
            port = parsed.port
        except ValueError as exc:
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED") from exc
        if (
            not canonical_host
            or actual_host != canonical_host
            or parsed.scheme.casefold() != "https"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or port not in (None, 443)
        ):
            raise ConnectorTransportError("CONNECTOR_EGRESS_NOT_APPROVED")
        if (
            not 0.1 <= connect_timeout_seconds <= 30.0
            or not 0.1 <= total_timeout_seconds <= 60.0
            or not 1024 <= max_response_bytes <= 2 * 1024 * 1024
        ):
            raise ConnectorTransportError("CONNECTOR_TRANSPORT_LIMIT_INVALID")

        query: dict[str, str] = {}
        for key, raw_value in params.items():
            if (
                not isinstance(key, str)
                or not key
                or len(key) > 64
                or any(char in key for char in "\r\n\t&=")
                or isinstance(raw_value, bool)
                or not isinstance(raw_value, (str, int))
            ):
                raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID")
            value = str(raw_value)
            if len(value) > 4096 or any(char in value for char in "\r\n\x00"):
                raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID")
            query[key] = value
        encoded = urlencode(query)
        url = f"{base_url}?{encoded}" if encoded else base_url
        request = ConnectorTransportRequest(
            connector_type="registry",
            url=url,
            operation="GET",
            arguments={},
            connect_timeout_seconds=connect_timeout_seconds,
            total_timeout_seconds=total_timeout_seconds,
            max_response_bytes=max_response_bytes,
            redirect_policy="deny",
            max_redirects=0,
            session_scope=f"public-registry:{canonical_host}",
        )
        try:
            async with asyncio.timeout(total_timeout_seconds):
                document = await self._send_document(
                    request,
                    method="GET",
                    url=url,
                    headers={"Accept": "application/json"},
                    body=None,
                )
        except TimeoutError as exc:
            raise ConnectorTransportError(
                "CONNECTOR_UPSTREAM_TIMEOUT", retryable=True,
            ) from exc
        if not isinstance(document.value, dict):
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        return document.value

    async def post_json(
        self,
        *,
        base_url: str,
        expected_host: str,
        headers: Mapping[str, str],
        body: dict[str, Any],
        connect_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 15.0,
        max_response_bytes: int = 512 * 1024,
    ) -> dict[str, Any]:
        """Perform a fixed-origin, bounded JSON POST for approved gateways.

        Provider adapters own the endpoint, authentication convention and
        request schema. This boundary rejects caller-controlled origins,
        redirects, unsafe headers, oversized request/response documents and
        non-JSON responses. Plain HTTP is available only through an explicit
        constructor flag and only for a loopback integration-test endpoint.
        """

        canonical_host = expected_host.strip().rstrip(".").casefold()
        try:
            parsed = urlsplit(base_url)
            actual_host = (parsed.hostname or "").rstrip(".").casefold()
            port = parsed.port
        except ValueError as exc:
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED") from exc
        loopback_test_url = self._is_allowed_loopback_http(parsed)
        if (
            not canonical_host
            or actual_host != canonical_host
            or (parsed.scheme.casefold() != "https" and not loopback_test_url)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (not loopback_test_url and port not in (None, 443))
        ):
            raise ConnectorTransportError("CONNECTOR_EGRESS_NOT_APPROVED")
        if (
            not 0.1 <= connect_timeout_seconds <= 30.0
            or not 0.1 <= total_timeout_seconds <= 60.0
            or not 1024 <= max_response_bytes <= 2 * 1024 * 1024
        ):
            raise ConnectorTransportError("CONNECTOR_TRANSPORT_LIMIT_INVALID")
        if not isinstance(body, dict):
            raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID")
        try:
            encoded_body = json.dumps(
                body,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID") from exc
        if len(encoded_body) > 64 * 1024:
            raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID")

        safe_headers: dict[str, str] = {}
        for key, value in headers.items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or not key
                or len(key) > 64
                or len(value) > 8192
                or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for char in key)
                or key.casefold() in {"host", "content-length", "transfer-encoding"}
                or any(char in value for char in "\r\n\x00")
            ):
                raise ConnectorTransportError("CONNECTOR_ARGUMENTS_INVALID")
            safe_headers[key] = value

        request = ConnectorTransportRequest(
            connector_type="registry",
            url=base_url,
            operation="POST",
            arguments={},
            connect_timeout_seconds=connect_timeout_seconds,
            total_timeout_seconds=total_timeout_seconds,
            max_response_bytes=max_response_bytes,
            redirect_policy="deny",
            max_redirects=0,
            session_scope=f"external-registry:{canonical_host}"[:128],
        )
        try:
            async with asyncio.timeout(total_timeout_seconds):
                document = await self._send_document(
                    request,
                    method="POST",
                    url=base_url,
                    headers={"Accept": "application/json", **safe_headers},
                    body=body,
                )
        except TimeoutError as exc:
            raise ConnectorTransportError(
                "CONNECTOR_UPSTREAM_TIMEOUT", retryable=True,
            ) from exc
        if not isinstance(document.value, dict):
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        return document.value

    async def exchange_oauth2_client_credentials(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "",
    ) -> tuple[str, float]:
        """Perform a bounded, pinned OAuth2 client-credentials exchange."""

        self._validate_target(token_url)
        if (
            not client_id
            or not client_secret
            or len(client_id) > 1024
            or len(client_secret) > 4096
            or any(char in client_id + client_secret for char in "\r\n")
        ):
            raise ConnectorTransportError("CONNECTOR_OAUTH_CREDENTIAL_INVALID")
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            if len(scope) > 2048 or "\r" in scope or "\n" in scope:
                raise ConnectorTransportError("CONNECTOR_OAUTH_CREDENTIAL_INVALID")
            form["scope"] = scope
        try:
            async with self._client.stream(
                "POST",
                token_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "iCoDer-Connector-Runtime/1.0",
                },
                content=urlencode(form).encode("utf-8"),
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0),
            ) as response:
                if response.status_code >= 400:
                    self._raise_status(response.status_code)
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 64 * 1024:
                        raise ConnectorTransportError("CONNECTOR_RESPONSE_TOO_LARGE")
                document = self._parse_document(
                    bytes(raw),
                    response.headers.get("content-type", ""),
                    allow_empty=False,
                )
        except ConnectorTransportError:
            raise
        except (httpx.TimeoutException, httpcore.TimeoutException) as exc:
            raise ConnectorTransportError(
                "CONNECTOR_OAUTH_TIMEOUT", retryable=True,
            ) from exc
        except (httpx.NetworkError, httpcore.NetworkError, OSError) as exc:
            raise ConnectorTransportError(
                "CONNECTOR_OAUTH_UNAVAILABLE", retryable=True,
            ) from exc
        token = document.get("access_token") if document else None
        token_type = str(document.get("token_type", "Bearer")) if document else ""
        expires_in = document.get("expires_in", 300) if document else 0
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or "\r" in token
            or "\n" in token
            or token_type.casefold() != "bearer"
        ):
            raise ConnectorTransportError("CONNECTOR_OAUTH_RESPONSE_INVALID")
        try:
            lifetime = max(60.0, min(float(expires_in), 86_400.0))
        except (TypeError, ValueError) as exc:
            raise ConnectorTransportError("CONNECTOR_OAUTH_RESPONSE_INVALID") from exc
        return token, lifetime

    def _validate_request(self, request: ConnectorTransportRequest) -> None:
        if request.connector_type not in {"mcp", "a2a"}:
            raise ConnectorTransportError("CONNECTOR_TRANSPORT_TYPE_UNSUPPORTED")
        if request.redirect_policy not in {"deny", "same-origin"}:
            raise ConnectorTransportError("CONNECTOR_REDIRECT_POLICY_INVALID")
        if not 0 <= request.max_redirects <= 2:
            raise ConnectorTransportError("CONNECTOR_REDIRECT_POLICY_INVALID")
        if (
            not request.session_scope
            or len(request.session_scope) > 128
            or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for char in request.session_scope)
        ):
            raise ConnectorTransportError("CONNECTOR_SESSION_SCOPE_INVALID")
        self._validate_target(request.url)

    def _validate_target(self, url: str) -> None:
        if any(char in url for char in "\r\n\t"):
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED")
        try:
            parsed = urlsplit(url)
            port = parsed.port
            hostname = parsed.hostname
        except ValueError as exc:
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED") from exc
        loopback_test_url = self._is_allowed_loopback_http(parsed)
        if (
            (parsed.scheme.casefold() != "https" and not loopback_test_url)
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or (not loopback_test_url and port not in (None, 443))
        ):
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED")
        if self._host_authorizer is not None and self._host_authorizer(
            hostname.casefold()
        ) is not True:
            raise ConnectorTransportError("CONNECTOR_EGRESS_NOT_APPROVED")
        try:
            self._resolver(hostname, port or 443)
        except SSRFError as exc:
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED") from exc

    def _is_allowed_loopback_http(self, parsed: Any) -> bool:
        if not self._allow_loopback_http_for_testing:
            return False
        hostname = (parsed.hostname or "").rstrip(".").casefold()
        return (
            parsed.scheme.casefold() == "http"
            and hostname in {"127.0.0.1", "localhost", "::1"}
            and parsed.port is not None
            and 1024 <= parsed.port <= 65535
        )

    async def _call_mcp(self, request: ConnectorTransportRequest) -> dict[str, Any]:
        if request.protocol_binding != "streamable-http":
            raise ConnectorTransportError("CONNECTOR_MCP_TRANSPORT_UNSUPPORTED")
        session_key = (request.url, request.session_scope)
        lock = self._mcp_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            if session_key not in self._mcp_initialized:
                await self._initialize_mcp(request, session_key)
        headers = dict(request.headers)
        session_id = self._mcp_sessions.get(session_key)
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        envelope = {
            "jsonrpc": "2.0",
            "id": f"con-{uuid.uuid4().hex}",
            "method": "tools/call",
            "params": {
                "name": request.operation,
                "arguments": request.arguments,
            },
        }
        document = await self._send_document(
            request,
            method="POST",
            url=request.url,
            headers=headers,
            body=envelope,
        )
        return self._unwrap_jsonrpc(document.value)

    async def _initialize_mcp(
        self,
        request: ConnectorTransportRequest,
        session_key: tuple[str, str],
    ) -> None:
        envelope = {
            "jsonrpc": "2.0",
            "id": f"init-{uuid.uuid4().hex}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "icoder-connector-runtime", "version": "1.0"},
            },
        }
        initialized = await self._send_document(
            request,
            method="POST",
            url=request.url,
            headers=dict(request.headers),
            body=envelope,
        )
        result = self._unwrap_jsonrpc(initialized.value)
        if not isinstance(result.get("protocolVersion"), str):
            raise ConnectorTransportError("CONNECTOR_MCP_INITIALIZE_INVALID")
        session_id = initialized.headers.get("mcp-session-id", "")
        if session_id:
            if len(session_id) > 512 or "\r" in session_id or "\n" in session_id:
                raise ConnectorTransportError("CONNECTOR_MCP_SESSION_INVALID")
            self._mcp_sessions[session_key] = session_id
        notify_headers = dict(request.headers)
        if session_id:
            notify_headers["Mcp-Session-Id"] = session_id
        await self._send_document(
            request,
            method="POST",
            url=request.url,
            headers=notify_headers,
            body={"jsonrpc": "2.0", "method": "notifications/initialized"},
            allow_empty=True,
        )
        self._mcp_initialized.add(session_key)

    async def _call_a2a(self, request: ConnectorTransportRequest) -> dict[str, Any]:
        endpoint = await self._verify_a2a_card(request)
        headers = {**request.headers, "A2A-Version": "1.0"}
        if request.protocol_binding == "JSONRPC":
            document = await self._send_document(
                request,
                method="POST",
                url=endpoint,
                headers=headers,
                body={
                    "jsonrpc": "2.0",
                    "id": f"con-{uuid.uuid4().hex}",
                    "method": request.operation,
                    "params": request.arguments,
                },
            )
            return self._unwrap_jsonrpc(document.value)
        if request.protocol_binding != "HTTP+JSON":
            raise ConnectorTransportError("CONNECTOR_A2A_BINDING_UNSUPPORTED")
        return await self._call_a2a_http_json(request, headers, endpoint)

    async def _verify_a2a_card(self, request: ConnectorTransportRequest) -> str:
        if not request.agent_card_url and not request.agent_card_digest:
            # Direct construction remains available to isolated protocol unit
            # tests. Persisted A2A configs always provide both fields.
            return request.url
        if (
            not request.agent_card_url
            or len(request.agent_card_digest) != 64
            or any(char not in "0123456789abcdef" for char in request.agent_card_digest)
        ):
            raise ConnectorTransportError("CONNECTOR_AGENT_CARD_PIN_INVALID")
        cache_key = (
            request.agent_card_url,
            request.agent_card_digest,
            request.session_scope,
            request.protocol_binding,
        )
        if cache_key in self._verified_a2a_cards:
            return request.url
        document = await self._send_document(
            request,
            method="GET",
            url=request.agent_card_url,
            headers={**request.headers, "A2A-Version": "1.0"},
            body=None,
        )
        card = document.value
        if card is None or canonical_agent_card_digest(card) != request.agent_card_digest:
            raise ConnectorTransportError("CONNECTOR_AGENT_CARD_DIGEST_MISMATCH")
        interfaces = card.get("supportedInterfaces")
        if not isinstance(interfaces, list):
            raise ConnectorTransportError("CONNECTOR_AGENT_CARD_INVALID")
        matches = [
            interface for interface in interfaces
            if isinstance(interface, dict)
            and interface.get("protocolBinding") == request.protocol_binding
            and interface.get("protocolVersion") == "1.0"
            and isinstance(interface.get("url"), str)
        ]
        if not matches:
            raise ConnectorTransportError("CONNECTOR_AGENT_CARD_BINDING_MISMATCH")
        if not any(
            str(interface["url"]).rstrip("/") == request.url.rstrip("/")
            for interface in matches
        ):
            raise ConnectorTransportError("CONNECTOR_AGENT_CARD_ENDPOINT_MISMATCH")
        self._verified_a2a_cards.add(cache_key)
        return request.url

    async def _call_a2a_http_json(
        self,
        request: ConnectorTransportRequest,
        headers: dict[str, str],
        endpoint: str,
    ) -> dict[str, Any]:
        method, path_template = _A2A_HTTP_PATHS[request.operation]
        arguments = dict(request.arguments)
        task_id = str(arguments.pop("taskId", "") or arguments.pop("id", ""))
        if "{task_id}" in path_template:
            if not task_id or len(task_id) > 256:
                raise ConnectorTransportError("CONNECTOR_A2A_TASK_ID_REQUIRED")
            path = path_template.format(task_id=quote(task_id, safe=""))
        else:
            path = path_template
        url = f"{endpoint.rstrip('/')}/{path}"
        query: dict[str, str] = {}
        if method == "GET":
            allowed = (
                {"historyLength"}
                if request.operation == "GetTask"
                else {"pageSize", "pageToken", "contextId"}
            )
            query = {
                key: str(value)
                for key, value in arguments.items()
                if key in allowed and value is not None
            }
            if query:
                url = f"{url}?{urlencode(query)}"
            body = None
        else:
            body = arguments
        document = await self._send_document(
            request,
            method=method,
            url=url,
            headers=headers,
            body=body,
        )
        if document.value is None:
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        return document.value

    async def _send_document(
        self,
        request: ConnectorTransportRequest,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        allow_empty: bool = False,
    ) -> _BoundedDocument:
        current_url = url
        redirects = 0
        while True:
            self._validate_target(current_url)
            request_headers = {
                "Accept": "application/json, application/a2a+json, text/event-stream",
                "Content-Type": "application/json",
                "User-Agent": "iCoDer-Connector-Runtime/1.0",
                **headers,
            }
            timeout = httpx.Timeout(
                connect=request.connect_timeout_seconds,
                read=request.total_timeout_seconds,
                write=request.total_timeout_seconds,
                pool=request.connect_timeout_seconds,
            )
            try:
                async with self._client.stream(
                    method,
                    current_url,
                    headers=request_headers,
                    json=body,
                    timeout=timeout,
                ) as response:
                    if 300 <= response.status_code < 400:
                        current_url = self._redirect_target(
                            request,
                            current_url=current_url,
                            status_code=response.status_code,
                            location=response.headers.get("location", ""),
                            redirect_count=redirects,
                        )
                        redirects += 1
                        continue
                    if response.status_code >= 400:
                        self._raise_status(response.status_code)
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > request.max_response_bytes:
                                raise ConnectorTransportError(
                                    "CONNECTOR_RESPONSE_TOO_LARGE"
                                )
                        except ValueError as exc:
                            raise ConnectorTransportError(
                                "CONNECTOR_RESPONSE_INVALID"
                            ) from exc
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > request.max_response_bytes:
                            raise ConnectorTransportError(
                                "CONNECTOR_RESPONSE_TOO_LARGE"
                            )
                    value = self._parse_document(
                        bytes(raw),
                        response.headers.get("content-type", ""),
                        allow_empty=allow_empty,
                    )
                    return _BoundedDocument(
                        status_code=response.status_code,
                        headers={key.casefold(): value for key, value in response.headers.items()},
                        value=value,
                    )
            except ConnectorTransportError:
                raise
            except (httpx.TimeoutException, httpcore.TimeoutException) as exc:
                raise ConnectorTransportError(
                    "CONNECTOR_UPSTREAM_TIMEOUT", retryable=True,
                ) from exc
            except (httpx.NetworkError, httpcore.NetworkError, OSError) as exc:
                raise ConnectorTransportError(
                    "CONNECTOR_UPSTREAM_UNAVAILABLE", retryable=True,
                ) from exc
            except (httpx.ProtocolError, httpcore.ProtocolError) as exc:
                raise ConnectorTransportError(
                    "CONNECTOR_UPSTREAM_PROTOCOL_ERROR", retryable=False,
                ) from exc

    def _redirect_target(
        self,
        request: ConnectorTransportRequest,
        *,
        current_url: str,
        status_code: int,
        location: str,
        redirect_count: int,
    ) -> str:
        if request.redirect_policy != "same-origin":
            raise ConnectorTransportError("CONNECTOR_REDIRECT_FORBIDDEN")
        if status_code not in {307, 308} or not location:
            raise ConnectorTransportError("CONNECTOR_REDIRECT_FORBIDDEN")
        if redirect_count >= request.max_redirects:
            raise ConnectorTransportError("CONNECTOR_REDIRECT_LIMIT_EXCEEDED")
        target = urljoin(current_url, location)
        if self._origin(target) != self._origin(current_url):
            raise ConnectorTransportError("CONNECTOR_REDIRECT_ORIGIN_FORBIDDEN")
        self._validate_target(target)
        return target

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int]:
        if any(char in url for char in "\r\n\t"):
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED")
        try:
            parsed = urlsplit(url)
            port = parsed.port or 443
            hostname = (parsed.hostname or "").casefold()
        except ValueError as exc:
            raise ConnectorTransportError("CONNECTOR_URL_BLOCKED") from exc
        return (
            parsed.scheme.casefold(),
            hostname,
            port,
        )

    @staticmethod
    def _raise_status(status_code: int) -> None:
        status_class = "4xx" if 400 <= status_code < 500 else "5xx"
        retryable = status_code in {408, 425, 429} or status_code >= 500
        code = (
            f"CONNECTOR_UPSTREAM_{status_code}"
            if 400 <= status_code <= 599
            else "CONNECTOR_UPSTREAM_STATUS_INVALID"
        )
        raise ConnectorTransportError(
            code,
            retryable=retryable,
            http_status_class=status_class,
        )

    @staticmethod
    def _parse_document(
        raw: bytes,
        content_type: str,
        *,
        allow_empty: bool,
    ) -> dict[str, Any] | None:
        if not raw:
            if allow_empty:
                return None
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        media_type = content_type.split(";", 1)[0].strip().casefold()
        try:
            if media_type == "text/event-stream":
                candidates = []
                data_lines: list[str] = []

                def flush_event() -> None:
                    if not data_lines:
                        return
                    payload = "\n".join(data_lines).strip()
                    data_lines.clear()
                    if payload and payload != "[DONE]":
                        candidates.append(json.loads(payload))

                for line in raw.decode("utf-8").splitlines():
                    if not line:
                        flush_event()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                flush_event()
                value = candidates[-1] if candidates else None
            elif media_type == "application/json" or media_type.endswith("+json"):
                value = json.loads(raw.decode("utf-8"))
            else:
                raise ConnectorTransportError(
                    "CONNECTOR_RESPONSE_CONTENT_TYPE_INVALID"
                )
        except ConnectorTransportError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID") from exc
        if not isinstance(value, dict):
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        return value

    @staticmethod
    def _unwrap_jsonrpc(value: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        if "error" in value:
            raise ConnectorTransportError("CONNECTOR_UPSTREAM_RPC_ERROR")
        result = value.get("result")
        if not isinstance(result, dict):
            raise ConnectorTransportError("CONNECTOR_RESPONSE_INVALID")
        return result


__all__ = [
    "GovernedConnectorHTTPTransport",
    "PinnedAsyncHTTPTransport",
    "PinnedDNSNetworkBackend",
    "canonical_agent_card_digest",
]
