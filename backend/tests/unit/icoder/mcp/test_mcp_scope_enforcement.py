"""Phase 3-D0 Task 1 — MCP Scope Enforcement.

Per Phase 3-D0-D1 Implementation Plan §Task 1 (2026-07-06):

  - ``ToolDescriptor.required_scopes`` field
  - ``tools/call`` checks resolved auth satisfies required_scopes
    before handler dispatch
  - Insufficient scope → ``MCP_AUTH_FORBIDDEN`` (-32012)
  - ``auth_config=None`` + non-empty required_scopes → FORBIDDEN
  - RunTrace (here: logger.info) records ``scope_check`` step with
    ``redacted_view`` only — never the raw token
  - ``tools/list`` advertises ``required_scopes`` (public, not a secret)

Test matrix:
  1. scope satisfied → handler executes
  2. scope missing → MCP_AUTH_FORBIDDEN, handler never called
  3. auth_config=None + required_scopes non-empty → FORBIDDEN
  4. scope_check log entry contains redacted_view, NOT raw token
  5. tools/list advertises required_scopes
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.icoder.mcp import mount_mcp
from app.icoder.mcp.auth import BearerAuthConfig
from app.icoder.mcp.auth_resolver import _clear_oauth_cache
from app.icoder.mcp.errors import MCPErrorCode
from app.icoder.mcp.tool_registry import TOOL_REGISTRY, ToolDescriptor


# ── Fixtures ─────────────────────────────────────────────────────────────


def _fake_vault():
    """CredentialVault fake — mirrors vault.resolve contract."""
    table = {"secret://mcp/bearer/scoped": "tok-bearer-xyz"}

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
    """Return a copy of TOOL_REGISTRY[name] with patched fields."""
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


# ── Test 1: scope satisfied → handler executes ──────────────────


def test_scope_satisfied_handler_executes(client, monkeypatch):
    """Bearer auth with required scope present → handler runs + AuthHeader injected."""
    captured: dict[str, Any] = {}

    async def fake_handler(arguments, request: Request):
        captured["auth_header"] = getattr(request.state, "auth_header", None)
        captured["called"] = True
        return {"ok": True}

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/scoped",
                scopes=["read", "coding:verify"],
                redacted_view="Bearer ••••-xyz",
            ),
            required_scopes=["coding:verify"],
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
    assert captured.get("called") is True
    auth_header = captured["auth_header"]
    assert auth_header is not None
    assert auth_header.kind == "bearer"
    assert auth_header.to_header() == "Bearer tok-bearer-xyz"
    assert "coding:verify" in auth_header.granted_scopes


# ── Test 2: scope missing → MCP_AUTH_FORBIDDEN ───────────────────


def test_scope_missing_returns_mcp_auth_forbidden(client, monkeypatch):
    """Bearer auth with required scope absent → -32012, handler never called."""
    async def fake_handler(arguments, request):
        raise AssertionError("handler must not run on scope failure")

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/scoped",
                scopes=["read"],  # missing "coding:verify"
                redacted_view="Bearer ••••-xyz",
            ),
            required_scopes=["coding:verify", "read"],  # one missing
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
    assert body["error"]["code"] == MCPErrorCode.MCP_AUTH_FORBIDDEN
    data = body["error"]["data"]
    assert data["mcp_error_code"] == "MCP_AUTH_FORBIDDEN"
    assert "coding:verify" in data["required_scopes"]
    assert "read" in data["granted_scopes"]
    assert "coding:verify" not in data["granted_scopes"]
    assert data["redacted_view"] == "Bearer ••••-xyz"
    # Raw token MUST NOT appear in the error envelope.
    dumped = json.dumps(body["error"])
    assert "tok-bearer-xyz" not in dumped
    assert "Bearer tok-bearer" not in dumped


# ── Test 3: auth_config=None + required_scopes → FORBIDDEN ───────


def test_auth_config_none_with_required_scopes_returns_forbidden(client, monkeypatch):
    """No auth + required_scopes non-empty → FORBIDDEN (no auth → no scopes)."""
    async def fake_handler(arguments, request):
        raise AssertionError("handler must not run when scope required but no auth")

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=None,  # no auth configured
            required_scopes=["coding:verify"],  # but scope required
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
    assert body["error"]["code"] == MCPErrorCode.MCP_AUTH_FORBIDDEN
    data = body["error"]["data"]
    assert data["required_scopes"] == ["coding:verify"]
    assert data["granted_scopes"] == []
    # No auth → no redacted_view (empty string is falsy, MCPAuthError
    # omits the field when redacted_view is empty).
    assert data.get("redacted_view", "") == ""


# ── Test 4: scope_check log entry has redacted_view, NOT raw token ─


def test_scope_check_logged_without_token(client, monkeypatch, caplog):
    """caplog: scope_check info line carries redacted_view, never the raw token."""
    import logging

    async def fake_handler(arguments, request):
        return {"ok": True}

    from app.icoder.mcp import server as mcp_server
    monkeypatch.setattr(mcp_server, "resolve_handler", lambda ref: fake_handler)

    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/scoped",
                scopes=["coding:verify"],
                redacted_view="Bearer ••••-xyz",
            ),
            required_scopes=["coding:verify"],
            handler_ref="fake:handler",
        ),
    )

    with caplog.at_level(logging.INFO, logger="app.icoder.mcp.server"):
        r = client.post(
            "/mcp/v1/tools/call",
            json=_rpc("tools/call", {
                "name": "verify_code",
                "arguments": {"code": "I50.900"},
            }),
        )
    assert r.status_code == 200

    # Find the scope_check log entry.
    scope_logs = [r for r in caplog.records if "scope_check" in r.getMessage()]
    assert len(scope_logs) >= 1, "scope_check line must be emitted"
    line = scope_logs[-1].getMessage()
    # Redacted view MUST appear.
    assert "Bearer ••••-xyz" in line
    # Raw token MUST NOT appear.
    assert "tok-bearer-xyz" not in line
    assert "Bearer tok-bearer" not in line
    # Required + granted scopes (public) appear for operator clarity.
    assert "coding:verify" in line
    assert "ok=True" in line


# ── Test 5: tools/list advertises required_scopes ────────────────


def test_tools_list_advertises_required_scopes(client, monkeypatch):
    """tools/list exposes required_scopes for every tool (empty list when no req)."""
    monkeypatch.setitem(
        TOOL_REGISTRY, "verify_code",
        _patch_tool(
            monkeypatch, "verify_code",
            auth_config=BearerAuthConfig(
                secret_ref="secret://mcp/bearer/scoped",
                scopes=["coding:verify"],
                redacted_view="Bearer ••••-xyz",
            ),
            required_scopes=["coding:verify"],
        ),
    )

    r = client.post("/mcp/v1/tools/list", json=_rpc("tools/list"))
    body = r.json()
    tools = {t["name"]: t for t in body["result"]["tools"]}

    # verify_code has required_scopes + auth (bearer).
    v = tools["verify_code"]
    assert v["required_scopes"] == ["coding:verify"]
    assert v["auth"]["type"] == "bearer"
    assert v["auth"]["scopes"] == ["coding:verify"]
    assert "secret_ref" not in v["auth"]
    dumped = json.dumps(v)
    assert "tok-bearer" not in dumped

    # Other tools default to empty required_scopes (backwards compat).
    s = tools["search_icd"]
    assert s["required_scopes"] == []
    assert "auth" not in s
