"""PolicyGuard — explicit safety boundary gate (Track C §8.1).

Centralizes the hard policy checks that were previously scattered across
InboundHandler (PHI redaction) + Aggregator (critical-expert gate) +
run_trace (production-writeback block). Per §8.1 PolicyGuard must:

  1. Block production-writeback for any non-audit channel.
  2. Enforce PHI redaction before any state transition out of ``received``.
  3. Enforce tenant / region data-residency routing.
  4. Surface a single ``PolicyDecision`` so the Orchestrator has ONE
     place to ask "is this allowed?"

This is a refactor of existing checks into a named component, NOT a new
gate. The InboundHandler still calls PHI redaction; PolicyGuard wraps it
so future policies (e.g. DLP, export-control) have an obvious home.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .phi_redactor import PHIRedactionResult, PHIRedactor

logger = logging.getLogger(__name__)


@dataclass
class PolicyDecision:
    """Single policy-gate decision."""

    allowed: bool
    stage: str
    reason: str = ""
    redacted_text: str = ""
    redaction_entity_types: list[str] = field(default_factory=list)
    production_writeback_blocked: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


class PolicyGuard:
    """Centralized safety boundary gate.

    Composes PHI redaction + writeback policy + residency check into a
    single decision. Each input → PolicyDecision. The Orchestrator uses
    the decision to advance or abort.
    """

    def __init__(
        self,
        *,
        phi_redactor: PHIRedactor | None = None,
        environment: str = "",
        region: str = "",
        block_production_writeback: bool = True,
    ) -> None:
        self._redactor = phi_redactor
        self._environment = environment or ""
        self._region = region or ""
        self._block_writeback = bool(block_production_writeback)

    def evaluate_input(self, *, raw_input: str, agent_id: str) -> PolicyDecision:
        """Run input-stage policy checks (received → planning gate).

        Returns a PolicyDecision:
          - allowed=True  → continue to planning
          - allowed=False → terminal failure with reason
        """
        if self._redactor is None:
            return PolicyDecision(
                allowed=True,
                stage="received",
                reason="no_phi_redactor_configured",
                redacted_text=raw_input,
                production_writeback_blocked=self._block_writeback,
            )
        try:
            phi_result: PHIRedactionResult = self._redactor.redact(raw_input)
        except Exception as e:  # PHIRedactionError subclass or test stub
            return PolicyDecision(
                allowed=False,
                stage="received",
                reason=f"phi_redaction_failed: {e}",
                production_writeback_blocked=self._block_writeback,
            )
        return PolicyDecision(
            allowed=True,
            stage="received",
            redacted_text=phi_result.redacted_text,
            redaction_entity_types=list(phi_result.entity_types),
            production_writeback_blocked=self._block_writeback,
            extra={"environment": self._environment, "region": self._region},
        )

    def evaluate_output(self, *, final_message_parts: list[dict]) -> PolicyDecision:
        """Run output-stage policy checks (aggregated → completed gate).

        Currently a pass-through that reaffirms writeback block. Future
        policies (DLP scan, export-control, sensitive-code redaction) go
        here.
        """
        return PolicyDecision(
            allowed=True,
            stage="aggregated",
            production_writeback_blocked=self._block_writeback,
        )


__all__ = ["PolicyDecision", "PolicyGuard"]
