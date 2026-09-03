from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.icoder.agent_runtime.specialized_telemetry import (
    build_configured_cny_cost,
    build_cdi_telemetry_event,
    build_medical_coding_telemetry_event,
)


def _stage(
    *,
    provider: str = "deepseek",
    model: str = "deepseek-chat",
    prompt: int = 10,
    completion: int = 5,
    total: int = 15,
    latency: int = 20,
    degraded: bool = False,
    expert_id: str = "",
    stage: str = "encounter_synthesis",
    provider_error_category: str = "",
    provider_http_status: int | None = None,
    provider_attempt_count: int | None = None,
    provider_retryable: bool | None = None,
):
    return SimpleNamespace(
        provider=provider,
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        latency_ms=latency,
        degraded=degraded,
        expert_id=expert_id,
        stage=stage,
        provider_error_category=provider_error_category,
        provider_http_status=provider_http_status,
        provider_attempt_count=provider_attempt_count,
        provider_retryable=provider_retryable,
    )


def test_medical_coding_maps_only_observed_model_usage_and_usd_cost():
    result = SimpleNamespace(
        raw_schema={"model": "deepseek-chat", "token_usage": {}},
        cost={
            "amount": 0.004,
            "currency": "USD",
            "token_usage": {"input_tokens": 20, "output_tokens": 7},
        },
        trace_events=[{
            "step": "llm_call",
            "status": "ok",
            "metadata": {"model": "deepseek-chat"},
        }],
        llm_provider="deepseek",
        latency_ms=31,
        error=False,
        degraded=False,
    )

    event = build_medical_coding_telemetry_event(
        result, output_contract="icoder/MedicalCodingOutput/v2"
    )

    assert event["status"] == "ok"
    assert event["duration_ms"] == 31
    metadata = event["safe_metadata"]
    assert metadata["backend_type"] == "medical_coding"
    assert metadata["model_provider"] == "deepseek"
    assert metadata["model_name"] == "deepseek-chat"
    assert metadata["input_tokens"] == 20
    assert metadata["output_tokens"] == 7
    assert metadata["total_tokens"] == 27
    assert metadata["model_cost_usd"] == 0.004
    assert metadata["llm_call_count"] == 1


def test_medical_coding_degraded_mock_does_not_publish_fake_llm_usage():
    result = SimpleNamespace(
        raw_schema={
            "model": "mock-model",
            "token_usage": {"input_tokens": 99, "output_tokens": 88},
        },
        cost={"amount": 1.0, "currency": "USD"},
        trace_events=[{"step": "llm_call", "status": "ok"}],
        llm_provider="mock",
        latency_ms=2,
        error=True,
        degraded=True,
    )

    metadata = build_medical_coding_telemetry_event(result)["safe_metadata"]

    assert metadata["provider_status"] == "degraded"
    for key in (
        "model_provider", "model_system", "model_name", "input_tokens",
        "output_tokens", "total_tokens", "model_cost_usd", "llm_call_count",
    ):
        assert key not in metadata


def test_medical_coding_preflight_failure_is_not_mislabeled_as_llm_call():
    result = SimpleNamespace(
        raw_schema={},
        cost={},
        trace_events=[{"step": "return", "status": "error"}],
        llm_provider="deepseek",
        latency_ms=1,
        error=True,
        degraded=False,
    )

    metadata = build_medical_coding_telemetry_event(result)["safe_metadata"]

    assert metadata["provider_status"] == "fail"
    assert "model_provider" not in metadata
    assert "model_name" not in metadata
    assert "llm_call_count" not in metadata


def test_cdi_aggregates_actual_stage_and_invoked_expert_calls_only():
    stage_traces = [_stage(prompt=10, completion=3, total=13)]
    expert_traces = [
        _stage(prompt=7, completion=2, total=9, expert_id="coding-expert"),
        _stage(
            prompt=0, completion=0, total=0,
            expert_id="pubmed-expert", latency=0,
        ),
    ]
    specialist_trace = [
        SimpleNamespace(
            expert_id="coding-expert", execution_mode="LLM_KNOWLEDGE_ONLY"
        ),
        SimpleNamespace(
            expert_id="pubmed-expert", execution_mode="SKIPPED_NOT_NEEDED"
        ),
    ]

    event = build_cdi_telemetry_event(
        stage_traces=stage_traces,
        expert_traces=expert_traces,
        specialist_trace=specialist_trace,
        output_contract="icoder/CDIOutput/v1",
    )

    metadata = event["safe_metadata"]
    assert event["status"] == "ok"
    assert metadata["model_provider"] == "deepseek"
    assert metadata["model_name"] == "deepseek-chat"
    assert metadata["input_tokens"] == 17
    assert metadata["output_tokens"] == 5
    assert metadata["total_tokens"] == 22
    assert metadata["llm_call_count"] == 2
    assert metadata["tool_rounds"] == 1
    assert metadata["provider_latency_ms"] == 40

    cost = build_configured_cny_cost(
        event,
        input_price_per_1m=1.0,
        output_price_per_1m=2.0,
    )
    assert cost == {
        "amount": 0.000027,
        "currency": "CNY",
        "source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }


def test_cdi_includes_gate_calls_and_content_free_latency_attribution():
    event = build_cdi_telemetry_event(
        stage_traces=[_stage(prompt=10, completion=3, total=13, latency=20)],
        expert_traces=[],
        specialist_trace=[],
        safety_gate_traces=[
            _stage(
                prompt=7, completion=2, total=9, latency=30,
                stage="claim_evidence_alignment_gate",
            ),
            _stage(
                prompt=6, completion=1, total=7, latency=40,
                stage="claim_evidence_alignment_gate",
            ),
        ],
        stage_duration_ms={
            "encounter_synthesis": 25,
            "claim_evidence_alignment_gate": 35,
            "semantic_necessity_gate": 45,
        },
        orchestration_latency_ms=120,
        latency_budget_ms=100,
        gate_max_concurrency=2,
    )

    metadata = event["safe_metadata"]
    assert metadata["input_tokens"] == 23
    assert metadata["output_tokens"] == 6
    assert metadata["total_tokens"] == 29
    assert metadata["llm_call_count"] == 3
    assert metadata["provider_latency_ms"] == 90
    assert metadata["orchestration_latency_ms"] == 120
    assert metadata["instrumented_stage_latency_ms"] == 105
    assert event["duration_ms"] == 120
    assert metadata["model_call_latency_sum_ms"] == 90
    assert metadata["parallel_model_calls_observed"] is True
    assert metadata["provider_latency_exceeds_wall_time"] is False
    assert metadata["non_provider_wall_latency_known"] is False
    assert "non_provider_wall_latency_ms" not in metadata
    assert metadata["slowest_stage"] == "semantic_necessity_gate"
    assert metadata["slowest_stage_latency_ms"] == 45
    assert metadata["latency_budget_ms"] == 100
    assert metadata["latency_budget_exceeded"] is True


def test_cdi_serial_latency_keeps_non_provider_wall_attribution() -> None:
    event = build_cdi_telemetry_event(
        stage_traces=[_stage(latency=60)],
        expert_traces=[],
        specialist_trace=[],
        stage_duration_ms={"encounter_synthesis": 80},
        orchestration_latency_ms=80,
        gate_max_concurrency=1,
    )

    metadata = event["safe_metadata"]
    assert event["duration_ms"] == 80
    assert metadata["parallel_model_calls_observed"] is False
    assert metadata["provider_latency_exceeds_wall_time"] is False
    assert metadata["non_provider_wall_latency_known"] is True
    assert metadata["non_provider_wall_latency_ms"] == 20


def test_cdi_omits_partial_token_aggregate_and_marks_degraded_failed():
    event = build_cdi_telemetry_event(
        stage_traces=[
            _stage(),
            _stage(prompt=0, completion=0, total=0, degraded=True),
        ],
        expert_traces=[],
        specialist_trace=[],
        degraded_safety_gates={"semantic_necessity_gate": "unavailable"},
    )

    assert event["status"] == "failed"
    metadata = event["safe_metadata"]
    assert metadata["provider_status"] == "degraded"
    assert metadata["llm_call_count"] == 2
    assert "input_tokens" not in metadata
    assert "output_tokens" not in metadata
    assert "total_tokens" not in metadata
    assert build_configured_cny_cost(
        event,
        input_price_per_1m=1.0,
        output_price_per_1m=2.0,
    ) == {}


def test_cdi_persists_only_bounded_provider_failure_diagnostics() -> None:
    event = build_cdi_telemetry_event(
        stage_traces=[
            _stage(
                degraded=True,
                provider_error_category="rate_limit",
                provider_http_status=429,
                provider_attempt_count=3,
                provider_retryable=True,
            )
        ],
        expert_traces=[],
        specialist_trace=[],
    )

    metadata = event["safe_metadata"]
    assert event["status"] == "failed"
    assert metadata["provider_error_category"] == "rate_limit"
    assert metadata["provider_http_status"] == 429
    assert metadata["provider_attempt_count"] == 3
    assert metadata["provider_retryable"] is True


def test_configured_cost_rejects_untrusted_prices_and_unobserved_calls():
    event = build_cdi_telemetry_event(
        stage_traces=[_stage()],
        expert_traces=[],
        specialist_trace=[],
    )

    assert build_configured_cny_cost(
        event,
        input_price_per_1m=float("inf"),
        output_price_per_1m=1.0,
    ) == {}
    assert build_configured_cny_cost(
        {"safe_metadata": {"input_tokens": 10, "output_tokens": 2}},
        input_price_per_1m=1.0,
        output_price_per_1m=1.0,
    ) == {}


def test_cdi_non_ascii_model_identifier_is_omitted():
    metadata = build_cdi_telemetry_event(
        stage_traces=[_stage(model="模型正文")],
        expert_traces=[],
        specialist_trace=[],
    )["safe_metadata"]

    assert metadata["model_provider"] == "deepseek"
    assert "model_name" not in metadata


def test_medical_coding_shared_dispatch_persists_attributed_telemetry(monkeypatch):
    from app.coding_runtime.base import CodingResult
    from app.icoder.agent_runtime import a2a_facade

    result = CodingResult(
        codes=[],
        runtime_mode="corti_like_fast",
        latency_ms=12,
        llm_provider="deepseek",
        run_id="run-medical-telemetry",
        trace_id="trace-medical-telemetry",
        cost={
            "currency": "USD",
            "amount": 0.001,
            "token_usage": {"input_tokens": 4, "output_tokens": 2},
        },
        raw_schema={"model": "deepseek-chat"},
        trace_events=[{"step": "llm_call", "status": "ok"}],
    )

    class Dispatcher:
        async def dispatch(self, request):
            assert request.run_id == "run-request"
            assert request.coding_system == "icd10cn"
            assert request.coding_systems == ("icd10cn", "icd9cm3")
            return result

    captured = []
    monkeypatch.setattr("app.coding_runtime.get_dispatcher", lambda: Dispatcher())
    monkeypatch.setattr(
        a2a_facade,
        "emit_trace_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    returned, run_id, trace_id = asyncio.run(
        a2a_facade.dispatch_medical_coding_fast(
            agent_id="medical-coding-agent",
            input_text="去标识化病历",
            extra=None,
            runtime_mode="corti_like_fast",
            include_trace=False,
            include_evidence=True,
            run_id="run-request",
            trace_id="trace-request",
            user_id="user-telemetry",
            tenant_id="org-telemetry",
        )
    )

    assert returned is result
    assert run_id == "run-medical-telemetry"
    assert trace_id == "trace-medical-telemetry"
    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args == ("run-medical-telemetry", "output_generated")
    assert kwargs["status"] == "ok"
    metadata = kwargs["safe_metadata"]
    assert metadata["model_name"] == "deepseek-chat"
    assert metadata["total_tokens"] == 6
    assert metadata["_trace_id"] == "trace-medical-telemetry"
    assert metadata["_organization_id"] == "org-telemetry"
    assert metadata["_user_id"] == "user-telemetry"


def test_medical_coding_shared_dispatch_accepts_only_supported_explicit_subset(
    monkeypatch,
):
    from app.coding_runtime.base import CodingResult
    from app.icoder.agent_runtime import a2a_facade

    captured_requests = []

    class Dispatcher:
        async def dispatch(self, request):
            captured_requests.append(request)
            return CodingResult(
                codes=[],
                runtime_mode="corti_like_fast",
                run_id=request.run_id,
                trace_id="trace-result",
            )

    monkeypatch.setattr("app.coding_runtime.get_dispatcher", lambda: Dispatcher())
    monkeypatch.setattr(a2a_facade, "emit_trace_event", lambda *args, **kwargs: None)

    asyncio.run(a2a_facade.dispatch_medical_coding_fast(
        agent_id="medical-coding-agent",
        input_text="去标识化病历",
        extra={"coding_systems": ["icd9cm3", "unsupported", "icd9cm3"]},
        runtime_mode="corti_like_fast",
        include_trace=False,
        include_evidence=True,
        run_id="run-subset",
        trace_id="trace-request",
    ))

    assert captured_requests[0].coding_system == "icd9cm3"
    assert captured_requests[0].coding_systems == ("icd9cm3",)
