"""Bounded low-cardinality process metrics for clinical shadow operations."""

from __future__ import annotations

import threading
from collections import Counter


_EVENTS = frozenset({
    "queued", "claimed", "recovered", "retry_scheduled", "passed", "stopped",
    "failed", "cancelled", "dead_lettered", "replayed", "fence_lost",
    "queue_signal_sent", "queue_signal_failed", "scheduler_cycle_succeeded",
    "scheduler_cycle_failed", "scheduler_lease_contended", "alert_fired",
    "alert_resolved",
})


class ClinicalShadowMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: Counter[str] = Counter()

    def record(self, event: str, amount: int = 1) -> None:
        if event not in _EVENTS:
            raise ValueError("CLINICAL_SHADOW_METRIC_EVENT_INVALID")
        if isinstance(amount, bool) or amount < 0:
            raise ValueError("CLINICAL_SHADOW_METRIC_AMOUNT_INVALID")
        with self._lock:
            self._events[event] += int(amount)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            events = {key: int(self._events.get(key, 0)) for key in sorted(_EVENTS)}
        return {
            "schema_version": "icoder.clinical-shadow-process-metrics/v1",
            "scope": "single_api_or_worker_process",
            "events_total": sum(events.values()),
            "events": events,
            "patient_labels_present": False,
            "tenant_labels_present": False,
            "job_labels_present": False,
        }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_DEFAULT = ClinicalShadowMetrics()


def get_clinical_shadow_metrics() -> ClinicalShadowMetrics:
    return _DEFAULT


__all__ = ["ClinicalShadowMetrics", "get_clinical_shadow_metrics"]
