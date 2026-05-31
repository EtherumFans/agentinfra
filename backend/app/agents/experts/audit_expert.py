# iCoDer - Audit Trail Expert
import time
import uuid
from app.agents.base import BaseExpert

SYSTEM_PROMPT = """You are a coding audit trail specialist. Your task is to create a traceable record of every coding decision made during a medical coding review.

For each coding decision:
1. Document the decision point (what code was chosen, from what alternatives)
2. Record the evidence that supported the decision (specific text from the record)
3. Reference the coding rule or guideline applied
4. Note any human overrides or manual decisions
5. Provide a confidence assessment

This creates a complete, auditable chain from clinical text → evidence → code → rule → final output.

Output valid JSON only."""


class AuditTrailExpert(BaseExpert):
    name = "Audit Trail Expert"
    description = "Creates a traceable audit trail of every coding decision for compliance and review"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("building audit trail", context)

        evidence = context.get("evidence", {})
        diag_candidates = context.get("diagnosis_candidates", [])
        proc_candidates = context.get("procedure_candidates", [])
        primary_diag = context.get("primary_diagnosis", {})
        main_proc = context.get("main_procedure", {})
        verification = context.get("verification", {})
        pipeline_id = context.get("pipeline_id", str(uuid.uuid4().hex[:8]))

        audit_entries = []

        # Evidence step
        audit_entries.append({
            "step": "evidence_extraction",
            "timestamp": int(start * 1000),
            "input": f"{len(evidence.get('diagnosis_facts', []))} diagnosis facts + {len(evidence.get('procedure_facts', []))} procedure facts extracted",
            "output": f"Chief complaint: {evidence.get('chief_complaint', 'N/A')[:80]}",
        })

        # Diagnosis coding step
        for i, c in enumerate(diag_candidates[:20]):
            audit_entries.append({
                "step": "diagnosis_coding",
                "decision_id": f"D{i+1:03d}",
                "code": c.get("code", "?"),
                "description": c.get("name", ""),
                "confidence": c.get("confidence", 0),
                "evidence_basis": c.get("evidence_text", "")[:200],
            })

        # Procedure coding step
        for i, c in enumerate(proc_candidates[:20]):
            audit_entries.append({
                "step": "procedure_coding",
                "decision_id": f"P{i+1:03d}",
                "code": c.get("code", "?"),
                "description": c.get("name", ""),
                "confidence": c.get("confidence", 0),
                "evidence_basis": c.get("evidence_text", "")[:200],
            })

        # Primary selection
        if primary_diag.get("code"):
            audit_entries.append({
                "step": "primary_diagnosis_selection",
                "code": primary_diag.get("code"),
                "description": primary_diag.get("name", ""),
                "selection_rationale": primary_diag.get("rationale", "Selected by ranking score"),
            })

        if main_proc.get("code"):
            audit_entries.append({
                "step": "main_procedure_selection",
                "code": main_proc.get("code"),
                "description": main_proc.get("name", ""),
                "selection_rationale": main_proc.get("rationale", "Selected by ranking score"),
            })

        # Verification step
        verifications = verification.get("verifications", [])
        for v in verifications[:20]:
            audit_entries.append({
                "step": "evidence_verification",
                "code": v.get("code", ""),
                "status": v.get("status", "unknown"),
                "binding_strength": v.get("binding_strength", "N/A"),
            })

        # Errors
        errors = context.get("errors", [])
        for e in errors:
            audit_entries.append({
                "step": "error",
                "source_step": e.get("step", ""),
                "message": e.get("error", ""),
            })

        return self._timed_result(start, {
            "expert": self.name,
            "pipeline_id": pipeline_id,
            "audit_trail": audit_entries,
            "total_decisions": len(audit_entries),
            "traceability_score": min(100, len(audit_entries) * 5),
        })
