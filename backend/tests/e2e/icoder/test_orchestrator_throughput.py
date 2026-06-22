"""T10 — Orchestrator throughput smoke (SPEC §11.5).

Drives 100 sequential ``InboundHandler.handle()`` calls against the
scripted test doubles (no real LLM, no real MedCodER) and reports
P50/P95/P99 wall-clock per call.

Purpose:
  - Catch latency regressions as the orchestrator grows new stages.
  - Phase 1 budgets: P95 < 500 ms / call on warm scripted doubles.
  - Phase 2 budgets (with real MedCodER): TBD after warmup.

Skip rules:
  - Always runs (uses scripted doubles — no env var needed).
  - Set ``ICODER_RUN_STRESS=1`` to opt in; otherwise ``SKIPPED`` so CI
    doesn't run 100 calls on every PR.

Reports are written to stdout as JSON so the result is greppable.
"""

from __future__ import annotations

import json
import os
import statistics
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
)


@dataclass
class _Agent:
    id: str = "medical-coding-agent"
    name: str = "Medical Coding Agent"
    expert_ids: list[str] = field(default_factory=lambda: ["coding-expert"])
    config: dict = field(default_factory=dict)


def _good_plan_json():
    return json.dumps(
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
            "reason": "throughput",
        }
    )


def _build_scripted_handler():
    """Build a fully-scripted InboundHandler — no I/O, deterministic."""
    from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig
    from app.icoder.agent_runtime.orchestrator.delegator import (
        DelegatorConfig,
    )

    def _llm(_sys, _user):
        return {"content": _good_plan_json(), "model": "fake", "latency_ms": 0}

    def _invoker(invocation):
        return {"echo": invocation.subtask_input}

    planner = Planner(llm_call=_llm, config=PlannerConfig())
    delegator = Delegator(invoker=_invoker, config=DelegatorConfig())
    aggregator = Aggregator()
    provider = DictAgentProvider({"medical-coding-agent": _Agent()})
    return InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=aggregator,
        agent_provider=provider,
    )


@pytest.mark.skipif(
    os.environ.get("ICODER_RUN_STRESS") != "1",
    reason="ICODER_RUN_STRESS=1 not set — skipping throughput smoke",
)
def test_orchestrator_100_sequential_calls_latency():
    """100 sequential handler.handle() calls — measure P50/P95/P99."""
    handler = _build_scripted_handler()
    req_template = lambda i: InboundRequest(  # noqa: E731
        message=InboundMessage(
            role="user",
            parts=[{"kind": "text", "text": f"病历 {i} 张三 胸痛"}],
            interaction_id=f"throughput-{i}",
        )
    )

    durations_ms: list[float] = []
    # Warm-up (JIT / page-cache style)
    handler.handle("medical-coding-agent", req_template(-1))

    for i in range(100):
        t0 = time.monotonic()
        resp = handler.handle("medical-coding-agent", req_template(i))
        dt = (time.monotonic() - t0) * 1000.0
        assert resp.kind == "message", f"call {i} failed: {resp.error}"
        durations_ms.append(dt)

    p50 = statistics.median(durations_ms)
    p95 = statistics.quantiles(durations_ms, n=20)[18]  # 95th percentile
    p99 = statistics.quantiles(durations_ms, n=100)[98] if len(durations_ms) >= 100 else max(durations_ms)

    report = {
        "n": len(durations_ms),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "max_ms": round(max(durations_ms), 3),
        "min_ms": round(min(durations_ms), 3),
    }
    # Surface the report so CI logs capture it.
    print(f"\n[orchestrator_throughput] {json.dumps(report)}")

    # Sanity: scripted doubles should not exceed 500 ms at P95 on CI.
    # Local dev: usually < 50 ms. Generous bound to avoid flakes.
    assert p95 < 500.0, f"P95 latency too high: {p95:.2f}ms"
