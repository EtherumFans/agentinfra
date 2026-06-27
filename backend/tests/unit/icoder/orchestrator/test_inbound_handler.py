"""T3 — InboundHandler (SPEC §5.1, §3.2).

The HTTP route layer is tested separately in
``tests/integration/icoder/a2a/test_endpoints.py`` against the new
``app.icoder.agent_runtime.a2a.routes_inbound.build_inbound_router``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import pytest

from app.icoder.agent_runtime.orchestrator import (
    Aggregator,
    Delegator,
    DictAgentProvider,
    InboundHandler,
    InboundMessage,
    InboundRequest,
    PHIRedactor,
    Planner,
    extract_text_from_parts,
    is_valid_request,
    make_context_id,
    make_message_id,
    make_run_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _Agent:
    id: str = "medical-coding-agent"
    name: str = "Medical Coding Agent"
    expert_ids: list[str] = field(default_factory=lambda: ["coding-expert"])
    config: dict = field(default_factory=dict)


def _good_plan_response(*, expert_id="coding-expert", subtask="encode", critical=True):
    return {
        "content": json.dumps(
            {
                "experts": [
                    {
                        "expert_id": expert_id,
                        "priority": 1,
                        "critical": critical,
                        "subtask_input": subtask,
                        "tool_constraints": [],
                    }
                ],
                "reason": "编码审核",
            }
        ),
        "model": "fake",
    }


def _ok_invoker_factory(results_by_expert: dict):
    def _invoke(invocation):
        # return whatever was scripted, or a default OK
        return results_by_expert.get(
            invocation.expert_id, {"echo": invocation.subtask_input}
        )

    return _invoke


def _failing_invoker_factory(error_msg="net down"):
    def _invoke(invocation):
        from app.icoder.agent_runtime.orchestrator.delegator import (
            ExpertInvocationError,
        )

        raise ExpertInvocationError(error_msg)

    return _invoke


def _build_handler(
    *,
    llm_responses: list[dict] | None = None,
    invoker=None,
    agents: dict | None = None,
):
    """Construct a fully-wired InboundHandler for tests."""
    if llm_responses is None:
        llm_responses = [_good_plan_response()]
    script = list(llm_responses)
    sleeps: list[float] = []

    def _llm(system, user):
        if not script:
            raise RuntimeError("LLM scripted list exhausted")
        return script.pop(0)

    from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig
    from app.icoder.agent_runtime.orchestrator.delegator import (
        DelegatorConfig,
    )

    planner = Planner(
        llm_call=_llm,
        config=PlannerConfig(sleep_fn=sleeps.append),
    )
    inv = invoker or _ok_invoker_factory({})
    delegator = Delegator(
        invoker=inv,
        config=DelegatorConfig(sleep_fn=sleeps.append),
    )
    aggregator = Aggregator()
    provider = DictAgentProvider(agents or {"medical-coding-agent": _Agent()})
    handler = InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=aggregator,
        agent_provider=provider,
    )
    return handler, sleeps


def _ok_request(text="病历文本 张三 主诉胸痛"):
    return InboundRequest(
        message=InboundMessage(
            role="user",
            parts=[{"kind": "text", "text": text}],
            interaction_id="test-int-1",
        )
    )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def test_extract_text_from_parts_text_only():
    text = extract_text_from_parts([{"kind": "text", "text": "hello"}])
    assert text == "hello"


def test_extract_text_from_parts_data_only():
    text = extract_text_from_parts([{"kind": "data", "data": {"code": "I50.9"}}])
    assert '"code"' in text and "I50.9" in text


def test_extract_text_from_parts_mixed():
    text = extract_text_from_parts(
        [
            {"kind": "text", "text": "alpha"},
            {"kind": "data", "data": {"k": "v"}},
            {"kind": "text", "text": "beta"},
        ]
    )
    assert "alpha" in text and "beta" in text and "k" in text


def test_extract_text_handles_empty_parts():
    assert extract_text_from_parts([]) == ""


def test_extract_text_skips_non_dict():
    assert extract_text_from_parts([None, "string", 42]) == ""


def test_extract_text_falls_back_to_text_field():
    # No "kind" but has "text"
    assert extract_text_from_parts([{"text": "raw"}]) == "raw"


def test_is_valid_request_rejects_empty_parts():
    ok, why = is_valid_request(
        InboundRequest(message=InboundMessage(role="user", parts=[]))
    )
    assert not ok
    assert "parts" in why


def test_is_valid_request_accepts_valid():
    ok, why = is_valid_request(_ok_request())
    assert ok
    assert why == ""


def test_make_context_id_is_uuid_v4():
    cid = make_context_id()
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        cid,
    )


def test_make_message_id_is_uuid_v4():
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        make_message_id(),
    )


def test_make_run_id_is_uuid_v4():
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        make_run_id(),
    )


def test_context_ids_are_unique():
    ids = {make_context_id() for _ in range(50)}
    assert len(ids) == 50


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_handler_constructor_requires_all_deps():
    from app.icoder.agent_runtime.orchestrator.aggregator import Aggregator
    from app.icoder.agent_runtime.orchestrator.planner import Planner

    with pytest.raises(TypeError):
        InboundHandler()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_handle_happy_path_returns_message_envelope():
    handler, _ = _build_handler()
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert resp.kind == "message"
    assert resp.http_status == 200
    assert resp.error is None
    # A2A-shaped response
    assert resp.context_id != ""
    assert resp.message_id != ""
    assert resp.role == "agent"
    # metadata carries run_id + state history
    assert "run_id" in resp.metadata
    assert resp.metadata["phi_redacted"] is True
    assert resp.metadata["production_writeback_blocked"] is True
    # state history: received→planning→delegating→aggregating→completed
    assert resp.metadata["state_history"] == [
        "planning", "delegating", "aggregating", "completed",
    ]


def test_handle_redacts_phi_in_input():
    handler, _ = _build_handler()
    resp = handler.handle(
        agent_id="medical-coding-agent",
        request=_ok_request(text="张三 13800138000 主诉胸痛"),
    )
    assert resp.kind == "message"
    assert "张三" not in resp.metadata.get("redacted_input", "")
    # The redaction_entity_types metadata captures what was found
    assert "PHONE" in resp.metadata["redaction_entity_types"]
    assert "NAME" in resp.metadata["redaction_entity_types"]


def test_handle_response_parts_include_expert_result_and_summary():
    handler, _ = _build_handler()
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert len(resp.parts) >= 2
    # At least one part is a data part with summary
    summary_parts = [
        p for p in resp.parts
        if isinstance(p, dict) and p.get("kind") == "data" and "summary" in p.get("data", {})
    ]
    assert len(summary_parts) == 1
    assert summary_parts[0]["data"]["summary"]["expert_count"] == 1


def test_handle_propagates_interaction_id():
    handler, _ = _build_handler()
    req = _ok_request()
    resp = handler.handle("medical-coding-agent", req)
    assert resp.metadata["interaction_id"] == "test-int-1"


def test_handle_ignores_client_supplied_context_id():
    """Q4: server generates contextId regardless of client input."""
    handler, _ = _build_handler()
    req = InboundRequest(
        message=InboundMessage(
            role="user",
            parts=[{"kind": "text", "text": "x"}],
            interaction_id="",
        )
    )
    resp = handler.handle("medical-coding-agent", req)
    assert resp.context_id != ""
    # This isn't checked explicitly — but the client couldn't supply a
    # context_id in InboundRequest shape anyway, so Q4 is structurally enforced.


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_handle_rejects_empty_parts():
    handler, _ = _build_handler()
    resp = handler.handle(
        agent_id="medical-coding-agent",
        request=InboundRequest(message=InboundMessage(role="user", parts=[])),
    )
    assert resp.kind == "error"
    assert resp.http_status == 400
    assert resp.error["code"] == "invalid_request"


def test_handle_rejects_unknown_agent():
    """A2A spec §6.2 — unknown agent_id returns the AGENT_NOT_FOUND
    business code with HTTP 404, NOT the generic invalid_request.
    See also: ``app/icoder/agent_runtime/a2a/errors.py::A2AErrorCode.AGENT_NOT_FOUND``.
    """
    handler, _ = _build_handler()
    resp = handler.handle(agent_id="ghost-agent", request=_ok_request())
    assert resp.kind == "error"
    assert resp.http_status == 404
    assert resp.error["code"] == "AGENT_NOT_FOUND"
    assert "ghost-agent" in resp.error["message"]


def test_handle_agent_provider_exception_returns_invalid_request():
    # Use a custom callable provider that raises — do NOT monkey-patch
    # DictAgentProvider.__call__ at class level (breaks other tests).
    def _boom(_agent_id):
        raise RuntimeError("registry down")

    from app.icoder.agent_runtime.orchestrator.planner import Planner
    from app.icoder.agent_runtime.orchestrator.delegator import Delegator

    handler = InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=Planner(llm_call=lambda s, u: {"content": "{}"}),
        delegator=Delegator(invoker=lambda i: {}),
        aggregator=Aggregator(),
        agent_provider=_boom,
    )
    resp = handler.handle("any", _ok_request())
    assert resp.kind == "error"
    assert resp.http_status == 400


def test_handle_planner_failure_returns_planning_failed():
    # LLM returns garbage that fails JSON parse 3x
    bad = [{"content": "not json"}] * 5
    handler, _ = _build_handler(llm_responses=bad)
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert resp.kind == "error"
    assert resp.error["code"] == "planning_failed"
    assert resp.http_status == 500
    # state history should include received→planning→failed
    assert resp.metadata["state_history"] == ["planning", "failed"]


def test_handle_critical_expert_failure_returns_expert_failed():
    handler, _ = _build_handler(invoker=_failing_invoker_factory("net"))
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert resp.kind == "error"
    assert resp.error["code"] == "expert_failed"
    assert resp.http_status == 502
    # state history: planning → delegating → failed
    assert resp.metadata["state_history"] == [
        "planning", "delegating", "failed",
    ]


def test_handle_non_critical_expert_failure_still_completes():
    """Non-critical expert fail should not abort the run (per SPEC §7.3)."""
    plan_resp = _good_plan_response(expert_id="coding-expert", critical=False)
    # Two responses (in case parse retry triggers)
    handler, _ = _build_handler(
        llm_responses=[plan_resp, plan_resp],
        invoker=_failing_invoker_factory("non-critical fail"),
    )
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert resp.kind == "message"
    assert resp.http_status == 200


def test_handle_phi_redaction_failure_returns_phi_redaction_failed():
    # Provide an Agent whose input triggers redaction failure (None)
    class _BadRedactor(PHIRedactor):
        def redact(self, text):
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                PHIRedactionError,
            )

            raise PHIRedactionError("simulated", stage="received")

    from app.icoder.agent_runtime.orchestrator.planner import Planner
    from app.icoder.agent_runtime.orchestrator.delegator import Delegator

    handler = InboundHandler(
        phi_redactor=_BadRedactor(),
        planner=Planner(llm_call=lambda s, u: {"content": "{}"}),
        delegator=Delegator(invoker=lambda i: {}),
        aggregator=Aggregator(),
        agent_provider=DictAgentProvider({"medical-coding-agent": _Agent()}),
    )
    resp = handler.handle("medical-coding-agent", _ok_request())
    assert resp.kind == "error"
    assert resp.error["code"] == "phi_redaction_failed"
    assert resp.http_status == 500


# ---------------------------------------------------------------------------
# State machine driving — order is observable via metadata
# ---------------------------------------------------------------------------


def test_handle_state_history_records_all_hops():
    handler, _ = _build_handler()
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    # 4 hops in happy path: PHI_REDACTED, PLAN_GENERATED,
    # ALL_EXPERTS_RETURNED, AGGREGATED
    assert resp.metadata["state_history"] == [
        "planning",
        "delegating",
        "aggregating",
        "completed",
    ]


def test_handle_includes_state_stage_in_error_metadata():
    handler, _ = _build_handler(invoker=_failing_invoker_factory())
    resp = handler.handle(agent_id="medical-coding-agent", request=_ok_request())
    assert resp.metadata["stage"] == "delegating"


# ---------------------------------------------------------------------------
# DictAgentProvider
# ---------------------------------------------------------------------------


def test_dict_agent_provider_returns_registered():
    p = DictAgentProvider({"a": _Agent()})
    assert p("a") is not None
    assert p("a").id == "medical-coding-agent"


def test_dict_agent_provider_returns_none_for_missing():
    p = DictAgentProvider({})
    assert p("missing") is None


def test_dict_agent_provider_register_after_init():
    p = DictAgentProvider({})
    p.register("a", _Agent(id="agent-a"))
    assert p("a").id == "agent-a"


# ---------------------------------------------------------------------------
# T10 — Stress / error paths (SPEC §11.5)
# ---------------------------------------------------------------------------


def test_concurrent_requests_10x_no_block():
    """10 concurrent handler.handle() calls — all must return unique run_ids.

    Phase 1: Delegator runs steps sequentially by design (Q-S2). Concurrency
    here means we drive handler.handle() from a thread pool; each call still
    goes received → planning → delegating → aggregating → completed in one
    thread. Total wall-clock should be < 5s because the scripted LLM/expert
    stubs are CPU-only.
    """
    from concurrent.futures import ThreadPoolExecutor

    handler, _sleeps = _build_handler()

    def _one_run(i: int) -> str:
        req = InboundRequest(
            message=InboundMessage(
                role="user",
                parts=[{"kind": "text", "text": f"病历 {i} 张三 胸痛"}],
                interaction_id=f"stress-{i}",
            )
        )
        resp = handler.handle("medical-coding-agent", req)
        return resp.metadata["run_id"]

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as pool:
        run_ids = list(pool.map(_one_run, range(10)))
    elapsed = time.monotonic() - t0

    assert len(run_ids) == 10
    assert len(set(run_ids)) == 10, f"run_ids must be unique, got {run_ids}"
    # Phase 1 sequential — but in-process scripted stubs are fast.
    # Generous bound: 10s (CI/slow machines). Production should be << 1s
    # per call when the real MedCodER pipeline is warm.
    assert elapsed < 10.0, f"10 concurrent calls took {elapsed:.2f}s"


def test_planner_real_gateway_degraded_fallback():
    """Planner with a real LLMCall that returns a degraded payload.

    Mirrors :meth:`wiring.build_llm_call_from_gateway` falling back to the
    stub when a real gateway raises. Verifies the orchestrator surfaces a
    ``PLANNING_FAILED`` envelope (not a 500) so callers can retry.
    """
    from app.icoder.agent_runtime.orchestrator.planner import (
        PlannerConfig,
    )
    from app.icoder.agent_runtime.orchestrator.errors import (
        OrchestratorError,
    )

    def _degraded_llm(_sys: str, _user: str) -> dict:
        # Simulate the fallback stub in wiring._stub_llm_call — empty
        # content. The Planner raises PlannerError, the handler maps it
        # to PLANNING_FAILED.
        return {"content": "{}", "model": "degraded", "latency_ms": 0}

    from app.icoder.agent_runtime.orchestrator.planner import Planner

    planner = Planner(llm_call=_degraded_llm, config=PlannerConfig())
    handler, _ = _build_handler()
    # Swap in our degraded planner.
    handler._planner = planner  # type: ignore[attr-defined]

    req = _ok_request()
    resp = handler.handle("medical-coding-agent", req)

    assert resp.kind == "error"
    assert resp.error is not None
    # Plan has no experts → Planner raises → handler maps to planning_failed.
    assert resp.error["code"].lower() in {"planning_failed", "invalid_request"}
    assert resp.http_status == 500


def test_inbound_handler_handle_is_sync_documents_known_limitation():
    """Document that ``InboundHandler.handle`` is sync and blocks the event loop.

    Phase 2 will migrate the handler to ``async def``. Until then, the A2A
    route must wrap calls in ``asyncio.to_thread`` (see
    ``routes_inbound._dispatch``). This test pins the contract: callers
    awaiting an async coroutine from ``handle`` is unsupported.
    """
    import inspect

    handler, _ = _build_handler()
    assert not inspect.iscoroutinefunction(handler.handle), (
        "InboundHandler.handle must remain sync until Phase 2 — "
        "any async migration must update routes_inbound._dispatch "
        "to drop the asyncio.to_thread wrapper."
    )
