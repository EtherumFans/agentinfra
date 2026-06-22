"""RecorderAdapter — Orchestrator → M2aRecorder bridge (SPEC §5.3, §7.3).

Maps Orchestrator state transitions and decisions into the 14-stage
M2a trace. Recorder failures NEVER raise — per spec §7.3, observability
does not block business logic. Failures log + swallow.

The adapter accepts any recorder-like object via dependency injection.
The default wires to the existing ``M2aRecorder`` from
``backend/icoder_runtime/m2a/recorder.py``; tests can inject a no-op
or recording stub.

Stage names match SPEC §5.3 verbatim.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from .metrics import OrchestratorMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recorder protocol (subset of M2aRecorder we use)
# ---------------------------------------------------------------------------


class RecorderLike(Any):
    """Anything that exposes ``inference(...).stage(name)`` works.

    The protocol matches M2aRecorder's public surface. We use ``Any`` for
    the type because M2aRecorder is in another package and we don't want
    to import it here.
    """

    @contextmanager
    def inference(self, **kwargs) -> Iterator[Any]: ...  # type: ignore[override]


# ---------------------------------------------------------------------------
# Stage names (SPEC §5.3 table) — centralized so callers don't typo
# ---------------------------------------------------------------------------

STAGE_INBOUND_RECEIVED = "inbound_received"
STAGE_PHI_REDACTED = "phi_redacted"
STAGE_PLANNING_STARTED = "planning_started"
STAGE_PLAN_GENERATED = "plan_generated"
STAGE_DELEGATING_STARTED = "delegating_started"
STAGE_EXPERT_INVOKED = "expert_invoked"
STAGE_EXPERT_RETURNED = "expert_returned"
STAGE_AGGREGATING_STARTED = "aggregating_started"
STAGE_AGGREGATED = "aggregated"
STAGE_RUN_COMPLETED = "run_completed"
STAGE_RUN_FAILED = "run_failed"


# ---------------------------------------------------------------------------
# RecorderAdapter
# ---------------------------------------------------------------------------


class NoopRecorder:
    """Stand-in for tests that don't care about recorder details."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    @contextmanager
    def inference(self, **kwargs) -> Iterator["NoopRun"]:
        run = NoopRun(recorder=self, **kwargs)
        try:
            yield run
        finally:
            self.calls.append(("finalize", {"final_status": run.final_status}))

    def _record(self, stage: str, payload: dict) -> None:
        self.calls.append((stage, payload))


class NoopRun:
    def __init__(self, recorder: NoopRecorder, **kwargs) -> None:
        self.recorder = recorder
        self.kwargs = kwargs
        self.run_id = kwargs.get("run_id", "")
        self.trace_id = kwargs.get("trace_id", "")
        self.final_status = "unknown"

    @contextmanager
    def stage(self, name: str) -> Iterator["NoopStage"]:
        stage = NoopStage(self.recorder, name)
        try:
            yield stage
        finally:
            pass


class NoopStage:
    def __init__(self, recorder: NoopRecorder, name: str) -> None:
        self.recorder = recorder
        self.name = name
        self.output: dict | None = None

    def set_output(self, payload: dict) -> None:
        self.output = payload
        self.recorder._record(self.name, payload)


class RecorderAdapter:
    """Adapter: Orchestrator events → M2a stages.

    Usage:
        adapter = RecorderAdapter(recorder=M2aRecorder(...), metrics=metrics)
        with adapter.start_run(run_id, agent_id) as run:
            adapter.record_plan_generated(run, plan)
            ...
    """

    def __init__(
        self,
        recorder: RecorderLike | None = None,
        metrics: OrchestratorMetrics | None = None,
        agent_ref: str = "orchestrator",
    ) -> None:
        self._recorder = recorder or NoopRecorder()
        self._metrics = metrics
        self._agent_ref = agent_ref

    # ── Top-level run context (SPEC §5.3)

    @contextmanager
    def start_run(
        self,
        *,
        run_id: str,
        agent_id: str,
        metadata: dict | None = None,
        is_sample: bool = False,
    ) -> Iterator[Any]:
        """Open an inference run. Yields the inner context so the caller
        can issue ``stage()`` calls if they need custom payloads beyond
        the typed methods below.

        Recorder failures NEVER raise (SPEC §7.3). If the recorder's
        ``inference()`` or its ``__enter__`` raises, we yield ``None``
        so the caller's ``with`` body still executes (with stages that
        no-op). The caller can pass ``run`` to typed methods which all
        check ``run is None`` defensively.
        """
        meta = dict(metadata or {})
        meta.setdefault("orchestrator", True)
        try:
            cm = self._recorder.inference(
                agent_ref=self._agent_ref,
                run_id=run_id,
                metadata=meta,
                is_sample=is_sample,
            )
            run = cm.__enter__()
        except Exception as e:
            logger.warning("RecorderAdapter.start_run swallowed exception: %s", e)
            yield None
            return
        try:
            yield run
        finally:
            try:
                cm.__exit__(None, None, None)
            except Exception as e:
                logger.warning(
                    "RecorderAdapter.start_run __exit__ swallowed: %s", e
                )

    # ── Typed stage methods (SPEC §5.3)

    def record_inbound_received(
        self,
        run: Any,
        *,
        agent_id: str,
        context_id: str,
        original_input_len: int,
        redacted_input_len: int,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_INBOUND_RECEIVED,
            {
                "agent_id": agent_id,
                "context_id": context_id,
                "original_input_len": original_input_len,
                "redacted_input_len": redacted_input_len,
            },
        )

    def record_phi_redacted(
        self,
        run: Any,
        *,
        entity_types: list[str],
    ) -> None:
        self._safe_stage(run, STAGE_PHI_REDACTED, {"entity_types": entity_types})
        if self._metrics is not None:
            for t in entity_types:
                self._metrics.phi_entities_redacted_total.inc(
                    labels={"entity_type": t}
                )

    def record_planning_started(self, run: Any, *, llm_model: str) -> None:
        self._safe_stage(run, STAGE_PLANNING_STARTED, {"llm_model": llm_model})

    def record_plan_generated(self, run: Any, *, plan: dict) -> None:
        steps = plan.get("steps") or []
        self._safe_stage(
            run,
            STAGE_PLAN_GENERATED,
            {
                "expert_count": len(steps),
                "reason": plan.get("reason", ""),
                "plan": plan,
            },
        )

    def record_delegating_started(self, run: Any, *, expert_count: int) -> None:
        self._safe_stage(
            run, STAGE_DELEGATING_STARTED, {"expert_count": expert_count}
        )

    def record_expert_invoked(
        self,
        run: Any,
        *,
        expert_id: str,
        subtask_input: str,
        attempt: int,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_EXPERT_INVOKED,
            {"expert_id": expert_id, "attempt": attempt,
             "subtask_input_len": len(subtask_input or "")},
        )

    def record_expert_returned(
        self,
        run: Any,
        *,
        expert_id: str,
        result: Any,
        latency_ms: int,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_EXPERT_RETURNED,
            {"expert_id": expert_id, "latency_ms": latency_ms,
             "ok": not (isinstance(result, dict) and result.get("error"))},
        )
        if self._metrics is not None:
            result_label = (
                "success" if not (isinstance(result, dict) and result.get("error"))
                else "failed"
            )
            self._metrics.expert_invocations_total.inc(
                labels={"expert_id": expert_id, "result": result_label}
            )
            self._metrics.expert_duration_seconds.observe(
                latency_ms / 1000.0, labels={"expert_id": expert_id}
            )

    def record_aggregating_started(
        self, run: Any, *, expert_result_count: int
    ) -> None:
        self._safe_stage(
            run,
            STAGE_AGGREGATING_STARTED,
            {"expert_result_count": expert_result_count},
        )

    def record_aggregated(
        self,
        run: Any,
        *,
        conflicted: bool,
        expert_count: int,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_AGGREGATED,
            {"conflicted": conflicted, "expert_count": expert_count},
        )

    def record_run_completed(
        self,
        run: Any,
        *,
        agent_id: str,
        total_duration_ms: int,
        expert_count: int,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_RUN_COMPLETED,
            {
                "agent_id": agent_id,
                "total_duration_ms": total_duration_ms,
                "expert_count": expert_count,
            },
        )
        if self._metrics is not None:
            self._metrics.runs_total.inc(labels={"agent_id": agent_id, "status": "success"})
            self._metrics.run_duration_seconds.observe(
                total_duration_ms / 1000.0,
                labels={"agent_id": agent_id, "terminal_state": "completed"},
            )

    def record_run_failed(
        self,
        run: Any,
        *,
        agent_id: str,
        error_code: str,
        error_stage: str,
        error_message: str,
        total_duration_ms: int = 0,
    ) -> None:
        self._safe_stage(
            run,
            STAGE_RUN_FAILED,
            {
                "agent_id": agent_id,
                "error_code": error_code,
                "error_stage": error_stage,
                "error_message": error_message,
                "total_duration_ms": total_duration_ms,
            },
        )
        if self._metrics is not None:
            self._metrics.runs_total.inc(
                labels={"agent_id": agent_id, "status": "failed"}
            )
            if total_duration_ms > 0:
                self._metrics.run_duration_seconds.observe(
                    total_duration_ms / 1000.0,
                    labels={"agent_id": agent_id, "terminal_state": "failed"},
                )

    def record_state_transition(
        self,
        run: Any,
        *,
        from_state: str,
        to_state: str,
    ) -> None:
        """Top-level state machine hop — separate from per-stage stages."""
        if self._metrics is not None:
            self._metrics.state_transitions_total.inc(
                labels={"from_state": from_state, "to_state": to_state}
            )

    def record_planning_llm_call(
        self,
        run: Any,
        *,
        model: str,
        latency_ms: int,
        success: bool,
    ) -> None:
        if self._metrics is not None:
            result_label = "success" if success else "failed"
            self._metrics.planning_llm_calls_total.inc(
                labels={"model": model, "result": result_label}
            )
            self._metrics.planning_llm_duration_seconds.observe(
                latency_ms / 1000.0, labels={"model": model}
            )

    # ── Internal

    def _safe_stage(self, run: Any, stage_name: str, payload: dict) -> None:
        """Issue a stage; swallow any recorder exception."""
        if run is None:
            return
        try:
            with run.stage(stage_name) as s:
                s.set_output(payload)
        except Exception as e:
            logger.warning(
                "RecorderAdapter stage=%s swallowed exception: %s", stage_name, e
            )


__all__ = [
    "NoopRecorder",
    "NoopRun",
    "NoopStage",
    "RecorderAdapter",
    "RecorderLike",
    "STAGE_AGGREGATED",
    "STAGE_AGGREGATING_STARTED",
    "STAGE_DELEGATING_STARTED",
    "STAGE_EXPERT_INVOKED",
    "STAGE_EXPERT_RETURNED",
    "STAGE_INBOUND_RECEIVED",
    "STAGE_PHI_REDACTED",
    "STAGE_PLAN_GENERATED",
    "STAGE_PLANNING_STARTED",
    "STAGE_RUN_COMPLETED",
    "STAGE_RUN_FAILED",
]