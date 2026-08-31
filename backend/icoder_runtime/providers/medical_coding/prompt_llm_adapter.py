"""PromptLLMAdapter — uses any LLMGateway provider to generate coding via prompt engineering."""

from __future__ import annotations

import json
import logging
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
)
from .dictionary_rag import (
    lookup_candidate_codes,
    format_candidates_block,
    _extract_user_text,
)
from .project_policy import apply_medical_coding_project_policy

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

    async def _build_prompt_with_candidates(self, base_prompt: str, encounter_text: str) -> str:
        """RAG injection — same pattern as DeepSeekCodingAdapter."""
        if not encounter_text:
            return base_prompt
        try:
            candidates = await lookup_candidate_codes(encounter_text, max_total=8)
        except Exception as e:
            logger.warning(f"PromptLLMAdapter: RAG lookup failed: {e}")
            return base_prompt
        block = format_candidates_block(candidates)
        if not block:
            return base_prompt
        return f"{base_prompt}\n\n{block}"

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        if not self._gateway or not self._gateway.is_configured:
            logger.warning("PromptLLMAdapter: no gateway configured; failing closed")
            return MedicalCodingOutputSchema.failure_result(
                self.name, reason="gateway_unavailable"
            )

        # RAG injection
        encounter_text = _extract_user_text(messages)
        system_prompt = await self._build_prompt_with_candidates(self._system_prompt, encounter_text)
        system_prompt = apply_medical_coding_project_policy(
            system_prompt,
            str((context or {}).get("project_policy") or ""),
        )
        full_messages = [{"role": "system", "content": system_prompt}] + list(messages)

        try:
            result = await self._gateway.generate(full_messages)
            content = result.get("content", "")
            gateway_mock = bool(result.get("degraded") or result.get("is_mock"))
            if gateway_mock:
                return MedicalCodingOutputSchema.failure_result(
                    self.name,
                    reason=result.get("degraded_reason") or "mock_provider",
                )
            if not isinstance(content, str) or not content.strip().startswith("{"):
                return MedicalCodingOutputSchema.failure_result(
                    self.name, reason="invalid_llm_response"
                )
            data = json.loads(content)
            if not isinstance(data, dict) or not data:
                return MedicalCodingOutputSchema.failure_result(
                    self.name, reason="invalid_llm_schema"
                )
            schema = MedicalCodingOutputSchema.from_dict(
                data,
                provider="prompt_llm_adapter",
                is_mock=False,
            )
            return schema
        except json.JSONDecodeError:
            logger.warning("PromptLLMAdapter: LLM returned invalid JSON; failing closed")
            return MedicalCodingOutputSchema.failure_result(
                self.name, reason="invalid_json"
            )
        except Exception as exc:
            logger.error(
                "PromptLLMAdapter: LLM call failed error_type=%s",
                type(exc).__name__,
            )
            return MedicalCodingOutputSchema.failure_result(
                self.name, reason="llm_call_failed"
            )

    def health_check(self) -> dict:
        status = "no_gateway"
        provider = ""
        if self._gateway and self._gateway.is_configured:
            try:
                selected = self._gateway.get()
                provider = getattr(selected, "name", "")
                status = (
                    "degraded"
                    if selected.__class__.__name__ == "MockLLMProvider"
                    else "configured"
                )
            except Exception:
                status = "no_gateway"
        return {
            "engine": self.name,
            "status": status,
            "provider": provider,
        }
