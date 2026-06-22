"""Inbound handler — Orchestrator entry point (SPEC §3.2, §5.1).

Implements ``POST /api/icoder/agents/{agent_id}/v1/message:send`` in a
testable shape:

  1. server-generated ``contextId`` (UUID v4, Q4)
  2. PHI redaction as the FIRST step (hard requirement, SPEC §6.3)
  3. drives the state machine ``received → planning → delegating →
     aggregating → completed/failed``
  4. returns an A2A-shaped response (Message + metadata) or an A2A
     error envelope on failure

The handler does NOT own transport concerns (HTTP, JSON parsing) — that's
the job of ``a2a_routes.py``. The handler accepts already-parsed request
data and returns already-shaped response data, so the FastAPI route is a
thin adapter.

Per RFC Q5, the OLD ``AgentRunner`` is NOT used; this handler is the only
entry point. Per Q4, ``contextId`` is server-generated even when the
client supplies one in the request (Q4 — strict contextId isolation).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .aggregator import Aggregator, AggregatorError
from .delegator import Delegator
from .errors import OrchestratorError
from .events import OrchestratorEvent
from .phi_redactor import PHIRedactionError, PHIRedactor
from .planner import Planner, PlannerError
from .run_context import RunContext
from .state_machine import (
    OrchestratorStateMachine,
)

if TYPE_CHECKING:
    from icoder_runtime.types import AgentDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent provider contract
# ---------------------------------------------------------------------------

AgentProvider = Any
"""A callable ``agent_provider(agent_id: str) -> AgentDefinition | None``.

The default production implementation reads from ``AgentRegistry``;
tests can pass a simple dict-backed stub. We don't import the registry
here to keep the handler module dependency-light.
"""


# ---------------------------------------------------------------------------
# Request / Response shapes — A2A 0.3 compatible (SPEC §5.1)
# ---------------------------------------------------------------------------


@dataclass
class InboundMessage:
    """Inbound A2A Message body."""

    role: str = "user"
    parts: list[dict] = field(default_factory=list)
    interaction_id: str = ""


@dataclass
class InboundRequest:
    """Inbound A2A request envelope."""

    message: InboundMessage
    metadata: dict = field(default_factory=dict)


@dataclass
class InboundResponse:
    """Outbound A2A Message response (SPEC §5.1.2) or error (SPEC §5.1.3)."""

    kind: str = "message"  # "message" | "error"
    message_id: str = ""
    context_id: str = ""
    role: str = "agent"
    parts: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: dict | None = None
    http_status: int = 200

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "kind": self.kind,
            "messageId": self.message_id,
            "contextId": self.context_id,
            "role": self.role,
            "parts": list(self.parts),
            "metadata": dict(self.metadata),
        }
        if self.error:
            out["error"] = self.error
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_text_from_parts(parts: list[dict]) -> str:
    """Pull text from a list of A2A Parts. DataParts contribute JSON-encoded text."""
    chunks: list[str] = []
    for p in parts or []:
        if not isinstance(p, dict):
            continue
        kind = p.get("kind") or p.get("type") or ""
        if kind == "text":
            t = p.get("text", "")
            if t:
                chunks.append(str(t))
        elif kind == "data":
            d = p.get("data")
            if d is not None:
                import json as _json

                chunks.append(_json.dumps(d, ensure_ascii=False))
        elif "text" in p and isinstance(p["text"], str):
            chunks.append(p["text"])
    return "\n".join(chunks).strip()


def make_context_id() -> str:
    """UUID v4 — server-generated (Q4 strict isolation)."""
    return str(uuid.uuid4())


def make_message_id() -> str:
    return str(uuid.uuid4())


def make_run_id() -> str:
    return str(uuid.uuid4())


def is_valid_request(req: InboundRequest) -> tuple[bool, str]:
    """Validate request shape before doing any work."""
    if not isinstance(req, InboundRequest):
        return False, "request must be InboundRequest"
    if not req.message.parts:
        return False, "message.parts must be non-empty"
    for i, p in enumerate(req.message.parts):
        if not isinstance(p, dict):
            return False, f"message.parts[{i}] must be an object"
    return True, ""


# ---------------------------------------------------------------------------
# InboundHandler
# ---------------------------------------------------------------------------


@dataclass
class InboundHandlerConfig:
    """Tunables — most behavior comes from the injected components."""

    fail_fast_on_agent_missing: bool = True


class InboundHandler:
    """Orchestrator entry point. Drives state machine + Planner/Delegator/Aggregator."""

    def __init__(
        self,
        *,
        phi_redactor: PHIRedactor,
        planner: Planner,
        delegator: Delegator,
        aggregator: Aggregator,
        agent_provider: AgentProvider,
        config: InboundHandlerConfig | None = None,
    ) -> None:
        self._redactor = phi_redactor
        self._planner = planner
        self._delegator = delegator
        self._aggregator = aggregator
        self._agent_provider = agent_provider
        self._config = config or InboundHandlerConfig()

    def handle(self, agent_id: str, request: InboundRequest) -> InboundResponse:
        """Synchronous handler — run inside ``asyncio.to_thread`` if needed."""
        run_id = make_run_id()
        context_id = make_context_id()  # Q4: server-generated

        # ── Step 0: request shape validation (before any state transition)
        ok, why = is_valid_request(request)
        if not ok:
            return self._error_response(
                context_id=context_id,
                run_id=run_id,
                code="invalid_request",
                message=why,
                http_status=400,
                stage="received",
            )

        # ── Step 1: load AgentDefinition
        try:
            agent = self._agent_provider(agent_id)
        except Exception as e:  # registry blew up
            return self._error_response(
                context_id=context_id,
                run_id=run_id,
                code="invalid_request",
                message=f"agent provider raised: {e}",
                http_status=400,
                stage="received",
            )
        if agent is None:
            if self._config.fail_fast_on_agent_missing:
                return self._error_response(
                    context_id=context_id,
                    run_id=run_id,
                    code="invalid_request",
                    message=f"agent_id={agent_id!r} not found",
                    http_status=400,
                    stage="received",
                )
            agent = None  # placeholder; downstream will fail
            return self._error_response(
                context_id=context_id,
                run_id=run_id,
                code="invalid_request",
                message=f"agent_id={agent_id!r} not found",
                http_status=400,
                stage="received",
            )

        # ── Step 2: extract text from parts
        original_input = extract_text_from_parts(request.message.parts)

        # ── Step 3: RunContext + state machine at received
        run_ctx = RunContext(
            run_id=run_id,
            context_id=context_id,
            agent_id=agent_id,
            agent_definition=agent,
            original_input=original_input,
            redacted_input="",
        )
        sm = OrchestratorStateMachine()
        # First transition: received → planning (after PHI redaction succeeds)
        # We do NOT call sm.transition(INBOUND_REQUEST_VALIDATED) — that's a
        # conceptual event, not a state machine event in SPEC §4.4.

        # ── Step 4: PHI redaction (HARD requirement)
        try:
            phi_result = self._redactor.redact(original_input)
        except PHIRedactionError as e:
            # Map PHIRedactionError → OrchestratorError envelope
            return self._wrap_terminal_failure(
                sm=sm,
                run_ctx=run_ctx,
                error=e,
                run_id=run_id,
                context_id=context_id,
            )
        run_ctx.redacted_input = phi_result.redacted_text
        sm = sm.transition(OrchestratorEvent.PHI_REDACTED)  # received → planning

        # ── Step 5: planning
        try:
            plan = self._planner.plan(redacted_input=phi_result.redacted_text, agent=agent)
        except PlannerError as e:
            run_ctx.error = e
            # Per SPEC §4.2: PLAN_FAILED loops to planning (already there) and
            # PLANNING_TIMEOUT → failed. After exhaustion we send timeout.
            sm = sm.transition(OrchestratorEvent.PLANNING_TIMEOUT)
            return self._wrap_terminal_failure(
                sm=sm,
                run_ctx=run_ctx,
                error=e,
                run_id=run_id,
                context_id=context_id,
            )
        run_ctx.plan = plan
        sm = sm.transition(OrchestratorEvent.PLAN_GENERATED)  # planning → delegating

        # ── Step 6: delegating
        try:
            results = self._delegator.delegate(
                plan_steps=list(plan.steps or []),
                context={
                    "run_id": run_id,
                    "context_id": context_id,
                    "agent_id": agent_id,
                    "interaction_id": request.message.interaction_id,
                    "redacted_input": run_ctx.redacted_input,
                    "plan_reason": plan.reason,
                },
            )
        except OrchestratorError as e:
            run_ctx.error = e
            sm = sm.transition(OrchestratorEvent.CRITICAL_EXPERT_FAILED)
            return self._wrap_terminal_failure(
                sm=sm,
                run_ctx=run_ctx,
                error=e,
                run_id=run_id,
                context_id=context_id,
            )

        run_ctx.expert_results = results

        # Detect critical expert failure (delegator returns per-step errors,
        # not raises — so we have to look at results here).
        step_critical = {
            step.get("expert_id", ""): bool(step.get("critical", True))
            for step in (plan.steps or [])
        }
        critical_failed = [
            r.expert_id for r in results
            if r.error and step_critical.get(r.expert_id, True)
        ]
        if critical_failed:
            # Include each failed expert's underlying error message so the
            # A2A error envelope shows the real cause (otherwise callers
            # only see "critical expert(s) failed: ['x']" with no detail).
            failure_details = [
                f"{r.expert_id}: {r.error}"
                for r in results
                if r.error and step_critical.get(r.expert_id, True)
            ]
            err = OrchestratorError.from_code(
                "EXPERT_FAILED",
                f"critical expert(s) failed: {sorted(critical_failed)} "
                f"| {failure_details}",
                stage="delegating",
                retryable=False,
            )
            run_ctx.error = err
            sm = sm.transition(OrchestratorEvent.CRITICAL_EXPERT_FAILED)
            return self._wrap_terminal_failure(
                sm=sm,
                run_ctx=run_ctx,
                error=err,
                run_id=run_id,
                context_id=context_id,
            )
        sm = sm.transition(OrchestratorEvent.ALL_EXPERTS_RETURNED)  # → aggregating

        # ── Step 7: aggregating
        try:
            message = self._aggregator.aggregate(
                plan_steps=list(plan.steps or []),
                expert_results=results,
                reason=plan.reason,
            )
        except AggregatorError as e:
            run_ctx.error = e
            sm = sm.transition(OrchestratorEvent.AGGREGATION_FAILED)
            return self._wrap_terminal_failure(
                sm=sm,
                run_ctx=run_ctx,
                error=e,
                run_id=run_id,
                context_id=context_id,
            )
        sm = sm.transition(OrchestratorEvent.AGGREGATED)  # → completed

        # ── Step 8: build response
        run_ctx.final_message = message
        response = InboundResponse(
            kind="message",
            message_id=make_message_id(),
            context_id=context_id,
            role="agent",
            parts=list(message.parts or []),
            metadata={
                "run_id": run_id,
                "agent_id": agent_id,
                "interaction_id": request.message.interaction_id,
                "plan_reason": plan.reason,
                "expert_count": len(results),
                "state_history": [
                    h.to_state for h in sm.state_history
                ],
                "phi_redacted": True,
                "production_writeback_blocked": True,
                "redaction_entity_types": list(phi_result.entity_types),
            },
            http_status=200,
        )
        return response

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _wrap_terminal_failure(
        self,
        *,
        sm: OrchestratorStateMachine,
        run_ctx: RunContext,
        error: OrchestratorError,
        run_id: str,
        context_id: str,
    ) -> InboundResponse:
        """Build an A2A error response from a terminal state failure."""
        run_ctx.error = error
        return self._error_response(
            context_id=context_id,
            run_id=run_id,
            code=error.code,
            message=error.message,
            http_status=error.http_status,
            stage=error.stage,
            state_history=[h.to_state for h in sm.state_history],
        )

    @staticmethod
    def _error_response(
        *,
        context_id: str,
        run_id: str,
        code: str,
        message: str,
        http_status: int,
        stage: str,
        state_history: list[str] | None = None,
    ) -> InboundResponse:
        return InboundResponse(
            kind="error",
            message_id="",
            context_id=context_id,
            role="agent",
            parts=[],
            metadata={
                "run_id": run_id,
                "stage": stage,
                "state_history": state_history or [],
                "phi_redacted": True,
                "production_writeback_blocked": True,
            },
            error={"code": code, "message": message},
            http_status=http_status,
        )


# ---------------------------------------------------------------------------
# Convenience: agent provider backed by a dict (for tests / dev)
# ---------------------------------------------------------------------------


class DictAgentProvider:
    """Minimal AgentProvider that looks up agents from a dict."""

    def __init__(self, agents: dict | None = None) -> None:
        self._agents: dict = dict(agents or {})

    def register(self, agent_id: str, agent_def: Any) -> None:
        self._agents[agent_id] = agent_def

    def __call__(self, agent_id: str) -> Any | None:
        return self._agents.get(agent_id)


__all__ = [
    "DictAgentProvider",
    "InboundHandler",
    "InboundHandlerConfig",
    "InboundMessage",
    "InboundRequest",
    "InboundResponse",
    "extract_text_from_parts",
    "is_valid_request",
    "make_context_id",
    "make_message_id",
    "make_run_id",
]