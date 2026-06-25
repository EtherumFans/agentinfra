"""M2 — MCP server tests (~15 cases).

Covers:
  - tools/list returns 5 tools with inputSchema/outputSchema
  - tools/call happy path for each of the 5 tools
  - JSON-RPC error envelopes (-32600/-32601/-32602/-32603/-32004)
  - ``_meta.contextId`` propagation to ``request.state.context_id``
  - PHI redaction ordering (called before handler dispatch)
  - Method-not-found for ``initialize`` / ``tools/foo`` etc.
  - Handler resolution failures → -32603 Internal Error
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixtures ──


@pytest.fixture
def app_with_strategy() -> FastAPI:
    """Fresh FastAPI app + a real mount of the MCP router.

    ``strategy`` is a MagicMock so handlers can be inspected via
    ``app.state.medcoder_strategy``.

    M2.5: also set ``app.state.medcoder_index_health = {"status": "ok"}``
    so the ``search_icd`` handler's governance gate passes — the
    dedicated degraded test exercises the failure path explicitly.
    """
    from app.icoder.mcp import mount_mcp

    app = FastAPI()
    strategy = MagicMock()
    strategy.stage2_retrieve = AsyncMock(return_value=[])
    strategy.stage4_rerank = AsyncMock(return_value=[])
    strategy._get_rule_set = MagicMock(return_value=MagicMock())
    mount_mcp(app, strategy=strategy, phi_redactor=None)
    # M2.5: default to healthy for handler unit tests.
    app.state.medcoder_index_health = {
        "status": "ok",
        "reason": None,
        "ntotal": 37897,
        "dim": 1024,
    }
    return app


@pytest.fixture
def client(app_with_strategy: FastAPI) -> TestClient:
    return TestClient(app_with_strategy)


# ── JSON-RPC envelope helpers ──


def _rpc(method: str, params: dict | None = None, req_id: str = "test-1") -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def _post(client: TestClient, payload: dict, path: str = "/mcp/v1/tools/list"):
    return client.post(path, json=payload)


# ── tools/list ──


def test_tools_list_returns_5_tools(client: TestClient):
    """tools/list returns exactly 5 tool descriptors."""
    r = _post(client, _rpc("tools/list"))
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "test-1"
    assert body["result"]["isError"] is False
    # The result envelope is {"tools": [...], "isError": false} (no
    # extra ``content`` nesting — that would have made list/call
    # shapes inconsistent). Tools live directly under ``result``.
    tools = body["result"]["tools"]
    assert len(tools) == 5
    names = {t["name"] for t in tools}
    assert names == {
        "search_icd", "verify_code", "get_differentiation_hint",
        "rerank_codes", "calibrate_confidence",
    }


def test_tools_list_accepts_empty_body(client: TestClient):
    """tools/list works with no body (some clients send empty POST)."""
    r = client.post("/mcp/v1/tools/list")
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["isError"] is False
    assert len(body["result"]["tools"]) == 5


def test_tools_list_rejects_unknown_method(client: TestClient):
    """Unknown methods return -32601 Method Not Found."""
    r = _post(client, _rpc("initialize"))
    body = r.json()
    assert body["error"]["code"] == -32601
    assert body["error"]["data"]["allowed_methods"] == ["tools/list", "tools/call"]


def test_tools_list_rejects_wrong_jsonrpc_version(client: TestClient):
    """Missing or wrong jsonrpc field returns -32600 Invalid Request."""
    r = client.post(
        "/mcp/v1/tools/list",
        json={"id": "x", "method": "tools/list"},  # no jsonrpc
    )
    assert r.json()["error"]["code"] == -32600


def test_tools_list_rejects_malformed_json(client: TestClient):
    """Bad JSON returns -32700 Parse Error."""
    r = client.post(
        "/mcp/v1/tools/list",
        content=b"not json {{{",
        headers={"content-type": "application/json"},
    )
    assert r.json()["error"]["code"] == -32700


# ── tools/call happy paths ──


def test_tools_call_search_icd_happy_path(
    client: TestClient, app_with_strategy: FastAPI,
):
    """tools/call dispatches search_icd → strategy.stage2_retrieve."""
    app_with_strategy.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=[{
            "code": "I50.900", "name": "心力衰竭",
            "score": 0.9, "chapter": "第9章", "source": "retrieve",
        }],
    )

    r = _post(
        client,
        _rpc("tools/call", {
            "name": "search_icd",
            "arguments": {"emr_text": "胸痛 2 小时", "top_k": 5},
        }),
        path="/mcp/v1/tools/call",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["isError"] is False
    candidates = body["result"]["content"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["code"] == "I50.900"
    app_with_strategy.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "胸痛 2 小时", top_k=5,
    )


def test_tools_call_verify_code_happy_path(client: TestClient):
    """tools/call dispatches verify_code → icd10cn_loader."""
    fake_entry = MagicMock()
    fake_entry.name_cn = "心力衰竭"
    fake_entry.synonyms_cn = ("心衰",)

    fake_loader = MagicMock()
    fake_loader.has = MagicMock(return_value=True)
    fake_loader.get = MagicMock(return_value=fake_entry)
    fake_loader.chapter_for = MagicMock(return_value="第9章")

    with patch(
        "app.services.icd10cn_loader.get_loader", return_value=fake_loader,
    ):
        r = _post(
            client,
            _rpc("tools/call", {
                "name": "verify_code",
                "arguments": {"code": "I50.900"},
            }),
            path="/mcp/v1/tools/call",
        )

    body = r.json()
    assert body["result"]["isError"] is False
    out = body["result"]["content"]
    assert out["in_catalog"] is True
    assert out["name"] == "心力衰竭"


def test_tools_call_rerank_codes_happy_path(
    client: TestClient, app_with_strategy: FastAPI,
):
    """tools/call dispatches rerank_codes → strategy.stage4_rerank."""
    app_with_strategy.state.medcoder_strategy.stage4_rerank = AsyncMock(
        return_value=[
            {"code": "I50.900", "name": "心力衰竭",
             "confidence": 0.92, "rationale": "best"},
        ],
    )

    r = _post(
        client,
        _rpc("tools/call", {
            "name": "rerank_codes",
            "arguments": {
                "disease_text": "心力衰竭",
                "evidence": "胸闷气短",
                "candidates": [{"code": "I50.900", "score": 0.85}],
            },
        }),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["result"]["isError"] is False
    assert body["result"]["content"]["ranked"][0]["code"] == "I50.900"


def test_tools_call_calibrate_confidence_happy_path(client: TestClient):
    """tools/call dispatches calibrate_confidence → confidence_calibrator.calibrate_all."""
    fake_result = {
        "coding_confidences": [{"code": "I50.900", "calibrated_score": 0.85}],
        "routing_decisions": [{"code": "I50.900", "tier": "review"}],
        "metrics": {"total_codes": 1},
    }
    with patch(
        "app.services.confidence_calibrator.calibrate_all",
        return_value=fake_result,
    ):
        r = _post(
            client,
            _rpc("tools/call", {
                "name": "calibrate_confidence",
                "arguments": {
                    "diagnosis_candidates": [
                        {"code": "I50.900", "name": "心力衰竭", "score": 0.85},
                    ],
                    "procedure_candidates": [],
                    "primary_diagnosis": {"code": "I50.900"},
                    "evidence_ranking": {},
                    "disagreement_analysis": {},
                    "primary_diag_reasoning": {},
                },
            }),
            path="/mcp/v1/tools/call",
        )

    body = r.json()
    assert body["result"]["isError"] is False
    assert body["result"]["content"]["metrics"]["total_codes"] == 1


# ── tools/call error envelopes ──


def test_tools_call_unknown_tool_returns_32601(client: TestClient):
    """Calling a non-existent tool returns -32601 Method Not Found."""
    r = _post(
        client,
        _rpc("tools/call", {"name": "nonexistent_tool"}),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["error"]["code"] == -32601
    assert "nonexistent_tool" in body["error"]["message"]
    assert body["error"]["data"]["allowed_tools"] == [
        "search_icd", "verify_code", "get_differentiation_hint",
        "rerank_codes", "calibrate_confidence",
    ]


def test_tools_call_missing_tool_name_returns_32602(client: TestClient):
    """Omitting ``params.name`` returns -32602 Invalid Params."""
    r = _post(
        client,
        _rpc("tools/call", {"arguments": {}}),
        path="/mcp/v1/tools/call",
    )
    assert r.json()["error"]["code"] == -32602


def test_tools_call_invalid_search_icd_args_returns_32602(client: TestClient):
    """Pydantic validation failure on inputSchema returns -32602."""
    r = _post(
        client,
        _rpc("tools/call", {
            "name": "search_icd",
            "arguments": {"top_k": 999},  # missing emr_text, out-of-range top_k
        }),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["error"]["code"] == -32602
    assert body["error"]["data"]["errors"]


def test_tools_call_handler_raises_returns_32603(
    client: TestClient, app_with_strategy: FastAPI,
):
    """Unhandled exceptions from a handler return -32603 Internal Error."""
    app_with_strategy.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        side_effect=RuntimeError("pipeline boom"),
    )

    r = _post(
        client,
        _rpc("tools/call", {
            "name": "search_icd",
            "arguments": {"emr_text": "x", "top_k": 5},
        }),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["error"]["code"] == -32603
    assert "pipeline boom" in body["error"]["message"]


def test_tools_call_handler_timeout_returns_32003(
    client: TestClient, app_with_strategy: FastAPI,
):
    """TimeoutError from a handler returns -32003 LLM Timeout."""
    app_with_strategy.state.medcoder_strategy.stage4_rerank = AsyncMock(
        side_effect=TimeoutError("deepseek timeout"),
    )

    r = _post(
        client,
        _rpc("tools/call", {
            "name": "rerank_codes",
            "arguments": {
                "disease_text": "x",
                "candidates": [{"code": "I50.900", "score": 0.5}],
            },
        }),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["error"]["code"] == -32003
    assert "deepseek timeout" in body["error"]["message"]


# ── _meta.contextId propagation ──


def test_context_id_propagates_to_request_state(
    app_with_strategy: FastAPI,
):
    """Middleware stashes ``_meta.contextId`` on ``request.state.context_id``.

    We probe the middleware directly because TestClient doesn't expose
    ``request.state`` post-hoc.
    """
    from app.icoder.mcp.server import _context_id_middleware

    captured: dict = {}

    async def _capture_state(request):
        captured["context_id"] = getattr(request.state, "context_id", None)
        # Return a minimal response so the middleware can complete.
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True})

    # Build a minimal request with the right shape.
    from starlette.requests import Request as StarletteRequest

    body = json.dumps({
        "jsonrpc": "2.0", "id": "r", "method": "tools/call",
        "params": {"_meta": {"contextId": "ctx-uuid-1234"}},
    }).encode("utf-8")

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http", "method": "POST",
        "path": "/mcp/v1/tools/call",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }
    req = StarletteRequest(scope, _receive)

    import asyncio
    asyncio.run(_context_id_middleware(req, _capture_state))

    assert captured["context_id"] == "ctx-uuid-1234"


def test_phi_redaction_failed_when_context_id_without_redactor(
    app_with_strategy: FastAPI,
):
    """When contextId is provided but no redactor is registered,
    return -32004 PHI Redaction Failed (fail-closed)."""
    client = TestClient(app_with_strategy)
    # app_with_strategy was mounted with phi_redactor=None.
    r = _post(
        client,
        _rpc("tools/call", {
            "name": "search_icd",
            "arguments": {"emr_text": "张三 13800138000 入院", "top_k": 5},
            "_meta": {"contextId": "ctx-uuid-fail"},
        }),
        path="/mcp/v1/tools/call",
    )
    body = r.json()
    assert body["error"]["code"] == -32004


def test_phi_redaction_called_before_dispatch(
    app_with_strategy: FastAPI,
):
    """When a redactor IS registered, string arguments are redacted
    BEFORE the handler sees them."""
    from app.icoder.agent_runtime.orchestrator.phi_redactor import PHIRedactor

    # Register a real redactor
    redactor = PHIRedactor()
    app_with_strategy.state.phi_redactor = redactor

    # Capture what the handler receives
    captured_args: dict = {}

    async def fake_handler(arguments, request):
        captured_args.update(arguments)
        return {"ok": True}

    # Patch the search_icd handler in the module
    import app.icoder.mcp.handlers.search_icd as search_mod
    original = search_mod.handle
    search_mod.handle = fake_handler
    try:
        client = TestClient(app_with_strategy)
        r = _post(
            client,
            _rpc("tools/call", {
                "name": "search_icd",
                "arguments": {
                    "emr_text": "张三 13800138000 入院治疗",
                    "top_k": 5,
                },
                "_meta": {"contextId": "ctx-uuid-redact"},
            }),
            path="/mcp/v1/tools/call",
        )
        assert r.json()["result"]["isError"] is False
        # PHI (phone number) must have been redacted before reaching handler.
        assert "13800138000" not in captured_args.get("emr_text", "")
        assert "<REDACTED:" in captured_args.get("emr_text", "")
    finally:
        search_mod.handle = original


# ── Helpers ──