"""A2A integration tests (SPEC §11.2).

Covers the 4 endpoint groups exposed by ``mount_a2a``:

- Inbound  ``POST /api/icoder/agents/{id}/v1/message:send``   — 7 cases
- Outbound ``POST /api/icoder/internal/experts/{id}/v1/message:send`` — 1 case
- Discovery: ``/.well-known/agent.json``, ``/llms.txt``,
             ``/api/icoder/agents``, ``/api/icoder/agents/{id}/card`` — 4 cases
- Task: ``GET /api/icoder/tasks/{id}``, ``POST /tasks/{id}/cancel`` — 2 negative cases (positive state-machine tests in test_api/test_a1b_ae_r_1_*)

Total: 14 cases. Matches the test matrix in SPEC §11.2 + §11.4.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.icoder.agent_runtime.a2a import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    build_a2a_routers,
)
from app.icoder.agent_runtime.a2a.a2a_routes import mount_a2a
from app.icoder.agent_runtime.a2a.agent_card import medcoder_coding_review_card
from app.icoder.agent_runtime.a2a.routes_discovery import AgentProvider
from app.icoder.agent_runtime.a2a.routes_outbound import ExpertCaller
from app.icoder.agent_runtime.orchestrator import (
    Aggregator,
    Delegator,
    DictAgentProvider,
    InboundHandler,
    PHIRedactor,
    Planner,
)
from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig
from app.icoder.agent_runtime.orchestrator.delegator import DelegatorConfig


# ---------------------------------------------------------------------------
# Test fixtures: handlers / providers / apps
# ---------------------------------------------------------------------------


@dataclass
class _StubAgent:
    id: str = "medcoder-coding-review"
    name: str = "MedCodER Coding Review Agent"
    expert_ids: list[str] = field(default_factory=lambda: ["coding-expert"])
    config: dict = field(default_factory=dict)


def _ok_plan_response(*, expert_id: str = "coding-expert", critical: bool = True) -> dict:
    return {
        "content": json.dumps(
            {
                "experts": [
                    {
                        "expert_id": expert_id,
                        "priority": 1,
                        "critical": critical,
                        "subtask_input": "encode",
                        "tool_constraints": [],
                    }
                ],
                "reason": "编码审核",
            }
        ),
        "model": "fake",
    }


def _build_handler(invoker=None, llm_response: dict | None = None) -> InboundHandler:
    llm_response = llm_response or _ok_plan_response()

    def _llm(system, user):
        return llm_response

    def _default_invoker(invocation):
        return {"echo": invocation.subtask_input}

    planner = Planner(llm_call=_llm, config=PlannerConfig(sleep_fn=lambda _: None))
    delegator = Delegator(
        invoker=invoker or _default_invoker,
        config=DelegatorConfig(sleep_fn=lambda _: None),
    )
    aggregator = Aggregator()
    provider = DictAgentProvider(
        {"medcoder-coding-review": _StubAgent()}
    )
    return InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=aggregator,
        agent_provider=provider,
    )


def _build_agent_provider() -> AgentProvider:
    """Return the canonical medcoder-coding-review card."""

    def _provider(agent_id: str):
        if agent_id == "medcoder-coding-review":
            return medcoder_coding_review_card()
        return None

    return _provider


def _build_expert_caller() -> ExpertCaller:
    """Stub expert that echoes back the inbound body."""

    def _caller(expert_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return {
            "kind": "message",
            "role": "agent",
            "messageId": "expert-msg-1",
            "contextId": body.get("params", {}).get("message", {}).get("messageId", ""),
            "parts": [
                {
                    "kind": "data",
                    "data": {
                        "expert_id": expert_id,
                        "delegated_by": body.get("metadata", {}).get("delegated_by", ""),
                        "echo": body.get("params", {}),
                    },
                }
            ],
            "metadata": {},
        }

    return _caller


@pytest.fixture
def handler() -> InboundHandler:
    return _build_handler()


@pytest.fixture
def agent_provider() -> AgentProvider:
    return _build_agent_provider()


@pytest.fixture
def expert_caller() -> ExpertCaller:
    return _build_expert_caller()


@pytest.fixture
def client(handler, agent_provider, expert_caller) -> TestClient:
    app = FastAPI()
    mount_a2a(
        app,
        handler=handler,
        agent_provider=agent_provider,
        expert_caller=expert_caller,
    )
    return TestClient(app)


def _version_header() -> dict[str, str]:
    return {A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION}


def _inbound_envelope(text: str = "病历主诉胸痛", **extra) -> dict:
    """Build a valid inbound JSON-RPC envelope for message/send."""
    body = {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": "client-msg-1",
                "metadata": {},
            }
        },
    }
    body.update(extra)
    return body


# ---------------------------------------------------------------------------
# Inbound — message:send (7 cases)
# ---------------------------------------------------------------------------


def test_inbound_message_send_happy_path(client):
    """§11.2.1 — happy path: 200 + JSON-RPC success + A2A header + run_id."""
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=_version_header(),
        json=_inbound_envelope(text="病历主诉胸痛"),
    )
    assert r.status_code == 200, r.text
    assert r.headers[A2A_PROTOCOL_HEADER] == A2A_PROTOCOL_VERSION
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "test-1"
    assert "result" in body
    result = body["result"]
    assert result["kind"] == "message"
    assert result["role"] == "agent"
    assert result["messageId"] != ""
    assert result["contextId"] != ""
    # server-generated UUID v4 isolation (Q4)
    assert result["contextId"] != "client-msg-1"
    # iCoDer metadata
    assert "run_id" in result["metadata"]
    assert result["metadata"]["phi_redacted"] is True
    # state machine history (received→planning→delegating→aggregating→completed)
    assert "state_history" in result["metadata"]


def test_inbound_missing_version_header_returns_400(client):
    """§11.2.2 — missing A2A-Protocol-Version → HTTP 400 + parse error envelope."""
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        json=_inbound_envelope(),
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert "error" in body
    assert body["error"]["code"] == -32700
    assert A2A_PROTOCOL_HEADER in r.headers


def test_inbound_malformed_json_returns_parse_error(client):
    """§11.2.3 — non-JSON body → -32700 + HTTP 200.

    Per JSON-RPC 2.0 spec the response itself is a valid HTTP 200
    carrying a JSON-RPC error envelope (only the version header check
    returns 400 directly because it cannot even build an envelope).
    """
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=_version_header(),
        content="not-json-at-all",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["error"]["code"] == -32700


def test_inbound_unsupported_method_returns_32601(client):
    """§11.2.4 — unknown JSON-RPC method → -32601 + HTTP 404."""
    body = _inbound_envelope()
    body["method"] = "tasks/cancel"  # not in SUPPORTED_METHODS
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=_version_header(),
        json=body,
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["code"] == -32601  # JSON_RPC_METHOD_NOT_FOUND
    # The a2a business code in data distinguishes this from generic 404s
    assert body["error"]["data"]["a2a_error_code"] == "METHOD_NOT_FOUND"


def test_inbound_filepart_rejected_with_invalid_params(client):
    """§11.2.5 — FilePart rejected → -32602 + HTTP 400 (Q-A9)."""
    body = _inbound_envelope()
    body["params"]["message"]["parts"] = [
        {
            "kind": "file",
            "file": {"name": "ct.dcm", "mimeType": "application/dicom"},
        }
    ]
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=_version_header(),
        json=body,
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == -32602


def test_inbound_unknown_agent_returns_agent_not_found(client):
    """§11.2.6 — agent_id not in provider → AGENT_NOT_FOUND.

    E1.1 (2026-06-26): InboundHandler now strictly returns the A2A
    business code ``AGENT_NOT_FOUND`` with HTTP 404 for unknown
    agents (per A2A spec §6.2 — distinct from INVALID_REQUEST / 400
    which is reserved for malformed request envelopes).
    """
    r = client.post(
        "/api/icoder/agents/ghost-agent/v1/message:send",
        headers=_version_header(),
        json=_inbound_envelope(),
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "AGENT_NOT_FOUND"
    assert "ghost-agent" in body["error"]["data"]["details"]


def test_inbound_phi_redaction_failure_returns_phi_code(handler, agent_provider, expert_caller):
    """§11.2.7 — PHI redaction failure → PHI_REDACTION_FAILED."""
    # Build a handler whose PHI redactor always raises
    class _BoomRedactor(PHIRedactor):
        def redact(self, text):
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                PHIRedactionError,
            )
            raise PHIRedactionError("simulated PHI failure", stage="received")

    def _llm(system, user):
        return {"content": "{}"}

    planner = Planner(llm_call=_llm, config=PlannerConfig(sleep_fn=lambda _: None))
    delegator = Delegator(invoker=lambda i: {}, config=DelegatorConfig(sleep_fn=lambda _: None))
    bad_handler = InboundHandler(
        phi_redactor=_BoomRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=Aggregator(),
        agent_provider=DictAgentProvider(
            {"medcoder-coding-review": _StubAgent()}
        ),
    )

    app = FastAPI()
    mount_a2a(
        app,
        handler=bad_handler,
        agent_provider=agent_provider,
        expert_caller=expert_caller,
    )
    client = TestClient(app)
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=_version_header(),
        json=_inbound_envelope(text="张三 主诉胸痛"),
    )
    assert r.status_code == 500, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "PHI_REDACTION_FAILED"


# ---------------------------------------------------------------------------
# Outbound — message:send (1 case)
# ---------------------------------------------------------------------------


def test_outbound_message_send_propagates_delegated_by(client):
    """§11.2.8 — Orchestrator → Expert: delegated_by metadata propagates."""
    body = _inbound_envelope(text="echo me")
    body["params"]["metadata"] = {"delegated_by": "orchestrator-run-42"}
    r = client.post(
        "/api/icoder/internal/experts/coding-expert/v1/message:send",
        headers=_version_header(),
        json=body,
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "test-1"
    assert "result" in resp
    # Find the data part the expert emitted
    parts = resp["result"]["parts"]
    data_part = next(p for p in parts if p.get("kind") == "data")
    assert data_part["data"]["expert_id"] == "coding-expert"
    assert data_part["data"]["delegated_by"] == "orchestrator-run-42"


# ---------------------------------------------------------------------------
# Discovery — 4 endpoints (4 cases)
# ---------------------------------------------------------------------------


def test_well_known_agent_json_lists_cards(client):
    """§11.2.9 — GET /.well-known/agent.json → AgentListResponse."""
    r = client.get(
        "/.well-known/agent.json", headers=_version_header()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "agents" in body
    assert len(body["agents"]) >= 1
    assert body["agents"][0]["name"] == "MedCodER Coding Review Agent"
    # JSON-RPC envelope not used here — raw list
    assert A2A_PROTOCOL_HEADER in r.headers


def test_llms_txt_renders_markdown(client):
    """§11.2.10 — GET /llms.txt → markdown body."""
    r = client.get("/llms.txt", headers=_version_header())
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/markdown")
    body = r.text
    assert "# iCoDer v1 Agent Runtime" in body
    assert "MedCodER Coding Review Agent" in body
    assert "search_icd" in body
    assert A2A_PROTOCOL_HEADER in r.headers


def test_agents_list_returns_simplified_cards(client):
    """§11.2.11 — GET /api/icoder/agents → simplified list."""
    r = client.get("/api/icoder/agents", headers=_version_header())
    assert r.status_code == 200, r.text
    body = r.json()
    assert "agents" in body
    assert len(body["agents"]) >= 1
    agent = body["agents"][0]
    # Simplified shape: id/name/description/version/capabilities/url
    assert "id" in agent
    assert agent["name"] == "MedCodER Coding Review Agent"
    assert "capabilities" in agent
    assert "url" in agent
    assert "v1/message:send" in agent["url"]


def test_agent_card_returns_full_card(client):
    """§11.2.12 — GET /api/icoder/agents/{id}/card → full AgentCard."""
    r = client.get(
        "/api/icoder/agents/medcoder-coding-review/card",
        headers=_version_header(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "MedCodER Coding Review Agent"
    assert body["version"] == "1.0.0"
    assert "skills" in body
    skill_ids = {s["id"] for s in body["skills"]}
    # MedCodER card surfaces the 5 MCP tools + 1 orchestration skill
    assert "search_icd" in skill_ids
    assert "verify_code" in skill_ids
    assert "rerank_codes" in skill_ids
    assert "medcoder_5_stage_pipeline" in skill_ids
    assert "metadata" in body
    assert body["metadata"]["icoder"]["production_writeback_blocked"] is True


def test_agent_card_unknown_returns_404(client):
    """Bonus: GET card for missing agent → 404 + AGENT_NOT_FOUND."""
    r = client.get(
        "/api/icoder/agents/ghost-agent/card",
        headers=_version_header(),
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "AGENT_NOT_FOUND"


def test_agents_list_capability_filter(client):
    """Bonus: capability filter narrows results."""
    r = client.get(
        "/api/icoder/agents",
        params={"capability": "search_icd"},
        headers=_version_header(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["agents"]) >= 1
    # Unknown capability → empty list
    r = client.get(
        "/api/icoder/agents",
        params={"capability": "no_such_skill"},
        headers=_version_header(),
    )
    assert r.status_code == 200
    assert r.json()["agents"] == []


# ---------------------------------------------------------------------------
# Task state machine — A1B-AE-R.1.a
# ---------------------------------------------------------------------------
# The 2 A1B-AE §11.2.13/14 stub tests (501 UNSUPPORTED_OPERATION) were
# removed: A1B-AE-R.1.a replaces the stub with a real state machine
# backed by ``context_task_refs``. Positive state-machine tests live in
# ``backend/tests/test_api/test_a1b_ae_r_1_task_state_machine.py``
# because they need the full-app fixture with DB access.


def test_tasks_get_unknown_returns_404_task_not_found(client):
    """A1B-AE-R.1.a — GET /tasks/{unknown} → 404 TASK_NOT_FOUND."""
    r = client.get(
        "/api/icoder/tasks/00000000-0000-4000-8000-000000000000",
        headers=_version_header(),
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "TASK_NOT_FOUND"
    assert A2A_PROTOCOL_HEADER in r.headers


def test_tasks_cancel_unknown_returns_404_task_not_found(client):
    """A1B-AE-R.1.a — POST /tasks/{unknown}/cancel → 404 TASK_NOT_FOUND."""
    r = client.post(
        "/api/icoder/tasks/00000000-0000-4000-8000-000000000000/cancel",
        headers=_version_header(),
        json={"reason": "user requested"},
    )
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["data"]["a2a_error_code"] == "TASK_NOT_FOUND"


# ---------------------------------------------------------------------------
# Cross-cutting: mount + protocol header on every response
# ---------------------------------------------------------------------------


def test_all_a2a_routes_set_protocol_header(client, handler, agent_provider, expert_caller):
    """Bonus: verify every mounted route returns the protocol header."""
    paths = [
        ("GET", "/.well-known/agent.json", None),
        ("GET", "/llms.txt", None),
        ("GET", "/api/icoder/agents", None),
        (
            "GET",
            "/api/icoder/agents/medcoder-coding-review/card",
            None,
        ),
        (
            "POST",
            "/api/icoder/agents/medcoder-coding-review/v1/message:send",
            _inbound_envelope(),
        ),
    ]
    for method, path, json_body in paths:
        r = client.request(
            method,
            path,
            headers=_version_header(),
            json=json_body,
        )
        assert A2A_PROTOCOL_HEADER in r.headers, (
            f"{method} {path} missing {A2A_PROTOCOL_HEADER}"
        )
        assert r.headers[A2A_PROTOCOL_HEADER] == A2A_PROTOCOL_VERSION


def test_build_a2a_routers_returns_separate_routers(handler, agent_provider, expert_caller):
    """Sanity: build_a2a_routers returns 5 distinct routers without mounting."""
    routers = build_a2a_routers(
        handler=handler,
        agent_provider=agent_provider,
        expert_caller=expert_caller,
    )
    assert set(routers.keys()) == {
        "inbound",
        "outbound",
        "discovery_root",
        "discovery_agents",
        "task",
    }
    # None are mounted on any app
    for r in routers.values():
        assert hasattr(r, "routes")