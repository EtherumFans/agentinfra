"""RunContext + Plan + ExpertResult + StateTransition (SPEC §4.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Plan:
    """Planner LLM output: ordered Expert calls with subtasks."""

    steps: list[dict] = field(default_factory=list)
    raw_llm_output: dict | None = None
    reason: str = ""


@dataclass
class ExpertResult:
    """Per-Expert outcome collected during delegating."""

    expert_id: str
    subtask_input: Any = None
    result: Any = None
    error: str = ""
    latency_ms: int = 0
    attempt: int = 1


@dataclass
class OrchestratorMessage:
    """Final agent output (A2A Message body)."""

    role: str = "agent"
    parts: list[dict] = field(default_factory=list)
    message_id: str = ""


@dataclass
class StateTransition:
    """Immutable audit record of one state machine hop."""

    from_state: str
    to_state: str
    event: str
    timestamp: datetime


@dataclass
class RunContext:
    """Per-run state. Created at received, destroyed at completed/failed.

    `original_input` is held only for audit; the runtime hot path uses
    `redacted_input`.
    """

    run_id: str
    context_id: str
    agent_id: str
    agent_definition: Any = None
    original_input: str = ""
    redacted_input: str = ""
    plan: Plan | None = None
    expert_results: list[ExpertResult] = field(default_factory=list)
    final_message: OrchestratorMessage | None = None
    error: "OrchestratorError | None" = None  # type: ignore[name-defined]
    state_history: list[StateTransition] = field(default_factory=list)