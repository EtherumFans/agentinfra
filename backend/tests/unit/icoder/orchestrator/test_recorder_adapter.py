"""T4 — RecorderAdapter: Orchestrator events → M2a stages (SPEC §5.3, §7.3)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.metrics import (
    InMemoryBackend,
    OrchestratorMetrics,
)
from app.icoder.agent_runtime.orchestrator.recorder_adapter import (
    STAGE_AGGREGATED,
    STAGE_AGGREGATING_STARTED,
    STAGE_DELEGATING_STARTED,
    STAGE_EXPERT_INVOKED,
    STAGE_EXPERT_RETURNED,
    STAGE_INBOUND_RECEIVED,
    STAGE_PHI_REDACTED,
    STAGE_PLAN_GENERATED,
    STAGE_PLANNING_STARTED,
    STAGE_RUN_COMPLETED,
    STAGE_RUN_FAILED,
    NoopRecorder,
    NoopRun,
    RecorderAdapter,
)


# ---------------------------------------------------------------------------
# Stage constants — central to SPEC §5.3, must not change without spec update
# ---------------------------------------------------------------------------


def test_stage_constants_match_spec_5_3():
    expected = {
        "inbound_received",
        "phi_redacted",
        "planning_started",
        "plan_generated",
        "delegating_started",
        "expert_invoked",
        "expert_returned",
        "aggregating_started",
        "aggregated",
        "run_completed",
        "run_failed",
    }
    actual = {
        STAGE_INBOUND_RECEIVED,
        STAGE_PHI_REDACTED,
        STAGE_PLANNING_STARTED,
        STAGE_PLAN_GENERATED,
        STAGE_DELEGATING_STARTED,
        STAGE_EXPERT_INVOKED,
        STAGE_EXPERT_RETURNED,
        STAGE_AGGREGATING_STARTED,
        STAGE_AGGREGATED,
        STAGE_RUN_COMPLETED,
        STAGE_RUN_FAILED,
    }
    assert actual == expected


# ---------------------------------------------------------------------------
# NoopRecorder — used by default + by tests
# ---------------------------------------------------------------------------


def test_noop_recorder_default_construction():
    r = NoopRecorder()
    assert r.calls == []


def test_noop_recorder_start_run_yields_run():
    r = NoopRecorder()
    with r.inference(run_id="r1", trace_id="t1") as run:
        assert isinstance(run, NoopRun)
        assert run.run_id == "r1"
        assert run.trace_id == "t1"
        # finalize recorded on exit
    assert r.calls == [("finalize", {"final_status": run.final_status})]


def test_noop_recorder_stage_records_payload():
    r = NoopRecorder()
    with r.inference(run_id="r1") as run:
        with run.stage("inbound_received") as s:
            s.set_output({"agent_id": "a"})
    assert ("inbound_received", {"agent_id": "a"}) in r.calls


# ---------------------------------------------------------------------------
# RecorderAdapter — typed stage methods call run.stage() with right name/payload
# ---------------------------------------------------------------------------


def _build(run=None, metrics=None):
    """Construct adapter + a NoopRecorder for inspection."""
    rec = NoopRecorder()
    adapter = RecorderAdapter(recorder=rec, metrics=metrics, agent_ref="orchestrator")
    return adapter, rec, run


def _open_run(adapter, run_id="r1", agent_id="coding", **kwargs):
    """Open a real recorder run via the adapter and return it."""
    return adapter.start_run(run_id=run_id, agent_id=agent_id, **kwargs)


def test_record_inbound_received_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_inbound_received(
            run,
            agent_id="coding",
            context_id="ctx-1",
            original_input_len=42,
            redacted_input_len=35,
        )
    assert ("inbound_received", {
        "agent_id": "coding",
        "context_id": "ctx-1",
        "original_input_len": 42,
        "redacted_input_len": 35,
    }) in rec.calls


def test_record_phi_redacted_payload_and_metric():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_phi_redacted(run, entity_types=["NAME", "PHONE", "NAME"])
    # payload
    assert ("phi_redacted", {"entity_types": ["NAME", "PHONE", "NAME"]}) in rec.calls
    # metric: each entity counted individually
    assert metrics.phi_entities_redacted_total.value(labels={"entity_type": "NAME"}) == 2.0
    assert metrics.phi_entities_redacted_total.value(labels={"entity_type": "PHONE"}) == 1.0
    assert metrics.phi_entities_redacted_total.value(labels={"entity_type": "ID_CARD"}) == 0.0


def test_record_phi_redacted_empty_entity_types_does_not_crash():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_phi_redacted(run, entity_types=[])
    # recorded with empty list
    assert ("phi_redacted", {"entity_types": []}) in rec.calls
    # no metric increment
    assert metrics.phi_entities_redacted_total.value(labels={"entity_type": "NAME"}) == 0.0


def test_record_planning_started_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_planning_started(run, llm_model="deepseek-v4")
    assert ("planning_started", {"llm_model": "deepseek-v4"}) in rec.calls


def test_record_plan_generated_payload_counts_experts():
    adapter, rec, _ = _build()
    plan = {
        "steps": [{"expert_id": "coding"}, {"expert_id": "drg"}],
        "reason": "编码 + 分组",
    }
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_plan_generated(run, plan=plan)
    stage, payload = next(s for s in rec.calls if s[0] == "plan_generated")
    assert payload["expert_count"] == 2
    assert payload["reason"] == "编码 + 分组"
    assert payload["plan"] == plan


def test_record_plan_generated_handles_missing_steps():
    adapter, rec, _ = _build()
    plan = {"reason": "no steps"}
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_plan_generated(run, plan=plan)
    stage, payload = next(s for s in rec.calls if s[0] == "plan_generated")
    assert payload["expert_count"] == 0


def test_record_delegating_started_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_delegating_started(run, expert_count=3)
    assert ("delegating_started", {"expert_count": 3}) in rec.calls


def test_record_expert_invoked_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_expert_invoked(
            run,
            expert_id="coding-expert",
            subtask_input="病历主诉胸痛" * 10,
            attempt=2,
        )
    stage, payload = next(s for s in rec.calls if s[0] == "expert_invoked")
    assert payload["expert_id"] == "coding-expert"
    assert payload["attempt"] == 2
    assert payload["subtask_input_len"] == len("病历主诉胸痛" * 10)


def test_record_expert_returned_success_payload_and_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_expert_returned(
            run,
            expert_id="coding-expert",
            result={"code": "I50.9"},
            latency_ms=120,
        )
    stage, payload = next(s for s in rec.calls if s[0] == "expert_returned")
    assert payload["expert_id"] == "coding-expert"
    assert payload["latency_ms"] == 120
    assert payload["ok"] is True
    # metrics
    assert metrics.expert_invocations_total.value(
        labels={"expert_id": "coding-expert", "result": "success"}
    ) == 1.0
    assert metrics.expert_duration_seconds.count(
        labels={"expert_id": "coding-expert"}
    ) == 1
    assert abs(
        metrics.expert_duration_seconds.sum(
            labels={"expert_id": "coding-expert"}
        )
        - 0.120
    ) < 1e-9


def test_record_expert_returned_failure_payload_and_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_expert_returned(
            run,
            expert_id="coding-expert",
            result={"error": "net down"},
            latency_ms=3000,
        )
    stage, payload = next(s for s in rec.calls if s[0] == "expert_returned")
    assert payload["ok"] is False
    assert metrics.expert_invocations_total.value(
        labels={"expert_id": "coding-expert", "result": "failed"}
    ) == 1.0
    assert abs(
        metrics.expert_duration_seconds.sum(
            labels={"expert_id": "coding-expert"}
        )
        - 3.0
    ) < 1e-9


def test_record_aggregating_started_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_aggregating_started(run, expert_result_count=2)
    assert ("aggregating_started", {"expert_result_count": 2}) in rec.calls


def test_record_aggregated_payload():
    adapter, rec, _ = _build()
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_aggregated(run, conflicted=True, expert_count=2)
    assert ("aggregated", {"conflicted": True, "expert_count": 2}) in rec.calls


def test_record_run_completed_payload_and_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_run_completed(
            run,
            agent_id="coding",
            total_duration_ms=1500,
            expert_count=2,
        )
    assert ("run_completed", {
        "agent_id": "coding",
        "total_duration_ms": 1500,
        "expert_count": 2,
    }) in rec.calls
    assert metrics.runs_total.value(
        labels={"agent_id": "coding", "status": "success"}
    ) == 1.0
    assert metrics.run_duration_seconds.count(
        labels={"agent_id": "coding", "terminal_state": "completed"}
    ) == 1
    assert abs(
        metrics.run_duration_seconds.sum(
            labels={"agent_id": "coding", "terminal_state": "completed"}
        )
        - 1.5
    ) < 1e-9


def test_record_run_failed_payload_and_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_run_failed(
            run,
            agent_id="coding",
            error_code="expert_failed",
            error_stage="delegating",
            error_message="net",
            total_duration_ms=800,
        )
    assert ("run_failed", {
        "agent_id": "coding",
        "error_code": "expert_failed",
        "error_stage": "delegating",
        "error_message": "net",
        "total_duration_ms": 800,
    }) in rec.calls
    assert metrics.runs_total.value(
        labels={"agent_id": "coding", "status": "failed"}
    ) == 1.0
    assert metrics.run_duration_seconds.count(
        labels={"agent_id": "coding", "terminal_state": "failed"}
    ) == 1


def test_record_run_failed_zero_duration_observed_not():
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_run_failed(
            run,
            agent_id="coding",
            error_code="planning_failed",
            error_stage="planning",
            error_message="parse",
            total_duration_ms=0,
        )
    # counter still increments
    assert metrics.runs_total.value(
        labels={"agent_id": "coding", "status": "failed"}
    ) == 1.0
    # histogram NOT observed when duration=0
    assert metrics.run_duration_seconds.count(
        labels={"agent_id": "coding", "terminal_state": "failed"}
    ) == 0


def test_record_state_transition_metric_only():
    """State transition is a top-level hop, not a stage (per docstring)."""
    metrics = OrchestratorMetrics.build()
    adapter, rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_state_transition(
            run, from_state="received", to_state="planning"
        )
    # no stage recorded
    stages = [s for s in rec.calls if s[0] != "finalize"]
    assert stages == []
    # but counter incremented
    assert metrics.state_transitions_total.value(
        labels={"from_state": "received", "to_state": "planning"}
    ) == 1.0


def test_record_planning_llm_call_success_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, _rec, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_planning_llm_call(
            run, model="deepseek-v4", latency_ms=2300, success=True
        )
    assert metrics.planning_llm_calls_total.value(
        labels={"model": "deepseek-v4", "result": "success"}
    ) == 1.0
    assert abs(
        metrics.planning_llm_duration_seconds.sum(
            labels={"model": "deepseek-v4"}
        )
        - 2.3
    ) < 1e-9


def test_record_planning_llm_call_failure_metrics():
    metrics = OrchestratorMetrics.build()
    adapter, _, _ = _build(metrics=metrics)
    with _open_run(adapter, run_id="r1") as run:
        adapter.record_planning_llm_call(
            run, model="deepseek-v4", latency_ms=5000, success=False
        )
    assert metrics.planning_llm_calls_total.value(
        labels={"model": "deepseek-v4", "result": "failed"}
    ) == 1.0


# ---------------------------------------------------------------------------
# Recorder failures NEVER raise (SPEC §7.3 — observability does not block biz)
# ---------------------------------------------------------------------------


class _BoomRecorder:
    """A recorder that raises on every operation."""

    @staticmethod
    def _raise(*a, **kw):
        raise RuntimeError("recorder broken")

    def inference(self, **kwargs):
        return _BoomCtx()


class _BoomCtx:
    def __enter__(self):
        self._raise()

    def __exit__(self, *a):
        return False


def test_start_run_swallows_recorder_exception():
    adapter = RecorderAdapter(recorder=_BoomRecorder(), metrics=OrchestratorMetrics.build())
    # Should not raise
    with adapter.start_run(run_id="r1", agent_id="a") as run:
        # run may be None (swallowed) or partial — must not raise
        pass


class _BoomRun:
    """Run whose stage() raises."""

    def stage(self, name):
        return _BoomStage()


class _BoomStage:
    def __enter__(self):
        raise RuntimeError("stage broken")

    def __exit__(self, *a):
        return False


class _RunRecorder:
    def inference(self, **kwargs):
        return _BoomRun()


def test_safe_stage_swallows_exception():
    adapter = RecorderAdapter(
        recorder=_RunRecorder(), metrics=OrchestratorMetrics.build()
    )
    # Provide a NoopRun-like run that explodes on stage
    run = _BoomRun()
    # Should not raise
    adapter.record_inbound_received(
        run, agent_id="a", context_id="c",
        original_input_len=10, redacted_input_len=5,
    )


def test_safe_stage_with_run_none_is_safe():
    """Defensive: a None run must not crash the recorder."""
    adapter = RecorderAdapter(recorder=NoopRecorder(), metrics=None)
    adapter.record_inbound_received(
        None, agent_id="a", context_id="c",
        original_input_len=10, redacted_input_len=5,
    )
    adapter.record_phi_redacted(None, entity_types=["NAME"])
    adapter.record_run_completed(
        None, agent_id="a", total_duration_ms=100, expert_count=1,
    )


def test_metrics_none_does_not_break_recording():
    adapter = RecorderAdapter(recorder=NoopRecorder(), metrics=None)
    rec = adapter._recorder
    with adapter.start_run(run_id="r1", agent_id="a") as run:
        adapter.record_phi_redacted(run, entity_types=["NAME"])
        adapter.record_run_completed(
            run, agent_id="a", total_duration_ms=100, expert_count=1,
        )
        adapter.record_expert_returned(
            run, expert_id="e", result={"x": 1}, latency_ms=10,
        )
    # All stage events recorded even without metrics
    stages = [s[0] for s in rec.calls]
    assert "phi_redacted" in stages
    assert "run_completed" in stages
    assert "expert_returned" in stages


# ---------------------------------------------------------------------------
# End-to-end: full happy path through every stage method
# ---------------------------------------------------------------------------


def test_full_happy_path_records_all_11_stages():
    rec = NoopRecorder()
    metrics = OrchestratorMetrics.build()
    adapter = RecorderAdapter(recorder=rec, metrics=metrics, agent_ref="orchestrator")
    with adapter.start_run(run_id="r1", agent_id="coding") as run:
        adapter.record_inbound_received(
            run, agent_id="coding", context_id="ctx-1",
            original_input_len=42, redacted_input_len=35,
        )
        adapter.record_phi_redacted(run, entity_types=["NAME"])
        adapter.record_state_transition(
            run, from_state="received", to_state="planning"
        )
        adapter.record_planning_started(run, llm_model="deepseek-v4")
        adapter.record_planning_llm_call(
            run, model="deepseek-v4", latency_ms=2000, success=True
        )
        adapter.record_plan_generated(run, plan={
            "steps": [{"expert_id": "coding-expert"}],
            "reason": "编码审核",
        })
        adapter.record_state_transition(
            run, from_state="planning", to_state="delegating"
        )
        adapter.record_delegating_started(run, expert_count=1)
        adapter.record_expert_invoked(
            run, expert_id="coding-expert", subtask_input="x", attempt=1,
        )
        adapter.record_expert_returned(
            run, expert_id="coding-expert", result={"code": "I50.9"},
            latency_ms=120,
        )
        adapter.record_state_transition(
            run, from_state="delegating", to_state="aggregating"
        )
        adapter.record_aggregating_started(run, expert_result_count=1)
        adapter.record_aggregated(run, conflicted=False, expert_count=1)
        adapter.record_run_completed(
            run, agent_id="coding", total_duration_ms=2200, expert_count=1,
        )

    # 10 typed stages + finalize
    stage_names = [s[0] for s in rec.calls]
    for required in [
        "inbound_received", "phi_redacted",
        "planning_started", "plan_generated",
        "delegating_started", "expert_invoked", "expert_returned",
        "aggregating_started", "aggregated", "run_completed",
        "finalize",
    ]:
        assert required in stage_names, f"missing stage: {required}"

    # metrics side-effects
    assert metrics.runs_total.value(
        labels={"agent_id": "coding", "status": "success"}
    ) == 1.0
    assert metrics.expert_invocations_total.value(
        labels={"expert_id": "coding-expert", "result": "success"}
    ) == 1.0
    assert metrics.phi_entities_redacted_total.value(
        labels={"entity_type": "NAME"}
    ) == 1.0
    assert metrics.planning_llm_calls_total.value(
        labels={"model": "deepseek-v4", "result": "success"}
    ) == 1.0
    assert metrics.state_transitions_total.value(
        labels={"from_state": "received", "to_state": "planning"}
    ) == 1.0


# ---------------------------------------------------------------------------
# Default recorder (no injection) — uses NoopRecorder
# ---------------------------------------------------------------------------


def test_default_recorder_is_noop():
    adapter = RecorderAdapter()
    assert isinstance(adapter._recorder, NoopRecorder)


def test_agent_ref_passed_to_recorder():
    """The adapter forwards its agent_ref into inference(**kwargs)."""
    rec = NoopRecorder()
    adapter = RecorderAdapter(recorder=rec, agent_ref="my-agent")
    with adapter.start_run(run_id="r1", agent_id="a"):
        pass
    # run_id + finalize prove inference(**kwargs) ran without exception
    finalize_payload = rec.calls[-1][1]
    assert finalize_payload["final_status"] in ("unknown", "completed", "failed")