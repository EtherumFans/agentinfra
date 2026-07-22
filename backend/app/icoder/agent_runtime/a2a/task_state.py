"""A2A v0.3 Task state machine (SPEC §7.5).

Per ``docs/ICODER_V1_A2A_SPEC.md`` §4.3 the Task object carries a
``status.state`` field with a fixed enum. This module is the canonical
source of truth for the state values + their transitions.

Allowed transitions:

    (none)    ──submit──▶ submitted
    submitted ──start────▶ working
    working   ──complete─▶ completed   (terminal)
    working   ──fail──────▶ failed     (terminal)
    working   ──cancel────▶ canceled   (terminal)
    submitted ──cancel────▶ canceled   (terminal — canceled before start)

Terminal states (``completed`` / ``failed`` / ``canceled``) accept no
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


TERMINAL_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
)


_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset({TaskState.WORKING, TaskState.CANCELED}),
    TaskState.WORKING: frozenset(
        {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELED: frozenset(),
}


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


__all__ = [
    "TERMINAL_STATES",
    "InvalidTaskTransition",
    "TaskState",
    "is_terminal",
    "next_state",
]
