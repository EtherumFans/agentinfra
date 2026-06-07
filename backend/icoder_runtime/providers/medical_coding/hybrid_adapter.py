"""HybridCodingAdapter — DeepSeekCodingAdapter → RuleEngineAdapter → validated output.

Pipeline:
  1. DeepSeekCodingAdapter (or PromptLLMAdapter as fallback): generate candidate codes
  2. RuleEngineAdapter: validate against local rules
  3. Merge rule issues into coding output
  4. Return MedicalCodingOutputSchema with quality flags

Supports multiple modes:
  - deepseek: DeepSeekCodingAdapter for inference
  - prompt_llm: PromptLLMAdapter for inference (generic LLM via prompt engineering)
  - hybrid: auto-select (deepseek if gateway configured, else prompt_llm)
"""

from __future__ import annotations

import logging
from typing import Any

from icoder_runtime.core.coding_schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema, CodingIssue,
)
from .deepseek_coding_adapter import DeepSeekCodingAdapter
from .prompt_llm_adapter import PromptLLMAdapter
from .rule_engine_adapter import RuleEngineAdapter

logger = logging.getLogger(__name__)


class HybridCodingAdapter(CodingEngineAdapter):
    """Orchestrates coding inference and rule validation.

    Modes:
      - "deepseek": DeepSeek V4 inference + rule validation (production)
      - "prompt_llm": Generic LLM inference + rule validation (fallback)
      - "hybrid": Auto-select (default)

    Pipeline:
      Stage 1: Coding inference (DeepSeekCodingAdapter or PromptLLMAdapter)
      Stage 2: Rule validation (RuleEngineAdapter)
      Stage 3: Merge results with quality flags
    """

    name = "hybrid_coding_adapter"

    def __init__(self, gateway=None, mode: str = "hybrid"):
        self._gateway = gateway
        self._mode = mode  # deepseek | prompt_llm | hybrid | no_repair
        self._rule_adapter = RuleEngineAdapter()
        # Repair is on by default; off in "no_repair" mode (tests + opt-out)
        self._repair_enabled = mode != "no_repair"

        # Resolve inference adapter
        if mode == "deepseek" or mode == "no_repair":
            self._inference = DeepSeekCodingAdapter(gateway=gateway)
        elif mode == "prompt_llm":
            self._inference = PromptLLMAdapter(gateway=gateway)
        else:  # hybrid: auto-select
            self._inference = DeepSeekCodingAdapter(gateway=gateway)

        self._fallback_inference = PromptLLMAdapter(gateway=gateway)

    def _build_repair_messages(
        self, original_messages: list, issues: list,
    ) -> list:
        """Build a follow-up message that includes the rule violations and
        asks the LLM to correct its output. Returns original_messages plus
        a single new user message (so the LLM sees its own prior assistant
        turn + the violation feedback).
        """
        issue_text = "; ".join(
            f"[{i.severity}] {i.code}: {i.message}" for i in issues[:5]
        )
        repair_user = (
            f"你之前的编码输出触发了以下规则违规：\n{issue_text}\n\n"
            f"请重新审查原始病历，输出修正后的 JSON (MedicalCodingOutputSchema 格式)，"
            f"避免重复违规。如果仍不确定，请设置 manual_review_required=true。"
        )
        return list(original_messages) + [{"role": "user", "content": repair_user}]

    def _calibration_input(self, result: MedicalCodingOutputSchema) -> tuple:
        """Convert MedicalCodingOutputSchema to calibrate_all()'s input shape.

        Returns: (diag_candidates, proc_candidates, primary_diagnosis, ...)
        """
        diag_candidates: list[dict] = []
        if result.primary_diagnosis.code:
            diag_candidates.append({
                "code": result.primary_diagnosis.code,
                "name": result.primary_diagnosis.description,
                "score": result.primary_diagnosis.confidence,
                "negation": False,
            })
        for d in result.secondary_diagnoses:
            if d.code:
                diag_candidates.append({
                    "code": d.code,
                    "name": d.description,
                    "score": d.confidence,
                    "negation": False,
                })
        proc_candidates = [
            {
                "code": p.code,
                "name": p.description,
                "score": p.confidence,
                "negation": False,
            }
            for p in result.procedures if p.code
        ]
        primary_diagnosis = {
            "code": result.primary_diagnosis.code,
            "name": result.primary_diagnosis.description,
            "rule_basis": [i.code for i in result.issues_found],
        }
        return diag_candidates, proc_candidates, primary_diagnosis, {}, {}, primary_diagnosis

    def _apply_calibration(self, result: MedicalCodingOutputSchema) -> None:
        """Run calibrate_all and update result.manual_review_required based on
        routing tier. Non-fatal: if calibration fails, log warning and keep
        the result unchanged.
        """
        try:
            from app.services.confidence_calibrator import calibrate_all
            diag_c, proc_c, pd, ev_rank, disagr, pd_reason = self._calibration_input(result)
            cal = calibrate_all(diag_c, proc_c, pd, ev_rank, disagr, pd_reason)
            # Tier check
            escalate = any(r.get("tier") == "escalate" for r in cal.get("routing_decisions", []))
            if escalate:
                result.manual_review_required = True
            # Notes summary
            m = cal.get("metrics", {})
            if m:
                cal_summary = (
                    f"calibration: {m.get('auto_count', 0)}A/"
                    f"{m.get('review_count', 0)}R/"
                    f"{m.get('escalate_count', 0)}E"
                )
                if result.notes:
                    result.notes = f"{result.notes} | {cal_summary}"
                else:
                    result.notes = cal_summary
            # Update confidence with the highest calibrated score across codes
            confs = [c.get("calibrated_score", 0) for c in cal.get("coding_confidences", [])]
            if confs:
                result.confidence = round(max(confs), 3)
        except Exception as e:
            logger.warning(f"HybridCodingAdapter: calibration failed (non-fatal): {e}")

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        # Stage 1: Coding inference
        logger.info(f"HybridCodingAdapter: Stage 1 — {self._inference.name}")
        try:
            result = await self._inference.infer_async(messages, tools, response_schema, context)
        except Exception as e:
            logger.warning(f"Primary inference failed ({self._inference.name}): {e}, trying fallback")
            try:
                result = await self._fallback_inference.infer_async(messages, tools, response_schema, context)
            except Exception as e2:
                logger.error(f"Fallback inference also failed: {e2}")
                return MedicalCodingOutputSchema.mock_result()

        # Stage 2: Rule validation
        logger.info("HybridCodingAdapter: Stage 2 — RuleEngineAdapter")
        rule_result = self._rule_adapter.validate(result)

        # Stage 3: Merge rule issues into output
        result.issues_found = rule_result.issues
        result.manual_review_required = (result.manual_review_required or
                                        rule_result.manual_review_required)

        # Update review_conclusion based on validation
        if rule_result.quality_flags.get("primary_diagnosis_missing"):
            result.review_conclusion = "FAIL"
        elif rule_result.quality_flags.get("invalid_code_format"):
            result.review_conclusion = "FAIL"
        elif rule_result.issues and not result.review_conclusion == "FAIL":
            result.review_conclusion = "WARNING"

        # Annotate notes
        notes_parts = [result.notes] if result.notes else []
        notes_parts.append(f"Rules fired: {len(rule_result.rules_fired)}")
        if rule_result.quality_flags:
            flags_str = ", ".join(f"{k}={v}" for k, v in rule_result.quality_flags.items() if v)
            notes_parts.append(f"Quality flags: {flags_str}")
        result.notes = "; ".join(notes_parts)

        # Stage 4 (Phase 2 of F1 0.76→0.85+): In-process repair loop.
        # The declared MC-R-REPAIR-001 rule says rule violations should
        # trigger a re-prompt. Until now no code implemented that. We
        # do one bounded retry when severity in (critical, high) and
        # the LLM produced a non-trivial output (not just an error
        # schema). Cap is 1 retry (no infinite loop).
        SEVERE = ("critical", "high")
        severe_issues = [i for i in rule_result.issues if i.severity in SEVERE]
        if self._repair_enabled and severe_issues and not result.is_mock:
            result.repair_attempted = True
            result.repair_rounds = 1
            try:
                repair_messages = self._build_repair_messages(messages, severe_issues)
                repaired = await self._inference.infer_async(
                    repair_messages, tools, response_schema, context,
                )
                # Re-validate the repaired output
                repaired_rules = self._rule_adapter.validate(repaired)
                still_severe = [i for i in repaired_rules.issues if i.severity in SEVERE]
                if not still_severe:
                    # Repair cleared the severe issues → accept the new output
                    result = repaired
                    result.repair_attempted = True
                    result.repair_success = True
                    result.repair_rounds = 1
                    result.issues_found = repaired_rules.issues
                    result.manual_review_required = (
                        result.manual_review_required or repaired_rules.manual_review_required
                    )
                    if repaired_rules.quality_flags.get("primary_diagnosis_missing") \
                            or repaired_rules.quality_flags.get("invalid_code_format"):
                        result.review_conclusion = "FAIL"
                    elif repaired_rules.issues:
                        result.review_conclusion = "WARNING"
                    else:
                        result.review_conclusion = "PASS"
                    logger.info(
                        f"HybridCodingAdapter: repair succeeded "
                        f"(severe issues: {len(severe_issues)} → 0)"
                    )
                else:
                    # Repair didn't help — keep original result, mark as failed repair
                    logger.info(
                        f"HybridCodingAdapter: repair did not clear severe issues "
                        f"({len(still_severe)} still severe)"
                    )
            except Exception as e:
                logger.warning(f"HybridCodingAdapter: repair attempt failed: {e}")
                # Keep original result; repair_attempted=True, repair_success=False

        # Stage 5 (Phase 3 of F1 0.76→0.85+): Confidence calibration.
        # Runs after repair so we calibrate the final answer. Sets
        # manual_review_required if any code's tier is "escalate".
        self._apply_calibration(result)

        return result

    def health_check(self) -> dict:
        return {
            "engine": self.name,
            "mode": self._mode,
            "active_inference": self._inference.name,
            "rule_engine": self._rule_adapter.health_check(),
            "status": "healthy",
        }

    @property
    def current_mode(self) -> str:
        return self._mode
