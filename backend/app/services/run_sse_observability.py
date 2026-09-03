"""Low-cardinality, PHI-safe process metrics for Run lifecycle SSE.

The API may run with more than one worker.  Each worker therefore exposes an
explicitly process-scoped snapshot for an external collector to aggregate.
No run, organization, user, cursor, token, event name, or clinical value is
accepted by this module.
"""

from __future__ import annotations

import math
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Deque, Iterable


_REJECTION_REASONS = frozenset({
    "token_required",
    "token_expired",
    "token_invalid",
    "token_run_mismatch",
    "token_malformed",
    "run_not_found",
    "org_mismatch",
    "visibility_denied",
    "trace_not_found",
    "cursor_invalid",
    "cursor_not_found",
    "trace_expired",
    "cursor_expired",
    "other",
})
_CLOSE_REASONS = frozenset({
    "terminal",
    "client_disconnected",
    "run_missing",
    "org_changed",
    "visibility_changed",
    "cancelled",
    "stream_error",
    "other",
})
_RENEWAL_OUTCOMES = frozenset({
    "success",
    "run_not_found",
    "visibility_denied",
    "audit_paused",
    "audit_failed",
    "other_failure",
})


def _safe_label(
    value: str,
    allowed: frozenset[str],
    *,
    fallback: str = "other",
) -> str:
    return value if value in allowed else fallback


def _quantile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return round(float(ordered[index]), 6)


class RunSSEMetrics:
    """Thread-safe bounded metrics for one API process."""

    def __init__(self, *, sample_limit: int = 2048) -> None:
        if sample_limit < 1:
            raise ValueError("sample_limit must be positive")
        self._sample_limit = sample_limit
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Reset all process metrics. Intended for isolated tests only."""
        with getattr(self, "_lock", threading.Lock()):
            self._started_at = datetime.now(timezone.utc).isoformat()
            self._connection_attempts = 0
            self._connections_accepted = 0
            self._resumed_connections = 0
            self._active_connections = 0
            self._events_emitted = 0
            self._heartbeats_emitted = 0
            self._rejections: Counter[str] = Counter()
            self._closes: Counter[str] = Counter()
            self._renewals: Counter[str] = Counter()
            self._recovery_observations_total = 0
            self._duration_observations_total = 0
            self._recovery_seconds: Deque[float] = deque(maxlen=self._sample_limit)
            self._stream_duration_seconds: Deque[float] = deque(maxlen=self._sample_limit)

    def connection_attempted(self) -> None:
        with self._lock:
            self._connection_attempts += 1

    def rejected(self, reason: str) -> None:
        with self._lock:
            self._rejections[_safe_label(reason, _REJECTION_REASONS)] += 1

    def stream_started(self, *, resumed: bool, recovery_seconds: float | None) -> None:
        with self._lock:
            self._connections_accepted += 1
            self._active_connections += 1
            if resumed:
                self._resumed_connections += 1
                if recovery_seconds is not None and recovery_seconds >= 0:
                    self._recovery_observations_total += 1
                    self._recovery_seconds.append(float(recovery_seconds))

    def event_emitted(self, amount: int = 1) -> None:
        if amount < 0:
            raise ValueError("amount must not be negative")
        with self._lock:
            self._events_emitted += amount

    def heartbeat_emitted(self) -> None:
        with self._lock:
            self._heartbeats_emitted += 1

    def stream_closed(self, *, reason: str, duration_seconds: float) -> None:
        with self._lock:
            self._active_connections = max(0, self._active_connections - 1)
            self._closes[_safe_label(reason, _CLOSE_REASONS)] += 1
            if duration_seconds >= 0:
                self._duration_observations_total += 1
                self._stream_duration_seconds.append(float(duration_seconds))

    def token_renewed(self, outcome: str) -> None:
        with self._lock:
            self._renewals[
                _safe_label(
                    outcome,
                    _RENEWAL_OUTCOMES,
                    fallback="other_failure",
                )
            ] += 1

    @staticmethod
    def _latency_snapshot(values: list[float], observations_total: int) -> dict:
        return {
            "observations_total": observations_total,
            "window_samples": len(values),
            "p50": _quantile(values, 0.50),
            "p95": _quantile(values, 0.95),
            "p99": _quantile(values, 0.99),
            "max": round(max(values), 6) if values else None,
        }

    def snapshot(self) -> dict:
        with self._lock:
            recovery = list(self._recovery_seconds)
            durations = list(self._stream_duration_seconds)
            renewals = dict(sorted(self._renewals.items()))
            closes = dict(sorted(self._closes.items()))
            accepted = self._connections_accepted
            unexpected = sum(
                count for reason, count in closes.items() if reason != "terminal"
            )
            renewal_total = sum(renewals.values())
            renewal_failures = renewal_total - renewals.get("success", 0)
            snapshot = {
                "schema_version": "icoder.run-sse-metrics/v1",
                "scope": "single_api_process",
                "started_at": self._started_at,
                "sample_limit": self._sample_limit,
                "connection_attempts_total": self._connection_attempts,
                "connections_accepted_total": accepted,
                "resumed_connections_total": self._resumed_connections,
                "active_connections": self._active_connections,
                "events_emitted_total": self._events_emitted,
                "heartbeats_emitted_total": self._heartbeats_emitted,
                "rejections_total": sum(self._rejections.values()),
                "rejections_by_reason": dict(sorted(self._rejections.items())),
                "stream_closes_total": sum(closes.values()),
                "stream_closes_by_reason": closes,
                "token_renewals_total": renewal_total,
                "token_renewals_by_outcome": renewals,
                "resume_recovery_seconds": self._latency_snapshot(
                    recovery, self._recovery_observations_total
                ),
                "stream_duration_seconds": self._latency_snapshot(
                    durations, self._duration_observations_total
                ),
            }

        disconnect_ratio = unexpected / accepted if accepted else 0.0
        renewal_failure_ratio = (
            renewal_failures / renewal_total if renewal_total else 0.0
        )
        recovery_p95 = snapshot["resume_recovery_seconds"]["p95"]
        snapshot["alert_evaluation"] = [
            {
                "code": "SSE_UNEXPECTED_CLOSE_RATIO_HIGH",
                "state": "firing" if accepted >= 20 and disconnect_ratio > 0.10 else "ok",
                "observed": round(disconnect_ratio, 6),
                "threshold": 0.10,
                "minimum_samples": 20,
            },
            {
                "code": "SSE_TOKEN_RENEW_FAILURE_RATIO_HIGH",
                "state": "firing" if renewal_total >= 20 and renewal_failure_ratio > 0.05 else "ok",
                "observed": round(renewal_failure_ratio, 6),
                "threshold": 0.05,
                "minimum_samples": 20,
            },
            {
                "code": "SSE_RESUME_RECOVERY_P95_HIGH",
                "state": (
                    "firing"
                    if snapshot["resume_recovery_seconds"]["observations_total"] >= 10
                    and recovery_p95 is not None
                    and recovery_p95 > 2.0
                    else "ok"
                ),
                "observed": recovery_p95,
                "threshold_seconds": 2.0,
                "minimum_samples": 10,
            },
        ]
        return snapshot


_DEFAULT_METRICS = RunSSEMetrics()


def get_run_sse_metrics() -> RunSSEMetrics:
    return _DEFAULT_METRICS


def reset_run_sse_metrics_for_tests() -> None:
    _DEFAULT_METRICS.reset()


__all__ = [
    "RunSSEMetrics",
    "get_run_sse_metrics",
    "reset_run_sse_metrics_for_tests",
]
