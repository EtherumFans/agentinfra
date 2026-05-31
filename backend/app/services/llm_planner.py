"""LLM Planner — intelligent step planning for the Agent Orchestrator.

iCoDer Agentic Framework equivalent: the Orchestrator's reasoning & planning layer.
Instead of a fixed pipeline, the LLM analyzes each request and determines which
experts to invoke and in what order.
"""
import json
import logging
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# Fixed pipeline step list — used as fallback and for LLM context
FIXED_PIPELINE_STEPS = [
    {
        "step": "evidence_extraction",
        "expert": "EvidenceExtractionExpert",
        "description": "Extract structured clinical facts from raw medical record text",
        "always_required": True,
    },
    {
        "step": "timeline_reconstruction",
        "expert": "TimelineReconstructionExpert",
        "description": "Reconstruct chronological clinical event timeline from all documents",
        "requires_evidence": True,
    },
    {
        "step": "diagnosis_coding",
        "expert": "ICDDiagnosisExpert",
        "description": "Map diagnosis facts to ICD-10 codes using code dictionary + LLM",
        "requires_evidence": True,
    },
    {
        "step": "procedure_coding",
        "expert": "ProcedureCodingExpert",
        "description": "Map procedure facts to ICD-9-CM-3 codes using code dictionary + LLM",
        "requires_evidence": True,
    },
    {
        "step": "homepage_ranking",
        "expert": "MedicalRecordHomepageExpert",
        "description": "Rank candidates, select primary diagnosis and main procedure, validate existing codes against rules",
        "requires_candidates": True,
    },
    {
        "step": "evidence_verification",
        "expert": "EvidenceVerificationExpert",
        "description": "Verify every code has supporting evidence, assign support status",
        "requires_candidates": True,
    },
    {
        "step": "evidence_ranking",
        "expert": "EvidenceRanker",
        "description": "Rank evidence by strength, detect unsupported codes and evidence conflicts",
        "requires_verification": True,
    },
    {
        "step": "disagreement_analysis",
        "expert": "DisagreementAnalyzer",
        "description": "Classify AI vs gold/existing coding disagreements, detect DRG-sensitive corrections",
        "requires_candidates": True,
    },
    {
        "step": "confidence_calibration",
        "expert": "ConfidenceCalibrator",
        "description": "Multi-source confidence calibration + selective automation routing (auto/review/escalate)",
        "requires_verification": True,
    },
    {
        "step": "drg_analysis",
        "expert": "DRGDIPExpert",
        "description": "DRG/DIP risk analysis, detect unspecified codes, missing MCC/CC, mismatches",
        "requires_homepage": True,
    },
    {
        "step": "doc_gap_analysis",
        "expert": "DocumentationGapExpert",
        "description": "Identify specificity gaps, missing anatomical sites, missing etiology",
        "requires_evidence": True,
    },
    {
        "step": "report_generation",
        "expert": "ReportExpert",
        "description": "Generate Markdown + HTML coding audit report",
        "always_required": True,
    },
]

PLANNER_SYSTEM_PROMPT = """You are an intelligent medical coding pipeline planner. Given a clinical encounter,
determine which expert steps should be executed and in what order.

Available steps:
{step_descriptions}

Analyze the encounter and return a JSON plan:
{{
  "reasoning": "Why these steps were chosen (or skipped)",
  "steps": [
    {{
      "step": "step_name",
      "expert": "ExpertClassName",
      "reason": "Why this step is needed for this encounter",
      "priority": "required|optional|skip"
    }}
  ]
}}

Planning rules:
1. evidence_extraction is ALWAYS required (text must be parsed first)
2. Skip diagnosis_coding if there are no diagnosis-related facts in the text
3. Skip procedure_coding if there are no surgical/procedure descriptions
4. Skip drg_analysis if this is an outpatient encounter (no DRG grouping)
5. Skip doc_gap_analysis if documentation appears complete
6. report_generation is ALWAYS required (output needed)
7. For short/simple encounters, skip steps that add no value
8. For complex multi-diagnosis encounters, include ALL steps

Be decisive — it's better to skip a step that isn't needed than to waste time and credits."""


class LLMPlanner:
    """LLM-powered pipeline planner that replaces the fixed 9-step execution.

    The planner analyzes the encounter content and decides which experts
    are needed, in what order. This is the iCoDer-style intelligent orchestration.
    """

    def __init__(self):
        self.step_descriptions = "\n".join(
            f"- {s['step']} ({s['expert']}): {s['description']}"
            for s in FIXED_PIPELINE_STEPS
        )

    async def plan(self, encounter_text: str, encounter_metadata: dict | None = None) -> dict:
        """Generate a dynamic execution plan for an encounter.

        Returns a dict with 'reasoning' and 'steps' — a prioritized list of
        expert steps to execute.
        """
        metadata_str = ""
        if encounter_metadata:
            parts = []
            if encounter_metadata.get("department"):
                parts.append(f"Department: {encounter_metadata['department']}")
            if encounter_metadata.get("existing_diagnosis_codes"):
                codes = encounter_metadata["existing_diagnosis_codes"]
                parts.append(f"Existing diagnosis codes: {len(codes)} codes")
            if encounter_metadata.get("existing_procedure_codes"):
                codes = encounter_metadata["existing_procedure_codes"]
                parts.append(f"Existing procedure codes: {len(codes)} codes")
            if parts:
                metadata_str = "Encounter metadata:\n" + "\n".join(parts) + "\n\n"

        user_prompt = f"""{metadata_str}Clinical text:
{encounter_text[:3000]}

Plan the pipeline steps for this encounter."""

        prompt = PLANNER_SYSTEM_PROMPT.format(step_descriptions=self.step_descriptions)

        try:
            result = await llm_service.extract_json(
                prompt=prompt,
                text=user_prompt,
                schema_hint="plan with steps array"
            )
            if isinstance(result, dict) and "steps" in result:
                logger.info(f"LLM Planner: {result.get('reasoning', '')[:100]}")
                return result
        except Exception as e:
            logger.warning(f"LLM Planner failed, using fixed pipeline: {e}")

        # Fallback: return all steps
        return self._fallback_plan()

    def _fallback_plan(self) -> dict:
        """Return the fixed 9-step pipeline as a fallback plan."""
        return {
            "reasoning": "Using fixed pipeline (LLM planning unavailable)",
            "steps": [
                {"step": s["step"], "expert": s["expert"], "priority": "required"}
                for s in FIXED_PIPELINE_STEPS
            ],
            "fallback": True,
        }

    async def compare_plans(self, encounter_text: str) -> dict:
        """Compare fixed vs dynamic plan for evaluation purposes."""
        fixed = self._fallback_plan()
        dynamic = await self.plan(encounter_text)

        fixed_count = len(fixed["steps"])
        dynamic_steps = dynamic.get("steps", [])
        active_steps = [s for s in dynamic_steps if s.get("priority") != "skip"]
        skipped = fixed_count - len(active_steps)

        return {
            "fixed_pipeline": {"step_count": fixed_count},
            "dynamic_plan": {
                "total_steps": len(dynamic_steps),
                "active_steps": len(active_steps),
                "skipped": [s["step"] for s in dynamic_steps if s.get("priority") == "skip"],
                "reasoning": dynamic.get("reasoning", ""),
                "savings": f"{skipped} steps saved" if skipped > 0 else "no savings",
            },
        }


llm_planner = LLMPlanner()
