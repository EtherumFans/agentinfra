"""OrchestratorError taxonomy (SPEC §7).

These are *expected* error shapes — the state machine itself does not raise
exceptions on bad transitions, but it raises ``OrchestratorStateError``.
Real LLM / Expert failures are mapped to ``OrchestratorError`` and attached
to ``RunContext.error`` so the recorder/response can carry structured
detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class OrchestratorError(Exception):
    """Structured failure context (carries A2A error_code + stage).

    Inherits from Exception so callers may ``raise`` it for transport,
    but the state machine treats it as a value — never raised internally.
    """

    message: str
    code: str = "ORCHESTRATION_FAILED"
    stage: str = "unknown"
    retryable: bool = False
    http_status: int = 500

    A2A_CODES: ClassVar[dict[str, tuple[str, int]]] = {
        "INVALID_REQUEST": ("invalid_request", 400),
        "PHI_REDACTION_FAILED": ("phi_redaction_failed", 500),
        "PLANNING_FAILED": ("planning_failed", 500),
        "EXPERT_FAILED": ("expert_failed", 502),
        "DELEGATION_TIMEOUT": ("delegation_timeout", 504),
        "AGGREGATION_FAILED": ("aggregation_failed", 500),
        "ORCHESTRATION_FAILED": ("orchestration_failed", 500),
    }

    @classmethod
    def from_code(
        cls,
        code: str,
        message: str,
        *,
        stage: str = "unknown",
        retryable: bool = False,
    ) -> "OrchestratorError":
        """Factory that fills http_status from the A2A code table."""
        a2a_code, http = cls.A2A_CODES.get(code, ("orchestration_failed", 500))
        return cls(
            message=message,
            code=a2a_code,
            stage=stage,
            retryable=retryable,
            http_status=http,
        )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.stage}: {self.message}"


class OrchestratorStateError(Exception):
    """Raised by the state machine when a transition is invalid.

    Distinct from OrchestratorError: this is a *programmer* error
    (wrong event for current state), not a *runtime* failure.
    """

    def __init__(
        self,
        message: str,
        *,
        current_state: str | None = None,
        event: str | None = None,
    ) -> None:
        super().__init__(message)
        self.current_state = current_state
        self.event = event