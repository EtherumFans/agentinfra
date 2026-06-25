"""TabularValidatorExpert — iCoDer Runtime expert for MedCodER Stage 5 (calibration).

Wraps the ``MedicalCodingRuleSet`` to validate a candidate coding
output (post Stages 1-4) against the 12-rule table (R001-R010 +
MC-R-M80-001). Pure deterministic — no LLM, no I/O beyond in-memory
data structures.

Phase 2 / D2 — 4 atomic experts. This is the "Stage 5 compliance +
calibration" building block that the MedCodER 5-stage pipeline uses
to flag manual-review-required issues.

Public contract
---------------
Same as :class:`CodingExpert` — sync ``__call__(invocation) -> dict``
for Phase 1, async ``invoke_async(structured_output, ctx) -> dict``
for Phase 2.

Error handling
--------------
Generic exceptions translated to :class:`ExpertInvocationError` with
``stage="validating"``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)

if TYPE_CHECKING:
    from compliance_services.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class TabularValidatorExpert:
    """Stage 5 validator: structured coding output → rule violations.

    Output schema (matches ``agent_pack.json#output_contract.validation``):
        {
          "passed":              bool,
          "issues":              [{"severity", "code", "message", "suggestion"}],
          "manual_review_required": bool,
          "rule_set":            "medical_coding",
          "expert_id":           "tabular-validator",
        }
    """

    EXPERT_ID: str = "tabular-validator"
    EXPERT_NAME: str = "Tabular Validator (MedCodER Stage 5)"

    def __init__(
        self,
        rule_engine: "RuleEngine | None" = None,
        *,
        rule_set: str = "medical_coding",
    ) -> None:
        """Construct the expert.

        ``rule_engine`` is injected so tests can pass a stub. When None,
        the expert uses the singleton RuleEngine that should already be
        registered in ``app.services.rule_engine_registry`` (production).
        """
        self._engine = rule_engine
        self._rule_set = rule_set

    # ── Phase 1 sync interface (Delegator still sync) ─────────────

    def invoke_sync(self, invocation: ExpertInvocation) -> dict:
        """Phase 1 entry — Delegator calls this with ``ExpertInvocation``.

        ``invocation.subtask_input`` is a JSON-serialized structured
        output: ``{"primary_diagnosis": {...}, "secondary_diagnoses":
        [...], "procedures": [...], "confidence": float}``.
        """
        import json
        ctx = invocation.context or {}
        try:
            payload = json.loads(invocation.subtask_input) if invocation.subtask_input else {}
        except (ValueError, TypeError):
            payload = {}
        return self._run_sync(payload, ctx)

    __call__ = invoke_sync

    # ── Phase 2 async interface (native) ──────────────────────────

    async def invoke_async(
        self,
        structured_output: dict[str, Any] | None = None,
        ctx: dict | None = None,
    ) -> dict:
        """Native async entry. Phase 2 will wire it directly.

        ``structured_output`` is the shape produced by the
        ``MedicalCodingOutputSchema.to_dict()`` — primary_diagnosis,
        secondary_diagnoses, procedures, confidence, evidence, etc.
        """
        structured_output = structured_output or {}
        ctx = ctx or {}
        try:
            return self._validate(structured_output, ctx)
        except ExpertInvocationError:
            raise
        except Exception as exc:  # translate to ExpertInvocationError
            logger.exception("TabularValidatorExpert: validation failed")
            raise ExpertInvocationError(
                f"TabularValidatorExpert: validation failed "
                f"[{type(exc).__name__}]: {exc}",
                stage="validating",
            ) from exc

    # ── helpers ───────────────────────────────────────────────────

    def _run_sync(self, structured_output: dict, ctx: dict) -> dict:
        async def _invoke() -> dict:
            return await self.invoke_async(structured_output, ctx)
        return asyncio.run(_invoke())

    def _validate(self, structured_output: dict, ctx: dict) -> dict:
        engine = self._engine
        if engine is None:
            # Lazy import to avoid hard dependency at module load
            from compliance_services.rule_engine import RuleEngine
            engine = RuleEngine()

        rule_set = ctx.get("rule_set") or self._rule_set
        result = engine.validate(rule_set, structured_output, ctx or None)

        # Map RuleIssue → plain dict for A2A wire format
        issues = [
            {
                "severity": issue.severity,
                "code": issue.rule_id,
                "message": issue.message,
                "suggestion": issue.suggestion,
            }
            for issue in (result.issues or [])
        ]
        manual_review = any(
            i.get("severity") in {"critical", "high"} for i in issues
        )

        return {
            "passed": result.passed,
            "issues": issues,
            "manual_review_required": manual_review,
            "rule_set": rule_set,
            "fired_rules": list(result.rules_fired or []),
            "quality_flags": dict(result.quality_flags or {}),
            "expert_id": self.EXPERT_ID,
        }


__all__ = ["TabularValidatorExpert"]
