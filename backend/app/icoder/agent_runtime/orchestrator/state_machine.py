"""OrchestratorStateMachine — pure, immutable, serializable (SPEC §4.3).

Each ``transition`` returns a *new* machine instance and a
``StateTransition`` record. The previous instance is untouched, so
the full history of state objects is replay-safe.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from .errors import OrchestratorStateError
from .events import OrchestratorEvent
from .run_context import StateTransition

ORCHESTRATOR_STATE_RECEIVED = "received"
ORCHESTRATOR_STATE_PLANNING = "planning"
ORCHESTRATOR_STATE_DELEGATING = "delegating"
ORCHESTRATOR_STATE_AGGREGATING = "aggregating"
ORCHESTRATOR_STATE_COMPLETED = "completed"
ORCHESTRATOR_STATE_FAILED = "failed"

ALL_STATES: frozenset[str] = frozenset(
    {
        ORCHESTRATOR_STATE_RECEIVED,
        ORCHESTRATOR_STATE_PLANNING,
        ORCHESTRATOR_STATE_DELEGATING,
        ORCHESTRATOR_STATE_AGGREGATING,
        ORCHESTRATOR_STATE_COMPLETED,
        ORCHESTRATOR_STATE_FAILED,
    }
)

TERMINAL_STATES: frozenset[str] = frozenset(
    {ORCHESTRATOR_STATE_COMPLETED, ORCHESTRATOR_STATE_FAILED}
)


# Transition table — maps (current_state, event) → next_state.
# SPEC §4.2 diagram; plan_failed loops back to planning for retry.
TRANSITIONS: dict[tuple[str, OrchestratorEvent], str] = {
    (ORCHESTRATOR_STATE_RECEIVED, OrchestratorEvent.PHI_REDACTED): ORCHESTRATOR_STATE_PLANNING,
    (ORCHESTRATOR_STATE_RECEIVED, OrchestratorEvent.INBOUND_INVALID): ORCHESTRATOR_STATE_FAILED,
    (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLAN_GENERATED): ORCHESTRATOR_STATE_DELEGATING,
    (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLAN_FAILED): ORCHESTRATOR_STATE_PLANNING,
    (ORCHESTRATOR_STATE_PLANNING, OrchestratorEvent.PLANNING_TIMEOUT): ORCHESTRATOR_STATE_FAILED,
    (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.ALL_EXPERTS_RETURNED): ORCHESTRATOR_STATE_AGGREGATING,
    (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.CRITICAL_EXPERT_FAILED): ORCHESTRATOR_STATE_FAILED,
    (ORCHESTRATOR_STATE_DELEGATING, OrchestratorEvent.DELEGATING_TIMEOUT): ORCHESTRATOR_STATE_FAILED,
    (ORCHESTRATOR_STATE_AGGREGATING, OrchestratorEvent.AGGREGATED): ORCHESTRATOR_STATE_COMPLETED,
    (ORCHESTRATOR_STATE_AGGREGATING, OrchestratorEvent.AGGREGATION_FAILED): ORCHESTRATOR_STATE_FAILED,
}


class OrchestratorStateMachine:
    """Pure transition function — side-effects go through explicit handlers."""

    def __init__(
        self,
        *,
        state: str = ORCHESTRATOR_STATE_RECEIVED,
        history: tuple[StateTransition, ...] = (),
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if state not in ALL_STATES:
            raise ValueError(f"unknown initial state: {state!r}")
        self._state = state
        self._history = history
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    @property
    def current_state(self) -> str:
        return self._state

    @property
    def state_history(self) -> tuple[StateTransition, ...]:
        return self._history

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def transition(self, event: OrchestratorEvent) -> "OrchestratorStateMachine":
        """Return a new SM instance with state advanced. Pure."""
        if self._state in TERMINAL_STATES:
            raise OrchestratorStateError(
                f"cannot transition from terminal state {self._state!r} via {event.value!r}",
                current_state=self._state,
                event=event.value,
            )
        target = TRANSITIONS.get((self._state, event))
        if target is None:
            raise OrchestratorStateError(
                f"no transition for ({self._state!r}, {event.value!r})",
                current_state=self._state,
                event=event.value,
            )
        record = StateTransition(
            from_state=self._state,
            to_state=target,
            event=event.value,
            timestamp=self._now(),
        )
        return OrchestratorStateMachine(
            state=target,
            history=(*self._history, record),
            now_fn=self._now,
        )

    def reachable_from(self, state: str) -> set[OrchestratorEvent]:
        return {ev for (s, ev) in TRANSITIONS if s == state}

    def to_dict(self) -> dict:
        return {
            "current_state": self._state,
            "history": [
                {
                    "from_state": h.from_state,
                    "to_state": h.to_state,
                    "event": h.event,
                    "timestamp": h.timestamp.isoformat(),
                }
                for h in self._history
            ],
        }