"""End-to-end evidence for multi-call Agent cost propagation.

The scripted provider performs one tool round and one final LLM round.  The
test proves their cumulative cost reaches the public Agent Run envelope, the
authoritative RunHistory row, and the per-Agent Usage aggregate without any
network or real credential.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-never-network")


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


class _ScriptedClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)

    async def complete_messages(self, **_kwargs):
        return self.responses.pop(0)


def _tool_call() -> dict[str, Any]:
    return {
        "id": "cost-call-1",
        "type": "function",
        "function": {
            "name": "verify_code",
            "arguments": json.dumps({"code": "I50.9"}),
        },
    }


def test_multi_round_cost_reaches_response_history_and_usage(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.api import agent_run
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from icoder_runtime.backends.llm_with_tools_provider import (
        LLMWithToolsProvider,
    )
    from icoder_runtime.backends.pure_llm_provider import LLMResponse

    agent_id = f"cumulative-cost-e2e-{uuid4().hex[:8]}"
    provider = LLMWithToolsProvider(
        llm_client=_ScriptedClient([
            LLMResponse(
                text="",
                tool_calls=[_tool_call()],
                cost_usd=0.011,
            ),
            LLMResponse(
                text="# Status: warning\n\nNeeds human review.",
                finish_reason="stop",
                cost_usd=0.022,
            ),
        ]),
        max_tool_rounds=2,
    )

    async def _dispatch(tool_name, args, request, *, run_id=None, **_kwargs):
        return {
            "content": {"verified": True, "code": args["code"]},
            "isError": False,
            "tool_name": tool_name,
            "duration_ms": 1,
        }

    provider._mcp_layer._dispatch_tool_fn = _dispatch
    provider._mcp_layer._list_tools_fn = lambda: [{
        "name": "verify_code",
        "description": "verify code",
        "input_schema": {"type": "object"},
    }]

    pack = {
        "agent_ref": f"icoder/{agent_id}@1.0.0",
        "manifest": {"human_review": "required"},
        "system_prompt": "Use the verification tool and summarize safely.",
        "backend_provider": provider.provider_id,
        "default_runtime_mode": "a2a_llm_with_tools",
    }

    class _Registry:
        def resolve_from_agent_pack(self, _pack):
            return provider

        def get_backend_config(self, _pack):
            return {
                "tools": {
                    "scope": ["verify_code"],
                    "mandatory": ["verify_code"],
                    "forbidden": [],
                }
            }

    monkeypatch.setattr(
        agent_run,
        "_load_pack_by_agent_id",
        lambda _agent_id: pack,
    )
    monkeypatch.setattr(agent_run, "get_default_registry", lambda: _Registry())

    response = client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={"input": {"text": "去标识病例：请核验 I50.9。"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is False
    assert body["cost"] == {"amount": 0.033, "currency": "CNY"}

    async def _read_history() -> float:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(RunHistoryModel).where(
                        RunHistoryModel.run_id == body["run_id"]
                    )
                )
            ).scalar_one()
            return float(row.cost_usd)

    assert asyncio.run(_read_history()) == pytest.approx(0.033)

    usage = client.get("/api/usage/by-agent", params={"days": 7})
    assert usage.status_code == 200, usage.text
    item = next(
        entry
        for entry in usage.json()["items"]
        if entry["agent_id"] == agent_id
    )
    assert item["cost"] == pytest.approx(0.033)

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(RunHistoryModel).where(
                        RunHistoryModel.run_id == body["run_id"]
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                await db.delete(row)
                await db.commit()

    asyncio.run(_cleanup())


def test_explicit_zero_cost_is_not_downgraded_to_unknown() -> None:
    import time

    from app.api.agent_run import _map_backend_response
    from icoder_runtime.backends.contracts import BackendResponse

    response = _map_backend_response(
        agent_id="zero-cost-rule-agent",
        run_id="run-zero-cost",
        trace_id="trace-zero-cost",
        runtime_mode="rule_engine",
        resp=BackendResponse(
            status="pass",
            summary="deterministic rule result",
            backend_provider="test.rule",
            backend_type="rule_engine",
            cost_usd=0.0,
        ),
        include_trace=False,
        include_evidence=False,
        t0=time.perf_counter(),
    )
    assert response.cost == {"amount": 0.0, "currency": "CNY"}


def test_cdi_configured_usage_estimate_reaches_response_and_history(
    client: TestClient,
    monkeypatch,
) -> None:
    from app.database import AsyncSessionLocal
    from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler
    from app.icoder.agent_runtime.orchestrator.inbound_handler import InboundResponse
    from app.models.run_history import RunHistoryModel

    estimated_cost = 0.00066472
    monkeypatch.setattr(
        CDIA2AHandler,
        "handle",
        lambda self, agent_id, request: InboundResponse(
            kind="message",
            context_id=request.message.context_id,
            role="agent",
            parts=[{"kind": "data", "data": {"trace_refs": {}}}],
            metadata={
                "run_id": request.metadata["run_id"],
                "runtime_mode": "cdi_real_orchestrator",
                "cost": {
                    "amount": estimated_cost,
                    "currency": "CNY",
                    "source": "configured_usage_pricing_estimate",
                    "billing_authoritative": False,
                },
            },
            redacted_input="synthetic-deidentified-cdi-case",
        ),
    )

    response = client.post(
        "/api/v1/agents/clinical-documentation-improvement-agent/run",
        json={"input": {"text": "去标识化合成 CDI 病例。"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is False
    assert body["cost"] == {
        "amount": estimated_cost,
        "currency": "CNY",
        "source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }

    async def _read_and_cleanup() -> float:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(RunHistoryModel).where(
                        RunHistoryModel.run_id == body["run_id"]
                    )
                )
            ).scalar_one()
            amount = float(row.cost_usd)
            await db.delete(row)
            await db.commit()
            return amount

    assert asyncio.run(_read_and_cleanup()) == pytest.approx(estimated_cost)
