"""PromptLLMAdapter — uses any LLMGateway provider to generate coding via prompt engineering."""

from __future__ import annotations

import json
import logging
from typing import Any

from icoder_runtime.core.coding_schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
)

logger = logging.getLogger(__name__)

CODING_SYSTEM_PROMPT = """You are a medical coding auditor for Chinese hospitals (医保结算清单 and 病案首页).
Review the patient encounter and return ONLY a JSON object with this exact structure:

{
  "review_conclusion": "PASS" | "WARNING" | "FAIL",
  "primary_diagnosis": {"code": "ICD-10 code", "description": "Chinese description", "confidence": 0.0-1.0, "category": "principal", "evidence": ["quote from medical record"]},
  "secondary_diagnoses": [{"code": "...", "description": "...", "confidence": 0.0-1.0, "category": "comorbidity|complication", "evidence": [...]}],
  "procedures": [{"code": "ICD-9-CM-3 code", "description": "...", "confidence": 0.0-1.0, "category": "principal|secondary", "evidence": [...]}],
  "issues_found": [{"severity": "critical|high|medium|low|info", "code": "rule code", "message": "Chinese description", "suggestion": "fix suggestion"}],
  "drg_suggestion": "DRG code or empty string",
  "dip_suggestion": "DIP code or empty string",
  "manual_review_required": true|false,
  "confidence": 0.0-1.0
}

Rules:
- ICD-10 codes must match pattern [A-Z][0-9]{2}(\\.[0-9]{1,4})?
- Primary diagnosis code cannot be empty
- Evidence must quote actual text from the medical record
- If uncertain, set manual_review_required=true and lower confidence
"""


class PromptLLMAdapter(CodingEngineAdapter):
    """Uses an LLM (via LLMGateway) with a medical coding prompt to generate results.

    This is a bridge between "no coding model" and "dedicated coding engine."
    While not as precise as a fine-tuned model, it provides real inference
    rather than hardcoded mock data.
    """

    name = "prompt_llm_adapter"

    def __init__(self, gateway=None, system_prompt: str = ""):
        self._gateway = gateway
        self._system_prompt = system_prompt or CODING_SYSTEM_PROMPT

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        if not self._gateway or not self._gateway.is_configured:
            logger.warning("PromptLLMAdapter: no gateway configured, falling back to mock")
            return MedicalCodingOutputSchema.mock_result()

        full_messages = [{"role": "system", "content": self._system_prompt}] + list(messages)

        try:
            result = await self._gateway.generate(full_messages)
            content = result.get("content", "")
            data = json.loads(content) if isinstance(content, str) and content.strip().startswith("{") else {}
            return MedicalCodingOutputSchema.from_dict(
                data,
                provider="prompt_llm_adapter",
                is_mock=False,
            )
        except json.JSONDecodeError:
            logger.warning("PromptLLMAdapter: LLM returned non-JSON, returning mock")
            return MedicalCodingOutputSchema.mock_result()
        except Exception as e:
            logger.error(f"PromptLLMAdapter: LLM call failed: {e}")
            return MedicalCodingOutputSchema.mock_result()

    def health_check(self) -> dict:
        return {
            "engine": self.name,
            "status": "configured" if self._gateway and self._gateway.is_configured else "no_gateway",
        }
