"""Canonical A2A Task state machine (v0.3 plus v1.0 states).

Per ``docs/ICODER_V1_A2A_SPEC.md`` §4.3 the Task object carries a
``status.state`` field with a fixed enum. This module is the canonical
source of truth for the state values + their transitions.

Allowed transitions:

    (none)    ──submit──▶ submitted
    submitted ──start────▶ working
    working   ──complete─▶ completed       (terminal)
    working   ──fail──────▶ failed          (terminal)
    working   ──cancel────▶ canceled        (terminal)
    working   ──reject────▶ rejected        (terminal)
    working   ──input─────▶ input-required  (interrupted/resumable)
    working   ──auth──────▶ auth-required   (interrupted/resumable)
    interrupted ──resume──▶ working
    submitted ──cancel────▶ canceled   (terminal — canceled before start)

Terminal states (``completed`` / ``failed`` / ``canceled`` / ``rejected``) accept no
further transitions; calling :func:`next_state` from a terminal state
raises :class:`InvalidTaskTransition`.
"""

from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELED,
        TaskState.REJECTED,
    }
)

INTERRUPTED_STATES: frozenset[TaskState] = frozenset(
    {TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED}
)

# A blocking send or SSE subscription is settled when the Agent either finishes
# or yields control to the caller. Interrupted states are deliberately not
# terminal because a later message with taskId resumes them.
SETTLED_STATES: frozenset[TaskState] = TERMINAL_STATES | INTERRUPTED_STATES


_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED, TaskState.REJECTED}
    ),
    TaskState.WORKING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELED,
            TaskState.REJECTED,
            TaskState.INPUT_REQUIRED,
            TaskState.AUTH_REQUIRED,
        }
    ),
    TaskState.INPUT_REQUIRED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED, TaskState.REJECTED}
    ),
    TaskState.AUTH_REQUIRED: frozenset(
        {TaskState.WORKING, TaskState.CANCELED, TaskState.REJECTED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELED: frozenset(),
    TaskState.REJECTED: frozenset(),
}


_RESULT_STATE_ALIASES: dict[str, TaskState] = {
    state.value: state for state in TaskState
}
_RESULT_STATE_ALIASES.update(
    {f"TASK_STATE_{state.value.replace('-', '_').upper()}": state for state in TaskState}
)


class InvalidTaskTransition(Exception):
    """Raised when a state transition is not allowed by the state machine."""

    def __init__(
        self,
        *,
        current: TaskState,
        target: TaskState,
    ) -> None:
        super().__init__(
            f"Task transition {current.value} → {target.value} is not allowed"
        )
        self.current = current
        self.target = target


def next_state(current: TaskState, target: TaskState) -> TaskState:
    """Validate the transition ``current → target`` and return ``target``.

    Raises :class:`InvalidTaskTransition` if the transition is not in
    :data:`_TRANSITIONS`. Terminal states have empty transition sets so
    any move from them raises.
    """
    allowed = _TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTaskTransition(current=current, target=target)
    return target


def is_terminal(state: TaskState) -> bool:
    """True iff ``state`` is a terminal state (no further transitions)."""
    return state in TERMINAL_STATES


def is_settled(state: TaskState) -> bool:
    """True when a blocking operation should return control to its caller."""

    return state in SETTLED_STATES


def settled_state_from_result(result: dict) -> TaskState:
    """Derive the durable settled state from one Agent result.

    Message results complete a Task. Task results must explicitly carry a
    terminal or interrupted state. Returning ``submitted``/``working`` from a
    completed handler invocation is ambiguous and therefore fails closed.
    """

    if result.get("kind") == "message":
        return TaskState.COMPLETED
    if result.get("kind") != "task":
        raise ValueError("Agent result must be an A2A Message or Task")
    status = result.get("status")
    raw_state = status.get("state") if isinstance(status, dict) else None
    state = _RESULT_STATE_ALIASES.get(str(raw_state or ""))
    if state is None or state not in SETTLED_STATES:
        raise ValueError("Agent Task result must have a settled A2A state")
    return state


__all__ = [
    "TERMINAL_STATES",
    "INTERRUPTED_STATES",
    "SETTLED_STATES",
    "InvalidTaskTransition",
    "TaskState",
    "is_terminal",
    "is_settled",
    "next_state",
    "settled_state_from_result",
]
