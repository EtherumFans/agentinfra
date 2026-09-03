"""Unit tests for StructuredOutputProjector (Phase 5 Track C Gate 1).

Covers:
- JSON fence + bare JSON extraction
- Per-contract extractors (NoteCompleteness, DrgAnalyzer, Procedure,
  Discharge, etc.)
- Defensive behavior (empty input, parse errors never raise)
- Markdown-table fallback for note-completeness
"""

from __future__ import annotations

import json

import pytest

from icoder_runtime.backends.structured_output_projector import (
    StructuredProjection,
    project,
    project_or_empty,
)


# ── Defensive behavior ─────────────────────────────────────────────────


def test_project_empty_markdown_returns_warnings():
    """Empty markdown should return an empty result with a warning."""
    proj = project("", "icoder/NoteCompleteness/v1", "test")
    assert proj.result == {}
    assert proj.extraction_method == "none"
    assert "empty markdown" in proj.parse_warnings


def test_project_unknown_contract_falls_back_to_json_block():
    """Unknown contract still extracts JSON block if present."""
    md = '```json\n{"foo": "bar"}\n```'
    proj = project(md, "icoder/Unknown/v1", "test")
    assert proj.result == {"foo": "bar"}
    assert proj.extraction_method == "json_block"


def test_project_never_raises_on_malformed_input():
    """Malformed markdown must not raise — returns empty + warnings."""
    proj = project("}{not valid json}{", "icoder/DrgAnalyzer/v1", "test")
    assert proj.result == {}
    assert proj.extraction_method in ("none", "section_header")


def test_project_or_empty_returns_dict():
    """project_or_empty convenience returns just the dict."""
    md = '```json\n{"risk_points": ["x"]}\n```'
    result = project_or_empty(md, "icoder/DrgAnalyzer/v1", "test")
    assert isinstance(result, dict)
    assert result.get("risk_points") == ["x"]


def test_project_does_not_mutate_input():
    """The input markdown must not be modified."""
    md = '```json\n{"a": 1}\n```'
    original = md
    project(md, "icoder/Unknown/v1", "test")
    assert md == original


# ── Per-contract extractors ─────────────────────────────────────────────


def test_drg_analyzer_json_block():
    md = """Here is the analysis:
```json
{
  "risk_points": [
    {"risk_type": "downcoding", "code": "J15.9", "severity": "high"}
  ],
  "drg_dip_rule_reservation_note": "考虑添加并发症编码"
}
```"""
    proj = project(md, "icoder/DrgAnalyzer/v1", "drg-analyzer")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["risk_points"]) == 1
    assert proj.result["risk_points"][0]["code"] == "J15.9"
    assert proj.result["drg_dip_rule_reservation_note"].startswith("考虑")


def test_note_completeness_markdown_table():
    """Note completeness fallback parses ❌ **缺失** table rows."""
    md = """### 评估
| 章节 | 状态 | 说明 |
| :--- | :--- | :--- |
| **主诉** | ❌ **缺失** | 未提供。 |
| **现病史** | ❌ **缺失** | 未提供。 |
| **诊断** | ⚠️ **部分缺失** | 提供了部分。 |

| 指标 | 值 |
| :--- | :--- |
| **Completeness Score** | **2 / 10** (20%) |
"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    # §7.6 contract: missing_sections + incomplete_sections (separate tiers).
    assert "missing_sections" in proj.result
    assert "主诉" in proj.result["missing_sections"]
    assert "现病史" in proj.result["missing_sections"]
    # "诊断" should be in incomplete_sections (部分缺失), not missing_sections.
    assert "诊断" not in proj.result["missing_sections"]
    assert any(s["section"] == "诊断" for s in proj.result.get("incomplete_sections", []))
    assert "completeness_score" in proj.result
    assert proj.result["completeness_score"] == 2.0


def test_note_completeness_json_block():
    md = """```json
{
  "required_sections": ["主诉","现病史","既往史"],
  "missing_sections": ["主诉", "现病史"],
  "incomplete_sections": [],
  "conflicts": [],
  "completeness_score": 0.33,
  "review_conclusion": "missing 2 of 3"
}
```"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert proj.extraction_method == "json_block"
    assert proj.result["missing_sections"] == ["主诉", "现病史"]
    assert proj.result["completeness_score"] == 0.33
    assert proj.result["review_conclusion"].startswith("missing")


def test_procedure_extractor_json_block():
    md = """```json
{
  "procedures": [
    {"text": "后路椎体成形术", "code": "81.6500"}
  ],
  "total_count": 1
}
```"""
    proj = project(md, "icoder/ProcedureExtractor/v1", "procedure-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["procedures"]) == 1
    assert proj.result["total_count"] == 1


def test_discharge_summary_bare_json():
    """Discharge summary accepts bare JSON envelope without fence."""
    md = """{
  "diagnoses": [
    {"text": "T12椎体压缩性骨折", "primary": true}
  ],
  "procedures": [
    {"text": "后路椎体成形术"}
  ],
  "treatment_summary": "术后恢复良好"
}"""
    proj = project(md, "icoder/DischargeSummary/v1", "discharge-summary-structuring")
    assert proj.extraction_method == "json_block"
    ss = proj.result["structured_sections"]
    assert "diagnoses" in ss
    assert "procedures" in ss
    assert ss["treatment_summary"].startswith("术后")


def test_compliance_guardrail_json_block():
    md = """```json
{
  "risk_points": ["x"],
  "violations": [{"rule": "R001"}],
  "risk_level": "high",
  "compliant": false
}
```"""
    proj = project(md, "icoder/ComplianceGuardrail/v1", "compliance-guardrail")
    assert proj.extraction_method == "json_block"
    assert proj.result["risk_level"] == "high"
    assert proj.result["compliant"] is False


def test_evidence_extractor_json_block():
    md = """```json
{
  "coded_evidence": [{"code": "I21.9", "strength": "high"}],
  "overall_strength": 0.85
}
```"""
    proj = project(md, "icoder/EvidenceExtractor/v1", "evidence-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["coded_evidence"]) == 1
    assert proj.result["overall_strength"] == 0.85


def test_principal_dx_json_block():
    md = """```json
{
  "principal_dx": "I21.9",
  "conflict": false,
  "rationale": "急性心梗为入院主因"
}
```"""
    proj = project(md, "icoder/PrincipalDxReview/v1", "principal-diagnosis-review")
    assert proj.extraction_method == "json_block"
    assert proj.result["principal_dx"] == "I21.9"
    assert proj.result["rationale"].startswith("急性")


def test_code_validation_json_block():
    md = """```json
{
  "validation_results": [{"code": "I21.19", "valid": true}],
  "overall_valid": true
}
```"""
    proj = project(md, "icoder/CodeValidation/v1", "code-validation-agent")
    assert proj.extraction_method == "json_block"
    assert proj.result["overall_valid"] is True


def test_rule_explanation_generic_json_contract():
    md = '''```json
{"status":"PASS","code":"I50.9","assignable":true,
 "explanation_summary":"工具已确认该编码",
 "guideline_basis":[{"tool":"get_guidelines","rule":"使用最具体编码"}],
 "evidence_tool_refs":["verify_code","get_guidelines"],
 "limitations":[],"manual_review_required":false}
```'''
    proj = project(md, "icoder/RuleExplanationOutput/v1", "rule-explainer")
    assert proj.extraction_method == "json_block"
    assert proj.result["code"] == "I50.9"
    assert proj.result["evidence_tool_refs"] == ["verify_code", "get_guidelines"]


# ── Structural assertions ───────────────────────────────────────────────


def test_structured_projection_dataclass_defaults():
    sp = StructuredProjection(result={}, raw_markdown="x")
    assert sp.parse_warnings == []
    assert sp.contract == ""
    assert sp.extraction_method == "none"


# ── Phase 5 Track C Gate 2 contracts ────────────────────────────────────


def test_procedure_extractor_status_gate_split():
    """§7.3: status=performed → procedures; others → non_billable_mentions."""
    md = """```json
{
  "procedures": [
    {"code": "81.0100", "display": "椎体成形术", "status": "performed", "evidence_text": "行椎体成形术"},
    {"code": "00.00",   "display": "PCI",        "status": "planned",    "evidence_text": "拟行 PCI"}
  ],
  "non_billable_mentions": [],
  "manual_review_required": true
}
```"""
    proj = project(md, "icoder/ProcedureExtractor/v1", "procedure-extractor")
    assert proj.extraction_method == "json_block"
    # Only performed remains in procedures.
    assert len(proj.result["procedures"]) == 1
    assert proj.result["procedures"][0]["code"] == "81.0100"
    # PCI moved to non_billable_mentions.
    assert len(proj.result["non_billable_mentions"]) == 1
    assert proj.result["non_billable_mentions"][0]["status"] == "planned"
    assert proj.result["total_count"] == 1


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [("completed", "PASS"), ("warning", "WARNING"), ("requires_review", "REQUIRES_REVIEW")],
)
def test_diagnosis_extractor_normalizes_legacy_statuses(raw_status: str, expected: str):
    proj = project(
        f'{{"status":"{raw_status}","diagnoses":[],"manual_review_required":true}}',
        "icoder/DiagnosisExtractionOutput/v3",
        "diagnosis-extractor",
    )
    assert proj.result["status"] == expected


def test_evidence_extractor_tier_classification():
    """§7.4 + §7.1: supported/uncertain/rejected tiers."""
    md = """```json
{
  "supported_codes": [
    {"code": "S22.000", "evidence_strength": "direct", "confidence": 0.92}
  ],
  "uncertain_candidates": [
    {"code": "J15.9", "evidence_strength": "suspected", "confidence": 0.5}
  ],
  "rejected_candidates": [
    {"code": "I50.9", "evidence_strength": "negated", "confidence": 0.1}
  ],
  "review_summary": "1 supported, 1 uncertain, 1 rejected"
}
```"""
    proj = project(md, "icoder/EvidenceExtractor/v1", "evidence-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["supported_codes"]) == 1
    assert len(proj.result["uncertain_candidates"]) == 1
    assert len(proj.result["rejected_candidates"]) == 1


def test_principal_dx_conflict_gate():
    """§7.5: coding_draft_consistent + manual_review_required."""
    md = """```json
{
  "candidates": [{"code": "S22.000", "recommended": true}],
  "recommended": {"code": "S22.000", "display": "T12 骨折"},
  "not_recommended": [{"code": "M80.900", "reason": "慢性合并症"}],
  "coding_draft_consistent": false,
  "conflict_reason": "draft=M80.900 but recommended=S22.000",
  "manual_review_required": true,
  "rationale": "S22.000 是主诊断因为..."
}
```"""
    proj = project(md, "icoder/PrincipalDxReview/v1", "principal-diagnosis-review")
    assert proj.extraction_method == "json_block"
    assert proj.result["coding_draft_consistent"] is False
    assert proj.result["manual_review_required"] is True
    assert "draft=M80.900" in proj.result["conflict_reason"]


def test_governed_principal_dx_v11_drops_legacy_recommendations_and_forces_safety():
    md = """```json
{
  "review_status": "READY_FOR_CODER_REVIEW",
  "documented_coding_draft": {"code": "S22.000", "authority_status": "VALIDATED"},
  "recommended": {"code": "J18.900"},
  "principal_dx": "J18.900",
  "diagnosis_extraction_performed": true,
  "code_assignment_performed": true,
  "principal_diagnosis_selection_performed": true,
  "clinical_inference_performed": true,
  "external_rules_used": true,
  "production_submission_blocked": false,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(md, "icoder/PrincipalDxReview/v11", "principal-diagnosis-review")

    assert "recommended" not in proj.result
    assert "principal_dx" not in proj.result
    assert proj.result["documented_coding_draft"]["authority_status"] == (
        "CODER_DOCUMENTED_DRAFT_NOT_CLINICALLY_VALIDATED"
    )
    assert proj.result["review_method"] == (
        "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"
    )
    assert proj.result["diagnosis_extraction_performed"] is False
    assert proj.result["code_assignment_performed"] is False
    assert proj.result["principal_diagnosis_selection_performed"] is False
    assert proj.result["clinical_inference_performed"] is False
    assert proj.result["external_rules_used"] is False
    assert proj.result["production_submission_blocked"] is True
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_note_completeness_full_contract():
    """§7.6: full structured contract via JSON block."""
    md = """```json
{
  "required_sections": ["主诉","现病史","既往史","体格检查","辅助检查","诊断","治疗经过"],
  "present_sections": ["诊断","治疗经过"],
  "missing_sections": ["主诉","现病史","既往史","体格检查","辅助检查"],
  "incomplete_sections": [{"section": "诊断", "deficit_note": "缺少入院诊断与出院诊断区分"}],
  "conflicts": [],
  "completeness_score": 0.25,
  "review_conclusion": "病历严重不完整, 必填章节缺失 5/7。",
  "corrected_draft": ""
}
```"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["required_sections"]) == 7
    assert len(proj.result["missing_sections"]) == 5
    assert proj.result["completeness_score"] == 0.25
    assert proj.result["review_conclusion"].startswith("病历严重不完整")


def test_known_contract_projection_preserves_new_pack_fields():
    """Compatibility extractors must not discard Pack-declared JSON fields."""
    md = """```json
{
  "review_conclusion": "需补充",
  "documentation_gaps": [{"section": "过敏史"}],
  "completeness_score": 0.75,
  "missing_sections": ["过敏史"],
  "present_sections": ["主诉"],
  "required_sections": ["主诉", "过敏史"],
  "trace_refs": ["trace-1"]
}
```"""
    proj = project(md, "icoder/NoteCompletenessOutput/v1", "note-completeness-agent")
    assert proj.result["documentation_gaps"] == [{"section": "过敏史"}]
    assert proj.result["trace_refs"] == ["trace-1"]


def test_note_completeness_normalizes_documentation_gaps_from_sections():
    md = """```json
{
  "required_sections": ["主诉", "过敏史"],
  "present_sections": ["主诉"],
  "missing_sections": ["过敏史"],
  "incomplete_sections": [],
  "conflicts": [],
  "completeness_score": 0.5,
  "review_conclusion": "需补充"
}
```"""
    proj = project(md, "icoder/NoteCompletenessOutput/v1", "note-completeness-agent")
    assert proj.result["documentation_gaps"] == [{
        "section": "过敏史", "gap_type": "missing", "description": "过敏史缺失",
    }]


def test_discharge_summary_preserves_top_level_pack_contract():
    md = """```json
{
  "diagnoses": ["慢性心力衰竭"],
  "procedures": [],
  "treatment_summary": "利尿治疗",
  "discharge_orders": ["低盐饮食"],
  "follow_up_recommendations": ["7日后复诊"],
  "discharge_status": "病情稳定",
  "manual_review_required": true
}
```"""
    proj = project(
        md, "icoder/DischargeSummaryStructured/v1",
        "discharge-summary-structuring",
    )
    for field in (
        "diagnoses", "procedures", "treatment_summary", "discharge_orders",
        "follow_up_recommendations", "discharge_status",
        "manual_review_required",
    ):
        assert field in proj.result
    assert proj.result["structured_sections"]["diagnoses"] == ["慢性心力衰竭"]


def test_medication_reconciliation_projection_enforces_unlicensed_screen_boundary():
    md = """```json
{
  "reconciliation_status": "COMPLETED",
  "interaction_screening_status": "ASSESSED",
  "interaction_risks": [{"risk": "model-memory claim"}],
  "manual_review_required": false
}
```"""
    proj = project(
        md,
        "icoder/MedicationReconciliationOutput/v4",
        "med-reconciliation",
    )

    assert proj.result["interaction_screening_status"] == (
        "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"
    )
    assert proj.result["interaction_risks"] == []
    assert proj.result["manual_review_required"] is True


def test_nursing_handoff_projection_enforces_local_safety_boundary():
    md = """```json
{
  "handoff_status": "PARTIAL",
  "clinical_priority_assessed": true,
  "medical_calculator_used": true,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(
        md,
        "icoder/NursingHandoffOutput/v4",
        "nursing-handoff",
    )

    assert proj.result["clinical_priority_assessed"] is False
    assert proj.result["medical_calculator_used"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_icu_summary_projection_enforces_local_expert_boundary():
    md = """```json
{
  "summary_status": "COMPLETED",
  "clinical_scores_status": "APACHE_CALCULATED",
  "medication_screening_status": "DRUGBANK_SCREENED",
  "clinical_recommendations_generated": true,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(md, "icoder/IcuSummaryOutput/v3", "icu-summary")

    assert proj.result["clinical_scores_status"] == (
        "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED"
    )
    assert proj.result["medication_screening_status"] == (
        "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED"
    )
    assert proj.result["clinical_recommendations_generated"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_discharge_education_projection_enforces_local_expert_boundary():
    md = """```json
{
  "education_status": "COMPLETED",
  "medication_reconciliation_status": "RECONCILED",
  "translation_status": "PATIENT_FRIENDLY_TRANSLATION",
  "external_knowledge_used": true,
  "clinical_interpretation_performed": true,
  "clinical_recommendations_generated": true,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(
        md,
        "icoder/DischargeEducationOutput/v3",
        "discharge-edu",
    )

    assert proj.result["medication_reconciliation_status"] == (
        "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED"
    )
    assert proj.result["translation_status"] == (
        "VERBATIM_DOCUMENTED_CONTENT_ONLY"
    )
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["clinical_interpretation_performed"] is False
    assert proj.result["clinical_recommendations_generated"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_discharge_summary_projection_enforces_local_safety_boundary():
    md = """```json
{
  "structuring_status": "COMPLETED",
  "summary_generation_status": "GENERATIVE_CLINICAL_SUMMARY",
  "icd_codes_assigned": true,
  "medication_reconciliation_performed": true,
  "clinical_inference_performed": true,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(
        md,
        "icoder/DischargeSummaryStructured/v5",
        "discharge-summary-structuring",
    )

    assert proj.result["summary_generation_status"] == (
        "VERBATIM_SECTION_REORGANIZATION_ONLY"
    )
    assert proj.result["icd_codes_assigned"] is False
    assert proj.result["medication_reconciliation_performed"] is False
    assert proj.result["clinical_inference_performed"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_referral_projection_enforces_no_inference_and_no_delivery_boundary():
    md = """```json
{
  "referral_status": "READY_FOR_REVIEW",
  "draft_generation_status": "GENERATIVE_CLINICAL_REFERRAL",
  "clinical_inference_performed": true,
  "new_diagnosis_generated": true,
  "new_treatment_recommended": true,
  "external_knowledge_used": true,
  "production_transmission_blocked": false,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(md, "icoder/ReferralOutput/v3", "referral-gen")

    assert proj.result["draft_generation_status"] == (
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    )
    assert proj.result["clinical_inference_performed"] is False
    assert proj.result["new_diagnosis_generated"] is False
    assert proj.result["new_treatment_recommended"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["production_transmission_blocked"] is True
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_prior_authorization_projection_enforces_review_and_submission_boundary():
    md = """```json
{
  "authorization_status": "READY_FOR_REVIEW",
  "medical_necessity_assessment_status": "APPROVED",
  "draft_generation_status": "GENERATIVE_POLICY_DECISION",
  "clinical_inference_performed": true,
  "new_diagnosis_generated": true,
  "new_treatment_recommended": true,
  "external_knowledge_used": true,
  "medical_calculator_used": true,
  "medical_coding_validation_performed": true,
  "production_submission_blocked": false,
  "production_writeback_blocked": false,
  "manual_review_required": false
}
```"""
    proj = project(md, "icoder/PriorAuthorizationOutput/v5", "prior-auth")

    assert proj.result["medical_necessity_assessment_status"] == (
        "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"
    )
    assert proj.result["draft_generation_status"] == (
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    )
    assert proj.result["clinical_inference_performed"] is False
    assert proj.result["new_diagnosis_generated"] is False
    assert proj.result["new_treatment_recommended"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["medical_calculator_used"] is False
    assert proj.result["medical_coding_validation_performed"] is False
    assert proj.result["production_submission_blocked"] is True
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_claim_check_projection_enforces_adjudication_and_submission_boundary():
    md = json.dumps({
        "review_status": "READY_FOR_REVIEW",
        "evidence_consistency_status": "ASSESSED",
        "comparison_basis": "model_memory",
        "clinical_support_assessed": True,
        "medical_necessity_assessed": True,
        "benefit_eligibility_determined": True,
        "code_assignment_performed": True,
        "drg_dip_grouping_performed": True,
        "external_knowledge_used": True,
        "production_submission_blocked": False,
        "production_writeback_blocked": False,
        "manual_review_required": False,
    }, ensure_ascii=False)

    proj = project(md, "icoder/ClaimCheckOutput/v4", "claim-check")

    assert proj.result["evidence_consistency_status"] == "NOT_ASSESSED_LITERAL_PACKET_ONLY"
    assert proj.result["comparison_basis"] == "DOCUMENTED_CLAIM_AND_POLICY_ONLY"
    assert proj.result["clinical_support_assessed"] is False
    assert proj.result["medical_necessity_assessed"] is False
    assert proj.result["benefit_eligibility_determined"] is False
    assert proj.result["code_assignment_performed"] is False
    assert proj.result["drg_dip_grouping_performed"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["production_submission_blocked"] is True
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_denial_appeals_projection_enforces_review_and_submission_boundary():
    md = json.dumps({
        "appeal_status": "READY_FOR_REVIEW",
        "denial_classification_status": "MODEL_CLASSIFIED",
        "draft_generation_status": "GENERATIVE_PAYER_ARGUMENT",
        "clinical_support_assessed": True,
        "medical_necessity_assessed": True,
        "benefit_eligibility_determined": True,
        "denial_root_cause_inferred": True,
        "payer_policy_lookup_performed": True,
        "medical_coding_validation_performed": True,
        "external_knowledge_used": True,
        "production_submission_blocked": False,
        "production_writeback_blocked": False,
        "manual_review_required": False,
    }, ensure_ascii=False)

    proj = project(md, "icoder/DenialAppealOutput/v3", "denial-appeals")

    assert proj.result["denial_classification_status"] == (
        "DOCUMENTED_ONLY_NO_INFERENCE"
    )
    assert proj.result["draft_generation_status"] == (
        "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
    )
    assert proj.result["clinical_support_assessed"] is False
    assert proj.result["medical_necessity_assessed"] is False
    assert proj.result["benefit_eligibility_determined"] is False
    assert proj.result["denial_root_cause_inferred"] is False
    assert proj.result["payer_policy_lookup_performed"] is False
    assert proj.result["medical_coding_validation_performed"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["production_submission_blocked"] is True
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_clinical_education_projection_enforces_source_bound_safety_boundary():
    md = json.dumps({
        "education_status": "READY_FOR_REVIEW",
        "content_generation_status": "MODEL_GENERATED_CLINICAL_TEACHING",
        "question_classification_performed": True,
        "clinical_reasoning_performed": True,
        "diagnostic_advice_generated": True,
        "treatment_advice_generated": True,
        "drug_interaction_assessed": True,
        "medical_calculator_used": True,
        "pubmed_lookup_performed": True,
        "web_search_performed": True,
        "external_knowledge_used": True,
        "production_writeback_blocked": False,
        "manual_review_required": False,
    }, ensure_ascii=False)

    proj = project(md, "icoder/ClinicalEducationOutput/v6", "clinical-education")

    assert proj.result["content_generation_status"] == "SOURCE_BOUND_TEMPLATE_ONLY"
    assert proj.result["question_classification_performed"] is False
    assert proj.result["clinical_reasoning_performed"] is False
    assert proj.result["diagnostic_advice_generated"] is False
    assert proj.result["treatment_advice_generated"] is False
    assert proj.result["drug_interaction_assessed"] is False
    assert proj.result["medical_calculator_used"] is False
    assert proj.result["pubmed_lookup_performed"] is False
    assert proj.result["web_search_performed"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True


def test_clinical_guidelines_projection_enforces_declared_rule_safety_boundary():
    md = json.dumps({
        "guideline_status": "READY_FOR_REVIEW",
        "source_authenticity_status": "VERIFIED_BY_MODEL",
        "source_currency_verified": True,
        "evaluation_method": "MODEL_CLINICAL_REASONING",
        "guideline_retrieval_performed": True,
        "web_search_performed": True,
        "clinical_inference_performed": True,
        "clinical_significance_assessed": True,
        "treatment_recommendations_generated": True,
        "external_knowledge_used": True,
        "production_writeback_blocked": False,
        "manual_review_required": False,
    }, ensure_ascii=False)

    proj = project(md, "icoder/ClinicalGuidelinesOutput/v6", "clinical-guidelines")

    assert proj.result["source_authenticity_status"] == (
        "USER_DOCUMENTED_METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED"
    )
    assert proj.result["source_currency_verified"] is False
    assert proj.result["evaluation_method"] == (
        "DECLARED_RULES_DETERMINISTIC_COMPARISON"
    )
    assert proj.result["guideline_retrieval_performed"] is False
    assert proj.result["web_search_performed"] is False
    assert proj.result["clinical_inference_performed"] is False
    assert proj.result["clinical_significance_assessed"] is False
    assert proj.result["treatment_recommendations_generated"] is False
    assert proj.result["external_knowledge_used"] is False
    assert proj.result["production_writeback_blocked"] is True
    assert proj.result["manual_review_required"] is True
