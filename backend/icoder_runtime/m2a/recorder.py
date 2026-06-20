"""M2a Task 5 — Recorder bridge: integrate Run Trace into AgentRunner / HybridCodingAdapter.

M2a recorder is a thin wrapper around RunTraceService. It does NOT change
the call signatures of the underlying adapters — instead it provides a
context-manager style API that *opt-in* adapters call to record stages.

Design rules:
- If `recorder is None`, all calls are no-ops → 752 existing tests stay green.
- If `recorder is set`, every call to `start_inference()` returns a context
  manager that records `start_run` + `add_tool_call` per stage + `finalize_run`.
- The recorder never raises — failures are logged as warnings and swallowed
  so that the underlying business logic is not blocked by observability.

This is the minimum-intrusion bridge that lets M2a Move from "exposed via
/api/m2a/*" to "auto-driven by AgentRunner / HybridCodingAdapter".
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .run_trace import RunTraceService

logger = logging.getLogger(__name__)


class M2aRecorder:
    """Bridge: wrap RunTraceService for adapter integration.

    Usage in HybridCodingAdapter:
        if self._recorder is not None:
            with self._recorder.inference(agent_ref="hybrid_coding_adapter") as ctx:
                with ctx.stage("inference") as s:
                    result = await self._inference.infer_async(...)
                    s.set_output({"primary": result.primary_diagnosis.code})
                with ctx.stage("rule_validation") as s:
                    ...
    """

    def __init__(self, run_trace: RunTraceService | None = None,
                 default_agent_ref: str = "icoder_runtime"):
        self._run_trace = run_trace
        self._default_agent_ref = default_agent_ref
        # 最近一次 finalize 的 run 元数据 (供 API 层透出 run_id/trace_id)
        # M2b-1 §5: 真实 API 路径需要把 trace id 返回给客户端
        self._last_finalized: dict[str, str] | None = None

    def is_active(self) -> bool:
        return self._run_trace is not None

    @property
    def last_finalized(self) -> dict[str, str] | None:
        return self._last_finalized

    @contextmanager
    def inference(self, agent_ref: str = "", data_source: str = "real",
                  is_sample: bool = False,
                  metadata: dict[str, Any] | None = None,
                  run_id: str | None = None,
                  trace_id: str | None = None) -> Iterator["_InferenceContext"]:
        """Top-level context for one full inference run.

        On enter: start_run. On exit: finalize_run.
        All stage() calls in between are recorded as tool calls.
        If recorder is inactive, yields a no-op context.

        ``run_id`` / ``trace_id`` are M3-0 hospital-pilot additions that
        let the API layer reuse its own identifiers as the M2a trace
        identifiers, so the trace can be looked up via the same run_id
        the client receives. Falls back to RunTraceService's own generated
        ids when not provided.
        """
        if self._run_trace is None:
            yield _InferenceContext(recorder=None, run_id=run_id or "", trace_id=trace_id or "")
            return
        try:
            trace = self._run_trace.start_run(
                agent_ref=agent_ref or self._default_agent_ref,
                data_source=data_source,
                is_sample=is_sample,
                metadata=metadata or {},
                run_id=run_id,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.warning(f"M2aRecorder: start_run failed (non-fatal): {e}")
            yield _InferenceContext(recorder=None, run_id=run_id or "", trace_id=trace_id or "")
            return

        ctx = _InferenceContext(recorder=self._run_trace, run_id=trace.run_id, trace_id=trace.trace_id)
        try:
            yield ctx
        finally:
            try:
                self._run_trace.finalize_run(
                    trace.run_id,
                    final_status=ctx.final_status,
                    risk_route=ctx.risk_route,
                    safety_gate=ctx.safety_gate,
                )
                # M2b-1 §5: 缓存最近一次 finalized run (供 API 透出)
                self._last_finalized = {
                    "run_id": trace.run_id,
                    "trace_id": trace.trace_id,
                }
            except Exception as e:
                logger.warning(f"M2aRecorder: finalize_run failed (non-fatal): {e}")


class _InferenceContext:
    """Per-inference context — collects stages and final status."""

    def __init__(self, recorder: RunTraceService | None, run_id: str, trace_id: str):
        self._recorder = recorder
        self._run_id = run_id
        self._trace_id = trace_id
        self.final_status: str = "success"
        self.risk_route: dict[str, Any] = {}
        self.safety_gate: dict[str, Any] = {}

    @contextmanager
    def stage(self, name: str, tool_input: dict[str, Any] | None = None) -> Iterator["_StageContext"]:
        """Record one tool-call-equivalent stage."""
        if self._recorder is None:
            yield _StageContext(active=False)
            return
        try:
            tc = self._recorder.add_tool_call(self._run_id, tool_name=name, tool_input=tool_input or {})
        except Exception as e:
            logger.warning(f"M2aRecorder: add_tool_call failed (non-fatal): {e}")
            yield _StageContext(active=False)
            return
        s = _StageContext(active=True, run_trace=self._recorder, run_id=self._run_id, tool_run_id=tc.tool_run_id)
        try:
            yield s
        finally:
            try:
                self._recorder.complete_tool_call(
                    self._run_id, tc.tool_run_id,
                    tool_output=s.output, status=s.status, error=s.error,
                )
            except Exception as e:
                logger.warning(f"M2aRecorder: complete_tool_call failed (non-fatal): {e}")


class _StageContext:
    """Per-stage handle for the caller to set output / status / error."""

    def __init__(self, active: bool, run_trace: RunTraceService | None = None,
                 run_id: str = "", tool_run_id: str = ""):
        self.active = active
        self._run_trace = run_trace
        self._run_id = run_id
        self._tool_run_id = tool_run_id
        self.output: dict[str, Any] = {}
        self.status: str = "ok"
        self.error: str = ""

    def set_output(self, output: dict[str, Any]) -> None:
        self.output = output

    def set_status(self, status: str, error: str = "") -> None:
        self.status = status
        self.error = error


# ── No-op helpers (used when recorder is None) ──

class NoOpContextManager:
    """Context manager that yields a sentinel and does nothing on exit."""

    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def noop_inference() -> NoOpContextManager:
    """Return a no-op context manager for `with ... as _inf_ctx:`."""
    return NoOpContextManager()


def noop_stage() -> NoOpContextManager:
    """Return a no-op context manager for `with ... as _s:`."""
    return NoOpContextManager()
