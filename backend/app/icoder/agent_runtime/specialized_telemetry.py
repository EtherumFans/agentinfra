"""Minimum-necessary telemetry for dedicated clinical Agent runtimes.

Provider Registry backends emit their metadata directly.  Medical Coding and
CDI use dedicated runtime envelopes, so their already-captured accounting must
be normalized into the same RunTrace shape before the API persists it.  This
module never receives prompts, chart text, model output, evidence, or tool
arguments/results.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    build_backend_safe_metadata,
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if 0 <= result <= 100_000_000 else None


def _usage_value(usage: Mapping[str, Any], *names: str) -> int | None:
    for name in names:
        if name in usage:
            return _count(usage.get(name))
    return None


def _identifier(value: Any, *, limit: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        return ""
    return text if all(
        ch.isascii() and (ch.isalnum() or ch in "._:/@+-") for ch in text
    ) else ""


def _inline_event(metadata: dict[str, Any]) -> dict[str, Any]:
    failed = str(metadata.get("provider_status") or "").lower() in {
        "fail", "failed", "error", "degraded", "unavailable",
    }
    return {
        "step": RunTraceStep.OUTPUT_GENERATED,
        "status": RunTraceStatus.FAILED if failed else RunTraceStatus.OK,
        # Dedicated orchestrators can contain overlapping provider calls. The
        # event duration is wall time; provider_latency_ms remains the sum of
        # observed call durations for accounting/diagnostics.
        "duration_ms": metadata.get(
            "orchestration_latency_ms",
            metadata.get("provider_latency_ms", 0),
        ),
        "safe_metadata": metadata,
    }


def build_configured_cny_cost(
    telemetry_event: Mapping[str, Any] | None,
    *,
    input_price_per_1m: Any,
    output_price_per_1m: Any,
) -> dict[str, Any]:
    """Build a truthful config-priced CNY estimate from observed usage only.

    Dedicated runtimes must not infer token counts from clinical text or label a
    local price-table estimate as a provider invoice.  An empty mapping means
    that complete observed usage was unavailable and callers must preserve an
    unknown-cost state.
    """

    event = _mapping(telemetry_event)
    metadata = _mapping(event.get("safe_metadata"))
    input_tokens = _count(metadata.get("input_tokens"))
    output_tokens = _count(metadata.get("output_tokens"))
    call_count = _count(metadata.get("llm_call_count"))
    if (
        input_tokens is None
        or output_tokens is None
        or call_count is None
        or call_count <= 0
        or not str(metadata.get("model_provider") or "").strip()
    ):
        return {}
    if isinstance(input_price_per_1m, bool) or isinstance(output_price_per_1m, bool):
        return {}
    try:
        input_price = float(input_price_per_1m)
        output_price = float(output_price_per_1m)
    except (TypeError, ValueError, OverflowError):
        return {}
    if (
        not math.isfinite(input_price)
        or not math.isfinite(output_price)
        or input_price < 0
        or output_price < 0
    ):
        return {}
    amount = (
        input_tokens * input_price + output_tokens * output_price
    ) / 1_000_000.0
    if not math.isfinite(amount) or amount < 0 or amount > 1_000_000:
        return {}
    return {
        "amount": round(amount, 8),
        "currency": "CNY",
        "source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }


def build_medical_coding_telemetry_event(
    result: Any,
    *,
    output_contract: str = "",
) -> dict[str, Any]:
    """Build one LLM span from a completed dedicated coding runtime result.

    Token and model values are emitted only when the runtime actually carried
    them.  In particular, the fail-closed mock envelope never becomes a fake
    model invocation and a CNY/internal-credit amount is never mislabeled as
    OpenInference's USD cost attribute.
    """

    raw_schema = _mapping(_value(result, "raw_schema", {}))
    cost = _mapping(_value(result, "cost", {}))
    usage = _mapping(cost.get("token_usage")) or _mapping(
        raw_schema.get("token_usage")
    )
    input_tokens = _usage_value(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_value(
        usage, "output_tokens", "completion_tokens"
    )
    total_tokens = _usage_value(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    trace_events = list(_value(result, "trace_events", []) or [])
    llm_events = [
        event for event in trace_events
        if isinstance(event, Mapping) and str(event.get("step") or "") == "llm_call"
    ]
    model_name = str(raw_schema.get("model") or "")
    if not model_name:
        for event in reversed(llm_events):
            event_metadata = _mapping(
                event.get("metadata") or event.get("safe_metadata")
            )
            if event_metadata.get("model"):
                model_name = str(event_metadata["model"])
                break

    degraded = bool(_value(result, "degraded", False))
    errored = bool(_value(result, "error", False))
    provider = str(_value(result, "llm_provider", "") or "")
    has_observed_model_call = bool(
        llm_events or model_name or usage
        or (
            str(cost.get("currency") or "").upper() == "USD"
            and cost.get("amount") is not None
        )
    )
    if provider.lower() == "mock" or degraded or not has_observed_model_call:
        provider = ""
        model_name = ""
        input_tokens = None
        output_tokens = None
        total_tokens = None
        llm_events = []

    model_cost_usd: float | None = None
    if not degraded and provider and str(cost.get("currency") or "").upper() == "USD":
        try:
            model_cost_usd = float(cost.get("amount"))
        except (TypeError, ValueError, OverflowError):
            model_cost_usd = None

    metadata = build_backend_safe_metadata(
        backend_provider="medical_coding_runtime",
        backend_type="medical_coding",
        provider_latency_ms=int(_value(result, "latency_ms", 0) or 0),
        provider_status=("degraded" if degraded else "fail" if errored else "complete"),
        provider_deterministic=False,
        supports_tool_calling=False,
        fallback_used=degraded,
        output_contract=output_contract,
        model_provider=provider,
        model_system=provider,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        model_cost_usd=model_cost_usd,
        llm_call_count=len(llm_events) if llm_events else None,
    )
    return _inline_event(metadata)


def build_cdi_telemetry_event(
    *,
    stage_traces: Iterable[Any],
    expert_traces: Iterable[Any],
    specialist_trace: Iterable[Any],
    safety_gate_traces: Iterable[Any] = (),
    stage_duration_ms: Mapping[str, Any] | None = None,
    orchestration_latency_ms: Any = None,
    latency_budget_ms: Any = None,
    gate_max_concurrency: Any = None,
    output_contract: str = "",
    degraded_safety_gates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate actual CDI LLM attempts into one bounded parent LLM span."""

    stages = list(stage_traces)
    experts = list(expert_traces)
    safety_calls = list(safety_gate_traces)
    specialist_modes = {
        str(_value(item, "expert_id", "") or ""): str(
            _value(item, "execution_mode", "") or ""
        )
        for item in specialist_trace
        if _value(item, "expert_id", "")
    }
    invoked_modes = {"REAL_TOOL", "LLM_KNOWLEDGE_ONLY", "DEGRADED"}
    actual_experts = []
    for trace in experts:
        expert_id = str(_value(trace, "expert_id", "") or "")
        mode = specialist_modes.get(expert_id, "")
        has_observed_usage = any(
            (_count(_value(trace, name, 0)) or 0) > 0
            for name in ("prompt_tokens", "completion_tokens", "total_tokens")
        )
        if (
            mode in invoked_modes
            or bool(_value(trace, "degraded", False))
            or has_observed_usage
        ):
            actual_experts.append(trace)
    calls = stages + actual_experts + safety_calls

    provider_values = [str(_value(trace, "provider", "") or "") for trace in calls]
    model_values = [str(_value(trace, "model", "") or "") for trace in calls]
    providers = set(provider_values)
    models = set(model_values)
    provider = (
        next(iter(providers)) if calls and len(providers) == 1 and "" not in providers
        else "mixed" if calls and len(providers) > 1 and "" not in providers
        else ""
    )
    model = (
        next(iter(models)) if calls and len(models) == 1 and "" not in models
        else "mixed" if calls and len(models) > 1 and "" not in models
        else ""
    )

    token_rows: list[tuple[int, int, int]] = []
    complete_usage = bool(calls)
    for trace in calls:
        prompt = _count(_value(trace, "prompt_tokens", None))
        completion = _count(_value(trace, "completion_tokens", None))
        total = _count(_value(trace, "total_tokens", None))
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        # StageTrace defaults missing accounting to all-zero.  Treat that as
        # unknown rather than silently undercounting an aggregate.
        if prompt is None or completion is None or total is None or total == 0:
            complete_usage = False
            break
        token_rows.append((prompt, completion, total))
    input_tokens = sum(row[0] for row in token_rows) if complete_usage else None
    output_tokens = sum(row[1] for row in token_rows) if complete_usage else None
    total_tokens = sum(row[2] for row in token_rows) if complete_usage else None

    degraded = bool(degraded_safety_gates) or any(
        bool(_value(trace, "degraded", False)) for trace in calls
    )
    failed_calls = [trace for trace in calls if bool(_value(trace, "degraded", False))]
    error_categories = {
        _identifier(_value(trace, "provider_error_category", ""))
        for trace in failed_calls
        if _identifier(_value(trace, "provider_error_category", ""))
    }
    error_statuses = {
        _count(_value(trace, "provider_http_status", None))
        for trace in failed_calls
        if _count(_value(trace, "provider_http_status", None)) is not None
    }
    attempt_counts = [
        _count(_value(trace, "provider_attempt_count", None))
        for trace in failed_calls
    ]
    attempt_counts = [value for value in attempt_counts if value is not None]
    retryable_values = [
        _value(trace, "provider_retryable", None) for trace in failed_calls
    ]
    retryable_values = [
        value for value in retryable_values if isinstance(value, bool)
    ]
    latency_ms = sum(
        max(_count(_value(trace, "latency_ms", 0)) or 0, 0)
        for trace in calls
    )
    metadata = build_backend_safe_metadata(
        backend_provider="cdi_real_orchestrator",
        backend_type="cdi_orchestrator",
        provider_latency_ms=latency_ms,
        provider_status="degraded" if degraded else "complete",
        provider_deterministic=False,
        supports_tool_calling=bool(actual_experts),
        fallback_used=False,
        output_contract=output_contract,
        tool_rounds=len(actual_experts),
        model_provider=provider,
        model_system=provider,
        model_name=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        llm_call_count=len(calls) if calls else None,
        provider_error_category=(
            next(iter(error_categories)) if len(error_categories) == 1
            else "mixed" if len(error_categories) > 1 else ""
        ),
        provider_http_status=(
            next(iter(error_statuses)) if len(error_statuses) == 1 else None
        ),
        provider_attempt_count=(sum(attempt_counts) if attempt_counts else None),
        provider_retryable=(
            all(retryable_values) if retryable_values else None
        ),
    )
    durations = {
        _identifier(stage): _count(duration)
        for stage, duration in dict(stage_duration_ms or {}).items()
    }
    durations = {
        stage: duration
        for stage, duration in durations.items()
        if stage and duration is not None
    }
    instrumented_stage_latency_ms = sum(durations.values())
    orchestration_latency = _count(orchestration_latency_ms)
    latency_budget = _count(latency_budget_ms)
    configured_gate_concurrency = _count(gate_max_concurrency)
    safety_stage_counts: dict[str, int] = {}
    for trace in safety_calls:
        stage = _identifier(_value(trace, "stage", ""))
        if stage:
            safety_stage_counts[stage] = safety_stage_counts.get(stage, 0) + 1
    parallel_model_calls_observed = bool(
        orchestration_latency is not None
        and latency_ms > orchestration_latency
    ) or bool(
        configured_gate_concurrency is not None
        and configured_gate_concurrency > 1
        and any(count > 1 for count in safety_stage_counts.values())
    )
    metadata["model_call_latency_sum_ms"] = latency_ms
    metadata["parallel_model_calls_observed"] = parallel_model_calls_observed
    if orchestration_latency is not None:
        metadata["orchestration_latency_ms"] = orchestration_latency
        metadata["provider_latency_exceeds_wall_time"] = bool(
            latency_ms > orchestration_latency
        )
        metadata["non_provider_wall_latency_known"] = bool(
            not parallel_model_calls_observed
            and latency_ms <= orchestration_latency
        )
        if metadata["non_provider_wall_latency_known"]:
            metadata["non_provider_wall_latency_ms"] = (
                orchestration_latency - latency_ms
            )
    if durations:
        slowest_stage, slowest_latency = max(
            durations.items(),
            key=lambda item: (item[1], item[0]),
        )
        metadata.update({
            "instrumented_stage_latency_ms": instrumented_stage_latency_ms,
            "slowest_stage": slowest_stage,
            "slowest_stage_latency_ms": slowest_latency,
        })
    if latency_budget is not None and latency_budget > 0:
        metadata["latency_budget_ms"] = latency_budget
        metadata["latency_budget_exceeded"] = bool(
            orchestration_latency is not None
            and orchestration_latency > latency_budget
        )
    return _inline_event(metadata)


__all__ = [
    "build_configured_cny_cost",
    "build_cdi_telemetry_event",
    "build_medical_coding_telemetry_event",
]
