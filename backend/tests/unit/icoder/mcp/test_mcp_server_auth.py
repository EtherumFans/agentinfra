"""Phase 3-C1 B5 #8 + #9 — MCP server tools/list + tools/call auth injection.

Per ICODER_V1_MCP_SPEC §11.6 (2026-07-05):

  B5 #8: tools/list with auth server tests — when a ToolDescriptor carries
         auth_config, tools/list advertises the auth requirement (redacted
         view only; secret_ref / client_*_ref never leak).
  B5 #9: tools/call injects auth header tests — when a ToolDescriptor
         carries auth_config, the dispatcher calls resolve_mcp_auth()
         before invoking the handler and injects the AuthHeader onto
         request.state.auth_header so handlers (or downstream MCP clients)
         can forward it.

These tests complement the resolver-level test_mcp_auth.py (B5 #1-#7, #10)
by exercising the server's integration with the resolver — proving the
wiring that was deferred to Phase 3-D per PHASE3C1 §9 is now complete.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.icoder.mcp import mount_mcp
from app.icoder.mcp.auth import (
    BearerAuthConfig,
    OAuth2AuthConfig,
    OAuth2ClientCredentialsConfig,
)
from app.icoder.mcp.auth_resolver import _clear_oauth_cache
from app.icoder.mcp.errors import MCPErrorCode
from app.icoder.mcp.tool_registry import TOOL_REGISTRY, ToolDescriptor


# ── Fixtures ─────────────────────────────────────────────────────────────


def _fake_vault():
    """CredentialVault fake — mirrors vault.resolve contract (KeyError on unknown)."""
    table = {
        "secret://mcp/bearer/tool-a": "tok-bearer-xyz",
        "secret://mcp/oauth/client_id": "cid-xyz",
        "secret://mcp/oauth/client_secret": "sec-789",
    }

    def resolve(secret_ref: str) -> str:
        if secret_ref not in table:
            raise KeyError(secret_ref)
        return table[secret_ref]

    return resolve


@pytest.fixture
def app() -> FastAPI:
    """FastAPI app with MCP mounted + a fake secret_resolver on app.state.

    http_client_factory + clock are per-test injectable via ``app.state``
    assignments (oauth2 tests set them directly).
    """
    app = FastAPI()
    strategy = MagicMock()
    mount_mcp(
        app,
        strategy=strategy,
        phi_redactor=None,
        secret_resolver=_fake_vault(),
    )
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_oauth_cache_between_tests():
    """Wipe the module-level OAuth2 cache before + after each test."""
    _clear_oauth_cache()
    yield
    _clear_oauth_cache()


def _rpc(method: str, params: dict | None = None, req_id: str = "test-1") -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def _patch_tool_auth(monkeypatch, name: str, auth_config, handler_ref: str | None = None):
    """Helper — return a copy of TOOL_REGISTRY[name] with auth_config set."""
    original = TOOL_REGISTRY[name]
    return ToolDescriptor(
        name=original.name,
        description=original.description,
        input_schema=original.input_schema,
        output_schema=original.output_schema,
        handler_ref=handler_ref or original.handler_ref,
        stage=original.stage,
        auth_config=auth_config,
    )


# ── B5 #8: tools/list with auth server ──────────────────────────────────


def test_tools_list_advertises_bearer_auth_redacted(client, monkeypatch):
    """B5 #8a — bearer auth_config surfaces as redacted auth field; secret_ref never leaks."""
    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool_auth(
            monkeypatch, "verify_code",
            BearerAuthConfig(
                secret_ref="secret://mcp/bearer/tool-a",
                redacted_view="Bearer ••••-xyz",
            ),
        ),
    )

    r = client.post("/mcp/v1/tools/list", json=_rpc("tools/list"))
    body = r.json()
    tools = {t["name"]: t for t in body["result"]["tools"]}
    auth = tools["verify_code"]["auth"]
    assert auth["type"] == "bearer"
    assert auth["redacted_view"] == "Bearer ••••-xyz"
    # secret_ref MUST NOT appear in the advertisement.
    assert "secret_ref" not in auth
    dumped = json.dumps(auth)
    assert "secret://" not in dumped
    assert "tok-bearer" not in dumped  # raw token never leaks


def test_tools_list_advertises_oauth2_auth_redacted(client, monkeypatch):
    """B5 #8b — oauth2.0 surfaces public fields only (token_url/scopes/audience); secret refs stripped."""
    monkeypatch.setitem(
        TOOL_REGISTRY, "calibrate_confidence",
        _patch_tool_auth(
            monkeypatch, "calibrate_confidence",
            OAuth2AuthConfig(
                oauth=OAuth2ClientCredentialsConfig(
                    token_url="https://oauth.example.com/token",
                    client_id_ref="secret://mcp/oauth/client_id",
                    client_secret_ref="secret://mcp/oauth/client_secret",
                    scopes=["read", "write"],
                    audience="mcp://example",
                ),
            ),
        ),
    )

    r = client.post("/mcp/v1/tools/list", json=_rpc("tools/list"))
    body = r.json()
    tools = {t["name"]: t for t in body["result"]["tools"]}
    auth = tools["calibrate_confidence"]["auth"]
    assert auth["type"] == "oauth2.0"
    assert auth["token_url"] == "https://oauth.example.com/token"
    assert auth["scopes"] == ["read", "write"]
    assert auth["audience"] == "mcp://example"
    # client_id_ref / client_secret_ref MUST NOT leak.
    assert "client_id_ref" not in auth
    assert "client_secret_ref" not in auth
    assert "oauth" not in auth  # nested oauth object not dumped wholesale
    dumped = json.dumps(auth)
    assert "secret://" not in dumped
    assert "sec-789" not in dumped


def test_tools_list_omits_auth_when_none(client):
    """B5 #8c — tools without auth_config have no auth field (backwards compat)."""
    r = client.post("/mcp/v1/tools/list", json=_rpc("tools/list"))
    body = r.json()
    for tool in body["result"]["tools"]:
        assert "auth" not in tool, f"{tool['name']} should not advertise auth"


# ── B5 #9: tools/call injects auth header ───────────────────────────────


def test_tools_call_injects_bearer_auth_header(client, monkeypatch):
    """B5 #9a — bearer auth resolves + AuthHeader lands on request.state for the handler."""
    captured: dict[str, Any] = {}

    async def fake_handler(arguments, request: Request):
        captured["auth_header"] = getattr(request.state, "auth_header", None)
        return {"ok": True}

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool_auth(
            monkeypatch, "verify_code",
            BearerAuthConfig(secret_ref="secret://mcp/bearer/tool-a"),
            handler_ref="fake:handler",
        ),
    )

    r = client.post(
        "/mcp/v1/tools/call",
        json=_rpc("tools/call", {
            "name": "verify_code",
            "arguments": {"code": "I50.900"},
        }),
    )
    body = r.json()
    assert body["result"]["isError"] is False
    auth_header = captured["auth_header"]
    assert auth_header is not None
    assert auth_header.kind == "bearer"
    assert auth_header.to_header() == "Bearer tok-bearer-xyz"


def test_tools_call_injects_oauth2_auth_header(client, app, monkeypatch):
    """B5 #9b — oauth2.0 exchange → AuthHeader on request.state; single httpx call."""
    captured: dict[str, Any] = {}

    async def fake_handler(arguments, request: Request):
        captured["auth_header"] = getattr(request.state, "auth_header", None)
        return {"ok": True}

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    transport = _CountingTransport(status_code=200, expires_in=3600)
    app.state.mcp_http_client_factory = _client_factory(transport)

    monkeypatch.setitem(
        TOOL_REGISTRY, "calibrate_confidence",
        _patch_tool_auth(
            monkeypatch, "calibrate_confidence",
            OAuth2AuthConfig(
                oauth=OAuth2ClientCredentialsConfig(
                    token_url="https://oauth.example.com/token",
                    client_id_ref="secret://mcp/oauth/client_id",
                    client_secret_ref="secret://mcp/oauth/client_secret",
                    scopes=["read"],
                ),
            ),
            handler_ref="fake:handler",
        ),
    )

    r = client.post(
        "/mcp/v1/tools/call",
        json=_rpc("tools/call", {
            "name": "calibrate_confidence",
            "arguments": {},
        }),
    )
    body = r.json()
    assert body["result"]["isError"] is False
    auth_header = captured["auth_header"]
    assert auth_header is not None
    assert auth_header.kind == "bearer"
    assert auth_header.token == "tok-1"  # _CountingTransport returns tok-N
    assert auth_header.to_header() == "Bearer tok-1"
    assert transport.calls == 1  # single exchange — no cache hit yet


def test_tools_call_auth_failure_returns_mcp_auth_error(client, monkeypatch):
    """B5 #9c — bearer with unknown secret_ref → MCP_AUTH_MISSING_CREDENTIALS, handler never called."""
    async def fake_handler(arguments, request):
        raise AssertionError("handler must not run on auth failure")

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool_auth(
            monkeypatch, "verify_code",
            BearerAuthConfig(secret_ref="secret://mcp/unknown/ref"),
            handler_ref="fake:handler",
        ),
    )

    r = client.post(
        "/mcp/v1/tools/call",
        json=_rpc("tools/call", {
            "name": "verify_code",
            "arguments": {"code": "I50.900"},
        }),
    )
    body = r.json()
    assert body["error"]["code"] == MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS
    dumped = json.dumps(body["error"])
    assert "MCP_AUTH_MISSING_CREDENTIALS" in dumped  # mcp_error_code survives redaction
    # Raw token never leaks (there is none here, but secret_ref is a ref, not a secret).
    assert "tok-bearer" not in dumped


def test_tools_call_no_auth_when_config_none(client, monkeypatch):
    """B5 #9d — auth_config=None → request.state.auth_header not set (backwards compat)."""
    captured: dict[str, Any] = {}

    async def fake_handler(arguments, request: Request):
        captured["has_auth_header"] = hasattr(request.state, "auth_header")
        return {"ok": True}

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    # verify_code default has auth_config=None — no patching needed.
    r = client.post(
        "/mcp/v1/tools/call",
        json=_rpc("tools/call", {
            "name": "verify_code",
            "arguments": {"code": "I50.900"},
        }),
    )
    body = r.json()
    assert body["result"]["isError"] is False
    assert captured["has_auth_header"] is False


# ── helpers for oauth2 tests ─────────────────────────────────────────────


class _CountingTransport:
    """httpx MockTransport that counts calls + returns a fresh access_token."""

    def __init__(self, *, status_code: int = 200, expires_in: int = 3600):
        self.calls = 0
        self._status_code = status_code
        self._expires_in = expires_in

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self._status_code != 200:
            return httpx.Response(
                self._status_code,
                content=b'{"error": "invalid_client"}',
                headers={"content-type": "application/json"},
            )
        body = (
            b'{"access_token": "tok-' + str(self.calls).encode()
            + b'", "expires_in": ' + str(self._expires_in).encode()
            + b', "token_type": "Bearer"}'
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"},
        )


def _client_factory(transport: _CountingTransport):
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(transport))
    return factory
