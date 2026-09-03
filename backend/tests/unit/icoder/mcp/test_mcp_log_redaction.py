"""Phase 3-D0 Task 2 — redacted_view Actual Log Capture.

Per Phase 3-D0-D1 Implementation Plan §Task 2 (2026-07-06):

  - Use ``caplog`` to capture real log output from the MCP server +
    auth resolver.
  - Verify raw ``token`` / ``client_secret`` / ``Authorization`` header
    never enter logs (any level, any logger).
  - Verify ``redacted_view`` CAN safely enter logs (it's designed for
    display).
  - Verify error envelope / scope_check log / tool dispatch log all
    stay secret-free.

Complements ``test_mcp_scope_enforcement.py::test_scope_check_logged_without_token``
which covers the scope_check line. This file broadens coverage to:

  1. Bearer auth resolution logs
  2. OAuth2.0 exchange + cache logs
  3. Scope check log line
  4. Error envelope when MCPAuthError raised (no raw token in payload
     even if the dispatcher logs it)
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.icoder.mcp import mount_mcp, server as mcp_server
from app.icoder.mcp.auth import (
    BearerAuthConfig,
    OAuth2AuthConfig,
    OAuth2ClientCredentialsConfig,
)
from app.icoder.mcp.auth_resolver import _clear_oauth_cache, resolve_mcp_auth
from app.icoder.mcp.errors import MCPErrorCode
from app.icoder.mcp.tool_registry import TOOL_REGISTRY, ToolDescriptor


# ── Fixtures ─────────────────────────────────────────────────────────────


def _fake_vault():
    table = {
        "secret://mcp/bearer/x": "tok-bearer-XYZ123abcd",
        "secret://mcp/oauth/cid": "cid-abc-def",
        "secret://mcp/oauth/sec": "sec-789-SECRET-stuff",
    }

    def resolve(secret_ref: str) -> str:
        if secret_ref not in table:
            raise KeyError(secret_ref)
        return table[secret_ref]

    return resolve


@pytest.fixture
def app() -> FastAPI:
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
    _clear_oauth_cache()
    yield
    _clear_oauth_cache()


def _rpc(method: str, params: dict | None = None, req_id: str = "test-1") -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def _patch_tool(monkeypatch, name: str, *, auth_config=None, required_scopes=None,
                handler_ref: str | None = None):
    original = TOOL_REGISTRY[name]
    return ToolDescriptor(
        name=original.name,
        description=original.description,
        input_schema=original.input_schema,
        output_schema=original.output_schema,
        handler_ref=handler_ref or original.handler_ref,
        stage=original.stage,
        auth_config=auth_config,
        required_scopes=required_scopes or [],
    )


# ── Counting transport for oauth2 ────────────────────────────────────────


class _CountingTransport:
    def __init__(self):
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        body = (
            b'{"access_token": "tok-exchanged-'
            + str(self.calls).encode()
            + b'-XYZ123abcd", "expires_in": 3600, "token_type": "Bearer"}'
        )
        return httpx.Response(
            200, content=body, headers={"content-type": "application/json"},
        )


def _client_factory(transport: _CountingTransport):
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(transport))
    return factory


# ── The raw tokens / secrets that MUST NOT appear in any log line ──────

RAW_TOKENS = (
    "tok-bearer-XYZ123abcd",
    "tok-exchanged-1-XYZ123abcd",
    "sec-789-SECRET-stuff",
    "Bearer tok-bearer",
    "Bearer tok-exchanged",
    "cid-abc-def",  # client_id is also secret-ish, never logged
)


def _assert_no_raw_token_in_logs(caplog) -> None:
    """Scan every captured log record's formatted message for any raw
    token substring. Fail on the first hit."""
    for record in caplog.records:
        msg = record.getMessage()
        for raw in RAW_TOKENS:
            assert raw not in msg, (
                f"raw token {raw!r} leaked into log: "
                f"{record.name} {record.levelname} {msg!r}"
            )


# ── Test 1: Bearer auth resolution logs ───────────────────────────


def test_bearer_resolution_logs_only_redacted_view(client, monkeypatch, caplog):
    """Bearer auth resolve + dispatch logs redacted_view, never the raw token."""
    async def fake_handler(arguments, request):
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/x",
                scopes=["coding:verify"],
                redacted_view="Bearer ••••abcd",
            ),
            required_scopes=["coding:verify"],
            handler_ref="fake:handler",
        ),
    )

    with caplog.at_level(logging.DEBUG, logger="app.icoder.mcp"):
        r = client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "verify_code",
                "arguments": {"code": "I50.900"},
            }),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["isError"] is False

    _assert_no_raw_token_in_logs(caplog)
    # redacted_view SHOULD appear in the scope_check line.
    scope_logs = [
        r for r in caplog.records
        if "scope_check" in r.getMessage() and "verify_code" in r.getMessage()
    ]
    assert len(scope_logs) >= 1
    assert "Bearer ••••abcd" in scope_logs[-1].getMessage()


# ── Test 2: OAuth2 exchange + cache logs ──────────────────────────


def test_oauth2_exchange_logs_only_redacted_view(client, app, monkeypatch, caplog):
    """OAuth2 token exchange + cache hit logs redacted_view, never raw token."""
    async def fake_handler(arguments, request):
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    transport = _CountingTransport()
    app.state.mcp_http_client_factory = _client_factory(transport)

    monkeypatch.setitem(
        TOOL_REGISTRY, "calibrate_confidence",
        _patch_tool(
            monkeypatch, "calibrate_confidence",
            auth_config=OAuth2AuthConfig(
                oauth=OAuth2ClientCredentialsConfig(
                    token_url="https://oauth.example.com/token",
                    client_id_ref="secret://mcp/oauth/cid",
                    client_secret_ref="secret://mcp/oauth/sec",
                    scopes=["read"],
                ),
                # Note: the resolver currently generates its own
                # redacted_view from the actual token's last 4 chars
                # (Bearer ••••abcd) rather than honoring this field.
                # That's a pre-existing resolver quirk; for this test
                # we just verify NO raw token leaks — we don't assert
                # the exact redacted_view string.
                redacted_view=None,
            ),
            required_scopes=[],
            handler_ref="fake:handler",
        ),
    )

    with caplog.at_level(logging.DEBUG, logger="app.icoder.mcp"):
        # First call: cache miss → exchange.
        r1 = client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "calibrate_confidence",
                "arguments": {},
            }, req_id="r1"),
        )
        assert r1.status_code == 200
        # Second call: cache hit.
        r2 = client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "calibrate_confidence",
                "arguments": {},
            }, req_id="r2"),
        )
        assert r2.status_code == 200

    assert transport.calls == 1, "second call must hit cache"

    _assert_no_raw_token_in_logs(caplog)
    # The scope_check log on calibrate_confidence should show a
    # redacted_view (the resolver-generated one), not the raw token.
    scope_logs = [
        r for r in caplog.records
        if "scope_check" in r.getMessage() and "calibrate_confidence" in r.getMessage()
    ]
    assert len(scope_logs) >= 1
    line = scope_logs[-1].getMessage()
    assert "redacted_view=" in line
    assert "Bearer ••••" in line  # default redaction format


# ── Test 3: scope_check log line carries redacted_view, no raw token ─


def test_scope_check_log_line_format(client, monkeypatch, caplog):
    """scope_check log line has all required fields + no raw token."""
    async def fake_handler(arguments, request):
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/x",
                scopes=["coding:verify"],
                redacted_view="Bearer ••••abcd",
            ),
            required_scopes=["coding:verify"],
            handler_ref="fake:handler",
        ),
    )

    with caplog.at_level(logging.INFO, logger="app.icoder.mcp.server"):
        client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "verify_code",
                "arguments": {"code": "I50.900"},
            }),
        )

    scope_logs = [
        r for r in caplog.records
        if "scope_check" in r.getMessage()
    ]
    assert len(scope_logs) >= 1
    line = scope_logs[-1].getMessage()
    # Required public fields.
    assert "tool=verify_code" in line
    assert "required=" in line
    assert "granted=" in line
    assert "ok=True" in line
    assert "redacted_view=" in line
    assert "Bearer ••••abcd" in line
    # Raw token MUST NOT appear.
    for raw in RAW_TOKENS:
        assert raw not in line, f"raw token {raw!r} leaked into scope_check log"


# ── Test 4: error envelope on MCPAuthError has no raw token ─────────


def test_error_envelope_no_raw_token_on_auth_failure(client, monkeypatch, caplog):
    """When MCP_AUTH_FORBIDDEN raised, the JSON-RPC error envelope + log
    lines carry redacted_view only — never the raw token / secret /
    Authorization header."""
    async def fake_handler(arguments, request):
        raise AssertionError("handler must not run on scope failure")

    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/x",
                scopes=[],  # no scopes granted
                redacted_view="Bearer ••••abcd",
            ),
            required_scopes=["coding:verify"],  # scope missing
            handler_ref="fake:handler",
        ),
    )

    with caplog.at_level(logging.DEBUG, logger="app.icoder.mcp"):
        r = client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "verify_code",
                "arguments": {"code": "I50.900"},
            }),
        )

    body = r.json()
    assert body["error"]["code"] == MCPErrorCode.MCP_AUTH_FORBIDDEN
    data = body["error"]["data"]
    assert data["mcp_error_code"] == "MCP_AUTH_FORBIDDEN"
    assert data["redacted_view"] == "Bearer ••••abcd"
    assert data["granted_scopes"] == []
    assert data["required_scopes"] == ["coding:verify"]

    # The error envelope itself must not contain any raw token.
    dumped = json.dumps(body)
    for raw in RAW_TOKENS:
        assert raw not in dumped, f"raw token {raw!r} leaked into error envelope"

    # And the logs must not contain any raw token either.
    _assert_no_raw_token_in_logs(caplog)


# ── Test 5 (bonus): direct resolver call logs only redacted_view ─────


def test_resolve_mcp_auth_direct_logs_no_token(caplog):
    """Calling resolve_mcp_auth() directly (not through the dispatcher)
    logs only redacted_view, never the raw token."""
    cfg = BearerAuthConfig(
        secret_ref="secret://mcp/bearer/x",
        scopes=["read"],
        redacted_view="Bearer ••••abcd",
    )

    with caplog.at_level(logging.DEBUG, logger="app.icoder.mcp"):
        import asyncio
        auth_header = asyncio.run(
            resolve_mcp_auth(cfg, secret_resolver=_fake_vault())
        )

    assert auth_header.kind == "bearer"
    assert auth_header.to_header() == "Bearer tok-bearer-XYZ123abcd"
    _assert_no_raw_token_in_logs(caplog)
