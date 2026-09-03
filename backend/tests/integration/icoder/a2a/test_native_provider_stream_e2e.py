from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.icoder.agent_runtime.a2a.a2a_routes import mount_a2a
from app.icoder.agent_runtime.a2a.agent_card import agent_card_from_pack
from app.icoder.agent_runtime.provider_a2a_handler import ProviderA2AHandler
from app.middleware.auth import (
    get_current_organization,
    get_current_user_or_oauth_client,
)
from icoder_runtime.backends.pure_llm_provider import PureLLMProvider
from icoder_runtime.backends.output_contract_validation import (
    declared_optional_fields,
)
from icoder_runtime.circuit_breaker import CircuitState, llm_circuit_breaker
from icoder_runtime.core.llm_gateway import DeepSeekProvider, LLMGateway


BACKEND_ROOT = Path(__file__).resolve().parents[4]
PURE_LLM_EXAMPLE = json.loads(
    (BACKEND_ROOT / "official_agents" / "triage" / "agent_pack.json").read_text(
        encoding="utf-8"
    )
)["example_outputs"][0]
PURE_LLM_INPUT = json.loads(
    (BACKEND_ROOT / "official_agents" / "triage" / "agent_pack.json").read_text(
        encoding="utf-8"
    )
)["example_inputs"][0]["input_text"]


def _transport() -> httpx.MockTransport:
    domain_result = json.loads(json.dumps(PURE_LLM_EXAMPLE))
    domain_result["manual_review_required"] = False
    domain_result["supporting_evidence"] = "validated native stream"
    final_text = json.dumps(domain_result)
    chunks = [
        {
            "id": "native-e2e",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {"content": final_text[:20]},
                "finish_reason": None,
            }],
            "usage": None,
        },
        {
            "id": "native-e2e",
            "model": "deepseek-chat",
            "choices": [{
                "index": 0,
                "delta": {"content": final_text[20:]},
                "finish_reason": "stop",
            }],
            "usage": None,
        },
        {
            "id": "native-e2e",
            "model": "deepseek-chat",
            "choices": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "total_tokens": 18,
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(chunk)}\n\n" for chunk in chunks
    ) + "data: [DONE]\n\n"

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload = json.loads(request.content)
        assert request_payload["stream"] is True
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body.encode("utf-8"),
        )

    return httpx.MockTransport(handler)


def _parse_sse(payload: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in payload.replace("\r\n", "\n").split("\n\n"):
        name = "message"
        data: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data.append(line[6:])
        if data:
            events.append((name, "\n".join(data)))
    return events


def test_deepseek_native_stream_reaches_a2a_safe_telemetry_and_final_result(
    monkeypatch,
) -> None:
    import app.icoder.agent_runtime.provider_a2a_handler as handler_module

    llm_circuit_breaker.state = CircuitState.CLOSED
    llm_circuit_breaker._failures = 0
    gateway = LLMGateway().register(
        DeepSeekProvider(api_key="test-only", _transport=_transport()),
        default=True,
    )
    provider = PureLLMProvider(llm_gateway=gateway)

    class _Registry:
        def resolve_from_agent_pack(self, pack):
            return provider

        def get_backend_config(self, pack):
            return {"llm": {"timeout_seconds": 10}, "tools": {}}

    monkeypatch.setattr(
        handler_module, "get_default_registry", lambda: _Registry(),
    )
    a2a_handler = ProviderA2AHandler(BACKEND_ROOT / "official_agents")
    agent_id = "triage"
    pack = a2a_handler.pack_for(agent_id)
    assert pack is not None

    app = FastAPI()
    mount_a2a(
        app,
        handler=a2a_handler,
        agent_provider=(
            lambda requested: agent_card_from_pack(pack)
            if requested == agent_id
            else None
        ),
        expert_caller=lambda expert_id, body: {},
    )

    class _Org:
        id = "org_native_e2e"

    app.dependency_overrides[get_current_organization] = lambda: _Org()
    app.dependency_overrides[get_current_user_or_oauth_client] = (
        lambda: (object(), None)
    )
    client = TestClient(app)
    envelope = {
        "jsonrpc": "2.0",
        "id": "native-e2e-request",
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                "messageId": "native-e2e-message",
                "parts": [{"kind": "text", "text": PURE_LLM_INPUT}],
                "metadata": {},
            },
        },
    }

    with client.stream(
        "POST",
        f"/api/icoder/agents/{agent_id}/v1/message:stream",
        headers={"A2A-Protocol-Version": "0.3"},
        json=envelope,
    ) as response:
        payload = "".join(response.iter_text())

    assert response.status_code == 200
    events = _parse_sse(payload)
    names = [name for name, _ in events]
    assert names.count("data-provider-progress") == 2
    assert "data-provider-usage" in names
    assert "data-json" in names
    progress = [
        json.loads(data)
        for name, data in events
        if name == "data-provider-progress"
    ]
    assert all(
        set(item) == {"kind", "characters", "native", "provisional"}
        for item in progress
    )
    assert all(item["native"] is True for item in progress)
    assert all(item["provisional"] is True for item in progress)
    assert "validated native stream" not in json.dumps(progress)
    final_envelope = json.loads(
        next(data for name, data in events if name == "data-json")
    )
    result = final_envelope["result"]
    data = result["parts"][0]["data"]
    output_contract = pack["output_contract"]
    required = set(output_contract["required_fields"])
    allowed = required | set(declared_optional_fields(output_contract))
    assert required.issubset(data)
    assert set(data).issubset(allowed)
    assert data["supporting_evidence"] == "validated native stream"
    assert "structured_extraction" not in data
    assert "backend_provider" not in data
    assert "tool_calls" not in data
    assert data["manual_review_required"] is True
    assert "markdown" not in data
    assert result["metadata"]["backend_provider"] == "icoder.pure-llm.v1"
    assert result["metadata"]["manual_review_required"] is True
