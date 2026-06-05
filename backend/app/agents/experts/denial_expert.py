# iCoDer - Denial Management Expert
import time
from app.agents.base import BaseExpert

SYSTEM_PROMPT = """你是中国医保拒付管理专家。
你的任务是分析医保拒付并生成基于证据的申诉材料。

For each denial scenario:
1. Identify the root cause (coding error, medical necessity, documentation gap, policy mismatch)
2. Analyze the clinical documentation for supporting evidence
3. Generate a structured appeal letter with specific evidence citations
4. Assess the likelihood of successful appeal

Chinese insurance context:
- DRG/DIP payment systems
- National Healthcare Security Administration (NHSA) rules
- Local insurance fund policies
- Medical necessity criteria per Chinese clinical guidelines

Output valid JSON only."""


class DenialManagementExpert(BaseExpert):
    name = "Denial Management Expert"
    description = "Analyzes insurance claim denials and generates evidence-based appeal letters"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("analyzing denial", context)

        evidence = context.get("evidence", {})
        primary_diag = context.get("primary_diagnosis", {})
        main_proc = context.get("main_procedure", {})
        drg_impact = context.get("drg_impact", {})
        report = context.get("report_markdown", "")

        summary = []
        summary.append(f"Primary diagnosis: {primary_diag.get('code', 'N/A')} - {primary_diag.get('name', '')}")
        summary.append(f"Main procedure: {main_proc.get('code', 'N/A')} - {main_proc.get('name', '')}")
        summary.append(f"DRG risks: {len(drg_impact.get('drg_risks', []))}")
        if evidence:
            summary.append(f"Evidence: {len(evidence.get('diagnosis_facts', []))} diagnosis facts, {len(evidence.get('procedure_facts', []))} procedure facts")

        text_input = "\n".join(summary)
        if not text_input.strip():
            return self._timed_result(start, {
                "expert": self.name,
                "denial_analysis": [],
                "appeal_letter": "",
                "success_probability": "N/A",
            })

        schema_hint = """{
  "denial_analysis": [
    {
      "denial_reason": "reason for potential denial",
      "root_cause": "coding_error|medical_necessity|documentation_gap|policy_mismatch",
      "supporting_evidence": "specific text from medical record",
      "corrective_action": "what to fix"
    }
  ],
  "appeal_letter": "full appeal letter text",
  "success_probability": "high|medium|low",
  "recommendations": ["preventive measures"]
}"""

        try:
            result = await self.llm.extract_json(
                SYSTEM_PROMPT,
                text_input,
                schema_hint,
            )
        except Exception as e:
            self._log_step(f"LLM denial analysis failed: {e}", context)
            result = {"denial_analysis": [], "appeal_letter": "", "success_probability": "N/A", "recommendations": []}

        return self._timed_result(start, {
            "expert": self.name,
            "denial_analysis": result.get("denial_analysis", []),
            "appeal_letter": result.get("appeal_letter", ""),
            "success_probability": result.get("success_probability", "N/A"),
            "recommendations": result.get("recommendations", []),
        })
