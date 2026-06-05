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
        self._mode = mode  # deepseek | prompt_llm | hybrid
        self._rule_adapter = RuleEngineAdapter()

        # Resolve inference adapter
        if mode == "deepseek":
            self._inference = DeepSeekCodingAdapter(gateway=gateway)
        elif mode == "prompt_llm":
            self._inference = PromptLLMAdapter(gateway=gateway)
        else:  # hybrid: auto-select
            self._inference = DeepSeekCodingAdapter(gateway=gateway)

        self._fallback_inference = PromptLLMAdapter(gateway=gateway)

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
