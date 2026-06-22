"""T4 — Prometheus-style metrics (SPEC §8.1)."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.orchestrator.metrics import (
    InMemoryBackend,
    OrchestratorMetrics,
    get_metrics,
    reset_default_metrics,
)


# ---------------------------------------------------------------------------
# InMemoryBackend
# ---------------------------------------------------------------------------


def test_backend_counter_inc_default_amount():
    b = InMemoryBackend()
    c = b.counter("c1", "help", ())
    c.inc()
    c.inc()
    assert c.value() == 2.0


def test_backend_counter_inc_with_amount():
    b = InMemoryBackend()
    c = b.counter("c1", "help", ())
    c.inc(amount=3.5)
    assert c.value() == 3.5


def test_backend_counter_labeled_keys_isolated():
    b = InMemoryBackend()
    c = b.counter("c1", "help", ("agent_id", "status"))
    c.inc(labels={"agent_id": "a", "status": "success"})
    c.inc(labels={"agent_id": "a", "status": "failed"})
    c.inc(2, labels={"agent_id": "a", "status": "success"})
    assert c.value(labels={"agent_id": "a", "status": "success"}) == 3.0
    assert c.value(labels={"agent_id": "a", "status": "failed"}) == 1.0
    assert c.value(labels={"agent_id": "b", "status": "success"}) == 0.0


def test_backend_counter_thread_safe():
    import threading

    b = InMemoryBackend()
    c = b.counter("c1", "help", ())

    def _hammer(n):
        for _ in range(n):
            c.inc()

    threads = [threading.Thread(target=_hammer, args=(1000,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert c.value() == 8000.0


def test_backend_counter_returns_same_instance():
    b = InMemoryBackend()
    a = b.counter("c1", "h", ())
    b.counter("c1", "h", ()).inc()
    assert a is b.counter("c1", "h", ())
    assert a.value() == 1.0


def test_backend_counter_snapshot():
    b = InMemoryBackend()
    c = b.counter("c1", "h", ("k",))
    c.inc(labels={"k": "x"})
    c.inc(labels={"k": "y"})
    snap = c.snapshot()
    assert ("x",) in snap
    assert ("y",) in snap


def test_backend_histogram_observe_count_and_sum():
    b = InMemoryBackend()
    h = b.histogram("h1", "help", ("expert_id",))
    h.observe(0.1, labels={"expert_id": "e1"})
    h.observe(0.5, labels={"expert_id": "e1"})
    assert h.count(labels={"expert_id": "e1"}) == 2
    assert abs(h.sum(labels={"expert_id": "e1"}) - 0.6) < 1e-9
    assert h.count() == 0  # unlabeled query returns default key, which is 0


def test_backend_histogram_labeled_keys_isolated():
    b = InMemoryBackend()
    h = b.histogram("h1", "help", ("expert_id",))
    h.observe(0.2, labels={"expert_id": "a"})
    h.observe(0.3, labels={"expert_id": "b"})
    assert h.count(labels={"expert_id": "a"}) == 1
    assert h.count(labels={"expert_id": "b"}) == 1


def test_backend_reset_clears_all_metrics():
    b = InMemoryBackend()
    c = b.counter("c", "h", ())
    h = b.histogram("h", "h", ())
    c.inc()
    h.observe(1.0)
    b.reset()
    assert c.value() == 0.0
    assert h.count() == 0


# ---------------------------------------------------------------------------
# OrchestratorMetrics — 8 metrics wired
# ---------------------------------------------------------------------------


def test_metrics_build_creates_eight():
    m = OrchestratorMetrics.build()
    # 5 counters
    assert m.runs_total is not None
    assert m.state_transitions_total is not None
    assert m.expert_invocations_total is not None
    assert m.phi_entities_redacted_total is not None
    assert m.planning_llm_calls_total is not None
    # 3 histograms
    assert m.run_duration_seconds is not None
    assert m.expert_duration_seconds is not None
    assert m.planning_llm_duration_seconds is not None


def test_metrics_use_injected_backend():
    backend = InMemoryBackend()
    m = OrchestratorMetrics.build(backend=backend)
    m.runs_total.inc(labels={"agent_id": "a", "status": "success"})
    # Same backend → same counter → same value
    assert backend.counter(
        "orchestrator_runs_total", "", ("agent_id", "status")
    ).value(labels={"agent_id": "a", "status": "success"}) == 1.0


def test_metrics_build_with_no_backend_uses_default_inmemory():
    m = OrchestratorMetrics.build()
    assert isinstance(m.backend, InMemoryBackend)


# ---------------------------------------------------------------------------
# End-to-end flows (exercise the 8 metrics)
# ---------------------------------------------------------------------------


def test_full_happy_path_increments_runs_total():
    m = OrchestratorMetrics.build()
    m.runs_total.inc(labels={"agent_id": "coding", "status": "success"})
    m.runs_total.inc(labels={"agent_id": "coding", "status": "success"})
    m.runs_total.inc(labels={"agent_id": "coding", "status": "failed"})
    assert (
        m.runs_total.value(labels={"agent_id": "coding", "status": "success"}) == 2.0
    )
    assert (
        m.runs_total.value(labels={"agent_id": "coding", "status": "failed"}) == 1.0
    )


def test_state_transition_counter_records_each_hop():
    m = OrchestratorMetrics.build()
    m.state_transitions_total.inc(labels={"from_state": "received", "to_state": "planning"})
    m.state_transitions_total.inc(labels={"from_state": "planning", "to_state": "delegating"})
    assert (
        m.state_transitions_total.value(
            labels={"from_state": "received", "to_state": "planning"}
        )
        == 1.0
    )


def test_expert_invocation_counter_tracks_outcomes():
    m = OrchestratorMetrics.build()
    m.expert_invocations_total.inc(labels={"expert_id": "coding", "result": "success"})
    m.expert_invocations_total.inc(labels={"expert_id": "coding", "result": "failed"})
    m.expert_invocations_total.inc(labels={"expert_id": "drg", "result": "success"})
    assert (
        m.expert_invocations_total.value(
            labels={"expert_id": "coding", "result": "success"}
        )
        == 1.0
    )
    assert (
        m.expert_invocations_total.value(
            labels={"expert_id": "drg", "result": "success"}
        )
        == 1.0
    )


def test_phi_counter_tracks_entity_types():
    m = OrchestratorMetrics.build()
    m.phi_entities_redacted_total.inc(labels={"entity_type": "NAME"})
    m.phi_entities_redacted_total.inc(labels={"entity_type": "NAME"})
    m.phi_entities_redacted_total.inc(labels={"entity_type": "PHONE"})
    assert m.phi_entities_redacted_total.value(labels={"entity_type": "NAME"}) == 2.0
    assert m.phi_entities_redacted_total.value(labels={"entity_type": "PHONE"}) == 1.0
    assert m.phi_entities_redacted_total.value(labels={"entity_type": "ID_CARD"}) == 0.0


def test_run_duration_histogram_observes():
    m = OrchestratorMetrics.build()
    m.run_duration_seconds.observe(1.5, labels={"agent_id": "a", "terminal_state": "completed"})
    m.run_duration_seconds.observe(0.7, labels={"agent_id": "a", "terminal_state": "completed"})
    assert (
        m.run_duration_seconds.count(
            labels={"agent_id": "a", "terminal_state": "completed"}
        )
        == 2
    )
    assert (
        abs(
            m.run_duration_seconds.sum(
                labels={"agent_id": "a", "terminal_state": "completed"}
            )
            - 2.2
        )
        < 1e-9
    )


def test_expert_duration_histogram_observes():
    m = OrchestratorMetrics.build()
    m.expert_duration_seconds.observe(0.05, labels={"expert_id": "coding"})
    m.expert_duration_seconds.observe(0.15, labels={"expert_id": "coding"})
    assert m.expert_duration_seconds.count(labels={"expert_id": "coding"}) == 2


def test_planning_llm_call_counter():
    m = OrchestratorMetrics.build()
    m.planning_llm_calls_total.inc(labels={"model": "deepseek-v4", "result": "success"})
    m.planning_llm_calls_total.inc(labels={"model": "deepseek-v4", "result": "failed"})
    assert (
        m.planning_llm_calls_total.value(
            labels={"model": "deepseek-v4", "result": "success"}
        )
        == 1.0
    )


def test_planning_llm_duration_histogram():
    m = OrchestratorMetrics.build()
    m.planning_llm_duration_seconds.observe(2.3, labels={"model": "deepseek-v4"})
    assert (
        m.planning_llm_duration_seconds.count(labels={"model": "deepseek-v4"}) == 1
    )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


def test_get_metrics_returns_singleton():
    reset_default_metrics()
    a = get_metrics()
    b = get_metrics()
    assert a is b


def test_reset_default_metrics_drops_cache():
    reset_default_metrics()
    a = get_metrics()
    reset_default_metrics()
    b = get_metrics()
    assert a is not b