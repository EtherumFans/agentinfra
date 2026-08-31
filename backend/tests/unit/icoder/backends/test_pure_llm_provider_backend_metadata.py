"""Tests for ``PureLLMProvider.invoke`` → ``emit_backend_metadata_event``
wiring — Phase 4-B Step 2(b).

Verifies:
  - ``invoke()`` emits a RunTrace ``backend_metadata`` event after a
    successful LLM response.
  - All 8 backend metadata fields are populated in the event's
    ``safe_metadata``.
  - ``fallback_used=True`` when the LLM response is degraded.
  - The event is persisted in the default RunTrace store.
  - ``invoke()`` still returns a valid ``BackendResponse`` (the
    metadata emission is non-blocking).
  - Missing LLM wiring fails closed and emits no success metadata.
"""
from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStore,
    get_default_store,
)
from icoder_runtime.backends import (
    AgentRunContext,
    BackendRequest,
)
from icoder_runtime.backends.pure_llm_provider import (
    LLMResponse,
    PureLLMProvider,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-p4b-backend-metadata",
        context_id="ctx-p4b",
        agent_id="note-completeness-agent",
        redacted_input="主诉：心悸3年...",
        agent_pack={"agent": {"system_prompt": "You are Note Completeness."}},
    )


class _MockLLMClient:
    """Mock LLM client returning a configurable LLMResponse."""
    def __init__(self, *, text: str = "ok", finish_reason: str = "stop",
                 latency_ms: int = 5, raise_exc: Exception | None = None,
                 raw: dict | None = None) -> None:
        self._text = text
        self._finish_reason = finish_reason
        self._latency_ms = latency_ms
        self._raise = raise_exc
        self._raw = raw or {}

    async def complete(self, *, system_prompt, user_input,
                       temperature=0.0, max_tokens=None, timeout_seconds=60.0):
        if self._raise is not None:
            raise self._raise
        return LLMResponse(
            text=self._text,
            finish_reason=self._finish_reason,
            latency_ms=self._latency_ms,
            raw=self._raw,
        )

    def stream(self, *, system_prompt, user_input, **kwargs):
        raise NotImplementedError("stream not implemented in mock")


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def fresh_trace_store():
    """Reset the default RunTrace store before + after each test."""
    store = get_default_store()
    if hasattr(store, "clear"):
        store.clear()
    # Inject a fresh in-memory store as the default so emit_backend_metadata_event writes to it.
    import app.icoder.agent_runtime.orchestrator.run_trace as rt_mod
    fresh = RunTraceStore()
    orig_get = getattr(rt_mod, "get_default_store", None)
    rt_mod.get_default_store = lambda: fresh
    try:
        yield fresh
    finally:
        if orig_get is not None:
            rt_mod.get_default_store = orig_get
        if hasattr(fresh, "clear"):
            fresh.clear()


# ── invoke() emits backend_metadata event ──────────────────────────


@pytest.mark.asyncio
async def test_invoke_emits_backend_metadata_event_with_all_fields(fresh_trace_store):
    """invoke() with a mock LLM client emits a backend_metadata RunTrace event."""
    mock = _MockLLMClient(
        text='{"review_conclusion":"PASS","completeness_score":1.0}',
        latency_ms=42,
        raw={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "usage": {"input_tokens": 11, "output_tokens": 7},
        },
    )
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(system_prompt="sys", user_input="主诉：心悸")
    resp = await p.invoke(req, _ctx())

    assert resp.backend_provider == "icoder.pure-llm.v1"
    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_events = [
        e for e in events
        if e.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    ]
    assert len(backend_events) == 1
    md = backend_events[0].safe_metadata
    assert md["backend_provider"] == "icoder.pure-llm.v1"
    assert md["backend_type"] == "pure_llm"
    assert md["provider_latency_ms"] == 42
    assert md["provider_deterministic"] is False
    assert md["supports_tool_calling"] is False
    assert md["fallback_used"] is False
    assert md["output_contract"] == "icoder/PureLLMOutput/v1"
    assert md["tool_rounds"] == 0
    assert md["model_provider"] == "deepseek"
    assert md["model_system"] == "deepseek"
    assert md["model_name"] == "deepseek-chat"
    assert md["input_tokens"] == 11
    assert md["output_tokens"] == 7
    assert md["total_tokens"] == 18
    assert md["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_invoke_marks_fallback_used_when_degraded(fresh_trace_store):
    """When LLM returns finish_reason='degraded:...', fallback_used=True in trace."""
    mock = _MockLLMClient(
        text="degraded fallback",
        finish_reason="degraded:no_api_key",
        latency_ms=1,
    )
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert resp.finish_reason == "llm_degraded: degraded:no_api_key"

    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_events = [
        e for e in events
        if e.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    ]
    assert len(backend_events) == 1
    assert backend_events[0].safe_metadata["fallback_used"] is True
    assert backend_events[0].safe_metadata["provider_status"] == "fail"
    assert backend_events[0].status == "failed"


@pytest.mark.asyncio
async def test_invoke_audits_tenant_model_routing_on_degraded_response(
    fresh_trace_store,
):
    """A failed-closed model call still retains its deployment decision."""
    mock = _MockLLMClient(
        text="degraded",
        finish_reason="degraded:provider_http_502",
        raw={
            "model_routing": {
                "mode": "pinned",
                "deployment_id": "hospital-local-a",
                "selection_version": 3,
                "decision": "tenant_pinned",
            }
        },
    )
    p = PureLLMProvider(llm_client=mock)
    resp = await p.invoke(
        BackendRequest(system_prompt="sys", user_input="hello"),
        _ctx(),
    )

    assert resp.status == "fail"
    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_event = next(
        event for event in events
        if event.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    )
    assert backend_event.safe_metadata["model_deployment_id"] == "hospital-local-a"
    assert backend_event.safe_metadata["model_routing_mode"] == "pinned"
    assert backend_event.safe_metadata["model_selection_version"] == 3
    assert backend_event.safe_metadata["model_routing_decision"] == "tenant_pinned"
    assert resp.raw_provider_response["model_routing"]["deployment_id"] == "hospital-local-a"


@pytest.mark.asyncio
async def test_invoke_without_llm_fails_closed_without_success_event(fresh_trace_store):
    """Missing LLM wiring must not emit a successful backend event."""
    p = PureLLMProvider()  # no llm_client
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "fail"
    assert resp.finish_state == "failed"
    assert "llm_unavailable" in resp.finish_reason

    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_events = [
        e for e in events
        if e.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    ]
    assert len(backend_events) == 1
    assert backend_events[0].safe_metadata["provider_status"] == "fail"
    assert backend_events[0].status == "failed"


@pytest.mark.asyncio
async def test_invoke_fail_envelope_emits_failed_audit_event(fresh_trace_store):
    """Failed runs stay auditable and are explicitly marked failed."""
    mock = _MockLLMClient(raise_exc=RuntimeError("LLM exploded"))
    p = PureLLMProvider(llm_client=mock)
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.status == "fail"
    # A failure event is retained for audit; it must not look successful.
    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_events = [
        e for e in events
        if e.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    ]
    assert len(backend_events) == 1
    assert backend_events[0].safe_metadata["provider_status"] == "fail"
    assert backend_events[0].status == "failed"


@pytest.mark.asyncio
async def test_invoke_via_gateway_adapter_emits_event(fresh_trace_store):
    """When llm_gateway is wired (not llm_client), the adapter path still emits."""
    class _MockGateway:
        async def generate(self, messages, *, provider="", tools=None,
                           response_schema=None, context=None):
            return {
                "content": '{"review_conclusion":"WARNING"}',
                "model": "mock",
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "latency_ms": 33,
            }
    p = PureLLMProvider(llm_gateway=_MockGateway())
    req = BackendRequest(system_prompt="sys", user_input="hello")
    resp = await p.invoke(req, _ctx())
    assert resp.backend_provider == "icoder.pure-llm.v1"

    events = fresh_trace_store.get_run("run-p4b-backend-metadata")
    backend_events = [
        e for e in events
        if e.safe_metadata.get("backend_provider") == "icoder.pure-llm.v1"
    ]
    assert len(backend_events) == 1
    assert backend_events[0].safe_metadata["provider_latency_ms"] == 33


@pytest.mark.asyncio
async def test_invoke_does_not_break_when_trace_unavailable(monkeypatch):
    """If RunTrace import fails, invoke() must still return a valid response.

    Defensive — observability never breaks the agent run.
    """
    mock = _MockLLMClient(text="ok", latency_ms=5)
    p = PureLLMProvider(llm_client=mock)

    # Simulate RunTrace being unavailable by making get_default_store raise.
    import app.icoder.agent_runtime.orchestrator.run_trace as rt_mod
    def _raise():
        raise RuntimeError("RunTrace unavailable in this test")
    monkeypatch.setattr(rt_mod, "get_default_store", _raise)

    req = BackendRequest(system_prompt="sys", user_input="hello")
    # Should not raise — _emit_backend_metadata swallows the exception.
    resp = await p.invoke(req, _ctx())
    assert resp.backend_provider == "icoder.pure-llm.v1"
    assert resp.markdown == "ok"
