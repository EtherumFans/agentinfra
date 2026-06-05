# iCoDer - CDI (Clinical Documentation Improvement) Expert
import time
from app.agents.base import BaseExpert

SYSTEM_PROMPT = """你是中国住院病历临床文书改进（CDI）专家。
你的任务是审查临床文书并提出改进建议，以实现更精准的编码。

For each documentation gap found:
1. Identify the specific missing information
2. Explain how it impacts coding specificity
3. Suggest the exact question to ask the clinician
4. Estimate the DRG/payment impact of improved documentation

Focus areas:
- Diagnosis specificity (anatomical site, laterality, etiology, severity)
- Procedure specificity (approach, devices, extent)
- Complication/Comorbidity (CC/MCC) capture
- Cause-and-effect relationships (e.g., manifestations of underlying disease)
- Present on Admission (POA) indicators

Output valid JSON only."""


class CDIExpert(BaseExpert):
    name = "CDI Expert"
    description = "Reviews clinical documentation and suggests improvements for more specific and accurate coding"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("reviewing documentation", context)

        evidence = context.get("evidence", {})
        diag_facts = evidence.get("diagnosis_facts", [])
        proc_facts = evidence.get("procedure_facts", [])
        candidates = context.get("diagnosis_candidates", []) + context.get("procedure_candidates", [])

        # Build a summary of current state for the LLM
        summary_lines = []
        summary_lines.append("Current diagnosis facts:")
        for f in diag_facts[:10]:
            summary_lines.append(f"  - {f.get('finding', '')}: site={f.get('body_site', '')}, certainty={f.get('certainty', '?')}")
        summary_lines.append("\nCurrent procedure facts:")
        for f in proc_facts[:10]:
            summary_lines.append(f"  - {f.get('procedure_name', '')}: site={f.get('body_site', '')}, approach={f.get('approach', '')}")

        schema_hint = """{
  "recommendations": [
    {
      "target": "diagnosis or procedure name",
      "gap": "what is missing (laterality/site/etiology/severity/approach/etc.)",
      "impact": "how this affects coding specificity",
      "query": "specific question to ask the clinician",
      "drg_impact": "low/medium/high - estimated payment impact"
    }
  ],
  "overall_assessment": "summary of documentation quality",
  "priority_items": ["top 3 most impactful queries"]
}"""

        text_input = "\n".join(summary_lines)
        if not text_input.strip():
            return self._timed_result(start, {
                "expert": self.name,
                "recommendations": [],
                "overall_assessment": "No documentation to review",
                "priority_items": [],
            })

        try:
            result = await self.llm.extract_json(
                SYSTEM_PROMPT,
                text_input,
                schema_hint,
            )
        except Exception as e:
            self._log_step(f"LLM CDI failed: {e}", context)
            result = {"recommendations": [], "overall_assessment": "Error", "priority_items": []}

        return self._timed_result(start, {
            "expert": self.name,
            "recommendations": result.get("recommendations", []),
            "overall_assessment": result.get("overall_assessment", ""),
            "priority_items": result.get("priority_items", []),
        })
