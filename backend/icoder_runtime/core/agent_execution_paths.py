"""Authoritative dedicated execution paths for Hub-visible official Agents.

Most official Agent Packs execute through ``ProviderA2AHandler`` and their
declared ``backend_provider``.  Five Agents intentionally use richer or
backwards-compatible adapters mounted in ``app.main``.  Keeping this catalog
outside the startup module lets release tooling distinguish a real dedicated
route from the legacy "missing provider -> rule engine" compatibility default.
"""

from __future__ import annotations

from typing import Final


DEDICATED_AGENT_EXECUTION_PATHS: Final[dict[str, dict[str, str]]] = {
    "medical-coding-agent": {
        "execution_path": "dedicated.medical_coding_dispatcher",
        "execution_target": "icoder.medical-coding-runtime.v2",
    },
    "clinical-documentation-improvement-agent": {
        "execution_path": "dedicated.cdi_a2a_handler",
        "execution_target": "icoder.cdi-real-orchestrator.v1",
    },
    "code-validation-agent": {
        "execution_path": "dedicated.governed_code_validation",
        "execution_target": "icoder.governed-code-validation.v1",
    },
    "compliance-guardrail-agent": {
        "execution_path": "dedicated.compliance_mcp",
        "execution_target": "icoder.rule-engine.v1",
    },
    "note-completeness-agent": {
        "execution_path": "dedicated.note_completeness_rules",
        "execution_target": "icoder.documentation-rule-engine.v1",
    },
}


EXTERNAL_LLM_EXECUTION_TARGETS: Final[frozenset[str]] = frozenset({
    "icoder.pure-llm.v1",
    "icoder.llm-with-tools.v1",
    "icoder.cdi-real-orchestrator.v1",
    "icoder.medical-coding-runtime.v2",
})


LOCAL_DETERMINISTIC_EXECUTION_TARGETS: Final[frozenset[str]] = frozenset({
    "icoder.rule-engine.v1",
    "icoder.documentation-rule-engine.v1",
    "icoder.governed-diagnosis-extractor.v1",
    "icoder.governed-drg-dip-risk-review.v1",
    "icoder.governed-claim-check.v1",
    "icoder.governed-clinical-education.v1",
    "icoder.governed-clinical-guidelines.v1",
    "icoder.governed-denial-appeals.v1",
    "icoder.governed-discharge-education.v1",
    "icoder.governed-discharge-summary.v1",
    "icoder.governed-evidence-extractor.v1",
    "icoder.governed-evidence-ranker.v1",
    "icoder.governed-icd-navigator.v1",
    "icoder.governed-icu-summary.v1",
    "icoder.governed-medication-reconciliation.v1",
    "icoder.governed-nursing-handoff.v1",
    "icoder.governed-prior-authorization.v1",
    "icoder.governed-principal-diagnosis-review.v1",
    "icoder.governed-procedure-extractor.v1",
    "icoder.governed-referral.v1",
    "icoder.governed-rule-explainer.v1",
    "icoder.governed-surgical-registry.v1",
    "icoder.governed-triage-questionnaire.v1",
})


OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS: Final[frozenset[str]] = frozenset({
    "icoder.governed-code-validation.v1",
})


LOCAL_BASELINE_EXECUTION_TARGETS: Final[frozenset[str]] = frozenset({
    *LOCAL_DETERMINISTIC_EXECUTION_TARGETS,
    *OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS,
})


def resolve_agent_execution(
    agent_id: str,
    backend_provider: str = "",
) -> dict[str, str]:
    """Return the authoritative execution path and target for one Agent."""
    dedicated = DEDICATED_AGENT_EXECUTION_PATHS.get(agent_id)
    if dedicated is not None:
        return dict(dedicated)
    return {
        "execution_path": "provider_registry",
        "execution_target": str(backend_provider or ""),
    }


def runtime_dependencies_for_target(target: str) -> list[str]:
    """Return deployment dependencies without claiming they are healthy."""
    if target == "icoder.medical-coding-runtime.v2":
        return [
            "external_llm_gateway",
            "medical_coding_retrieval_service_or_validated_native_worker",
        ]
    if target == "icoder.cdi-real-orchestrator.v1":
        return ["external_llm_gateway", "cdi_orchestration_runtime"]
    if target == "icoder.llm-with-tools.v1":
        return ["external_llm_gateway", "mcp_tool_runtime"]
    if target == "icoder.pure-llm.v1":
        return ["external_llm_gateway"]
    if target == "icoder.rule-engine.v1":
        return ["local_rule_engine"]
    if target == "icoder.documentation-rule-engine.v1":
        return ["local_documentation_section_rules"]
    if target == "icoder.governed-code-validation.v1":
        return [
            "local_hash_pinned_icd_catalogs",
            "optional_external_llm_gateway",
            "optional_mcp_tool_runtime",
        ]
    if target == "icoder.governed-claim-check.v1":
        return ["local_documented_claim_and_policy_review"]
    if target == "icoder.governed-clinical-education.v1":
        return ["local_approved_source_clinical_education_policy"]
    if target == "icoder.governed-clinical-guidelines.v1":
        return ["local_approved_guideline_declared_rule_comparison_policy"]
    if target == "icoder.governed-denial-appeals.v1":
        return ["local_documented_denial_appeal_and_corrected_claim_review"]
    if target == "icoder.governed-icd-navigator.v1":
        return ["local_hash_pinned_icd10cn_catalog_and_term_index"]
    if target == "icoder.governed-evidence-ranker.v1":
        return ["local_documentation_grounding_policy"]
    if target == "icoder.governed-evidence-extractor.v1":
        return ["local_hash_pinned_icd10cn_catalog_and_exact_mention_policy"]
    if target == "icoder.governed-diagnosis-extractor.v1":
        return ["local_hash_pinned_icd10cn_catalog_and_explicit_assertion_policy"]
    if target == "icoder.governed-drg-dip-risk-review.v1":
        return [
            "local_hash_pinned_development_drg_dip_risk_rule_pack",
            "authorized_regional_or_hospital_grouper_for_production_gate",
        ]
    if target == "icoder.governed-discharge-education.v1":
        return ["local_documented_discharge_education_policy"]
    if target == "icoder.governed-discharge-summary.v1":
        return ["local_documented_discharge_summary_structuring_policy"]
    if target == "icoder.governed-surgical-registry.v1":
        return ["local_explicit_surgical_registry_extraction_policy"]
    if target == "icoder.governed-procedure-extractor.v1":
        return ["local_hash_pinned_icd9cm3_catalog_and_explicit_status_policy"]
    if target == "icoder.governed-rule-explainer.v1":
        return [
            "local_hash_pinned_icd10cn_catalog",
            "local_catalog_only_rule_explanation_policy",
        ]
    if target == "icoder.governed-medication-reconciliation.v1":
        return ["local_documented_medication_reconciliation_policy"]
    if target == "icoder.governed-nursing-handoff.v1":
        return ["local_documented_nursing_handoff_policy"]
    if target == "icoder.governed-icu-summary.v1":
        return ["local_documented_icu_admission_summary_policy"]
    if target == "icoder.governed-referral.v1":
        return ["local_documented_referral_template_assembly_policy"]
    if target == "icoder.governed-prior-authorization.v1":
        return ["local_documented_prior_authorization_policy"]
    if target == "icoder.governed-principal-diagnosis-review.v1":
        return ["local_documented_principal_draft_evidence_review_policy"]
    if target == "icoder.governed-triage-questionnaire.v1":
        return [
            "local_explicit_triage_questionnaire_path_policy",
            "hospital_approved_triage_protocol_for_production_gate",
        ]
    return ["dedicated_runtime"]


def health_provider_for_target(target: str) -> str:
    """Map dedicated runtimes to the Provider whose config gates execution."""
    if target in {
        "icoder.cdi-real-orchestrator.v1",
        "icoder.medical-coding-runtime.v2",
    }:
        return "icoder.pure-llm.v1"
    return target


__all__ = [
    "DEDICATED_AGENT_EXECUTION_PATHS",
    "EXTERNAL_LLM_EXECUTION_TARGETS",
    "LOCAL_BASELINE_EXECUTION_TARGETS",
    "LOCAL_DETERMINISTIC_EXECUTION_TARGETS",
    "OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS",
    "health_provider_for_target",
    "resolve_agent_execution",
    "runtime_dependencies_for_target",
]
