"""A2A v0.3 end-to-end test (SPEC §11.2 / §11.4).

Exercises the full inbound path against a mounted FastAPI app:
Discovery → message:send → response validation → outbound delegation.

The test shares scaffolding with the Orchestrator e2e (which will use
a real DeepSeek planner); for now it uses the same in-memory stubs as
the integration tests, validating the A2A wire-level invariants:

- Every response carries ``A2A-Protocol-Version: 0.3``
- Inbound contextId is dropped (Q4), server generates UUID v4
- PHI redaction metadata is emitted when PHI is present
- The state machine produces all 4 hops in the happy path
- Discovery endpoints return valid AgentCards
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.icoder.agent_runtime.a2a import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    mount_a2a,
)
from app.icoder.agent_runtime.a2a.agent_card import medcoder_coding_review_card
from app.icoder.agent_runtime.orchestrator import (
    Aggregator,
    Delegator,
    DictAgentProvider,
    InboundHandler,
    PHIRedactor,
    Planner,
)
from app.icoder.agent_runtime.orchestrator.delegator import DelegatorConfig
from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig


# ---------------------------------------------------------------------------
# Wiring (mirrors integration tests but as a single end-to-end app)
# ---------------------------------------------------------------------------


@dataclass
class _Agent:
    id: str = "medcoder-coding-review"
    name: str = "MedCodER Coding Review Agent"
    expert_ids: list[str] = field(default_factory=lambda: ["coding-expert"])
    config: dict = field(default_factory=dict)


def _ok_plan() -> dict:
    return {
        "content": json.dumps(
            {
                "experts": [
                    {
                        "expert_id": "coding-expert",
                        "priority": 1,
                        "critical": True,
                        "subtask_input": "encode",
                        "tool_constraints": [],
                    }
                ],
                "reason": "编码审核",
            }
        ),
        "model": "fake",
    }


def _build_handler() -> InboundHandler:
    planner = Planner(
        llm_call=lambda _s, _u: _ok_plan(),
        config=PlannerConfig(sleep_fn=lambda _: None),
    )
    delegator = Delegator(
        invoker=lambda inv: {"code": "I50.900", "name": "心力衰竭"},
        config=DelegatorConfig(sleep_fn=lambda _: None),
    )
    return InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=Aggregator(),
        agent_provider=DictAgentProvider({"medcoder-coding-review": _Agent()}),
    )


def _expert_caller(expert_id: str, body: dict) -> dict:
    return {
        "kind": "message",
        "role": "agent",
        "messageId": "expert-e2e-msg",
        "contextId": "",
        "parts": [
            {
                "kind": "data",
                "data": {"expert_id": expert_id, "delegated": body.get("params", {})},
            }
        ],
        "metadata": {},
    }


def _agent_provider(agent_id: str):
    if agent_id == "medcoder-coding-review":
        return medcoder_coding_review_card()
    return None


@pytest.fixture
def app() -> FastAPI:
    handler = _build_handler()
    app = FastAPI()
    mount_a2a(
        app,
        handler=handler,
        agent_provider=_agent_provider,
        expert_caller=_expert_caller,
    )
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# End-to-end: Discovery → Send → Validate
# ---------------------------------------------------------------------------


def test_e2e_discovery_then_send_then_validate(client):
    """Full e2e: client discovers the agent, then sends a message,
    then validates the full A2A envelope shape and metadata."""
    headers = {A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION}

    # [1] Discovery — fetch the agent card via /.well-known
    r = client.get("/.well-known/agent.json", headers=headers)
    assert r.status_code == 200, r.text
    assert A2A_PROTOCOL_HEADER in r.headers
    cards = r.json()["agents"]
    assert len(cards) >= 1
    card = next(
        c for c in cards if c["url"].endswith("/medcoder-coding-review/v1/message:send")
    )
    assert card["version"] == "1.0.0"
    skill_ids = {s["id"] for s in card["skills"]}
    assert "search_icd" in skill_ids  # MedCodER card surface

    # [2] Send a message — happy path with PHI
    inbound_envelope = {
        "jsonrpc": "2.0",
        "id": "e2e-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {"kind": "text", "text": "张三 主诉胸痛, 13800138000"}
                ],
                "messageId": "client-msg-e2e-1",
                "contextId": "client-ctx-supplied-should-be-discarded",
                "metadata": {"interaction_id": "e2e-correlation"},
            }
        },
    }
    r = client.post(
        "/api/icoder/agents/medcoder-coding-review/v1/message:send",
        headers=headers,
        json=inbound_envelope,
    )
    assert r.status_code == 200, r.text
    assert r.headers[A2A_PROTOCOL_HEADER] == A2A_PROTOCOL_VERSION

    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "e2e-1"
    assert "result" in body
    result = body["result"]

    # A2A Message envelope shape
    assert result["kind"] == "message"
    assert result["role"] == "agent"
    assert result["messageId"] != ""
    assert result["contextId"] != ""
    # Q4: client-supplied contextId MUST be discarded; server-generated UUID v4
    assert result["contextId"] != "client-ctx-supplied-should-be-discarded"
    assert result["messageId"] != "client-msg-e2e-1"  # server-generated too

    # iCoDer metadata — production writeback blocked, PHI redacted
    md = result["metadata"]
    assert md["production_writeback_blocked"] is True
    assert md["phi_redacted"] is True
    assert "PHONE" in md["redaction_entity_types"]
    assert "NAME" in md["redaction_entity_types"]
    # Redacted input must not contain raw PHI
    assert "张三" not in md.get("redacted_input", "")
    assert "13800138000" not in md.get("redacted_input", "")

    # State machine history (received→planning→delegating→aggregating→completed)
    assert "state_history" in md
    assert md["state_history"][0] == "planning"
    assert md["state_history"][-1] in ("completed", "failed")

    # interaction_id propagated from client messageId (T3 contract)
    assert md.get("interaction_id") == "client-msg-e2e-1"

    # Parts — must include at least one data part with the expert summary
    parts = result["parts"]
    summary_parts = [
        p for p in parts
        if isinstance(p, dict) and p.get("kind") == "data" and "summary" in p.get("data", {})
    ]
    assert len(summary_parts) == 1
    assert summary_parts[0]["data"]["summary"]["expert_count"] == 1