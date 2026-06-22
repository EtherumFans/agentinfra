"""MockCodingAdapter — dictionary-backed deterministic stub for development.

Without an API key the original mock returned a hard-coded I21.0/I10/00.66
triple, which made the F1 metric plateau near zero. The upgraded mock
extracts keywords from the encounter text and returns the top dictionary
hits, so the metric reflects dictionary-relevance (still not a real LLM,
but not a constant either).
"""

from __future__ import annotations

import logging
from typing import Any
from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
    DiagnosisEntry,
)
from .dictionary_rag import lookup_candidate_codes, _extract_user_text

logger = logging.getLogger(__name__)


class MockCodingAdapter(CodingEngineAdapter):
    """Dictionary-backed deterministic mock. is_mock=True."""

    name = "mock_coding_adapter"

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        encounter = _extract_user_text(messages)
        if not encounter:
            return MedicalCodingOutputSchema.mock_result()

        try:
            candidates = await lookup_candidate_codes(encounter, max_total=3)
        except Exception as e:
            logger.warning("MockCodingAdapter: RAG lookup failed, using fixed mock: %s", e)
            return MedicalCodingOutputSchema.mock_result()

        if not candidates:
            return MedicalCodingOutputSchema.mock_result()

        result = MedicalCodingOutputSchema.mock_result()
        top = candidates[0]
        result.primary_diagnosis = DiagnosisEntry(
            code=top.get("code", "I21.0"),
            description=top.get("name", ""),
            confidence=min(0.9, max(0.6, top.get("score", 0.5))),
            category="principal",
            evidence=[encounter[:30]] if encounter else [],
        )
        # 1-2 secondary from next candidates
        result.secondary_diagnoses = [
            DiagnosisEntry(
                code=c.get("code", ""),
                description=c.get("name", ""),
                confidence=min(0.85, max(0.5, c.get("score", 0.5))),
                category="comorbidity",
                evidence=[encounter[:30]] if encounter else [],
            )
            for c in candidates[1:3] if c.get("code")
        ]
        result.confidence = min(0.9, max(0.6, top.get("score", 0.5)))
        result.notes = (
            f"MockCodingAdapter: dictionary-backed stub, top={top.get('code', '')} "
            f"({len(candidates)} candidates)"
        )
        return result

    def health_check(self) -> dict:
        return {"engine": self.name, "status": "healthy", "mode": "mock-dict"}
