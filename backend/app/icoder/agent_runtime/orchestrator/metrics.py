"""Prometheus-style metrics for the Orchestrator (SPEC §8.1).

8 metrics are defined:

  - ``orchestrator_runs_total``              Counter    labels: agent_id, status
  - ``orchestrator_run_duration_seconds``    Histogram  labels: agent_id, terminal_state
  - ``orchestrator_state_transitions_total`` Counter    labels: from_state, to_state
  - ``orchestrator_expert_invocations_total`` Counter   labels: expert_id, result
  - ``orchestrator_expert_duration_seconds`` Histogram  labels: expert_id
  - ``orchestrator_phi_entities_redacted_total`` Counter labels: entity_type
  - ``orchestrator_planning_llm_calls_total`` Counter   labels: model, result
  - ``orchestrator_planning_llm_duration_seconds`` Histogram labels: model

Backend abstraction: ``MetricsBackend`` is an in-memory implementation with
the same shape as ``prometheus_client``. When ``prometheus_client`` is
installed in production, swap to a backend that delegates to its
``Counter`` / ``Histogram`` — the public API of this module does not change.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class _CounterProto(Protocol):
    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None: ...
    def value(self, labels: dict[str, str] | None = None) -> float: ...


class _HistogramProto(Protocol):
    def observe(self, value: float, labels: dict[str, str] | None = None) -> None: ...
    def count(self, labels: dict[str, str] | None = None) -> int: ...
    def sum(self, labels: dict[str, str] | None = None) -> float: ...


class MetricsBackend(Protocol):
    def counter(self, name: str, help: str, labelnames: tuple[str, ...]) -> _CounterProto: ...
    def histogram(self, name: str, help: str, labelnames: tuple[str, ...]) -> _HistogramProto: ...


# ---------------------------------------------------------------------------
# In-memory backend (used in tests and any env without prometheus_client)
# ---------------------------------------------------------------------------


@dataclass
class _LabelKey:
    """Hashable tuple of (label_name -> value) for dict-of-dict lookups."""

    values: tuple[str, ...]

    def __hash__(self) -> int:
        return hash(self.values)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _LabelKey) and self.values == other.values


def _make_label_key(labelnames: tuple[str, ...], labels: dict[str, str] | None) -> _LabelKey:
    if not labels:
        return _LabelKey(tuple())
    return _LabelKey(tuple(labels.get(n, "") for n in labelnames))


class _InMemoryCounter:
    def __init__(self, labelnames: tuple[str, ...]) -> None:
        self._labelnames = labelnames
        self._values: dict[_LabelKey, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = _make_label_key(self._labelnames, labels)
        with self._lock:
            self._values[key] += amount

    def value(self, labels: dict[str, str] | None = None) -> float:
        key = _make_label_key(self._labelnames, labels)
        return self._values.get(key, 0.0)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()

    def snapshot(self) -> dict[tuple[str, ...], float]:
        with self._lock:
            return {k.values: v for k, v in self._values.items()}


class _InMemoryHistogram:
    """Simple bucket-free histogram (count + sum + last_value).

    Prometheus Histogram has buckets; we keep this minimal because the
    spec only requires the metric is observable. Production swaps to
    prometheus_client which has full buckets.
    """

    def __init__(self, labelnames: tuple[str, ...]) -> None:
        self._labelnames = labelnames
        self._counts: dict[_LabelKey, int] = defaultdict(int)
        self._sums: dict[_LabelKey, float] = defaultdict(float)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = _make_label_key(self._labelnames, labels)
        with self._lock:
            self._counts[key] += 1
            self._sums[key] += value

    def count(self, labels: dict[str, str] | None = None) -> int:
        key = _make_label_key(self._labelnames, labels)
        return self._counts.get(key, 0)

    def sum(self, labels: dict[str, str] | None = None) -> float:
        key = _make_label_key(self._labelnames, labels)
        return self._sums.get(key, 0.0)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._sums.clear()

    def snapshot(self) -> dict[tuple[str, ...], dict[str, float]]:
        with self._lock:
            out: dict[tuple[str, ...], dict[str, float]] = {}
            for k in self._counts:
                out[k.values] = {
                    "count": float(self._counts[k]),
                    "sum": self._sums[k],
                }
            return out


class InMemoryBackend:
    """Thread-safe in-memory backend. Default for tests."""

    def __init__(self) -> None:
        self._counters: dict[str, _InMemoryCounter] = {}
        self._histograms: dict[str, _InMemoryHistogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, help: str, labelnames: tuple[str, ...]) -> _InMemoryCounter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _InMemoryCounter(labelnames)
            return self._counters[name]

    def histogram(self, name: str, help: str, labelnames: tuple[str, ...]) -> _InMemoryHistogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _InMemoryHistogram(labelnames)
            return self._histograms[name]

    def reset(self) -> None:
        """Test helper — wipe all metrics state, including existing
        references returned before the reset.
        """
        with self._lock:
            for c in self._counters.values():
                c.reset()
            for h in self._histograms.values():
                h.reset()
            self._counters.clear()
            self._histograms.clear()


# ---------------------------------------------------------------------------
# Orchestrator metrics — 8 metric families (SPEC §8.1)
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorMetrics:
    """Container of all 8 Orchestrator metrics.

    Construction accepts a backend; the default is ``InMemoryBackend``.
    Production should construct once at app startup and reuse the same
    instance across all runs.
    """

    backend: MetricsBackend = field(default_factory=InMemoryBackend)

    # ── Counters
    runs_total: Any = None
    state_transitions_total: Any = None
    expert_invocations_total: Any = None
    phi_entities_redacted_total: Any = None
    planning_llm_calls_total: Any = None

    # ── Histograms
    run_duration_seconds: Any = None
    expert_duration_seconds: Any = None
    planning_llm_duration_seconds: Any = None

    @classmethod
    def build(cls, backend: MetricsBackend | None = None) -> "OrchestratorMetrics":
        b = backend or InMemoryBackend()
        m = cls(backend=b)
        m.runs_total = b.counter(
            "orchestrator_runs_total",
            "Orchestrator runs by terminal status",
            ("agent_id", "status"),
        )
        m.state_transitions_total = b.counter(
            "orchestrator_state_transitions_total",
            "State machine transitions",
            ("from_state", "to_state"),
        )
        m.expert_invocations_total = b.counter(
            "orchestrator_expert_invocations_total",
            "Expert invocations by outcome",
            ("expert_id", "result"),
        )
        m.phi_entities_redacted_total = b.counter(
            "orchestrator_phi_entities_redacted_total",
            "PHI entities redacted by type",
            ("entity_type",),
        )
        m.planning_llm_calls_total = b.counter(
            "orchestrator_planning_llm_calls_total",
            "Planning LLM calls by outcome",
            ("model", "result"),
        )
        m.run_duration_seconds = b.histogram(
            "orchestrator_run_duration_seconds",
            "Wall-clock run duration by terminal state",
            ("agent_id", "terminal_state"),
        )
        m.expert_duration_seconds = b.histogram(
            "orchestrator_expert_duration_seconds",
            "Expert invocation duration",
            ("expert_id",),
        )
        m.planning_llm_duration_seconds = b.histogram(
            "orchestrator_planning_llm_duration_seconds",
            "Planning LLM call duration",
            ("model",),
        )
        return m


# ---------------------------------------------------------------------------
# Module-level singleton + lazy init
# ---------------------------------------------------------------------------

_DEFAULT_METRICS: OrchestratorMetrics | None = None
_DEFAULT_LOCK = threading.Lock()


def get_metrics() -> OrchestratorMetrics:
    """Lazy singleton accessor — tests should construct their own."""
    global _DEFAULT_METRICS
    if _DEFAULT_METRICS is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_METRICS is None:
                _DEFAULT_METRICS = OrchestratorMetrics.build()
    return _DEFAULT_METRICS


def reset_default_metrics() -> None:
    """Test helper — drop the cached default."""
    global _DEFAULT_METRICS
    with _DEFAULT_LOCK:
        _DEFAULT_METRICS = None


__all__ = [
    "InMemoryBackend",
    "MetricsBackend",
    "OrchestratorMetrics",
    "get_metrics",
    "reset_default_metrics",
]