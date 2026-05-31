"""Context Scoping — give each Expert only the context it needs.

iCoDer Agentic Framework equivalent: "The Orchestrator has full access to the context,
while Experts typically only have scoped access to relevant portions."

This prevents Experts from:
- Seeing unrelated patient data (privacy)
- Getting confused by irrelevant context (accuracy)
- Exceeding token limits (cost)
"""
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Expert context scoping rules — which context fields each expert needs
EXPERT_SCOPES = {
    "EvidenceExtractionExpert": {
        "required": ["documents"],
        "optional": ["existing_diagnosis_codes", "existing_procedure_codes"],
        "max_text_length": 10000,
    },
    "TimelineReconstructionExpert": {
        "required": ["documents"],
        "optional": [],
        "max_text_length": 10000,
    },
    "ICDDiagnosisExpert": {
        "required": ["evidence", "existing_diagnosis_codes"],
        "optional": ["documents"],
        "max_text_length": 5000,
    },
    "ProcedureCodingExpert": {
        "required": ["evidence", "existing_procedure_codes"],
        "optional": ["documents"],
        "max_text_length": 5000,
    },
    "MedicalRecordHomepageExpert": {
        "required": ["diagnosis_candidates", "procedure_candidates", "existing_diagnosis_codes", "existing_procedure_codes"],
        "optional": ["documents", "evidence", "timeline", "admission_reason"],
    },
    "EvidenceVerificationExpert": {
        "required": ["evidence", "diagnosis_candidates", "procedure_candidates"],
        "optional": ["documents"],
    },
    "DRGDIPExpert": {
        "required": ["primary_diagnosis", "main_procedure", "diagnosis_candidates", "procedure_candidates"],
        "optional": ["documents"],
    },
    "DocumentationGapExpert": {
        "required": ["evidence", "documents"],
        "optional": ["diagnosis_candidates"],
        "max_text_length": 8000,
    },
    "ReportExpert": {
        "required": [],  # Report expert gets everything
        "optional": [],
    },
}


class ContextScoper:
    """Scopes context for each Expert, limiting what data they can access."""

    def scope_for(self, expert_name: str, full_context: dict) -> dict:
        """Create a scoped context for a specific Expert.

        Args:
            expert_name: Class name of the expert (e.g., 'ICDDiagnosisExpert')
            full_context: The full Orchestrator context

        Returns:
            Scoped context with only the fields that Expert needs
        """
        scope = EXPERT_SCOPES.get(expert_name, {})
        if not scope:
            # Unknown expert — give everything (safety: don't break existing code)
            return full_context

        scoped = {}
        for field in scope.get("required", []):
            if field in full_context:
                scoped[field] = self._trim_field(field, full_context[field], scope)

        for field in scope.get("optional", []):
            if field in full_context:
                trimmed = self._trim_field(field, full_context[field], scope)
                # Only include if non-empty
                if trimmed is not None and (not isinstance(trimmed, (list, dict)) or trimmed):
                    scoped[field] = trimmed

        # Always include metadata
        for meta_key in ["pipeline_id", "encounter_id", "agent_version", "model_used"]:
            if meta_key in full_context:
                scoped[meta_key] = full_context[meta_key]

        return scoped

    def _trim_field(self, field_name: str, value: any, scope: dict) -> any:
        """Trim large text fields to respect max_text_length."""
        max_length = scope.get("max_text_length")
        if max_length and isinstance(value, str):
            return value[:max_length]
        if max_length and isinstance(value, list):
            return [self._trim_list_item(item, max_length) for item in value[:20]]
        return value

    def _trim_list_item(self, item: any, max_length: int) -> any:
        """Trim individual items in a list."""
        if isinstance(item, dict):
            trimmed = {}
            for k, v in item.items():
                if isinstance(v, str) and len(v) > max_length // 5:
                    trimmed[k] = v[:max_length // 5] + "..."
                else:
                    trimmed[k] = v
            return trimmed
        if isinstance(item, str):
            return item[:max_length // 5] + ("..." if len(item) > max_length // 5 else "")
        return item

    def get_scope_report(self, full_context: dict) -> dict:
        """Generate a report showing what each expert would see."""
        report = {}
        for expert_name, scope in EXPERT_SCOPES.items():
            scoped = self.scope_for(expert_name, full_context)
            original_keys = set(full_context.keys())
            scoped_keys = set(scoped.keys())
            report[expert_name] = {
                "fields_available": len(scoped_keys),
                "fields_hidden": len(original_keys - scoped_keys),
                "hidden_fields": sorted(original_keys - scoped_keys),
            }
        return report


context_scoper = ContextScoper()
