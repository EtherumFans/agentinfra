# iCoDer - HCC Risk Adjustment Expert
import time
from app.agents.base import BaseExpert

SYSTEM_PROMPT = """You are a Hierarchical Condition Category (HCC) risk adjustment coding specialist.
Your task is to identify and validate HCC-relevant diagnoses for risk adjustment purposes.

Key responsibilities:
1. Map ICD-10-CN codes to HCC categories
2. Identify missed HCC opportunities in clinical documentation
3. Validate existing HCC assignments against documentation
4. Assess RAF (Risk Adjustment Factor) score impact
5. Recommend documentation improvements for HCC capture

Chinese context:
- China's evolving risk adjustment models for insurance
- DRG/DIP payment system interaction with risk adjustment
- Chronic disease management programs

Output valid JSON only."""


class HCCRiskAdjustmentExpert(BaseExpert):
    name = "HCC Risk Adjustment Expert"
    description = "Maps diagnoses to HCC categories and identifies risk adjustment opportunities"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("analyzing HCC categories", context)

        evidence = context.get("evidence", {})
        diag_candidates = context.get("diagnosis_candidates", [])
        primary_diag = context.get("primary_diagnosis", {})
        secondary_diags = context.get("secondary_diagnoses", [])

        all_diagnoses = [primary_diag] if primary_diag.get("code") else []
        all_diagnoses.extend(secondary_diags)

        # Build analysis text
        lines = []
        lines.append("Diagnoses for HCC analysis:")
        for d in all_diagnoses:
            lines.append(f"  {d.get('code', '?')}: {d.get('name', '')} (confidence: {d.get('confidence', 0)})")
        if not all_diagnoses:
            for c in diag_candidates:
                lines.append(f"  [Candidate] {c.get('code', '?')}: {c.get('name', '')} (score: {c.get('score', 0)})")

        text_input = "\n".join(lines)
        if not text_input.strip():
            return self._timed_result(start, {
                "expert": self.name,
                "hcc_mappings": [],
                "missed_opportunities": [],
                "raf_estimate": {"score": 0, "detail": "No diagnoses available"},
                "documentation_gaps": [],
            })

        schema_hint = """{
  "hcc_mappings": [
    {"code": "ICD-10 code", "hcc_category": "HCC category number", "hcc_name": "category name", "raf_weight": 0.0}
  ],
  "missed_opportunities": [
    {"condition": "condition from documentation", "potential_code": "more specific code", "hcc_impact": "how this would affect RAF"}
  ],
  "raf_estimate": {"score": 0.0, "detail": "explanation"},
  "documentation_gaps": ["specific documentation improvements needed"]
}"""

        try:
            result = await self.llm.extract_json(
                SYSTEM_PROMPT,
                text_input,
                schema_hint,
            )
        except Exception as e:
            self._log_step(f"LLM HCC analysis failed: {e}", context)
            result = {"hcc_mappings": [], "missed_opportunities": [], "raf_estimate": {"score": 0, "detail": ""}, "documentation_gaps": []}

        return self._timed_result(start, {
            "expert": self.name,
            "hcc_mappings": result.get("hcc_mappings", []),
            "missed_opportunities": result.get("missed_opportunities", []),
            "raf_estimate": result.get("raf_estimate", {"score": 0}),
            "documentation_gaps": result.get("documentation_gaps", []),
        })
