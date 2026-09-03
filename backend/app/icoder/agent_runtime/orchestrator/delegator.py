"""Delegator — invokes Experts sequentially per Plan (SPEC §3.1, §7.2, §7.3).

Phase 1: sequential only (Q-S2 — concurrency is Phase 5 work).

Per spec §7.2 retry table:
  - Critical expert → 2 retries, exp backoff (1s, 2s), total 30s
  - Non-critical expert → 1 retry, constant 1s backoff, total 15s

The Expert invocation contract is a callable injected at construction time.
Tests inject deterministic local invokers. Runtime assembly must inject a real
implementation or an explicit fail-closed callable; this module does not ship
a synthetic-success fallback.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import OrchestratorError
from .run_context import ExpertResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Invocation contract
# ---------------------------------------------------------------------------


@dataclass
class ExpertInvocation:
    """Payload handed to an Expert invoker."""

    expert_id: str
    subtask_input: str
    tool_constraints: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    attempt: int = 1


# Type for injected invoker (sync, in-process for Phase 1)
ExpertInvoker = Callable[[ExpertInvocation], dict]
"""Signature: ``invoker(invocation) -> dict``"""

# Async variant (Phase 5)
AsyncExpertInvoker = Callable[[ExpertInvocation], "Any"]


class ExpertInvocationError(OrchestratorError):
    """Raised by the invoker for hard failures (network, 5xx, parse)."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        stage: str = "delegating",
        code: str = "expert_failed",
        http_status: int | None = None,
    ) -> None:
        if http_status is None:
            http_status = OrchestratorError.A2A_CODES.get("EXPERT_FAILED", (None, 502))[1]
        super().__init__(
            message=message,
            code=code,
            stage=stage,
            retryable=retryable,
            http_status=http_status,
        )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class DelegatorConfig:
    """Retry + backoff tunables — match SPEC §7.2."""

    critical_max_retries: int = 2
    non_critical_max_retries: int = 1
    critical_backoff_seconds: float = 1.0
    non_critical_backoff_seconds: float = 1.0
    per_expert_timeout_seconds: float = 30.0
    sleep_fn: Callable[[float], None] = time.sleep


# ---------------------------------------------------------------------------
# Delegator
# ---------------------------------------------------------------------------


class Delegator:
    """Sequential Expert delegator.

    Returns a list of ``ExpertResult`` — one per Plan step. Caller
    inspects each result's ``error`` field to decide if a critical
    expert failed (=> fail the run).
    """

    def __init__(
        self,
        invoker: ExpertInvoker,
        *,
        config: DelegatorConfig | None = None,
    ) -> None:
        if invoker is None:
            raise ValueError("invoker is required")
        self._invoker = invoker
        self._config = config or DelegatorConfig()

    def delegate(
        self,
        *,
        plan_steps: list[dict],
        context: dict | None = None,
    ) -> list[ExpertResult]:
        """Invoke each Plan step sequentially. Never raises on expert failure.

        Returns a result per step. Critical expert failures are surfaced
        via ``ExpertResult.error`` AND an ``OrchestratorError`` payload
        (via the ``error`` field) — caller decides state-machine transition.
        """
        results: list[ExpertResult] = []
        for step in plan_steps:
            r = self._invoke_with_retries(step, context=context or {})
            results.append(r)
        return results

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _invoke_with_retries(
        self,
        step: dict,
        *,
        context: dict,
    ) -> ExpertResult:
        cfg = self._config
        expert_id = step.get("expert_id", "")
        subtask = step.get("subtask_input", "")
        tool_constraints = list(step.get("tool_constraints", []))
        critical = bool(step.get("critical", True))

        max_retries = (
            cfg.critical_max_retries if critical else cfg.non_critical_max_retries
        )
        backoff = (
            cfg.critical_backoff_seconds
            if critical
            else cfg.non_critical_backoff_seconds
        )

        last_error: str = ""
        attempt = 0
        started = time.monotonic()
        while attempt <= max_retries:
            attempt += 1
            invocation = ExpertInvocation(
                expert_id=expert_id,
                subtask_input=subtask,
                tool_constraints=tool_constraints,
                context=dict(context),
                attempt=attempt,
            )
            t0 = time.monotonic()
            try:
                result = self._invoker(invocation) or {}
            except ExpertInvocationError as e:
                last_error = e.message
                logger.warning(
                    "delegator.expert_failed expert=%s attempt=%d/%d retryable=%s error=%s",
                    expert_id, attempt, max_retries + 1, e.retryable, e,
                )
                # Non-retryable errors fail fast — do not waste retries
                if not e.retryable:
                    return ExpertResult(
                        expert_id=expert_id,
                        subtask_input=subtask,
                        result=None,
                        error=last_error,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        attempt=attempt,
                    )
                if attempt > max_retries:
                    return ExpertResult(
                        expert_id=expert_id,
                        subtask_input=subtask,
                        result=None,
                        error=last_error,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        attempt=attempt,
                    )
                self._sleep_backoff(backoff, attempt)
                continue
            except Exception as e:  # any other failure → treat as retryable
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "delegator.expert_raised expert=%s attempt=%d/%d error=%s",
                    expert_id, attempt, max_retries + 1, e,
                )
                if attempt > max_retries:
                    return ExpertResult(
                        expert_id=expert_id,
                        subtask_input=subtask,
                        result=None,
                        error=last_error,
                        latency_ms=int((time.monotonic() - t0) * 1000),
                        attempt=attempt,
                    )
                self._sleep_backoff(backoff, attempt)
                continue

            # success
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ExpertResult(
                expert_id=expert_id,
                subtask_input=subtask,
                result=result,
                error="",
                latency_ms=latency_ms,
                attempt=attempt,
            )

        # unreachable: above loops always return
        return ExpertResult(
            expert_id=expert_id,
            subtask_input=subtask,
            error=last_error or "unknown",
            attempt=attempt,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def _sleep_backoff(self, base: float, attempt: int) -> None:
        try:
            self._config.sleep_fn(base * (2 ** (attempt - 1)))
        except Exception:  # pragma: no cover - defensive
            pass


__all__ = [
    "Delegator",
    "DelegatorConfig",
    "ExpertInvocation",
    "ExpertInvocationError",
    "ExpertInvoker",
]
