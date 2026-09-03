"""Derive reviewed recursive schemas for Hub-visible Agent Pack outputs.

Only the small schema subset enforced by ``output_contract_validation`` is
emitted. Checked-in examples provide the normal path; explicit overrides
cover legitimate arrays that are empty in the sample so the command never
silently emits an unconstrained ``items`` schema. Dry-run is the default.
Reviewed ``field_relations`` add bounded cross-field implications without
deriving clinical truth from examples.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
INTEGRITY_EXCLUDED_FIELDS = {
    "integrity", "downloads", "published_at", "loaded_at", "_pack_mtime_iso",
}
MAX_STRING_LENGTH = 32_768
MAX_ARRAY_ITEMS = 100

ENUM_OVERRIDES: dict[tuple[str, str], list[str]] = {
    ("drg-analyzer", "review_status"): [
        "INPUT_REQUIRED", "EVIDENCE_REVIEW_REQUIRED",
        "READY_FOR_CODER_REVIEW", "RUNTIME_FAILED",
    ],
    ("drg-analyzer", "review_conclusion"): [
        "NOT_ASSESSABLE", "WARNING", "FAIL",
    ],
    ("drg-analyzer", "coded_case.patient_gender.documented_text"): ["", "M", "F"],
    ("drg-analyzer", "coded_case.primary_diagnosis.evidence_status"): [
        "NOT_PROVIDED", "EXACT_INPUT_SPAN",
    ],
    ("drg-analyzer", "development_candidate_group.result_status"): [
        "NOT_ASSESSED", "EXPERIMENTAL_UNVERIFIED_CANDIDATE",
    ],
    ("drg-analyzer", "dip_review.status"): [
        "NOT_ASSESSED", "NO_AUTHORIZED_REGIONAL_DIP_PACK",
    ],
    ("drg-analyzer", "risk_findings[].severity"): [
        "critical", "high", "medium", "low", "info",
    ],
    ("triage", "assessment_status"): [
        "INPUT_REQUIRED", "PROTOCOL_INVALID", "CONFLICT_REVIEW_REQUIRED",
        "READY_FOR_ONSITE_REVIEW",
    ],
    ("triage", "acuity_level"): [
        "NOT_ASSIGNED", "DEVELOPMENT_PROTOCOL_CANDIDATE_IMMEDIATE",
        "DEVELOPMENT_PROTOCOL_CANDIDATE_URGENT",
        "DEVELOPMENT_PROTOCOL_CANDIDATE_STANDARD",
        "DEVELOPMENT_PROTOCOL_CANDIDATE_LOWER_ACUITY",
    ],
    ("triage", "protocol_governance.declared_status"): [
        "", "DEVELOPMENT_FIXTURE", "HOSPITAL_APPROVED_ATTESTED",
    ],
    ("triage", "protocol_governance.verification_status"): [
        "NOT_VERIFIED", "DEVELOPMENT_ONLY_UNVERIFIED",
        "CALLER_DECLARED_APPROVAL_NOT_PLATFORM_VERIFIED",
    ],
    ("triage", "protocol_candidate.candidate_level"): [
        "NOT_ASSIGNED", "IMMEDIATE", "URGENT", "STANDARD", "LOWER_ACUITY",
    ],
    ("triage", "protocol_candidate.result_status"): [
        "NOT_ASSESSED", "DEVELOPMENT_UNVERIFIED_PROTOCOL_CANDIDATE",
    ],
    ("triage", "decision_path[].answer_type"): ["boolean", "number", "enum"],
    ("triage", "decision_path[].matched_operator"): [
        "equals", "in", "lt", "lte", "gt", "gte", "default",
    ],
    ("triage", "evidence_items[].evidence_status"): ["EXACT_INPUT_SPAN"],
    ("claim-check", "review_status"):
        ["INPUT_REQUIRED", "POLICY_REQUIRED", "READY_FOR_REVIEW"],
    ("claim-check", "policy_evaluation_status"):
        ["POLICY_NOT_PROVIDED", "DOCUMENTED_POLICY_INCOMPLETE", "DOCUMENTED_POLICY_ONLY"],
    ("claim-check", "evidence_items[].field"): [
        "claim_id", "encounter_id", "claim_type", "service_date",
        "patient_name", "member_id", "facility", "provider_name",
        "provider_identifier", "payer_name", "plan_name", "payer_region",
        "billed_diagnoses", "billed_procedures", "billed_items",
        "total_billed_amount", "currency", "clinical_documentation",
        "payer_requirements", "policy_identifier", "policy_version",
        "policy_effective_date", "policy_source", "denial_reason",
    ],
    ("denial-appeals", "appeal_status"): [
        "INPUT_REQUIRED", "PATH_REVIEW_REQUIRED", "POLICY_REQUIRED",
        "READY_FOR_REVIEW",
    ],
    ("denial-appeals", "resolution_path_status"): [
        "RESOLUTION_PATH_NOT_PROVIDED", "DOCUMENTED_PATH_ONLY",
    ],
    ("denial-appeals", "policy_evaluation_status"): [
        "POLICY_NOT_PROVIDED", "DOCUMENTED_POLICY_INCOMPLETE",
        "DOCUMENTED_POLICY_ONLY",
    ],
    ("denial-appeals", "evidence_items[].field"): [
        "claim_id", "denial_notice_id", "denial_date", "service_date",
        "denial_reason_code", "denial_reason_description",
        "documented_denial_category", "denied_amount", "currency",
        "appeal_deadline", "appeal_level", "submission_channel",
        "patient_name", "member_id", "provider_name", "provider_identifier",
        "facility", "provider_contact", "payer_name", "plan_name",
        "payer_type", "payer_region", "managing_agency",
        "denied_claim_lines", "denied_diagnoses", "denied_procedures",
        "denied_items", "clinical_documentation", "submitted_documents",
        "prior_authorization_information", "eligibility_information",
        "payer_requirements", "policy_identifier", "policy_version",
        "policy_effective_date", "policy_source", "resolution_path",
        "requested_resolution", "documented_corrections",
    ],
    ("clinical-education", "education_status"): [
        "INPUT_REQUIRED", "SOURCE_REVIEW_REQUIRED", "READY_FOR_REVIEW",
    ],
    ("clinical-education", "source_sufficiency_status"): [
        "SOURCE_NOT_PROVIDED", "SOURCE_METADATA_OR_APPROVAL_INCOMPLETE",
        "DOCUMENTED_SOURCE_SCOPE_LIMITED", "DOCUMENTED_SOURCE_READY_FOR_REVIEW",
    ],
    ("clinical-education", "evidence_items[].field"): [
        "topic", "audience", "response_mode", "learner_level",
        "source_title", "source_version", "publication_date",
        "approval_status", "approval_date", "approval_organization",
        "source_organization", "source_url", "source_scope",
        "source_statements",
    ],
    ("clinical-documentation-improvement-agent", "documentation_gaps[].priority"):
        ["routine", "urgent"],
    ("clinical-documentation-improvement-agent", "proposed_provider_queries[].priority"):
        ["routine", "urgent"],
    ("clinical-documentation-improvement-agent", "human_review.review_priority"):
        ["routine", "urgent"],
    ("clinical-guidelines", "overall_assessment"):
        ["MET", "NOT_MET", "NOT_ASSESSABLE"],
    ("clinical-guidelines", "guideline_status"): [
        "INPUT_REQUIRED", "SOURCE_REVIEW_REQUIRED",
        "APPLICABILITY_REVIEW_REQUIRED", "READY_FOR_REVIEW",
    ],
    ("clinical-guidelines", "criteria_checked[].assessment"):
        ["MET", "NOT_MET", "NOT_ASSESSABLE"],
    ("clinical-guidelines", "applicability_status"): [
        "NOT_ASSESSABLE", "DOCUMENTED_POPULATION_MATCH",
        "DOCUMENTED_POPULATION_MISMATCH_OR_MISSING",
    ],
    ("clinical-guidelines", "document_consistency_status"): [
        "NOT_ASSESSED", "NO_CONFLICTS_DETECTED", "CONFLICTS_DETECTED",
    ],
    ("clinical-guidelines", "guideline_availability_status"): [
        "SOURCE_NOT_PROVIDED", "DOCUMENTED_SOURCE_NOT_ELIGIBLE",
        "DOCUMENTED_GUIDELINE_APPLICABILITY_UNCONFIRMED",
        "DOCUMENTED_GUIDELINE_AVAILABLE",
    ],
    ("clinical-guidelines", "evidence_items[].field"): [
        "clinical_question", "guideline_domain", "source_title",
        "source_version", "publication_date", "approval_status",
        "approval_date", "approval_organization", "source_organization",
        "source_url", "guideline_population", "patient_population",
        "source_scope", "documentation_scope", "guideline_criteria",
        "evaluation_rules", "documented_facts",
    ],
    ("code-validation", "review_conclusion"):
        ["PASS", "WARNING", "FAIL"],
    ("code-validation", "validated_codes[].status"):
        ["valid", "invalid"],
    ("compliance-guardrail", "reviewed_codes[].code_system"):
        ["ICD-10-CN", "ICD-9-CM-3"],
    ("compliance-guardrail", "reviewed_codes[].role"):
        ["primary_diagnosis", "secondary_diagnosis", "procedure"],
    ("diagnosis-extractor", "status"):
        ["PASS", "WARNING", "REQUIRES_REVIEW"],
    ("diagnosis-extractor", "diagnoses[].assertion_status"):
        ["present", "suspected", "negated", "history_of", "family_history"],
    ("diagnosis-extractor", "diagnoses[].confidence"):
        ["high", "medium", "low"],
    ("diagnosis-extractor", "non_codable_mentions[].assertion_status"):
        ["suspected", "negated", "history_of", "family_history", "unresolved"],
    ("icd10_navigator", "search_status"):
        ["CANDIDATES_FOUND", "NO_CANDIDATES", "INPUT_REQUIRED", "CATALOG_UNAVAILABLE"],
    ("icd10_navigator", "candidate_codes[].match_type"):
        ["exact_code", "prefix_code", "term_index", "lexical_name"],
    ("med_reconciliation", "reconciliation_status"):
        ["COMPLETED", "PARTIAL", "INPUT_REQUIRED"],
    ("med_reconciliation", "home_medications[].status"):
        ["LISTED", "GIVEN", "HELD", "REFUSED", "STOPPED", "CONTINUED", "STARTED"],
    ("med_reconciliation", "inpatient_medications[].status"):
        ["LISTED", "GIVEN", "HELD", "REFUSED", "STOPPED", "CONTINUED", "STARTED"],
    ("med_reconciliation", "discharge_medications[].status"):
        ["LISTED", "GIVEN", "HELD", "REFUSED", "STOPPED", "CONTINUED", "STARTED"],
    ("med_reconciliation", "home_medications[].source"): ["home"],
    ("med_reconciliation", "inpatient_medications[].source"): ["inpatient"],
    ("med_reconciliation", "discharge_medications[].source"): ["discharge"],
    ("med_reconciliation", "home_medications[].identity_basis"):
        ["verbatim_name", "adjacent_single_medication_reference"],
    ("med_reconciliation", "inpatient_medications[].identity_basis"):
        ["verbatim_name", "adjacent_single_medication_reference"],
    ("med_reconciliation", "discharge_medications[].identity_basis"):
        ["verbatim_name", "adjacent_single_medication_reference"],
    ("med_reconciliation", "reconciliation_summary[].category"):
        ["CONTINUE", "START", "STOP", "CHANGE", "NEEDS_CLARIFICATION"],
    ("med_reconciliation", "discrepancies[].type"): [
        "EXACT_NAME_DUPLICATE",
        "MISSING_DOCUMENTED_DETAILS",
        "DOCUMENTED_FIELD_CHANGE",
        "HELD_THEN_RELISTED",
        "MISSING_DISCHARGE_DISPOSITION",
        "HOME_NOT_ON_DISCHARGE_LIST",
    ],
    ("med_reconciliation", "interaction_screening_status"):
        ["NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"],
    ("med_reconciliation", "allergy_review_status"):
        ["NO_ALLERGY_SOURCE", "EXACT_LITERAL_SCREEN_ONLY"],
    ("med_reconciliation", "allergy_conflicts[].match_basis"):
        ["EXACT_LITERAL_NAME_ONLY"],
    ("nursing_handoff", "handoff_status"):
        ["COMPLETED", "PARTIAL", "INPUT_REQUIRED"],
    ("nursing_handoff", "evidence_items[].field"): [
        "patient_identifier",
        "room_bed",
        "primary_issue",
        "current_status",
        "background",
        "recent_events",
        "lines_devices",
        "medications",
        "labs_diagnostics",
        "pending_tasks",
        "safety_precautions",
        "documented_escalation_triggers",
        "gaps_conflicts",
    ],
    ("icu_summary", "summary_status"):
        ["COMPLETED", "PARTIAL", "INPUT_REQUIRED"],
    ("icu_summary", "admission_diagnoses[].assertion"): ["DOCUMENTED"],
    ("icu_summary", "active_problems[].status"): ["DOCUMENTED"],
    ("icu_summary", "organ_support[].type"): ["DOCUMENTED_ORGAN_SUPPORT"],
    ("icu_summary", "pending_items[].status"): ["DOCUMENTED_PENDING"],
    ("icu_summary", "evidence_items[].field"): [
        "patient_information",
        "admission_reason",
        "admission_diagnoses",
        "medical_history",
        "surgical_history",
        "allergies",
        "social_history",
        "timeline",
        "active_problems",
        "organ_support",
        "medications",
        "vital_signs",
        "laboratory_results",
        "procedures",
        "key_trends",
        "pending_items",
        "risks",
        "conflicts",
    ],
    ("discharge_edu", "education_status"):
        ["COMPLETED", "PARTIAL", "INPUT_REQUIRED"],
    ("discharge_edu", "key_results[].category"):
        ["LABORATORY_RESULT", "IMAGING_RESULT", "PROCEDURE"],
    ("discharge_edu", "contradictions[].resolution"):
        ["UNRESOLVED_CLINICAL_REVIEW_REQUIRED"],
    ("discharge_edu", "evidence_items[].field"): [
        "diagnosis_summary",
        "reason_for_visit",
        "treatment_course",
        "discharge_destination",
        "laboratory_result",
        "imaging_result",
        "procedure",
        "medication_instructions",
        "follow_up",
        "warning_signs",
        "lifestyle",
        "pending_results",
        "contradiction",
    ],
    ("discharge_summary_structuring", "structuring_status"):
        ["COMPLETED", "PARTIAL", "INPUT_REQUIRED"],
    ("discharge_summary_structuring", "diagnoses[].role"): [
        "DOCUMENTED_PRIMARY",
        "DOCUMENTED_SECONDARY",
        "DOCUMENTED_UNSPECIFIED",
    ],
    ("discharge_summary_structuring", "key_results[].category"):
        ["LABORATORY_RESULT", "IMAGING_RESULT"],
    ("discharge_summary_structuring", "discharge_orders[].category"): [
        "GENERAL", "MEDICATION", "ACTIVITY", "DIET", "WOUND_CARE",
    ],
    ("discharge_summary_structuring", "discharge_status.normalized_status"): [
        "CURED", "IMPROVED", "NOT_CURED", "DECEASED", "OTHER",
        "DOCUMENTED_UNMAPPED", "NOT_DOCUMENTED",
    ],
    ("discharge_summary_structuring", "conflicts[].resolution"):
        ["UNRESOLVED_CLINICAL_REVIEW_REQUIRED"],
    ("discharge_summary_structuring", "evidence_items[].field"): [
        "admission_date",
        "discharge_date",
        "department",
        "discharge_destination",
        "admission_reason",
        "diagnoses",
        "procedures",
        "treatment_course",
        "laboratory_results",
        "imaging_results",
        "discharge_orders",
        "follow_up_recommendations",
        "discharge_status",
        "allergies",
        "pending_results",
        "complications",
        "conflicts",
    ],
    ("evidence_extractor", "extraction_status"):
        ["COMPLETED", "INPUT_REQUIRED", "CATALOG_UNAVAILABLE"],
    ("evidence_extractor", "located_mentions[].match_type"):
        ["exact_code_literal", "exact_catalog_term"],
    ("evidence_extractor", "located_mentions[].context_status"):
        ["current_mention", "negated", "historical", "family_history", "suspected"],
    ("evidence_extractor", "code_results[].catalog_status"):
        ["found", "not_found", "unavailable"],
    ("evidence_extractor", "code_results[].result_status"):
        ["EXACT_MENTION_FOUND", "NO_EXACT_MENTION", "CODE_NOT_IN_CATALOG", "CATALOG_UNAVAILABLE"],
    ("evidence-ranker", "ranking_status"):
        ["RANKED", "RANKED_WITH_GAPS", "INPUT_REQUIRED"],
    ("evidence-ranker", "ranked_evidence[].span_status"):
        ["valid", "mismatch", "missing_coordinates", "source_unavailable"],
    ("evidence-ranker", "ranked_evidence[].certainty"):
        ["confirmed", "suspected", "probable", "ruled_out", "unknown"],
    ("evidence-ranker", "conflicts[].conflict_type"):
        ["duplicate_evidence_id"],
    ("evidence-ranker", "unsupported_claims[].reason_code"):
        ["empty_content", "missing_source_label", "span_mismatch", "source_unavailable"],
    ("evidence-ranker", "confidence_calibration.overall_confidence"):
        ["high", "moderate", "low", "not_assessed"],
    ("procedure-extractor", "procedures[].status"):
        ["performed", "planned", "historical", "cancelled", "negated", "unknown"],
    ("procedure-extractor", "non_billable_mentions[].status"):
        ["performed", "planned", "historical", "cancelled", "negated", "unknown"],
    ("rule_explainer", "status"):
        ["WARNING", "REQUIRES_REVIEW"],
    ("rule_explainer", "catalog_status"):
        ["ASSIGNABLE", "CATEGORY_OR_PREFIX", "NOT_FOUND", "INPUT_REQUIRED", "CATALOG_UNAVAILABLE"],
    ("rule_explainer", "rule_content_status"):
        ["UNAVAILABLE_IN_GOVERNED_ASSET"],
    ("referral_gen", "referral_status"):
        ["INPUT_REQUIRED", "PARTIAL", "READY_FOR_REVIEW"],
    ("prior_auth", "authorization_status"):
        ["INPUT_REQUIRED", "POLICY_REQUIRED", "READY_FOR_REVIEW"],
    ("prior_auth", "policy_evaluation_status"):
        ["POLICY_NOT_PROVIDED", "DOCUMENTED_POLICY_INCOMPLETE", "DOCUMENTED_POLICY_ONLY"],
    ("prior_auth", "evidence_items[].field"): [
        "patient_name", "date_of_birth", "member_id", "provider_name",
        "provider_credentials", "provider_identifier", "provider_facility",
        "provider_contact", "payer_name", "plan_name", "payer_region",
        "request_type", "requested_item_name", "dose", "route", "frequency",
        "duration", "requested_code", "diagnosis_context", "diagnosis_code",
        "request_reason", "clinical_documentation", "objective_evidence",
        "prior_treatments", "contraindications_intolerances",
        "payer_requirements", "policy_identifier", "policy_version",
        "policy_effective_date", "policy_source",
        "documented_medical_necessity", "denial_reason",
    ],
    ("principal_diagnosis_review", "review_status"): [
        "INPUT_REQUIRED", "EVIDENCE_REVIEW_REQUIRED", "READY_FOR_CODER_REVIEW",
    ],
    ("principal_diagnosis_review", "draft_consistency_status"): [
        "NOT_ASSESSABLE", "DRAFT_NOT_IN_CANDIDATE_SET", "DECLARED_INPUT_CONFLICT",
        "DOCUMENTED_DRAFT_EVIDENCE_INCOMPLETE",
        "DOCUMENTED_DRAFT_AND_EVIDENCE_PRESENT",
    ],
    ("principal_diagnosis_review", "selection_basis_status"): [
        "NOT_PROVIDED", "DOCUMENTED", "CONFLICTING",
    ],
    ("principal_diagnosis_review", "candidates[].evidence_status"): [
        "EXACT_INPUT_SPAN",
    ],
    ("principal_diagnosis_review", "declared_selection_basis[].basis_type"): [
        "ADMISSION_REASON", "MAIN_TREATMENT", "RESOURCE_USE",
        "HOSPITAL_APPROVED_OTHER",
    ],
    ("principal_diagnosis_review", "evidence_items[].field"): [
        "review_purpose", "coding_system", "coding_version", "documentation_scope",
        "documented_draft", "candidate_evidence", "selection_basis",
    ],
}

# Governance values are implementation-owned invariants, not clinical facts
# inferred from one example.  Keeping them here makes schema regeneration
# deterministic and prevents an LLM response from claiming official authority.
CONST_OVERRIDES: dict[tuple[str, str], Any] = {
    ("drg-analyzer", "review_method"):
        "EXPLICIT_CODED_CASE_DETERMINISTIC_UNVERIFIED_RISK_REVIEW",
    ("drg-analyzer", "coded_case.secondary_diagnoses[].evidence_status"):
        "EXACT_INPUT_SPAN",
    ("drg-analyzer", "coded_case.procedures[].evidence_status"):
        "EXACT_INPUT_SPAN",
    ("drg-analyzer", "quality_flags.candidate_only"): True,
    ("drg-analyzer", "governance.rule_pack_id"):
        "cn.drg_dip.risk_heuristics",
    ("drg-analyzer", "governance.rule_pack_version"):
        "1.0.0-development",
    ("drg-analyzer", "governance.jurisdiction"): "CN_GENERIC_DEVELOPMENT",
    ("drg-analyzer", "governance.authority_status"): "experimental_unverified",
    ("drg-analyzer", "governance.license_status"): "external_review_required",
    ("drg-analyzer", "governance.use_restriction"):
        "development_risk_review_only_not_for_grouping_payment_or_settlement",
    ("drg-analyzer", "code_extraction_performed"): False,
    ("drg-analyzer", "code_assignment_performed"): False,
    ("drg-analyzer", "code_validation_performed"): False,
    ("drg-analyzer", "clinical_inference_performed"): False,
    ("drg-analyzer", "official_grouping_performed"): False,
    ("drg-analyzer", "official_dip_scoring_performed"): False,
    ("drg-analyzer", "payment_calculation_performed"): False,
    ("drg-analyzer", "production_submission_blocked"): True,
    ("drg-analyzer", "production_writeback_blocked"): True,
    ("triage", "review_method"):
        "EXPLICIT_ANSWER_DETERMINISTIC_QUESTIONNAIRE_PATH_REVIEW",
    ("triage", "protocol_governance.jurisdiction"):
        "CN_HOSPITAL_LOCAL_DECLARATION",
    ("triage", "transcript_extraction_performed"): False,
    ("triage", "questionnaire_answer_inference_performed"): False,
    ("triage", "clinical_inference_performed"): False,
    ("triage", "medical_calculator_used"): False,
    ("triage", "external_knowledge_used"): False,
    ("triage", "final_acuity_assignment_performed"): False,
    ("triage", "production_action_blocked"): True,
    ("triage", "production_writeback_blocked"): True,
    ("triage", "manual_review_required"): True,
    ("claim-check", "evidence_consistency_status"):
        "NOT_ASSESSED_LITERAL_PACKET_ONLY",
    ("claim-check", "comparison_basis"):
        "DOCUMENTED_CLAIM_AND_POLICY_ONLY",
    ("claim-check", "clinical_support_assessed"): False,
    ("claim-check", "medical_necessity_assessed"): False,
    ("claim-check", "benefit_eligibility_determined"): False,
    ("claim-check", "code_assignment_performed"): False,
    ("claim-check", "drg_dip_grouping_performed"): False,
    ("claim-check", "external_knowledge_used"): False,
    ("claim-check", "production_submission_blocked"): True,
    ("claim-check", "production_writeback_blocked"): True,
    ("claim-check", "manual_review_required"): True,
    ("denial-appeals", "denial_classification_status"):
        "DOCUMENTED_ONLY_NO_INFERENCE",
    ("denial-appeals", "draft_generation_status"):
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY",
    ("denial-appeals", "clinical_support_assessed"): False,
    ("denial-appeals", "medical_necessity_assessed"): False,
    ("denial-appeals", "benefit_eligibility_determined"): False,
    ("denial-appeals", "denial_root_cause_inferred"): False,
    ("denial-appeals", "payer_policy_lookup_performed"): False,
    ("denial-appeals", "medical_coding_validation_performed"): False,
    ("denial-appeals", "external_knowledge_used"): False,
    ("denial-appeals", "production_submission_blocked"): True,
    ("denial-appeals", "production_writeback_blocked"): True,
    ("denial-appeals", "manual_review_required"): True,
    ("clinical-education", "content_generation_status"):
        "SOURCE_BOUND_TEMPLATE_ONLY",
    ("clinical-education", "question_classification_performed"): False,
    ("clinical-education", "clinical_reasoning_performed"): False,
    ("clinical-education", "diagnostic_advice_generated"): False,
    ("clinical-education", "treatment_advice_generated"): False,
    ("clinical-education", "drug_interaction_assessed"): False,
    ("clinical-education", "medical_calculator_used"): False,
    ("clinical-education", "pubmed_lookup_performed"): False,
    ("clinical-education", "web_search_performed"): False,
    ("clinical-education", "external_knowledge_used"): False,
    ("clinical-education", "production_writeback_blocked"): True,
    ("clinical-education", "manual_review_required"): True,
    ("clinical-guidelines", "source_authenticity_status"):
        "USER_DOCUMENTED_METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED",
    ("clinical-guidelines", "source_currency_verified"): False,
    ("clinical-guidelines", "evaluation_method"):
        "DECLARED_RULES_DETERMINISTIC_COMPARISON",
    ("clinical-guidelines", "guideline_retrieval_performed"): False,
    ("clinical-guidelines", "web_search_performed"): False,
    ("clinical-guidelines", "clinical_inference_performed"): False,
    ("clinical-guidelines", "clinical_significance_assessed"): False,
    ("clinical-guidelines", "treatment_recommendations_generated"): False,
    ("clinical-guidelines", "external_knowledge_used"): False,
    ("clinical-guidelines", "production_writeback_blocked"): True,
    ("clinical-guidelines", "manual_review_required"): True,
    ("drg-analyzer", "rule_authority_status"): "experimental_unverified",
    ("drg-analyzer", "billing_authoritative"): False,
    ("drg-analyzer", "rule_pack_id"): "cn.drg_dip.risk_heuristics",
    ("drg-analyzer", "rule_pack_version"): "1.0.0-development",
    ("drg-analyzer", "jurisdiction"): "CN_GENERIC_DEVELOPMENT",
    ("icd10_navigator", "candidate_codes[].instructional_notes_available"): False,
    ("icd10_navigator", "candidate_codes[].source_asset_id"): "cn.icd10cn.catalog",
    ("evidence-ranker", "ranking_basis"): "DOCUMENTATION_GROUNDING_ONLY",
    ("evidence_extractor", "match_basis"): "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY",
    ("evidence_extractor", "located_mentions[].clinical_support_assessed"): False,
    ("evidence_extractor", "code_results[].clinical_support_assessed"): False,
    ("evidence_extractor", "manual_review_required"): True,
    ("rule_explainer", "code_system"): "ICD-10-CN",
    ("rule_explainer", "rule_content_status"): "UNAVAILABLE_IN_GOVERNED_ASSET",
    ("rule_explainer", "manual_review_required"): True,
    ("med_reconciliation", "interaction_screening_status"):
        "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED",
    ("med_reconciliation", "manual_review_required"): True,
    ("nursing_handoff", "source_completeness.max_patients"): 10,
    ("nursing_handoff", "clinical_priority_assessed"): False,
    ("nursing_handoff", "medical_calculator_used"): False,
    ("nursing_handoff", "production_writeback_blocked"): True,
    ("nursing_handoff", "manual_review_required"): True,
    ("icu_summary", "clinical_scores_status"):
        "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED",
    ("icu_summary", "medication_screening_status"):
        "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED",
    ("icu_summary", "clinical_recommendations_generated"): False,
    ("icu_summary", "production_writeback_blocked"): True,
    ("icu_summary", "manual_review_required"): True,
    ("discharge_edu", "medication_reconciliation_status"):
        "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED",
    ("discharge_edu", "translation_status"):
        "VERBATIM_DOCUMENTED_CONTENT_ONLY",
    ("discharge_edu", "external_knowledge_used"): False,
    ("discharge_edu", "clinical_interpretation_performed"): False,
    ("discharge_edu", "clinical_recommendations_generated"): False,
    ("discharge_edu", "production_writeback_blocked"): True,
    ("discharge_edu", "manual_review_required"): True,
    ("discharge_summary_structuring", "summary_generation_status"):
        "VERBATIM_SECTION_REORGANIZATION_ONLY",
    ("discharge_summary_structuring", "icd_codes_assigned"): False,
    ("discharge_summary_structuring", "medication_reconciliation_performed"):
        False,
    ("discharge_summary_structuring", "clinical_inference_performed"): False,
    ("discharge_summary_structuring", "production_writeback_blocked"): True,
    ("discharge_summary_structuring", "manual_review_required"): True,
    ("referral_gen", "draft_generation_status"):
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY",
    ("referral_gen", "clinical_inference_performed"): False,
    ("referral_gen", "new_diagnosis_generated"): False,
    ("referral_gen", "new_treatment_recommended"): False,
    ("referral_gen", "external_knowledge_used"): False,
    ("referral_gen", "production_transmission_blocked"): True,
    ("referral_gen", "production_writeback_blocked"): True,
    ("referral_gen", "manual_review_required"): True,
    ("prior_auth", "medical_necessity_assessment_status"):
        "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED",
    ("prior_auth", "draft_generation_status"):
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY",
    ("prior_auth", "clinical_inference_performed"): False,
    ("prior_auth", "new_diagnosis_generated"): False,
    ("prior_auth", "new_treatment_recommended"): False,
    ("prior_auth", "external_knowledge_used"): False,
    ("prior_auth", "medical_calculator_used"): False,
    ("prior_auth", "medical_coding_validation_performed"): False,
    ("prior_auth", "production_submission_blocked"): True,
    ("prior_auth", "production_writeback_blocked"): True,
    ("prior_auth", "manual_review_required"): True,
    ("principal_diagnosis_review", "documented_coding_draft.authority_status"):
        "CODER_DOCUMENTED_DRAFT_NOT_CLINICALLY_VALIDATED",
    ("principal_diagnosis_review", "review_method"):
        "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY",
    ("principal_diagnosis_review", "diagnosis_extraction_performed"): False,
    ("principal_diagnosis_review", "code_assignment_performed"): False,
    ("principal_diagnosis_review", "principal_diagnosis_selection_performed"): False,
    ("principal_diagnosis_review", "clinical_inference_performed"): False,
    ("principal_diagnosis_review", "external_rules_used"): False,
    ("principal_diagnosis_review", "production_submission_blocked"): True,
    ("principal_diagnosis_review", "production_writeback_blocked"): True,
    ("principal_diagnosis_review", "manual_review_required"): True,
}

# Optional audit coordinates may be absent from a compact example but remain
# valid contract properties.  They are reviewed here so regeneration neither
# drops them nor incorrectly makes them required.
OPTIONAL_OBJECT_PROPERTY_OVERRIDES: dict[
    tuple[str, str], dict[str, dict[str, Any]]
] = {
    ("medical_coding", "code_assignment.primary_diagnosis.evidence[]"): {
        "char_start": {"type": "integer"},
        "char_end": {"type": "integer"},
        "doc_id": {"type": "string"},
        "doc_type": {"type": "string"},
        "confidence": {"type": "number"},
    },
    ("surgical_registry", "evidence_spans"): {
        "procedure": {"type": "string"},
        "indications": {"type": "string"},
        "comorbidities": {"type": "string"},
        "operative_details": {"type": "string"},
        "anesthesia": {"type": "string"},
        "outcomes": {"type": "string"},
        "complications": {"type": "string"},
    },
}

# Some evidence maps are sparse by design: a key exists only when the same
# output field is non-empty.  Examples cannot safely infer required keys for
# these maps because one sample does not prove universal presence.
OBJECT_REQUIRED_OVERRIDES: dict[tuple[str, str], list[str]] = {
    ("drg-analyzer", "coded_case"): [
        "review_purpose", "diagnosis_coding_standard",
        "procedure_coding_standard", "patient_gender", "patient_age",
        "primary_diagnosis", "secondary_diagnoses", "procedures",
    ],
    ("drg-analyzer", "coded_case.primary_diagnosis"): [
        "code", "display", "source_document", "evidence_text", "char_span",
        "evidence_ref", "evidence_status",
    ],
    ("drg-analyzer", "coded_case.secondary_diagnoses[]"): [
        "code", "display", "source_document", "evidence_text", "char_span",
        "evidence_ref", "evidence_status",
    ],
    ("drg-analyzer", "coded_case.procedures[]"): [
        "code", "display", "source_document", "evidence_text", "char_span",
        "evidence_ref", "evidence_status",
    ],
    ("drg-analyzer", "development_candidate_group"): [
        "candidate_drg", "candidate_name", "mdc", "mdc_name", "adrg",
        "cc_level", "grouping_method", "coverage", "result_status",
    ],
    ("drg-analyzer", "dip_review"): ["status", "note"],
    ("drg-analyzer", "risk_findings[]"): [
        "rule_id", "severity", "category", "message", "review_action",
        "input_evidence_refs",
    ],
    ("drg-analyzer", "governance"): [
        "rule_pack_id", "rule_pack_version", "jurisdiction",
        "authority_status", "license_status", "use_restriction",
    ],
    ("drg-analyzer", "evidence_items[]"): [
        "evidence_id", "field", "label", "text", "char_span",
    ],
    ("drg-analyzer", "trace_refs"): ["run_id", "provider_trace_refs"],
    ("triage", "protocol_governance"): [
        "protocol_id", "protocol_version", "declared_status", "protocol_source",
        "approval_attestation_id", "verification_status", "jurisdiction",
    ],
    ("triage", "questionnaire_validation"): [
        "valid", "errors", "question_count", "endpoint_count",
        "all_references_resolved", "cycle_free",
    ],
    ("triage", "decision_path[]"): [
        "step_index", "question_id", "answer_type", "documented_value",
        "evidence_ref", "matched_branch_index", "matched_operator", "next_node",
    ],
    ("triage", "protocol_candidate"): [
        "reached", "endpoint_id", "candidate_level", "disposition",
        "red_flag_codes", "result_status",
    ],
    ("triage", "evidence_items[]"): [
        "evidence_id", "field", "source_document", "text", "char_span",
        "evidence_status",
    ],
    ("triage", "trace_refs"): ["run_id", "provider_trace_refs"],
    ("surgical_registry", "evidence_spans"): [],
}

FIELD_RELATION_OVERRIDES: dict[str, list[dict[str, Any]]] = {
    "triage": [
        {
            "id": "ready_triage_candidate_has_valid_reached_path",
            "when": [{
                "path": "assessment_status", "operator": "equals",
                "value": "READY_FOR_ONSITE_REVIEW",
            }],
            "must": [
                {"path": "missing_information", "operator": "empty"},
                {"path": "input_conflicts", "operator": "empty"},
                {"path": "questionnaire_validation.valid", "operator": "equals", "value": True},
                {"path": "decision_path", "operator": "non_empty"},
                {"path": "protocol_candidate.reached", "operator": "equals", "value": True},
                {"path": "protocol_candidate.result_status", "operator": "equals", "value": "DEVELOPMENT_UNVERIFIED_PROTOCOL_CANDIDATE"},
            ],
        },
        {
            "id": "unreached_triage_candidate_is_not_assessed",
            "when": [{
                "path": "assessment_status", "operator": "not_equals",
                "value": "READY_FOR_ONSITE_REVIEW",
            }],
            "must": [
                {"path": "acuity_level", "operator": "equals", "value": "NOT_ASSIGNED"},
                {"path": "protocol_candidate.result_status", "operator": "equals", "value": "NOT_ASSESSED"},
            ],
        },
        {
            "id": "governed_triage_never_infers_or_assigns_final_acuity",
            "when": [{
                "path": "review_method", "operator": "equals",
                "value": "EXPLICIT_ANSWER_DETERMINISTIC_QUESTIONNAIRE_PATH_REVIEW",
            }],
            "must": [
                {"path": "transcript_extraction_performed", "operator": "equals", "value": False},
                {"path": "questionnaire_answer_inference_performed", "operator": "equals", "value": False},
                {"path": "clinical_inference_performed", "operator": "equals", "value": False},
                {"path": "medical_calculator_used", "operator": "equals", "value": False},
                {"path": "external_knowledge_used", "operator": "equals", "value": False},
                {"path": "final_acuity_assignment_performed", "operator": "equals", "value": False},
            ],
        },
        {
            "id": "governed_triage_always_requires_onsite_gate",
            "when": [{
                "path": "review_method", "operator": "equals",
                "value": "EXPLICIT_ANSWER_DETERMINISTIC_QUESTIONNAIRE_PATH_REVIEW",
            }],
            "must": [
                {"path": "production_action_blocked", "operator": "equals", "value": True},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
    ],
    "evidence-ranker": [
        {
            "id": "input_required_has_no_ranked_evidence",
            "when": [{"path": "ranking_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [{"path": "ranked_evidence", "operator": "empty"}],
        },
        {
            "id": "ranked_status_has_evidence",
            "when": [{"path": "ranking_status", "operator": "equals", "value": "RANKED"}],
            "must": [{"path": "ranked_evidence", "operator": "non_empty"}],
        },
        {
            "id": "ranked_with_gaps_has_evidence",
            "when": [{"path": "ranking_status", "operator": "equals", "value": "RANKED_WITH_GAPS"}],
            "must": [{"path": "ranked_evidence", "operator": "non_empty"}],
        },
        {
            "id": "documentation_ranking_requires_human_review",
            "when": [{"path": "ranking_basis", "operator": "equals", "value": "DOCUMENTATION_GROUNDING_ONLY"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
    ],
    "claim-check": [
        {
            "id": "input_required_has_no_review_packet",
            "when": [{"path": "review_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [{"path": "claim_review_packet", "operator": "empty"}],
        },
        {
            "id": "policy_required_has_missing_policy_items",
            "when": [{"path": "review_status", "operator": "equals", "value": "POLICY_REQUIRED"}],
            "must": [{"path": "missing_policy_items", "operator": "non_empty"}],
        },
        {
            "id": "ready_for_review_has_complete_input_and_policy",
            "when": [{"path": "review_status", "operator": "equals", "value": "READY_FOR_REVIEW"}],
            "must": [
                {"path": "missing_required_fields", "operator": "empty"},
                {"path": "missing_policy_items", "operator": "empty"},
                {"path": "claim_review_packet", "operator": "non_empty"},
            ],
        },
        {
            "id": "claim_review_is_human_only_and_non_submitting",
            "when": [{"path": "comparison_basis", "operator": "equals", "value": "DOCUMENTED_CLAIM_AND_POLICY_ONLY"}],
            "must": [
                {"path": "manual_review_required", "operator": "equals", "value": True},
                {"path": "production_submission_blocked", "operator": "equals", "value": True},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
            ],
        },
    ],
    "denial-appeals": [
        {
            "id": "input_required_has_no_denial_output",
            "when": [{"path": "appeal_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "appeal_letter_draft", "operator": "empty"},
                {"path": "corrected_claim_checklist", "operator": "empty"},
            ],
        },
        {
            "id": "path_review_required_has_no_denial_output",
            "when": [{"path": "appeal_status", "operator": "equals", "value": "PATH_REVIEW_REQUIRED"}],
            "must": [
                {"path": "appeal_letter_draft", "operator": "empty"},
                {"path": "corrected_claim_checklist", "operator": "empty"},
            ],
        },
        {
            "id": "ready_denial_output_has_complete_core_input",
            "when": [{"path": "appeal_status", "operator": "equals", "value": "READY_FOR_REVIEW"}],
            "must": [
                {"path": "missing_required_fields", "operator": "empty"},
                {"path": "evidence_items", "operator": "non_empty"},
                {"path": "documented_resolution_path.documented_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "governed_denial_review_never_claims_external_authority",
            "when": [{"path": "draft_generation_status", "operator": "equals", "value": "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"}],
            "must": [
                {"path": "denial_classification_status", "operator": "equals", "value": "DOCUMENTED_ONLY_NO_INFERENCE"},
                {"path": "clinical_support_assessed", "operator": "equals", "value": False},
                {"path": "medical_necessity_assessed", "operator": "equals", "value": False},
                {"path": "benefit_eligibility_determined", "operator": "equals", "value": False},
                {"path": "denial_root_cause_inferred", "operator": "equals", "value": False},
                {"path": "payer_policy_lookup_performed", "operator": "equals", "value": False},
                {"path": "medical_coding_validation_performed", "operator": "equals", "value": False},
                {"path": "external_knowledge_used", "operator": "equals", "value": False},
            ],
        },
        {
            "id": "governed_denial_review_never_crosses_delivery_boundary",
            "when": [{"path": "draft_generation_status", "operator": "equals", "value": "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"}],
            "must": [
                {"path": "production_submission_blocked", "operator": "equals", "value": True},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
    ],
    "clinical-education": [
        {
            "id": "input_required_has_no_teaching_content",
            "when": [{"path": "education_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "source_statements", "operator": "empty"},
                {"path": "learning_objectives", "operator": "empty"},
                {"path": "key_points", "operator": "empty"},
                {"path": "evidence_citations", "operator": "empty"},
                {"path": "knowledge_checks", "operator": "empty"},
            ],
        },
        {
            "id": "source_review_required_has_no_generated_teaching_content",
            "when": [{"path": "education_status", "operator": "equals", "value": "SOURCE_REVIEW_REQUIRED"}],
            "must": [
                {"path": "learning_objectives", "operator": "empty"},
                {"path": "key_points", "operator": "empty"},
                {"path": "knowledge_checks", "operator": "empty"},
            ],
        },
        {
            "id": "ready_education_has_approved_source_and_bound_content",
            "when": [{"path": "education_status", "operator": "equals", "value": "READY_FOR_REVIEW"}],
            "must": [
                {"path": "missing_required_fields", "operator": "empty"},
                {"path": "missing_source_metadata", "operator": "empty"},
                {"path": "approved_source.approval_status.documented_text", "operator": "equals", "value": "已批准"},
                {"path": "source_statements", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "ready_education_has_bound_teaching_material",
            "when": [{"path": "education_status", "operator": "equals", "value": "READY_FOR_REVIEW"}],
            "must": [
                {"path": "learning_objectives", "operator": "non_empty"},
                {"path": "key_points", "operator": "non_empty"},
                {"path": "evidence_citations", "operator": "non_empty"},
                {"path": "knowledge_checks", "operator": "non_empty"},
            ],
        },
        {
            "id": "source_insufficient_requires_limitations_and_review",
            "when": [{"path": "source_insufficient", "operator": "equals", "value": True}],
            "must": [
                {"path": "limitations", "operator": "non_empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "governed_education_never_claims_external_or_clinical_reasoning",
            "when": [{"path": "content_generation_status", "operator": "equals", "value": "SOURCE_BOUND_TEMPLATE_ONLY"}],
            "must": [
                {"path": "question_classification_performed", "operator": "equals", "value": False},
                {"path": "clinical_reasoning_performed", "operator": "equals", "value": False},
                {"path": "diagnostic_advice_generated", "operator": "equals", "value": False},
                {"path": "treatment_advice_generated", "operator": "equals", "value": False},
                {"path": "drug_interaction_assessed", "operator": "equals", "value": False},
                {"path": "medical_calculator_used", "operator": "equals", "value": False},
                {"path": "pubmed_lookup_performed", "operator": "equals", "value": False},
                {"path": "web_search_performed", "operator": "equals", "value": False},
            ],
        },
        {
            "id": "governed_education_never_crosses_external_or_delivery_boundary",
            "when": [{"path": "content_generation_status", "operator": "equals", "value": "SOURCE_BOUND_TEMPLATE_ONLY"}],
            "must": [
                {"path": "external_knowledge_used", "operator": "equals", "value": False},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
    ],
    "clinical-documentation-improvement-agent": [
        {
            "id": "withheld_query_requires_human_action",
            "when": [
                {
                    "path": "query_gate_summary.manual_cdi_action_required",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "must": [
                {
                    "path": "human_review.cdi_specialist_review_required",
                    "operator": "equals",
                    "value": True,
                },
                {
                    "path": "human_review.clinician_response_required",
                    "operator": "equals",
                    "value": True,
                },
            ],
        },
        {
            "id": "draft_queries_require_traceable_content",
            "for_each": "proposed_provider_queries",
            "when": [{"path": "lifecycle_state", "operator": "equals", "value": "DRAFT"}],
            "must": [
                {"path": "query_id", "operator": "non_empty"},
                {"path": "gap_id", "operator": "non_empty"},
                {"path": "query_text", "operator": "non_empty"},
                {"path": "evidence_spans", "operator": "non_empty"},
                {"path": "response_options", "operator": "non_empty"},
            ],
        },
    ],
    "clinical-guidelines": [
        {
            "id": "input_required_has_no_guideline_assessment",
            "when": [{"path": "guideline_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "overall_assessment", "operator": "equals", "value": "NOT_ASSESSABLE"},
                {"path": "aligned_items", "operator": "empty"},
                {"path": "deviations", "operator": "empty"},
            ],
        },
        {
            "id": "source_review_required_has_no_guideline_conclusion",
            "when": [{"path": "guideline_status", "operator": "equals", "value": "SOURCE_REVIEW_REQUIRED"}],
            "must": [
                {"path": "guideline_source_eligible_for_review", "operator": "equals", "value": False},
                {"path": "overall_assessment", "operator": "equals", "value": "NOT_ASSESSABLE"},
            ],
        },
        {
            "id": "applicability_review_required_has_no_guideline_conclusion",
            "when": [{"path": "guideline_status", "operator": "equals", "value": "APPLICABILITY_REVIEW_REQUIRED"}],
            "must": [
                {"path": "overall_assessment", "operator": "equals", "value": "NOT_ASSESSABLE"},
                {"path": "not_assessable_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "ready_guideline_requires_eligible_source_and_bound_inputs",
            "when": [{"path": "guideline_status", "operator": "equals", "value": "READY_FOR_REVIEW"}],
            "must": [
                {"path": "guideline_source_eligible_for_review", "operator": "equals", "value": True},
                {"path": "applicability_status", "operator": "equals", "value": "DOCUMENTED_POPULATION_MATCH"},
                {"path": "missing_required_fields", "operator": "empty"},
                {"path": "missing_source_metadata", "operator": "empty"},
                {"path": "guideline_criteria", "operator": "non_empty"},
                {"path": "documented_facts", "operator": "non_empty"},
                {"path": "criteria_checked", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "unmet_guideline_requires_deviation",
            "when": [{"path": "overall_assessment", "operator": "equals", "value": "NOT_MET"}],
            "must": [
                {"path": "deviations", "operator": "non_empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "unmet_criterion_requires_deviation",
            "for_each": "criteria_checked",
            "when": [{"path": "assessment", "operator": "equals", "value": "NOT_MET"}],
            "must": [
                {"path": "deviations", "operator": "non_empty"},
                {"path": "citations", "operator": "non_empty"},
            ],
        },
        {
            "id": "unassessable_criterion_requires_uncertainty",
            "for_each": "criteria_checked",
            "when": [
                {"path": "assessment", "operator": "equals", "value": "NOT_ASSESSABLE"}
            ],
            "must": [{"path": "uncertainty", "operator": "non_empty"}],
        },
        {
            "id": "governed_guideline_never_claims_external_authority",
            "when": [{"path": "evaluation_method", "operator": "equals", "value": "DECLARED_RULES_DETERMINISTIC_COMPARISON"}],
            "must": [
                {"path": "source_authenticity_status", "operator": "equals", "value": "USER_DOCUMENTED_METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED"},
                {"path": "source_currency_verified", "operator": "equals", "value": False},
                {"path": "guideline_retrieval_performed", "operator": "equals", "value": False},
                {"path": "web_search_performed", "operator": "equals", "value": False},
                {"path": "clinical_inference_performed", "operator": "equals", "value": False},
                {"path": "clinical_significance_assessed", "operator": "equals", "value": False},
                {"path": "treatment_recommendations_generated", "operator": "equals", "value": False},
                {"path": "external_knowledge_used", "operator": "equals", "value": False},
            ],
        },
        {
            "id": "governed_guideline_comparison_is_review_only",
            "when": [{"path": "evaluation_method", "operator": "equals", "value": "DECLARED_RULES_DETERMINISTIC_COMPARISON"}],
            "must": [
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
    ],
    "code-validation": [
        {
            "id": "failed_validation_requires_review",
            "when": [{"path": "review_conclusion", "operator": "equals", "value": "FAIL"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
        {
            "id": "valid_code_requires_catalog_assignability",
            "for_each": "validated_codes",
            "when": [{"path": "status", "operator": "equals", "value": "valid"}],
            "must": [
                {"path": "in_catalog", "operator": "equals", "value": True},
                {"path": "assignable", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "invalid_code_requires_issue",
            "for_each": "validated_codes",
            "when": [{"path": "status", "operator": "equals", "value": "invalid"}],
            "must": [
                {"path": "assignable", "operator": "equals", "value": False},
                {"path": "issue", "operator": "non_empty"},
            ],
        },
    ],
    "diagnosis-extractor": [
        {
            "id": "codable_diagnosis_requires_current_evidence",
            "for_each": "diagnoses",
            "when": [{"path": "diagnosis_text", "operator": "present"}],
            "must": [
                {"path": "assertion_status", "operator": "equals", "value": "present"},
                {"path": "icd10_cn_code", "operator": "non_empty"},
                {"path": "icd10_cn_name", "operator": "non_empty"},
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "noncodable_mention_requires_reason",
            "for_each": "non_codable_mentions",
            "when": [{"path": "mention_text", "operator": "present"}],
            "must": [
                {
                    "path": "assertion_status",
                    "operator": "in",
                    "value": [
                        "suspected",
                        "negated",
                        "history_of",
                        "family_history",
                        "unresolved",
                    ],
                },
                {"path": "evidence_text", "operator": "non_empty"},
                {"path": "reason", "operator": "non_empty"},
            ],
        },
        {
            "id": "codable_and_noncodable_evidence_are_disjoint",
            "when": [{"path": "diagnoses", "operator": "present"}],
            "must": [{
                "path": "diagnoses",
                "operator": "disjoint_fields",
                "item_path": "evidence_text",
                "other_path": "non_codable_mentions",
                "other_item_path": "evidence_text",
            }],
        },
    ],
    "rule_explainer": [
        {
            "id": "assignable_requires_catalog_leaf",
            "when": [{"path": "assignable", "operator": "equals", "value": True}],
            "must": [{"path": "catalog_status", "operator": "equals", "value": "ASSIGNABLE"}],
        },
        {
            "id": "nonassignable_statuses_are_not_assignable",
            "when": [
                {
                    "path": "catalog_status",
                    "operator": "in",
                    "value": ["CATEGORY_OR_PREFIX", "NOT_FOUND", "INPUT_REQUIRED", "CATALOG_UNAVAILABLE"],
                }
            ],
            "must": [{"path": "assignable", "operator": "equals", "value": False}],
        },
        {
            "id": "missing_governed_rule_content_requires_review",
            "when": [
                {
                    "path": "rule_content_status",
                    "operator": "equals",
                    "value": "UNAVAILABLE_IN_GOVERNED_ASSET",
                }
            ],
            "must": [
                {"path": "guideline_basis", "operator": "non_empty"},
                {"path": "unsupported_scope", "operator": "non_empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "review_status_requires_review",
            "when": [{"path": "status", "operator": "equals", "value": "REQUIRES_REVIEW"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
    ],
    "med_reconciliation": [
        {
            "id": "input_required_has_no_medication_claims",
            "when": [{"path": "reconciliation_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "home_medications", "operator": "empty"},
                {"path": "inpatient_medications", "operator": "empty"},
                {"path": "discharge_medications", "operator": "empty"},
                {"path": "reconciliation_summary", "operator": "empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "completed_comparison_has_sources_and_summary",
            "when": [{"path": "reconciliation_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [
                {"path": "source_completeness.comparison_ready", "operator": "equals", "value": True},
                {"path": "reconciliation_summary", "operator": "non_empty"},
            ],
        },
        {
            "id": "unlicensed_interaction_screen_is_empty_and_reviewed",
            "when": [{"path": "interaction_screening_status", "operator": "equals", "value": "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"}],
            "must": [
                {"path": "interaction_risks", "operator": "empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "clarification_category_requires_clinician_confirmation",
            "for_each": "reconciliation_summary",
            "when": [{"path": "category", "operator": "equals", "value": "NEEDS_CLARIFICATION"}],
            "must": [{"path": "clarification_required", "operator": "equals", "value": True}],
        },
        {
            "id": "home_medication_is_traceable",
            "for_each": "home_medications",
            "when": [{"path": "drug_name", "operator": "present"}],
            "must": [
                {"path": "source", "operator": "equals", "value": "home"},
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "inpatient_medication_is_traceable",
            "for_each": "inpatient_medications",
            "when": [{"path": "drug_name", "operator": "present"}],
            "must": [
                {"path": "source", "operator": "equals", "value": "inpatient"},
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "discharge_medication_is_traceable",
            "for_each": "discharge_medications",
            "when": [{"path": "drug_name", "operator": "present"}],
            "must": [
                {"path": "source", "operator": "equals", "value": "discharge"},
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
    ],
    "nursing_handoff": [
        {
            "id": "input_required_has_no_handoff_claims",
            "when": [{"path": "handoff_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "assignment_summary", "operator": "empty"},
                {"path": "patient_handoffs", "operator": "empty"},
                {"path": "evidence_items", "operator": "empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "completed_handoff_has_patients_and_evidence",
            "when": [{"path": "handoff_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [
                {"path": "assignment_summary", "operator": "non_empty"},
                {"path": "patient_handoffs", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "partial_handoff_has_patients_and_evidence",
            "when": [{"path": "handoff_status", "operator": "equals", "value": "PARTIAL"}],
            "must": [
                {"path": "patient_handoffs", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "local_handoff_never_claims_clinical_priority",
            "when": [{"path": "clinical_priority_assessed", "operator": "equals", "value": False}],
            "must": [
                {"path": "medical_calculator_used", "operator": "equals", "value": False},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "patient_handoff_is_traceable",
            "for_each": "patient_handoffs",
            "when": [{"path": "patient_identifier", "operator": "present"}],
            "must": [
                {"path": "patient_identifier", "operator": "non_empty"},
                {"path": "evidence_refs", "operator": "non_empty"},
            ],
        },
    ],
    "icu_summary": [
        {
            "id": "input_required_has_no_icu_fact_claims",
            "when": [{"path": "summary_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "admission_diagnoses", "operator": "empty"},
                {"path": "active_problems", "operator": "empty"},
                {"path": "organ_support", "operator": "empty"},
                {"path": "evidence_items", "operator": "empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "completed_icu_summary_has_evidence",
            "when": [{"path": "summary_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [
                {"path": "admission_reason", "operator": "non_empty"},
                {"path": "admission_diagnoses", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "partial_icu_summary_has_evidence",
            "when": [{"path": "summary_status", "operator": "equals", "value": "PARTIAL"}],
            "must": [{"path": "evidence_items", "operator": "non_empty"}],
        },
        {
            "id": "local_icu_summary_never_claims_expert_outputs",
            "when": [
                {
                    "path": "clinical_scores_status",
                    "operator": "equals",
                    "value": "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED",
                }
            ],
            "must": [
                {
                    "path": "medication_screening_status",
                    "operator": "equals",
                    "value": "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED",
                },
                {"path": "clinical_recommendations_generated", "operator": "equals", "value": False},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "icu_diagnosis_is_traceable",
            "for_each": "admission_diagnoses",
            "when": [{"path": "diagnosis", "operator": "present"}],
            "must": [
                {"path": "diagnosis", "operator": "non_empty"},
                {"path": "evidence_ref", "operator": "non_empty"},
            ],
        },
        {
            "id": "icu_organ_support_is_traceable",
            "for_each": "organ_support",
            "when": [{"path": "detail", "operator": "present"}],
            "must": [
                {"path": "detail", "operator": "non_empty"},
                {"path": "evidence_ref", "operator": "non_empty"},
            ],
        },
    ],
    "discharge_edu": [
        {
            "id": "input_required_has_no_discharge_fact_claims",
            "when": [{"path": "education_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "diagnosis_summary", "operator": "equals", "value": ""},
                {"path": "medication_instructions", "operator": "equals", "value": ""},
                {"path": "follow_up", "operator": "equals", "value": ""},
                {"path": "warning_signs", "operator": "equals", "value": ""},
                {"path": "lifestyle", "operator": "equals", "value": ""},
                {"path": "pending_results", "operator": "equals", "value": ""},
                {"path": "key_results", "operator": "empty"},
                {"path": "evidence_items", "operator": "empty"},
            ],
        },
        {
            "id": "completed_discharge_education_has_core_evidence",
            "when": [{"path": "education_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [
                {"path": "diagnosis_summary", "operator": "non_empty"},
                {"path": "medication_instructions", "operator": "non_empty"},
                {"path": "follow_up", "operator": "non_empty"},
                {"path": "warning_signs", "operator": "non_empty"},
                {"path": "lifestyle", "operator": "non_empty"},
                {"path": "missing_items", "operator": "empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "partial_discharge_education_has_evidence_and_gaps",
            "when": [{"path": "education_status", "operator": "equals", "value": "PARTIAL"}],
            "must": [
                {"path": "missing_items", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "documented_contradictions_require_clarification",
            "when": [{"path": "contradictions", "operator": "non_empty"}],
            "must": [
                {"path": "clarification_questions", "operator": "non_empty"},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "local_discharge_education_never_claims_expert_outputs",
            "when": [{"path": "translation_status", "operator": "equals", "value": "VERBATIM_DOCUMENTED_CONTENT_ONLY"}],
            "must": [
                {"path": "external_knowledge_used", "operator": "equals", "value": False},
                {"path": "clinical_interpretation_performed", "operator": "equals", "value": False},
                {"path": "clinical_recommendations_generated", "operator": "equals", "value": False},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "discharge_key_result_is_traceable",
            "for_each": "key_results",
            "when": [{"path": "documented_result", "operator": "present"}],
            "must": [
                {"path": "documented_result", "operator": "non_empty"},
                {"path": "evidence_ref", "operator": "non_empty"},
            ],
        },
    ],
    "discharge_summary_structuring": [
        {
            "id": "input_required_has_no_discharge_summary_claims",
            "when": [{"path": "structuring_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "diagnoses", "operator": "empty"},
                {"path": "procedures", "operator": "empty"},
                {"path": "treatment_course", "operator": "equals", "value": ""},
                {"path": "discharge_orders", "operator": "empty"},
                {"path": "follow_up_recommendations", "operator": "empty"},
                {"path": "evidence_items", "operator": "empty"},
            ],
        },
        {
            "id": "completed_discharge_summary_has_core_sections",
            "when": [{"path": "structuring_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [
                {"path": "diagnoses", "operator": "non_empty"},
                {"path": "treatment_course", "operator": "non_empty"},
                {"path": "discharge_orders", "operator": "non_empty"},
                {"path": "follow_up_recommendations", "operator": "non_empty"},
                {"path": "discharge_status.documented_text", "operator": "non_empty"},
                {"path": "missing_sections", "operator": "empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "partial_discharge_summary_has_evidence_and_gaps",
            "when": [{"path": "structuring_status", "operator": "equals", "value": "PARTIAL"}],
            "must": [
                {"path": "missing_sections", "operator": "non_empty"},
                {"path": "evidence_items", "operator": "non_empty"},
            ],
        },
        {
            "id": "governed_discharge_summary_never_claims_inference_or_coding",
            "when": [{"path": "summary_generation_status", "operator": "equals", "value": "VERBATIM_SECTION_REORGANIZATION_ONLY"}],
            "must": [
                {"path": "icd_codes_assigned", "operator": "equals", "value": False},
                {"path": "medication_reconciliation_performed", "operator": "equals", "value": False},
                {"path": "clinical_inference_performed", "operator": "equals", "value": False},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
        {
            "id": "diagnosis_items_are_traceable",
            "for_each": "diagnoses",
            "when": [{"path": "text", "operator": "present"}],
            "must": [
                {"path": "text", "operator": "non_empty"},
                {"path": "evidence_ref", "operator": "non_empty"},
            ],
        },
        {
            "id": "documented_conflicts_require_review",
            "when": [{"path": "conflicts", "operator": "non_empty"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
    ],
    "evidence_extractor": [
        {
            "id": "input_required_has_no_extraction_results",
            "when": [{"path": "extraction_status", "operator": "equals", "value": "INPUT_REQUIRED"}],
            "must": [
                {"path": "input_codes", "operator": "empty"},
                {"path": "located_mentions", "operator": "empty"},
                {"path": "code_results", "operator": "empty"},
            ],
        },
        {
            "id": "completed_extraction_has_input_codes",
            "when": [{"path": "extraction_status", "operator": "equals", "value": "COMPLETED"}],
            "must": [{"path": "input_codes", "operator": "non_empty"}],
        },
        {
            "id": "exact_mentions_are_traceable_not_clinical_support",
            "for_each": "located_mentions",
            "when": [{"path": "evidence_text", "operator": "present"}],
            "must": [
                {"path": "code", "operator": "non_empty"},
                {"path": "evidence_text", "operator": "non_empty"},
                {"path": "clinical_support_assessed", "operator": "equals", "value": False},
            ],
        },
        {
            "id": "exact_mention_policy_requires_manual_review",
            "when": [{"path": "match_basis", "operator": "equals", "value": "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
    ],
    "medical_coding": [
        {
            "id": "failed_rules_require_human_review",
            "when": [{"path": "validation_summary.passed", "operator": "equals", "value": False}],
            "must": [{"path": "human_review.review_required", "operator": "equals", "value": True}],
        },
    ],
    "principal_diagnosis_review": [
        {
            "id": "ready_principal_draft_review_has_complete_evidence",
            "when": [{"path": "review_status", "operator": "equals", "value": "READY_FOR_CODER_REVIEW"}],
            "must": [
                {"path": "missing_required_fields", "operator": "empty"},
                {"path": "candidates", "operator": "non_empty"},
                {"path": "input_conflicts", "operator": "empty"},
                {"path": "candidate_evidence_gaps", "operator": "empty"},
                {"path": "draft_in_candidate_set", "operator": "equals", "value": True},
                {"path": "draft_evidence_complete", "operator": "equals", "value": True},
                {"path": "selection_basis_status", "operator": "equals", "value": "DOCUMENTED"},
            ],
        },
        {
            "id": "complete_principal_draft_status_matches_evidence",
            "when": [{"path": "draft_consistency_status", "operator": "equals", "value": "DOCUMENTED_DRAFT_AND_EVIDENCE_PRESENT"}],
            "must": [
                {"path": "draft_in_candidate_set", "operator": "equals", "value": True},
                {"path": "draft_evidence_complete", "operator": "equals", "value": True},
                {"path": "selection_basis_status", "operator": "equals", "value": "DOCUMENTED"},
            ],
        },
        {
            "id": "matched_draft_has_exactly_one_candidate_flag",
            "when": [{"path": "draft_in_candidate_set", "operator": "equals", "value": True}],
            "must": [{
                "path": "candidates",
                "operator": "count_where_equals",
                "where": [
                    {"path": "is_documented_draft", "operator": "equals", "value": True}
                ],
                "value": 1,
            }],
        },
        {
            "id": "draft_candidate_requires_exact_evidence",
            "for_each": "candidates",
            "when": [{"path": "is_documented_draft", "operator": "equals", "value": True}],
            "must": [
                {"path": "evidence_text", "operator": "non_empty"},
                {"path": "evidence_ref", "operator": "non_empty"},
                {"path": "evidence_status", "operator": "equals", "value": "EXACT_INPUT_SPAN"},
            ],
        },
        {
            "id": "governed_principal_review_never_selects_or_writes",
            "when": [{"path": "review_method", "operator": "equals", "value": "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"}],
            "must": [
                {"path": "diagnosis_extraction_performed", "operator": "equals", "value": False},
                {"path": "code_assignment_performed", "operator": "equals", "value": False},
                {"path": "principal_diagnosis_selection_performed", "operator": "equals", "value": False},
                {"path": "clinical_inference_performed", "operator": "equals", "value": False},
                {"path": "external_rules_used", "operator": "equals", "value": False},
                {"path": "production_submission_blocked", "operator": "equals", "value": True},
                {"path": "production_writeback_blocked", "operator": "equals", "value": True},
                {"path": "manual_review_required", "operator": "equals", "value": True},
            ],
        },
    ],
    "procedure-extractor": [
        {
            "id": "procedure_count_matches_items",
            "when": [{"path": "procedures", "operator": "present"}],
            "must": [
                {
                    "path": "procedures",
                    "operator": "length_equals",
                    "other_path": "total_count",
                }
            ],
        },
        {
            "id": "billable_procedure_requires_performed_evidence",
            "for_each": "procedures",
            "when": [{"path": "code", "operator": "present"}],
            "must": [
                {"path": "status", "operator": "equals", "value": "performed"},
                {"path": "code", "operator": "non_empty"},
                {"path": "display", "operator": "non_empty"},
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "nonbillable_procedure_requires_status_evidence",
            "for_each": "non_billable_mentions",
            "when": [{"path": "text", "operator": "present"}],
            "must": [
                {
                    "path": "status",
                    "operator": "in",
                    "value": ["planned", "historical", "cancelled", "negated", "unknown"],
                },
                {"path": "evidence_text", "operator": "non_empty"},
            ],
        },
        {
            "id": "billable_and_nonbillable_evidence_are_disjoint",
            "when": [{"path": "procedures", "operator": "present"}],
            "must": [{
                "path": "procedures",
                "operator": "disjoint_fields",
                "item_path": "evidence_text",
                "other_path": "non_billable_mentions",
                "other_item_path": "evidence_text",
            }],
        },
        {
            "id": "procedure_issues_require_review",
            "when": [{"path": "issues_found", "operator": "non_empty"}],
            "must": [{"path": "manual_review_required", "operator": "equals", "value": True}],
        },
    ],
}

EVIDENCE_BINDING_OVERRIDES: dict[str, list[dict[str, Any]]] = {
    "triage": [
        {
            "id": "triage_evidence_items_match_input",
            "for_each": "evidence_items",
            "text_path": "text",
            "span_path": "char_span",
        },
    ],
    "claim-check": [
        {
            "id": "claim_check_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "denial-appeals": [
        {
            "id": "denial_appeal_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "clinical-education": [
        {
            "id": "clinical_education_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "text",
            "span_path": "char_span",
        },
    ],
    "clinical-guidelines": [
        {
            "id": "clinical_guidelines_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "text",
            "span_path": "char_span",
        },
    ],
    "clinical-documentation-improvement-agent": [
        {
            "id": "cdi_gap_evidence_matches_document",
            "for_each": "documentation_gaps",
            "text_path": "evidence_span.quote",
            "start_path": "evidence_span.char_start",
            "end_path": "evidence_span.char_end",
            "document_id_path": "evidence_span.document_id",
        },
        {
            "id": "cdi_query_evidence_matches_document",
            "for_each": "proposed_provider_queries",
            "text_path": "evidence_span.quote",
            "start_path": "evidence_span.char_start",
            "end_path": "evidence_span.char_end",
            "document_id_path": "evidence_span.document_id",
        },
    ],
    "diagnosis-extractor": [
        {
            "id": "diagnosis_evidence_matches_input",
            "for_each": "diagnoses",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "noncodable_evidence_matches_input",
            "for_each": "non_codable_mentions",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "evidence_extractor": [
        {
            "id": "located_mention_matches_input",
            "for_each": "located_mentions",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "principal_diagnosis_review": [
        {
            "id": "principal_review_evidence_items_match_input",
            "for_each": "evidence_items",
            "text_path": "text",
            "span_path": "char_span",
        },
        {
            "id": "principal_candidate_evidence_matches_input",
            "for_each": "candidates",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "principal_selection_basis_matches_input",
            "for_each": "declared_selection_basis",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "procedure-extractor": [
        {
            "id": "procedure_evidence_matches_input",
            "for_each": "procedures",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "nonbillable_evidence_matches_input",
            "for_each": "non_billable_mentions",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "medical_coding": [
        {
            "id": "coding_diagnosis_evidence_matches_document",
            "for_each": "documentation_analysis.diagnosis_evidence",
            "text_path": "text",
            "start_path": "char_start",
            "end_path": "char_end",
            "document_id_path": "doc_id",
        },
        {
            "id": "coding_procedure_evidence_matches_document",
            "for_each": "documentation_analysis.procedure_evidence",
            "text_path": "text",
            "start_path": "char_start",
            "end_path": "char_end",
            "document_id_path": "doc_id",
        },
        {
            "id": "coding_negated_evidence_matches_document",
            "for_each": "documentation_analysis.negated_findings",
            "text_path": "text",
            "start_path": "char_start",
            "end_path": "char_end",
            "document_id_path": "doc_id",
        },
        {
            "id": "coding_history_evidence_matches_document",
            "for_each": "documentation_analysis.historical_conditions",
            "text_path": "text",
            "start_path": "char_start",
            "end_path": "char_end",
            "document_id_path": "doc_id",
        },
    ],
    "med_reconciliation": [
        {
            "id": "home_medication_evidence_matches_input",
            "for_each": "home_medications",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "inpatient_medication_evidence_matches_input",
            "for_each": "inpatient_medications",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "discharge_medication_evidence_matches_input",
            "for_each": "discharge_medications",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
        {
            "id": "unresolved_medication_evidence_matches_input",
            "for_each": "unresolved_mentions",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "nursing_handoff": [
        {
            "id": "nursing_handoff_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "icu_summary": [
        {
            "id": "icu_summary_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "discharge_edu": [
        {
            "id": "discharge_education_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
    "discharge_summary_structuring": [
        {
            "id": "discharge_summary_evidence_matches_input",
            "for_each": "evidence_items",
            "text_path": "evidence_text",
            "span_path": "char_span",
        },
    ],
}

CROSS_AGENT_RELATION_OVERRIDES: dict[str, list[dict[str, Any]]] = {
    "compliance-guardrail": [{
        "id": "reviewed_codes_match_code_validation",
        "local_path": "reviewed_codes",
        "local_item_path": "code",
        "upstream_agent_id": "code-validation-agent",
        "upstream_path": "validated_codes",
        "upstream_item_path": "code",
        "operator": "local_items_subset_upstream_items",
        "normalization": "medical_code",
        "required": False,
    }],
    "code-validation": [{
        "id": "validated_codes_match_medical_coding",
        "local_path": "validated_codes",
        "local_item_path": "code",
        "upstream_agent_id": "medical-coding-agent",
        "upstream_sources": [
            {"path": "code_assignment.primary_diagnosis.code"},
            {
                "path": "code_assignment.secondary_diagnoses",
                "item_path": "code",
            },
            {
                "path": "code_assignment.procedures",
                "item_path": "code",
            },
        ],
        "operator": "local_items_subset_upstream_values",
        "normalization": "medical_code",
        "required": False,
    }],
    "drg-analyzer": [
        {
            "id": "drg_primary_matches_medical_coding",
            "local_path": "coded_case.primary_diagnosis.code",
            "upstream_agent_id": "medical-coding-agent",
            "upstream_path": "code_assignment.primary_diagnosis.code",
            "upstream_item_path": "code",
            "operator": "equals_upstream",
            "normalization": "medical_code",
            "required": False,
        },
        {
            "id": "drg_secondary_matches_medical_coding",
            "local_path": "coded_case.secondary_diagnoses",
            "local_item_path": "code",
            "upstream_agent_id": "medical-coding-agent",
            "upstream_path": "code_assignment.secondary_diagnoses",
            "upstream_item_path": "code",
            "operator": "local_items_subset_upstream_items",
            "normalization": "medical_code",
            "allow_empty_local": True,
            "required": False,
        },
        {
            "id": "drg_procedures_match_medical_coding",
            "local_path": "coded_case.procedures",
            "local_item_path": "code",
            "upstream_agent_id": "medical-coding-agent",
            "upstream_path": "code_assignment.procedures",
            "upstream_item_path": "code",
            "operator": "local_items_subset_upstream_items",
            "normalization": "medical_code",
            "allow_empty_local": True,
            "required": False,
        },
    ],
    "principal_diagnosis_review": [{
        "id": "documented_draft_code_matches_extracted_diagnosis",
        "local_path": "documented_coding_draft.code",
        "upstream_agent_id": "diagnosis-extractor",
        "upstream_path": "diagnoses",
        "upstream_item_path": "icd10_cn_code",
        "operator": "scalar_in_upstream_items",
        "normalization": "medical_code",
        "required": False,
    }],
    "evidence_extractor": [{
        "id": "input_codes_match_extracted_diagnoses",
        "local_path": "code_results",
        "local_item_path": "code",
        "upstream_agent_id": "diagnosis-extractor",
        "upstream_path": "diagnoses",
        "upstream_item_path": "icd10_cn_code",
        "operator": "local_items_subset_upstream_items",
        "normalization": "medical_code",
        "required": False,
    }],
    "medical_coding": [
        {
            "id": "coding_primary_matches_principal_review",
            "local_path": "code_assignment.primary_diagnosis.code",
            "upstream_agent_id": "principal-diagnosis-review",
            "upstream_path": "candidates",
            "upstream_item_path": "code",
            "operator": "scalar_in_upstream_items",
            "normalization": "medical_code",
            "required": False,
        },
        {
            "id": "coding_secondary_matches_extracted_diagnoses",
            "local_path": "code_assignment.secondary_diagnoses",
            "local_item_path": "code",
            "upstream_agent_id": "diagnosis-extractor",
            "upstream_path": "diagnoses",
            "upstream_item_path": "icd10_cn_code",
            "operator": "local_items_subset_upstream_items",
            "normalization": "medical_code",
            "allow_empty_local": True,
            "required": False,
        },
        {
            "id": "coding_procedures_match_extracted_procedures",
            "local_path": "code_assignment.procedures",
            "local_item_path": "code",
            "upstream_agent_id": "procedure-extractor",
            "upstream_path": "procedures",
            "upstream_item_path": "code",
            "operator": "local_items_subset_upstream_items",
            "normalization": "medical_code",
            "allow_empty_local": True,
            "required": False,
        },
    ],
}


def primitive(type_name: str) -> dict[str, Any]:
    return {"type": type_name}


def array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": copy.deepcopy(items)}


def obj(
    properties: dict[str, dict[str, Any]],
    *,
    required: list[str] | None = None,
    additional: bool | dict[str, Any] = False,
) -> dict[str, Any]:
    return {
        "type": "object",
        # Split shared leaf constants (for example STRING) so applying a
        # constraint to one property cannot mutate its siblings.
        "properties": {
            name: copy.deepcopy(child) for name, child in properties.items()
        },
        "required": required if required is not None else list(properties),
        "additionalProperties": copy.deepcopy(additional),
    }


STRING = primitive("string")
INTEGER = primitive("integer")
NUMBER = primitive("number")
BOOLEAN = primitive("boolean")
STRING_ARRAY = array(STRING)
INTEGER_ARRAY = array(INTEGER)

EVIDENCE_CANDIDATE = obj({
    "code": STRING,
    "evidence_text": STRING,
    "evidence_strength": STRING,
    "char_span": INTEGER_ARRAY,
    "confidence": NUMBER,
    "manual_review_prompt": STRING,
})
EVIDENCE_SPAN = obj({
    "text": STRING,
    "char_start": INTEGER,
    "char_end": INTEGER,
    "doc_id": STRING,
    "doc_type": STRING,
    "confidence": NUMBER,
}, required=["text"])
CODE_EVIDENCE = obj({
    "text": STRING,
    "kind": STRING,
    "char_start": INTEGER,
    "char_end": INTEGER,
    "doc_id": STRING,
    "doc_type": STRING,
    "confidence": NUMBER,
}, required=["text"])
DIAGNOSIS_ENTRY = obj({
    "code": STRING,
    "description": STRING,
    "confidence": NUMBER,
    "category": STRING,
    "evidence": array(CODE_EVIDENCE),
}, required=["code", "description", "confidence", "category", "evidence"])
PROCEDURE_ENTRY = DIAGNOSIS_ENTRY

STRING_LENGTH_OVERRIDES: dict[tuple[str, str], tuple[int | None, int]] = {
    ("claim-check", "missing_required_fields[]"): (1, 256),
    ("claim-check", "missing_policy_items[]"): (1, 256),
    ("claim-check", "evidence_items[].evidence_id"): (1, 64),
    ("claim-check", "evidence_items[].field"): (1, 64),
    ("claim-check", "evidence_items[].source_label"): (1, 128),
    ("claim-check", "evidence_items[].evidence_text"): (1, 32768),
    ("claim-check", "limitations[]"): (1, 1024),
    ("claim-check", "trace_refs.run_id"): (1, 128),
    ("claim-check", "trace_refs.provider_trace_refs[]"): (1, 512),
    ("compliance-guardrail", "reviewed_codes[].code"): (1, 64),
    ("evidence-ranker", "candidate_code"): (None, 32),
    ("evidence-ranker", "ranked_evidence[].evidence_id"): (1, 64),
    ("evidence-ranker", "ranked_evidence[].source"): (None, 200),
    ("evidence-ranker", "ranked_evidence[].content"): (1, 1000),
    ("evidence-ranker", "ranked_evidence[].score_components[]"): (1, 128),
    ("evidence-ranker", "ranked_evidence[].rationale"): (1, 1024),
    ("evidence-ranker", "conflicts[].evidence_ids[]"): (1, 64),
    ("evidence-ranker", "conflicts[].description"): (1, 512),
    ("evidence-ranker", "unsupported_claims[].evidence_id"): (1, 64),
    ("evidence-ranker", "unsupported_claims[].claim"): (None, 200),
    ("evidence-ranker", "unsupported_claims[].reason"): (1, 512),
    ("evidence-ranker", "confidence_calibration.rationale"): (1, 512),
    ("evidence-ranker", "source_coverage.covered_sources[]"): (1, 200),
    ("evidence-ranker", "source_coverage.missing_sources[]"): (1, 64),
    ("evidence-ranker", "source_coverage.coverage_assessment"): (1, 512),
    ("evidence-ranker", "limitations[]"): (1, 512),
    ("evidence-ranker", "summary"): (1, 512),
    ("evidence-ranker", "markdown"): (1, 20000),
    ("evidence_extractor", "input_codes[]"): (1, 32),
    ("evidence_extractor", "located_mentions[].code"): (1, 32),
    ("evidence_extractor", "located_mentions[].evidence_text"): (1, 200),
    ("evidence_extractor", "located_mentions[].matched_term"): (1, 200),
    ("evidence_extractor", "located_mentions[].context_rule"): (1, 128),
    ("evidence_extractor", "code_results[].code"): (1, 32),
    ("evidence_extractor", "code_results[].catalog_display"): (0, 512),
    ("evidence_extractor", "code_results[].manual_review_prompt"): (1, 1024),
    ("evidence_extractor", "unmatched_codes[]"): (1, 32),
    ("evidence_extractor", "source_version"): (0, 512),
    ("evidence_extractor", "limitations[]"): (1, 512),
    ("evidence_extractor", "summary"): (1, 512),
    ("evidence_extractor", "markdown"): (1, 20000),
    ("icd10_navigator", "query_interpretation"): (0, 512),
    ("icd10_navigator", "query_used"): (0, 256),
    ("icd10_navigator", "rephrased_query"): (0, 256),
    ("icd10_navigator", "index_terms[]"): (0, 256),
    ("icd10_navigator", "candidate_codes[].code"): (0, 32),
    ("icd10_navigator", "candidate_codes[].display"): (0, 512),
    ("icd10_navigator", "candidate_codes[].description"): (0, 1024),
    ("icd10_navigator", "candidate_codes[].index_term"): (0, 256),
    ("icd10_navigator", "candidate_codes[].rationale"): (0, 1024),
    ("icd10_navigator", "candidate_codes[].parent.code"): (0, 32),
    ("icd10_navigator", "candidate_codes[].parent.display"): (0, 512),
    ("icd10_navigator", "candidate_codes[].siblings[].code"): (0, 32),
    ("icd10_navigator", "candidate_codes[].siblings[].display"): (0, 512),
    ("icd10_navigator", "candidate_codes[].children[].code"): (0, 32),
    ("icd10_navigator", "candidate_codes[].children[].display"): (0, 512),
    ("icd10_navigator", "candidate_codes[].source_version"): (0, 128),
    ("icd10_navigator", "hierarchy_notes[]"): (0, 1024),
    ("icd10_navigator", "inclusion_exclusion_notes[]"): (0, 1024),
    ("icd10_navigator", "source_version"): (0, 512),
    ("rule_explainer", "code"): (0, 32),
    ("rule_explainer", "catalog_name"): (0, 512),
    ("rule_explainer", "chapter"): (0, 512),
    ("rule_explainer", "hierarchy.chapter_no"): (0, 64),
    ("rule_explainer", "hierarchy.category_code"): (0, 32),
    ("rule_explainer", "hierarchy.children[].code"): (1, 32),
    ("rule_explainer", "hierarchy.children[].display"): (0, 512),
    ("rule_explainer", "explanation_summary"): (1, 1024),
    ("rule_explainer", "catalog_facts[]"): (1, 1024),
    ("rule_explainer", "guideline_basis[]"): (1, 2048),
    ("rule_explainer", "evidence_refs[]"): (1, 1024),
    ("rule_explainer", "unsupported_scope[]"): (1, 1024),
    ("rule_explainer", "limitations[]"): (1, 2048),
    ("rule_explainer", "source_version"): (0, 512),
    ("med_reconciliation", "home_medications[].drug_name"): (1, 256),
    ("med_reconciliation", "inpatient_medications[].drug_name"): (1, 256),
    ("med_reconciliation", "discharge_medications[].drug_name"): (1, 256),
    ("med_reconciliation", "home_medications[].evidence_text"): (1, 1024),
    ("med_reconciliation", "inpatient_medications[].evidence_text"): (1, 1024),
    ("med_reconciliation", "discharge_medications[].evidence_text"): (1, 1024),
    ("med_reconciliation", "reconciliation_summary[].drug_name"): (1, 256),
    ("med_reconciliation", "discrepancies[].description"): (1, 2048),
    ("med_reconciliation", "missing_rationale[]"): (1, 2048),
    ("med_reconciliation", "follow_up_items[]"): (1, 2048),
    ("med_reconciliation", "limitations[]"): (1, 2048),
    ("nursing_handoff", "assignment_summary[].patient_identifier"): (1, 160),
    ("nursing_handoff", "assignment_summary[].room_bed"): (0, 160),
    ("nursing_handoff", "assignment_summary[].primary_issue"): (0, 2048),
    ("nursing_handoff", "assignment_summary[].current_status"): (0, 2048),
    ("nursing_handoff", "assignment_summary[].open_items[]"): (1, 2048),
    ("nursing_handoff", "assignment_summary[].evidence_refs[]"): (1, 128),
    ("nursing_handoff", "patient_handoffs[].patient_identifier"): (1, 160),
    ("nursing_handoff", "patient_handoffs[].room_bed"): (0, 160),
    ("nursing_handoff", "patient_handoffs[].primary_issue"): (0, 2048),
    ("nursing_handoff", "patient_handoffs[].current_status"): (0, 2048),
    ("nursing_handoff", "patient_handoffs[].background"): (0, 2048),
    ("nursing_handoff", "patient_handoffs[].recent_events[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].lines_devices[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].medications[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].labs_diagnostics[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].pending_tasks[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].safety_precautions[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].documented_escalation_triggers[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].gaps_conflicts[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].key_considerations[]"): (1, 2048),
    ("nursing_handoff", "patient_handoffs[].evidence_refs[]"): (1, 128),
    ("nursing_handoff", "patient_handoffs[].missing_sections[]"): (1, 128),
    ("nursing_handoff", "evidence_items[].evidence_id"): (1, 128),
    ("nursing_handoff", "evidence_items[].source_label"): (1, 128),
    ("nursing_handoff", "evidence_items[].evidence_text"): (1, 2048),
    ("nursing_handoff", "source_completeness.missing_sections[]"): (1, 128),
    ("nursing_handoff", "limitations[]"): (1, 2048),
    ("nursing_handoff", "trace_refs.run_id"): (1, 128),
    ("nursing_handoff", "trace_refs.trace_id"): (0, 128),
    ("nursing_handoff", "trace_refs.provider_trace_refs[]"): (1, 512),
    ("icu_summary", "patient_background.patient_information"): (0, 2048),
    ("icu_summary", "patient_background.medical_history"): (0, 4096),
    ("icu_summary", "patient_background.surgical_history"): (0, 4096),
    ("icu_summary", "patient_background.allergies"): (0, 2048),
    ("icu_summary", "patient_background.social_history"): (0, 4096),
    ("icu_summary", "admission_reason"): (0, 4096),
    ("icu_summary", "admission_diagnoses[].diagnosis"): (1, 2048),
    ("icu_summary", "admission_diagnoses[].evidence_ref"): (1, 128),
    ("icu_summary", "timeline[].time"): (0, 128),
    ("icu_summary", "timeline[].event"): (1, 4096),
    ("icu_summary", "timeline[].evidence_ref"): (1, 128),
    ("icu_summary", "active_problems[].problem"): (1, 2048),
    ("icu_summary", "active_problems[].evidence_ref"): (1, 128),
    ("icu_summary", "organ_support[].detail"): (1, 2048),
    ("icu_summary", "organ_support[].route"): (0, 256),
    ("icu_summary", "organ_support[].evidence_ref"): (1, 128),
    ("icu_summary", "medications[].documented_text"): (1, 2048),
    ("icu_summary", "medications[].dose"): (0, 256),
    ("icu_summary", "medications[].route"): (0, 256),
    ("icu_summary", "medications[].evidence_ref"): (1, 128),
    ("icu_summary", "vital_signs[].text"): (1, 2048),
    ("icu_summary", "vital_signs[].evidence_ref"): (1, 128),
    ("icu_summary", "laboratory_results[].text"): (1, 2048),
    ("icu_summary", "laboratory_results[].evidence_ref"): (1, 128),
    ("icu_summary", "procedures[].text"): (1, 2048),
    ("icu_summary", "procedures[].evidence_ref"): (1, 128),
    ("icu_summary", "key_trends[].indicator"): (1, 256),
    ("icu_summary", "key_trends[].trend"): (1, 2048),
    ("icu_summary", "key_trends[].interpretation"): (1, 512),
    ("icu_summary", "key_trends[].evidence_ref"): (1, 128),
    ("icu_summary", "pending_items[].item"): (1, 2048),
    ("icu_summary", "pending_items[].evidence_ref"): (1, 128),
    ("icu_summary", "risks[].risk"): (1, 2048),
    ("icu_summary", "risks[].basis"): (1, 512),
    ("icu_summary", "risks[].evidence_ref"): (1, 128),
    ("icu_summary", "conflicts[].description"): (1, 2048),
    ("icu_summary", "conflicts[].evidence"): (1, 2048),
    ("icu_summary", "conflicts[].field"): (1, 128),
    ("icu_summary", "conflicts[].evidence_ref"): (1, 128),
    ("icu_summary", "source_completeness.missing_sections[]"): (1, 128),
    ("icu_summary", "evidence_items[].evidence_id"): (1, 128),
    ("icu_summary", "evidence_items[].source_label"): (1, 128),
    ("icu_summary", "evidence_items[].evidence_text"): (1, 4096),
    ("icu_summary", "limitations[]"): (1, 2048),
    ("icu_summary", "trace_refs.run_id"): (1, 128),
    ("icu_summary", "trace_refs.trace_id"): (0, 128),
    ("icu_summary", "trace_refs.provider_trace_refs[]"): (1, 512),
    ("discharge_edu", "diagnosis_summary"): (0, 4096),
    ("discharge_edu", "encounter_summary.reason_for_visit"): (0, 4096),
    ("discharge_edu", "encounter_summary.treatment_course"): (0, 4096),
    ("discharge_edu", "encounter_summary.discharge_destination"): (0, 1024),
    ("discharge_edu", "key_results[].documented_result"): (1, 4096),
    ("discharge_edu", "key_results[].interpretation"): (1, 512),
    ("discharge_edu", "key_results[].evidence_ref"): (1, 128),
    ("discharge_edu", "medication_instructions"): (0, 4096),
    ("discharge_edu", "follow_up"): (0, 4096),
    ("discharge_edu", "warning_signs"): (0, 4096),
    ("discharge_edu", "lifestyle"): (0, 4096),
    ("discharge_edu", "pending_results"): (0, 4096),
    ("discharge_edu", "teach_back_questions[]"): (1, 1024),
    ("discharge_edu", "clarification_questions[]"): (1, 1024),
    ("discharge_edu", "contradictions[].description"): (1, 2048),
    ("discharge_edu", "contradictions[].evidence_ref"): (1, 128),
    ("discharge_edu", "missing_items[]"): (1, 128),
    ("discharge_edu", "source_completeness.documented_sections[]"): (1, 128),
    ("discharge_edu", "source_completeness.missing_sections[]"): (1, 128),
    ("discharge_edu", "evidence_items[].evidence_id"): (1, 128),
    ("discharge_edu", "evidence_items[].source_label"): (1, 128),
    ("discharge_edu", "evidence_items[].evidence_text"): (1, 4096),
    ("discharge_edu", "limitations[]"): (1, 2048),
    ("discharge_edu", "trace_refs.run_id"): (1, 128),
    ("discharge_edu", "trace_refs.provider_trace_refs[]"): (1, 512),
    ("discharge_summary_structuring", "encounter_metadata.admission_date"):
        (0, 256),
    ("discharge_summary_structuring", "encounter_metadata.discharge_date"):
        (0, 256),
    ("discharge_summary_structuring", "encounter_metadata.department"):
        (0, 512),
    ("discharge_summary_structuring", "encounter_metadata.discharge_destination"):
        (0, 512),
    ("discharge_summary_structuring", "admission_reason"): (0, 4096),
    ("discharge_summary_structuring", "diagnoses[].text"): (1, 4096),
    ("discharge_summary_structuring", "diagnoses[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "procedures[].text"): (1, 4096),
    ("discharge_summary_structuring", "procedures[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "treatment_course"): (0, 32768),
    ("discharge_summary_structuring", "key_results[].documented_result"):
        (1, 4096),
    ("discharge_summary_structuring", "key_results[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "discharge_orders[].documented_instruction"):
        (1, 4096),
    ("discharge_summary_structuring", "discharge_orders[].evidence_ref"):
        (1, 128),
    ("discharge_summary_structuring", "follow_up_recommendations[].documented_instruction"):
        (1, 4096),
    ("discharge_summary_structuring", "follow_up_recommendations[].evidence_ref"):
        (1, 128),
    ("discharge_summary_structuring", "discharge_status.documented_text"):
        (0, 4096),
    ("discharge_summary_structuring", "discharge_status.evidence_ref"): (0, 128),
    ("discharge_summary_structuring", "allergies"): (0, 4096),
    ("discharge_summary_structuring", "pending_results[].documented_text"):
        (1, 4096),
    ("discharge_summary_structuring", "pending_results[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "complications[].documented_text"):
        (1, 4096),
    ("discharge_summary_structuring", "complications[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "conflicts[].description"): (1, 4096),
    ("discharge_summary_structuring", "conflicts[].evidence_ref"): (1, 128),
    ("discharge_summary_structuring", "missing_sections[]"): (1, 128),
    ("discharge_summary_structuring", "source_completeness.documented_sections[]"):
        (1, 128),
    ("discharge_summary_structuring", "source_completeness.missing_sections[]"):
        (1, 128),
    ("discharge_summary_structuring", "evidence_items[].evidence_id"): (1, 128),
    ("discharge_summary_structuring", "evidence_items[].source_label"): (1, 128),
    ("discharge_summary_structuring", "evidence_items[].evidence_text"):
        (1, 4096),
    ("discharge_summary_structuring", "limitations[]"): (1, 2048),
    ("discharge_summary_structuring", "trace_refs.run_id"): (1, 128),
    ("discharge_summary_structuring", "trace_refs.provider_trace_refs[]"):
        (1, 512),
    ("referral_gen", "referral_direction.evidence_ref"): (0, 128),
    ("referral_gen", "patient_identifiers.name.evidence_ref"): (0, 128),
    ("referral_gen", "patient_identifiers.date_of_birth.evidence_ref"): (0, 128),
    ("referral_gen", "patient_identifiers.medical_record_number.evidence_ref"): (0, 128),
    ("referral_gen", "referring_party.clinician.evidence_ref"): (0, 128),
    ("referral_gen", "referring_party.facility.evidence_ref"): (0, 128),
    ("referral_gen", "referring_party.department.evidence_ref"): (0, 128),
    ("referral_gen", "referring_party.contact.evidence_ref"): (0, 128),
    ("referral_gen", "receiving_party.clinician.evidence_ref"): (0, 128),
    ("referral_gen", "receiving_party.specialty.evidence_ref"): (0, 128),
    ("referral_gen", "receiving_party.facility.evidence_ref"): (0, 128),
    ("referral_gen", "referral_reason.evidence_ref"): (0, 128),
    ("referral_gen", "urgency.evidence_refs[]"): (0, 128),
    ("referral_gen", "clinical_summary.chief_concern.evidence_ref"): (0, 128),
    ("referral_gen", "clinical_summary.relevant_history.evidence_ref"): (0, 128),
    ("referral_gen", "clinical_summary.current_presentation.evidence_ref"): (0, 128),
    ("referral_gen", "clinical_summary.working_assessment.evidence_ref"): (0, 128),
    ("referral_gen", "diagnostic_results[].documented_text"): (1, 32768),
    ("referral_gen", "diagnostic_results[].evidence_ref"): (1, 128),
    ("referral_gen", "medications[].documented_text"): (1, 32768),
    ("referral_gen", "medications[].evidence_ref"): (1, 128),
    ("referral_gen", "allergies[].documented_text"): (1, 32768),
    ("referral_gen", "allergies[].evidence_ref"): (1, 128),
    ("referral_gen", "requested_action.evidence_ref"): (0, 128),
    ("referral_gen", "missing_required_fields[]"): (1, 256),
    ("referral_gen", "missing_supporting_items[]"): (1, 256),
    ("referral_gen", "evidence_items[].evidence_id"): (1, 128),
    ("referral_gen", "evidence_items[].field"): (1, 128),
    ("referral_gen", "evidence_items[].source_label"): (1, 128),
    ("referral_gen", "evidence_items[].evidence_text"): (1, 32768),
    ("referral_gen", "limitations[]"): (1, 1024),
    ("referral_gen", "trace_refs.run_id"): (1, 128),
    ("referral_gen", "trace_refs.provider_trace_refs[]"): (1, 512),
    ("prior_auth", "missing_required_fields[]"): (1, 256),
    ("prior_auth", "missing_supporting_items[]"): (1, 256),
    ("prior_auth", "missing_policy_items[]"): (1, 256),
    ("prior_auth", "evidence_items[].evidence_id"): (1, 64),
    ("prior_auth", "evidence_items[].field"): (1, 64),
    ("prior_auth", "evidence_items[].source_label"): (1, 128),
    ("prior_auth", "evidence_items[].evidence_text"): (1, 32768),
    ("prior_auth", "limitations[]"): (1, 1024),
    ("prior_auth", "trace_refs.run_id"): (1, 128),
    ("prior_auth", "trace_refs.provider_trace_refs[]"): (1, 512),
}
ARRAY_LENGTH_OVERRIDES: dict[tuple[str, str], tuple[int | None, int]] = {
    ("drg-analyzer", "limitations"): (1, 100),
    ("triage", "red_flags"): (0, 64),
    ("triage", "immediate_actions"): (1, 10),
    ("triage", "missing_information"): (0, 64),
    ("triage", "questionnaire_validation.errors"): (0, 128),
    ("triage", "decision_path"): (0, 64),
    ("triage", "protocol_candidate.red_flag_codes"): (0, 64),
    ("triage", "clarification_questions"): (0, 64),
    ("triage", "input_conflicts"): (0, 128),
    ("triage", "evidence_items"): (0, 100),
    ("triage", "evidence_items[].char_span"): (2, 2),
    ("triage", "limitations"): (6, 6),
    ("triage", "trace_refs.provider_trace_refs"): (1, 20),
    ("principal_diagnosis_review", "candidates"): (0, 100),
    ("principal_diagnosis_review", "candidates[].char_span"): (2, 2),
    ("principal_diagnosis_review", "declared_selection_basis"): (0, 100),
    ("principal_diagnosis_review", "declared_selection_basis[].char_span"): (2, 2),
    ("principal_diagnosis_review", "candidate_evidence_gaps"): (0, 100),
    ("principal_diagnosis_review", "input_conflicts"): (0, 100),
    ("principal_diagnosis_review", "input_conflicts[].evidence_refs"): (1, 100),
    ("principal_diagnosis_review", "evidence_items"): (0, 300),
    ("principal_diagnosis_review", "evidence_items[].char_span"): (2, 2),
    ("principal_diagnosis_review", "missing_required_fields"): (0, 20),
    ("principal_diagnosis_review", "limitations"): (6, 6),
    ("principal_diagnosis_review", "trace_refs.provider_trace_refs"): (0, 20),
    ("claim-check", "billed_diagnoses"): (0, 80),
    ("claim-check", "billed_procedures"): (0, 80),
    ("claim-check", "billed_items"): (0, 80),
    ("claim-check", "clinical_documentation"): (0, 80),
    ("claim-check", "provided_policy.requirements"): (0, 80),
    ("claim-check", "missing_required_fields"): (0, 20),
    ("claim-check", "missing_policy_items"): (0, 10),
    ("claim-check", "evidence_items"): (0, 200),
    ("claim-check", "evidence_items[].char_span"): (2, 2),
    ("claim-check", "limitations"): (7, 8),
    ("claim-check", "trace_refs.provider_trace_refs"): (0, 20),
    ("denial-appeals", "denied_claim_lines"): (0, 80),
    ("denial-appeals", "denied_diagnoses"): (0, 80),
    ("denial-appeals", "denied_procedures"): (0, 80),
    ("denial-appeals", "denied_items"): (0, 80),
    ("denial-appeals", "clinical_documentation"): (0, 80),
    ("denial-appeals", "submitted_documents"): (0, 80),
    ("denial-appeals", "prior_authorization_information"): (0, 80),
    ("denial-appeals", "eligibility_information"): (0, 80),
    ("denial-appeals", "provided_policy.requirements"): (0, 80),
    ("denial-appeals", "documented_corrections"): (0, 80),
    ("denial-appeals", "corrected_claim_checklist"): (0, 80),
    ("denial-appeals", "missing_required_fields"): (0, 20),
    ("denial-appeals", "missing_supporting_items"): (0, 20),
    ("denial-appeals", "missing_policy_items"): (0, 10),
    ("denial-appeals", "evidence_items"): (0, 200),
    ("denial-appeals", "evidence_items[].char_span"): (2, 2),
    ("denial-appeals", "limitations"): (8, 9),
    ("denial-appeals", "trace_refs.provider_trace_refs"): (0, 20),
    ("clinical-education", "source_statements"): (0, 80),
    ("clinical-education", "learning_objectives"): (0, 80),
    ("clinical-education", "learning_objectives[].source_statement_ids"): (1, 80),
    ("clinical-education", "key_points"): (0, 80),
    ("clinical-education", "evidence_citations"): (0, 80),
    ("clinical-education", "knowledge_checks"): (0, 80),
    ("clinical-education", "evidence_items"): (0, 200),
    ("clinical-education", "evidence_items[].char_span"): (2, 2),
    ("clinical-education", "missing_required_fields"): (0, 20),
    ("clinical-education", "missing_source_metadata"): (0, 20),
    ("clinical-education", "limitations"): (6, 7),
    ("clinical-education", "trace_refs.provider_trace_refs"): (0, 20),
    ("clinical-guidelines", "guideline_criteria"): (0, 100),
    ("clinical-guidelines", "documented_facts"): (0, 100),
    ("clinical-guidelines", "documentation_conflicts"): (0, 100),
    ("clinical-guidelines", "documentation_conflicts[].documented_values"): (2, 100),
    ("clinical-guidelines", "documentation_conflicts[].source_documents"): (2, 100),
    ("clinical-guidelines", "documentation_conflicts[].evidence_refs"): (2, 100),
    ("clinical-guidelines", "criteria_checked"): (0, 100),
    ("clinical-guidelines", "criteria_checked[].observed_evidence"): (0, 20),
    ("clinical-guidelines", "criteria_checked[].patient_evidence_refs"): (0, 20),
    ("clinical-guidelines", "aligned_items"): (0, 100),
    ("clinical-guidelines", "deviations"): (0, 100),
    ("clinical-guidelines", "not_assessable_items"): (0, 100),
    ("clinical-guidelines", "evidence_citations"): (0, 100),
    ("clinical-guidelines", "evidence_items"): (0, 300),
    ("clinical-guidelines", "evidence_items[].char_span"): (2, 2),
    ("clinical-guidelines", "missing_required_fields"): (0, 20),
    ("clinical-guidelines", "missing_source_metadata"): (0, 20),
    ("clinical-guidelines", "missing_patient_information"): (0, 100),
    ("clinical-guidelines", "limitations"): (6, 8),
    ("clinical-guidelines", "trace_refs.provider_trace_refs"): (0, 20),
    ("evidence_extractor", "input_codes"): (0, 20),
    ("evidence_extractor", "located_mentions"): (0, 100),
    ("evidence_extractor", "code_results"): (0, 20),
    ("evidence_extractor", "unmatched_codes"): (0, 20),
    ("evidence_extractor", "uncoded_findings"): (0, 0),
    ("evidence_extractor", "limitations"): (1, 10),
    ("evidence-ranker", "ranked_evidence"): (0, 50),
    ("evidence-ranker", "ranked_evidence[].score_components"): (0, 10),
    ("evidence-ranker", "conflicts"): (0, 50),
    ("evidence-ranker", "conflicts[].evidence_ids"): (1, 50),
    ("evidence-ranker", "unsupported_claims"): (0, 100),
    ("evidence-ranker", "source_coverage.covered_sources"): (0, 50),
    ("evidence-ranker", "source_coverage.missing_sources"): (0, 50),
    ("evidence-ranker", "limitations"): (1, 10),
    ("icd10_navigator", "index_terms"): (0, 6),
    ("icd10_navigator", "candidate_codes"): (0, 3),
    ("icd10_navigator", "candidate_codes[].siblings"): (0, 10),
    ("icd10_navigator", "candidate_codes[].children"): (0, 10),
    ("icd10_navigator", "hierarchy_notes"): (0, 3),
    ("icd10_navigator", "inclusion_exclusion_notes"): (0, 3),
    ("rule_explainer", "hierarchy.children"): (0, 10),
    ("rule_explainer", "catalog_facts"): (0, 20),
    ("rule_explainer", "guideline_basis"): (1, 10),
    ("rule_explainer", "evidence_refs"): (0, 10),
    ("rule_explainer", "unsupported_scope"): (1, 10),
    ("rule_explainer", "limitations"): (1, 10),
    ("med_reconciliation", "home_medications"): (0, 100),
    ("med_reconciliation", "inpatient_medications"): (0, 100),
    ("med_reconciliation", "discharge_medications"): (0, 100),
    ("med_reconciliation", "reconciliation_summary"): (0, 100),
    ("med_reconciliation", "discrepancies"): (0, 200),
    ("med_reconciliation", "interaction_risks"): (0, 0),
    ("med_reconciliation", "allergy_conflicts"): (0, 100),
    ("med_reconciliation", "missing_rationale"): (0, 200),
    ("med_reconciliation", "follow_up_items"): (0, 200),
    ("med_reconciliation", "unresolved_mentions"): (0, 100),
    ("med_reconciliation", "limitations"): (1, 10),
    ("nursing_handoff", "assignment_summary"): (0, 10),
    ("nursing_handoff", "assignment_summary[].open_items"): (0, 100),
    ("nursing_handoff", "assignment_summary[].evidence_refs"): (1, 200),
    ("nursing_handoff", "patient_handoffs"): (0, 10),
    ("nursing_handoff", "patient_handoffs[].recent_events"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].lines_devices"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].medications"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].labs_diagnostics"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].pending_tasks"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].safety_precautions"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].documented_escalation_triggers"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].gaps_conflicts"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].key_considerations"): (0, 100),
    ("nursing_handoff", "patient_handoffs[].evidence_refs"): (1, 200),
    ("nursing_handoff", "patient_handoffs[].missing_sections"): (0, 8),
    ("nursing_handoff", "safety_risks"): (0, 100),
    ("nursing_handoff", "lines_devices"): (0, 100),
    ("nursing_handoff", "pending_tasks"): (0, 200),
    ("nursing_handoff", "source_completeness.missing_sections"): (0, 8),
    ("nursing_handoff", "evidence_items"): (0, 200),
    ("nursing_handoff", "limitations"): (4, 5),
    ("nursing_handoff", "trace_refs.provider_trace_refs"): (0, 10),
    ("icu_summary", "admission_diagnoses"): (0, 100),
    ("icu_summary", "timeline"): (0, 100),
    ("icu_summary", "active_problems"): (0, 100),
    ("icu_summary", "organ_support"): (0, 100),
    ("icu_summary", "medications"): (0, 100),
    ("icu_summary", "vital_signs"): (0, 100),
    ("icu_summary", "laboratory_results"): (0, 100),
    ("icu_summary", "procedures"): (0, 100),
    ("icu_summary", "key_trends"): (0, 100),
    ("icu_summary", "pending_items"): (0, 100),
    ("icu_summary", "risks"): (0, 100),
    ("icu_summary", "conflicts"): (0, 100),
    ("icu_summary", "source_completeness.missing_sections"): (0, 11),
    ("icu_summary", "evidence_items"): (0, 200),
    ("icu_summary", "limitations"): (5, 5),
    ("icu_summary", "trace_refs.provider_trace_refs"): (0, 10),
    ("discharge_edu", "key_results"): (0, 100),
    ("discharge_edu", "teach_back_questions"): (0, 30),
    ("discharge_edu", "clarification_questions"): (0, 30),
    ("discharge_edu", "contradictions"): (0, 100),
    ("discharge_edu", "missing_items"): (0, 5),
    ("discharge_edu", "source_completeness.documented_sections"): (0, 13),
    ("discharge_edu", "source_completeness.missing_sections"): (0, 5),
    ("discharge_edu", "evidence_items"): (0, 200),
    ("discharge_edu", "evidence_items[].char_span"): (2, 2),
    ("discharge_edu", "limitations"): (6, 6),
    ("discharge_edu", "trace_refs.provider_trace_refs"): (0, 10),
    ("discharge_summary_structuring", "diagnoses"): (0, 100),
    ("discharge_summary_structuring", "procedures"): (0, 100),
    ("discharge_summary_structuring", "key_results"): (0, 100),
    ("discharge_summary_structuring", "discharge_orders"): (0, 100),
    ("discharge_summary_structuring", "follow_up_recommendations"): (0, 100),
    ("discharge_summary_structuring", "pending_results"): (0, 100),
    ("discharge_summary_structuring", "complications"): (0, 100),
    ("discharge_summary_structuring", "conflicts"): (0, 100),
    ("discharge_summary_structuring", "missing_sections"): (0, 5),
    ("discharge_summary_structuring", "source_completeness.documented_sections"):
        (0, 17),
    ("discharge_summary_structuring", "source_completeness.missing_sections"):
        (0, 5),
    ("discharge_summary_structuring", "evidence_items"): (0, 200),
    ("discharge_summary_structuring", "evidence_items[].char_span"): (2, 2),
    ("discharge_summary_structuring", "limitations"): (7, 7),
    ("discharge_summary_structuring", "trace_refs.provider_trace_refs"): (0, 10),
    ("referral_gen", "urgency.evidence_refs"): (0, 2),
    ("referral_gen", "diagnostic_results"): (0, 50),
    ("referral_gen", "medications"): (0, 50),
    ("referral_gen", "allergies"): (0, 50),
    ("referral_gen", "missing_required_fields"): (0, 20),
    ("referral_gen", "missing_supporting_items"): (0, 20),
    ("referral_gen", "evidence_items"): (0, 160),
    ("referral_gen", "evidence_items[].char_span"): (2, 2),
    ("referral_gen", "limitations"): (1, 20),
    ("referral_gen", "trace_refs.provider_trace_refs"): (0, 10),
    ("prior_auth", "diagnosis_context"): (0, 60),
    ("prior_auth", "clinical_documentation"): (0, 60),
    ("prior_auth", "objective_evidence"): (0, 60),
    ("prior_auth", "prior_treatments"): (0, 60),
    ("prior_auth", "contraindications_intolerances"): (0, 60),
    ("prior_auth", "payer_policy.requirements"): (0, 60),
    ("prior_auth", "missing_required_fields"): (0, 30),
    ("prior_auth", "missing_supporting_items"): (0, 30),
    ("prior_auth", "missing_policy_items"): (0, 10),
    ("prior_auth", "evidence_items"): (0, 200),
    ("prior_auth", "evidence_items[].char_span"): (2, 2),
    ("prior_auth", "limitations"): (1, 20),
    ("prior_auth", "trace_refs.provider_trace_refs"): (0, 20),
}
NUMERIC_RANGE_OVERRIDES: dict[tuple[str, str], tuple[float | int, float | int]] = {
    ("triage", "questionnaire_validation.question_count"): (0, 64),
    ("triage", "questionnaire_validation.endpoint_count"): (0, 16),
    ("triage", "decision_path[].step_index"): (0, 63),
    ("triage", "decision_path[].matched_branch_index"): (0, 15),
    ("evidence_extractor", "input_code_count"): (0, 20),
    ("evidence_extractor", "located_mentions[].input_index"): (0, 19),
    ("evidence_extractor", "code_results[].input_index"): (0, 19),
    ("evidence_extractor", "code_results[].mention_count"): (0, 5),
    ("evidence-ranker", "ranked_evidence[].rank"): (1, 50),
    ("evidence-ranker", "ranked_evidence[].documentation_grounding_score"): (0, 1),
    ("evidence-ranker", "source_coverage.evidence_count"): (0, 50),
    ("evidence-ranker", "source_coverage.sourced_count"): (0, 50),
    ("evidence-ranker", "source_coverage.valid_span_count"): (0, 50),
    ("evidence-ranker", "source_coverage.invalid_span_count"): (0, 50),
    ("evidence-ranker", "source_coverage.source_coverage_ratio"): (0, 1),
    ("icd10_navigator", "candidate_codes[].match_score"): (0, 1),
    ("icd10_navigator", "candidate_codes[].related_codes_count"): (0, 100_000),
    ("nursing_handoff", "source_completeness.patient_count"): (0, 10),
    ("nursing_handoff", "source_completeness.max_patients"): (10, 10),
    ("nursing_handoff", "evidence_items[].patient_index"): (0, 9),
    ("icu_summary", "source_completeness.evidence_item_count"): (0, 200),
    ("discharge_edu", "source_completeness.evidence_item_count"): (0, 200),
    ("discharge_summary_structuring", "source_completeness.evidence_item_count"):
        (0, 200),
}
UNIQUE_ARRAY_OVERRIDES = {
    ("drg-analyzer", "review_actions"),
    ("drg-analyzer", "missing_required_fields"),
    ("drg-analyzer", "risk_findings[].input_evidence_refs"),
    ("triage", "red_flags"),
    ("triage", "protocol_candidate.red_flag_codes"),
    ("triage", "input_conflicts"),
    ("compliance-guardrail", "reviewed_codes"),
    ("evidence-ranker", "source_coverage.covered_sources"),
    ("evidence-ranker", "source_coverage.missing_sources"),
    ("icd10_navigator", "index_terms"),
    ("nursing_handoff", "assignment_summary[].evidence_refs"),
    ("nursing_handoff", "patient_handoffs[].evidence_refs"),
    ("discharge_edu", "source_completeness.documented_sections"),
    ("discharge_edu", "source_completeness.missing_sections"),
    ("discharge_summary_structuring", "source_completeness.documented_sections"),
    ("discharge_summary_structuring", "source_completeness.missing_sections"),
}


EMPTY_ARRAY_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("drg-analyzer", "missing_required_fields"): STRING,
    ("drg-analyzer", "input_conflicts"): obj({
        "field": STRING,
        "documented_value": STRING,
        "reason": STRING,
        "evidence_refs": STRING_ARRAY,
    }, required=["field", "documented_value", "reason", "evidence_refs"]),
    ("triage", "missing_information"): STRING,
    ("triage", "questionnaire_validation.errors"): STRING,
    ("triage", "clarification_questions"): STRING,
    ("triage", "input_conflicts"): STRING,
    ("principal_diagnosis_review", "candidate_evidence_gaps"): STRING,
    ("principal_diagnosis_review", "input_conflicts"): obj({
        "field": STRING,
        "documented_value": STRING,
        "reason": STRING,
        "evidence_refs": STRING_ARRAY,
    }, required=["field", "documented_value", "reason", "evidence_refs"]),
    ("principal_diagnosis_review", "missing_required_fields"): STRING,
    ("claim-check", "missing_required_fields"): STRING,
    ("claim-check", "missing_policy_items"): STRING,
    ("denial-appeals", "documented_corrections"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("denial-appeals", "corrected_claim_checklist"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("denial-appeals", "missing_required_fields"): STRING,
    ("denial-appeals", "missing_supporting_items"): STRING,
    ("denial-appeals", "missing_policy_items"): STRING,
    ("clinical-education", "missing_required_fields"): STRING,
    ("clinical-education", "missing_source_metadata"): STRING,
    ("clinical-guidelines", "documentation_conflicts"): obj({
        "field": STRING,
        "documented_values": STRING_ARRAY,
        "source_documents": STRING_ARRAY,
        "evidence_refs": STRING_ARRAY,
    }, required=[
        "field", "documented_values", "source_documents", "evidence_refs",
    ]),
    ("clinical-guidelines", "aligned_items"): obj({
        "criterion_id": STRING,
        "documented_alignment": STRING,
    }, required=["criterion_id", "documented_alignment"]),
    ("clinical-guidelines", "not_assessable_items"): obj({
        "criterion_id": STRING,
        "reason": STRING,
    }, required=["criterion_id", "reason"]),
    ("clinical-guidelines", "missing_required_fields"): STRING,
    ("clinical-guidelines", "missing_source_metadata"): STRING,
    ("clinical-guidelines", "missing_patient_information"): STRING,
    ("clinical-documentation-improvement-agent", "coding_specificity_checklist"):
        obj({"condition": STRING, "elements_to_address": STRING_ARRAY}),
    ("clinical-documentation-improvement-agent", "proposed_provider_queries[].nlq_gate_block_reasons"):
        STRING,
    ("clinical-documentation-improvement-agent", "specialist_trace[].accepted"): STRING,
    ("clinical-documentation-improvement-agent", "specialist_trace[].rejected"): STRING,
    ("evidence_extractor", "unmatched_codes"): STRING,
    ("evidence_extractor", "uncoded_findings"): obj({
        "finding": STRING,
        "evidence_text": STRING,
        "char_span": INTEGER_ARRAY,
        "reason": STRING,
    }, required=["finding", "reason"]),
    ("icd10_navigator", "candidate_codes"): obj({
        "code": STRING,
        "display": STRING,
        "description": STRING,
        "index_term": STRING,
        "rationale": STRING,
    }, required=["code"]),
    ("icd10_navigator", "candidate_codes[].children"): obj({
        "code": STRING,
        "display": STRING,
    }, required=["code", "display"]),
    ("icu_summary", "conflicts"): obj({
        "description": STRING,
        "evidence": STRING,
        "field": STRING,
        "evidence_ref": STRING,
    }, required=["description", "evidence", "field", "evidence_ref"]),
    ("icu_summary", "source_completeness.missing_sections"): STRING,
    ("discharge_edu", "clarification_questions"): STRING,
    ("discharge_edu", "contradictions"): obj({
        "description": STRING,
        "resolution": STRING,
        "evidence_ref": STRING,
    }, required=["description", "resolution", "evidence_ref"]),
    ("discharge_edu", "missing_items"): STRING,
    ("discharge_edu", "source_completeness.missing_sections"): STRING,
    ("discharge_summary_structuring", "complications"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("discharge_summary_structuring", "conflicts"): obj({
        "description": STRING,
        "resolution": STRING,
        "evidence_ref": STRING,
    }, required=["description", "resolution", "evidence_ref"]),
    ("discharge_summary_structuring", "missing_sections"): STRING,
    ("discharge_summary_structuring", "source_completeness.missing_sections"):
        STRING,
    ("referral_gen", "missing_required_fields"): STRING,
    ("referral_gen", "missing_supporting_items"): STRING,
    ("prior_auth", "objective_evidence"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("prior_auth", "prior_treatments"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("prior_auth", "contraindications_intolerances"): obj({
        "documented_text": STRING,
        "evidence_ref": STRING,
    }, required=["documented_text", "evidence_ref"]),
    ("prior_auth", "missing_required_fields"): STRING,
    ("prior_auth", "missing_policy_items"): STRING,
    ("medical_coding", "encounter_summary.key_findings"): STRING,
    ("medical_coding", "encounter_summary.document_sources"): obj({
        "doc_id": STRING, "doc_type": STRING,
    }),
    ("medical_coding", "documentation_analysis.diagnosis_evidence"): EVIDENCE_SPAN,
    ("medical_coding", "documentation_analysis.procedure_evidence"): EVIDENCE_SPAN,
    ("medical_coding", "documentation_analysis.negated_findings"): EVIDENCE_SPAN,
    ("medical_coding", "documentation_analysis.historical_conditions"): EVIDENCE_SPAN,
    ("medical_coding", "code_assignment.secondary_diagnoses"): DIAGNOSIS_ENTRY,
    ("medical_coding", "code_assignment.procedures"): PROCEDURE_ENTRY,
    ("medical_coding", "documentation_gaps"): obj({
        "gap_type": STRING,
        "description": STRING,
        "related_code": STRING,
        "suggestion": STRING,
    }),
    ("medical_coding", "uncodable_items"): obj({
        "item_type": STRING, "text": STRING, "reason": STRING,
    }),
    ("medical_coding", "human_review.review_focus"): STRING,
    ("medical_coding", "trace_refs.stage_trace"): obj({
        "stage": STRING,
        "status": STRING,
        "latency_ms": INTEGER,
        "provider": STRING,
        "model": STRING,
        "method_id": STRING,
        "error_code": STRING,
    }, required=["stage", "status"]),
    ("med_reconciliation", "interaction_risks"): obj({
        "medications": STRING_ARRAY,
        "risk": STRING,
        "evidence_refs": STRING_ARRAY,
    }, required=["medications", "risk", "evidence_refs"]),
    ("med_reconciliation", "reconciliation_summary[].differences"): STRING,
    ("med_reconciliation", "allergy_conflicts"): obj({
        "drug_name": STRING,
        "allergen": STRING,
        "match_basis": STRING,
        "evidence_refs": STRING_ARRAY,
    }, required=["drug_name", "allergen", "match_basis", "evidence_refs"]),
    ("med_reconciliation", "unresolved_mentions"): obj({
        "source": STRING,
        "evidence_text": STRING,
        "char_span": INTEGER_ARRAY,
        "reason": STRING,
    }, required=["source", "evidence_text", "char_span", "reason"]),
    ("nursing_handoff", "patient_handoffs[].missing_sections"): STRING,
    ("nursing_handoff", "source_completeness.missing_sections"): STRING,
    ("note-completeness", "missing_sections"): STRING,
    ("procedure-extractor", "procedures[].warnings"): STRING,
    ("procedure-extractor", "non_billable_mentions"): obj({
        "text": STRING,
        "status": STRING,
        "evidence_text": STRING,
        "char_span": INTEGER_ARRAY,
    }),
    ("procedure-extractor", "issues_found"): obj({
        "category": STRING,
        "message": STRING,
        "severity": STRING,
        "suggestion": STRING,
    }, required=["category", "message"]),
}


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float) and math.isfinite(value):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    raise ValueError(f"unsupported JSON value type {type(value).__name__}")


def _infer(values: list[Any], *, agent: str, path: str) -> dict[str, Any]:
    observed = {_json_type(value) for value in values}
    if observed == {"integer", "number"}:
        observed = {"number"}
    if len(observed) != 1:
        raise ValueError(f"{agent}:{path} has conflicting types {sorted(observed)}")
    kind = observed.pop()
    if kind not in {"object", "array"}:
        return primitive(kind)
    if kind == "array":
        items = [item for value in values for item in value]
        if not items:
            override = EMPTY_ARRAY_OVERRIDES.get((agent, path))
            if override is None:
                raise ValueError(f"{agent}:{path} needs an explicit empty-array item schema")
            return array(copy.deepcopy(override))
        return array(_infer(items, agent=agent, path=f"{path}[]"))

    keys = sorted({key for value in values for key in value})
    if not keys:
        raise ValueError(f"{agent}:{path} cannot infer an empty object schema")
    properties = {
        key: _infer(
            [value[key] for value in values if key in value],
            agent=agent,
            path=f"{path}.{key}",
        )
        for key in keys
    }
    required = [key for key in keys if all(key in value for value in values)]
    return obj(properties, required=required)


def _apply_value_constraints(
    schema: dict[str, Any],
    *,
    agent: str,
    path: str,
    human_review_required: bool,
) -> dict[str, Any]:
    """Apply the reviewed semantic subset without deriving clinical facts."""
    kind = schema.get("type")
    leaf = path.rsplit(".", 1)[-1].removesuffix("[]")
    if kind == "string":
        schema["maxLength"] = MAX_STRING_LENGTH
        length_override = STRING_LENGTH_OVERRIDES.get((agent, path))
        if length_override is not None:
            minimum, maximum = length_override
            if minimum is not None:
                schema["minLength"] = minimum
            schema["maxLength"] = maximum
    elif kind == "array":
        schema["maxItems"] = MAX_ARRAY_ITEMS
        length_override = ARRAY_LENGTH_OVERRIDES.get((agent, path))
        if length_override is not None:
            minimum, maximum = length_override
            if minimum is not None:
                schema["minItems"] = minimum
            schema["maxItems"] = maximum
        if (agent, path) in UNIQUE_ARRAY_OVERRIDES:
            schema["uniqueItems"] = True
        if leaf == "char_span":
            schema.update({"minItems": 2, "maxItems": 2, "x-order": "nondecreasing"})
        items = schema.get("items")
        if leaf == "char_span" and isinstance(items, dict):
            items["minimum"] = 0
        if isinstance(items, dict):
            _apply_value_constraints(
                items,
                agent=agent,
                path=f"{path}[]",
                human_review_required=human_review_required,
            )
    elif kind == "object":
        properties = schema.setdefault("properties", {})
        optional_properties = OPTIONAL_OBJECT_PROPERTY_OVERRIDES.get((agent, path), {})
        for name, child in optional_properties.items():
            properties.setdefault(name, copy.deepcopy(child))
        for name, child in (schema.get("properties") or {}).items():
            if isinstance(child, dict):
                _apply_value_constraints(
                    child,
                    agent=agent,
                    path=f"{path}.{name}",
                    human_review_required=human_review_required,
                )
        required_override = OBJECT_REQUIRED_OVERRIDES.get((agent, path))
        if required_override is not None:
            schema["required"] = list(required_override)
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            _apply_value_constraints(
                additional,
                agent=agent,
                path=f"{path}.{{}}",
                human_review_required=human_review_required,
            )
    if kind in {"integer", "number"} and leaf == "confidence":
        schema.update({"minimum": 0, "maximum": 1})
    numeric_override = NUMERIC_RANGE_OVERRIDES.get((agent, path))
    if kind in {"integer", "number"} and numeric_override is not None:
        schema.update({"minimum": numeric_override[0], "maximum": numeric_override[1]})
    if human_review_required and leaf == "manual_review_required" and kind == "boolean":
        schema["const"] = True
    if (
        agent == "clinical-documentation-improvement-agent"
        and leaf in {"cdi_specialist_review_required", "clinician_response_required"}
        and kind == "boolean"
    ):
        schema["const"] = True
    enum = ENUM_OVERRIDES.get((agent, path))
    if enum is not None:
        schema["enum"] = enum
    const = CONST_OVERRIDES.get((agent, path))
    if const is not None or (agent, path) in CONST_OVERRIDES:
        schema["const"] = const
    return schema


def _force_manual_review(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "manual_review_required" and isinstance(child, bool):
                value[key] = True
            else:
                _force_manual_review(child)
    elif isinstance(value, list):
        for child in value:
            _force_manual_review(child)


def _canonical_pack_sha256(pack: dict[str, Any]) -> str:
    clean = {key: value for key, value in pack.items() if key not in INTEGRITY_EXCLUDED_FIELDS}
    payload = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def derive_field_schemas(pack: dict[str, Any], *, agent: str) -> dict[str, Any]:
    contract = pack.get("output_contract") or {}
    field_types = contract.get("field_types") or {}
    examples = [item for item in (pack.get("example_outputs") or []) if isinstance(item, dict)]
    human_review_required = (pack.get("manifest") or {}).get("human_review") == "required"
    result: dict[str, Any] = {}
    for field, kind in field_types.items():
        values = [example[field] for example in examples if field in example]
        if not values:
            raise ValueError(f"{agent}:{field} has no example value")
        schema = _infer(values, agent=agent, path=field)
        if field == "trace_refs" and schema.get("type") == "object":
            properties = schema.setdefault("properties", {})
            # Never attach the shared primitive templates directly: recursive
            # constraint application mutates schemas in place and would make
            # later Agents depend on traversal order.
            properties.setdefault("run_id", copy.deepcopy(STRING))
            properties.setdefault("trace_id", copy.deepcopy(STRING))
            properties.setdefault(
                "provider_trace_refs", copy.deepcopy(STRING_ARRAY)
            )
            # Dedicated handlers may publish additional declared trace
            # structure, while unified Run always owns the correlation id.
            schema["required"] = ["run_id"]
        result[field] = _apply_value_constraints(
            schema,
            agent=agent,
            path=field,
            human_review_required=human_review_required,
        )
    return result


def sync_field_schemas(
    agents_dir: Path,
    *,
    write: bool,
    agent_names: set[str] | None = None,
) -> dict[str, Any]:
    visible = 0
    changed: list[str] = []
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        if agent_names is not None and pack_path.parent.name not in agent_names:
            continue
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        visible += 1
        agent = pack_path.parent.name
        contract = pack.get("output_contract")
        if not isinstance(contract, dict):
            raise ValueError(f"{agent}: output_contract must be an object")
        if (pack.get("manifest") or {}).get("human_review") == "required":
            for example in pack.get("example_outputs") or []:
                _force_manual_review(example)
        if agent == "diagnosis-extractor":
            for example in pack.get("example_outputs") or []:
                if example.get("status") == "completed":
                    example["status"] = "PASS"
        schemas = derive_field_schemas(pack, agent=agent)
        schemas_changed = contract.get("field_schemas") != schemas
        contract["field_schemas"] = schemas
        relations_changed = False
        if agent in FIELD_RELATION_OVERRIDES:
            relations = copy.deepcopy(FIELD_RELATION_OVERRIDES[agent])
            relations_changed = contract.get("field_relations") != relations
            contract["field_relations"] = relations
        bindings_changed = False
        if agent in EVIDENCE_BINDING_OVERRIDES:
            bindings = copy.deepcopy(EVIDENCE_BINDING_OVERRIDES[agent])
            bindings_changed = contract.get("evidence_bindings") != bindings
            contract["evidence_bindings"] = bindings
        cross_relations_changed = False
        if agent in CROSS_AGENT_RELATION_OVERRIDES:
            cross_relations = copy.deepcopy(CROSS_AGENT_RELATION_OVERRIDES[agent])
            cross_relations_changed = (
                contract.get("cross_agent_relations") != cross_relations
            )
            contract["cross_agent_relations"] = cross_relations
        expected_sha = _canonical_pack_sha256(pack)
        integrity_changed = bool(
            isinstance(pack.get("integrity"), dict)
            and pack["integrity"].get("sha256") != expected_sha
        )
        if (
            not schemas_changed
            and not relations_changed
            and not bindings_changed
            and not cross_relations_changed
            and not integrity_changed
        ):
            continue
        changed.append(agent)
        if write:
            if isinstance(pack.get("integrity"), dict):
                pack["integrity"]["sha256"] = expected_sha
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return {"visible_agents": visible, "changed_agents": changed, "write": write}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument(
        "--agent",
        action="append",
        dest="agents",
        help="Restrict synchronization to one pack directory name; repeatable.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        sync_field_schemas(
            args.agents_dir.resolve(),
            write=args.write,
            agent_names=set(args.agents) if args.agents else None,
        ),
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
