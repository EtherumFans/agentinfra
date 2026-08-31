"""Offline API E2E for every Hub-visible Agent.

This suite is a safety/orchestration gate, not a semantic capability claim.
With external LLM egress disabled, the 4 model-dependent Agents must publish
no clinical contract output. Compliance Guardrail, Note Completeness, the
ICD-10 Navigator, Diagnosis Extractor, Evidence Extractor, Evidence Ranker,
Procedure Extractor, and Surgical Registry run deterministically; Code
Validation runs its governed local catalog baseline with optional semantic
enhancement disabled. Rule Explainer publishes only governed catalog facts;
Medication Reconciliation compares only explicitly labelled source lists;
Nursing Handoff, ICU Summary, Discharge Education, and Discharge Summary
Structuring extract only explicitly labelled patient/field sections. Referral
Generator assembles only explicitly labelled referral fields into a blocked,
review-only draft. Prior Authorization assembles only explicitly documented
request evidence and versioned payer-policy fields, without making a coverage
or medical-necessity decision. Claim Check likewise assembles only labelled
claim, chart, and versioned policy fields without adjudicating payment.
Clinical Education copies only explicitly labelled, hospital-approved source
statements into fixed teaching templates without clinical reasoning or retrieval.
Clinical Guidelines compares only supplied approved-source rules with explicit
documented facts and never claims guideline retrieval, authenticity or currency.
Principal Diagnosis Review checks only a coder-documented draft against an
explicit candidate set and exact evidence; it never selects or assigns a code.
DRG/DIP Risk Review consumes only explicit coder-supplied codes and evidence,
and emits an unverified development candidate without official grouping or payment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


OFFICIAL_AGENTS = Path(__file__).resolve().parents[3] / "official_agents"
ADVERSARIAL_CASES = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "corti_parity"
    / "agent_hub_adversarial_cases.json"
)
LOCAL_ONLY_AGENT_IDS = frozenset({
    "claim-check",
    "clinical-education",
    "clinical-guidelines",
    "code-validation-agent",
    "compliance-guardrail-agent",
    "denial-appeals",
    "diagnosis-extractor",
    "discharge-edu",
    "discharge-summary-structuring",
    "drg-analyzer",
    "evidence-extractor",
    "evidence-ranker",
    "icd10-navigator",
    "icu-summary",
    "med-reconciliation",
    "note-completeness-agent",
    "nursing-handoff",
    "principal-diagnosis-review",
    "prior-auth",
    "procedure-extractor",
    "referral-gen",
    "rule-explainer",
    "surgical-registry",
    "triage",
})
LOCAL_PROVIDER_BY_AGENT = {
    "claim-check": "icoder.governed-claim-check.v1",
    "clinical-education": "icoder.governed-clinical-education.v1",
    "clinical-guidelines": "icoder.governed-clinical-guidelines.v1",
    "code-validation-agent": "icoder.governed-code-validation.v1",
    "compliance-guardrail-agent": "icoder.rule-engine.v1",
    "denial-appeals": "icoder.governed-denial-appeals.v1",
    "diagnosis-extractor": "icoder.governed-diagnosis-extractor.v1",
    "discharge-edu": "icoder.governed-discharge-education.v1",
    "discharge-summary-structuring": "icoder.governed-discharge-summary.v1",
    "drg-analyzer": "icoder.governed-drg-dip-risk-review.v1",
    "evidence-extractor": "icoder.governed-evidence-extractor.v1",
    "evidence-ranker": "icoder.governed-evidence-ranker.v1",
    "icd10-navigator": "icoder.governed-icd-navigator.v1",
    "icu-summary": "icoder.governed-icu-summary.v1",
    "med-reconciliation": "icoder.governed-medication-reconciliation.v1",
    "note-completeness-agent": "icoder.documentation-rule-engine.v1",
    "nursing-handoff": "icoder.governed-nursing-handoff.v1",
    "principal-diagnosis-review": "icoder.governed-principal-diagnosis-review.v1",
    "prior-auth": "icoder.governed-prior-authorization.v1",
    "procedure-extractor": "icoder.governed-procedure-extractor.v1",
    "referral-gen": "icoder.governed-referral.v1",
    "rule-explainer": "icoder.governed-rule-explainer.v1",
    "surgical-registry": "icoder.governed-surgical-registry.v1",
    "triage": "icoder.governed-triage-questionnaire.v1",
}
LOCAL_BACKEND_TYPE_BY_AGENT = {
    "claim-check": "rule_engine",
    "clinical-education": "rule_engine",
    "clinical-guidelines": "rule_engine",
    "code-validation-agent": "hybrid",
    "compliance-guardrail-agent": "rule_engine",
    "denial-appeals": "rule_engine",
    "diagnosis-extractor": "rule_engine",
    "discharge-edu": "rule_engine",
    "discharge-summary-structuring": "rule_engine",
    "drg-analyzer": "rule_engine",
    "evidence-extractor": "rule_engine",
    "evidence-ranker": "rule_engine",
    "icd10-navigator": "rule_engine",
    "icu-summary": "rule_engine",
    "med-reconciliation": "rule_engine",
    "note-completeness-agent": "rule_engine",
    "nursing-handoff": "rule_engine",
    "principal-diagnosis-review": "rule_engine",
    "prior-auth": "rule_engine",
    "procedure-extractor": "rule_engine",
    "referral-gen": "rule_engine",
    "rule-explainer": "rule_engine",
    "surgical-registry": "rule_engine",
    "triage": "rule_engine",
}
SAFE_FAILURE_FIELDS = frozenset({
    "status",
    "markdown",
    "issues",
    "corrected_draft",
    "risk_flags",
    "tool_calls",
    "finish_state",
    "finish_reason",
    "backend_provider",
    "backend_type",
    "structured_extraction",
    "structured_validation",
    "contract_output_suppressed",
    "manual_review_required",
})


def _visible_cases() -> list[Any]:
    cases = []
    for path in sorted(OFFICIAL_AGENTS.glob("*/agent_pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        agent_id = str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0]
        example = (pack.get("example_inputs") or [{}])[0]
        text = str(example.get("input_text") or example.get("text") or "")
        cases.append(pytest.param(agent_id, pack, text, id=agent_id))
    assert len(cases) == 26
    return cases


def _adversarial_cases() -> list[Any]:
    case_doc = json.loads(ADVERSARIAL_CASES.read_text(encoding="utf-8"))
    suffix = str(case_doc.get("shared_untrusted_suffix") or "")
    packs = {
        str(pack.values[0]): pack.values[1]
        for pack in _visible_cases()
    }
    cases = []
    for case in case_doc.get("cases") or []:
        agent_id = str(case["agent_id"])
        cases.append(pytest.param(
            agent_id,
            packs[agent_id],
            str(case["input_text"]) + suffix,
            id=agent_id,
        ))
    assert len(cases) == len(packs) == 26
    return cases


def _configure_offline_runtime(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "false")
    monkeypatch.setenv("ICODER_DISABLE_NATIVE_MEDCODER", "true")


async def _run_and_assert_offline_truth(
    client,
    *,
    agent_id: str,
    pack: dict,
    input_text: str,
) -> dict:
    response = await client.post(
        f"/api/v1/agents/{agent_id}/run",
        json={
            "input": {"text": input_text or "离线安全端到端测试"},
            "include_trace": True,
            "include_evidence": True,
        },
    )
    assert response.status_code == 200, (agent_id, response.text)
    body = response.json()
    assert body["agent_id"] == agent_id
    assert str(body.get("run_id") or "").startswith("run-")
    assert str(body.get("trace_id") or "").startswith("trace-")
    assert body.get("manual_review_required") is True

    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    required = set((pack.get("output_contract") or {}).get("required_fields") or [])

    if agent_id in LOCAL_ONLY_AGENT_IDS:
        assert body.get("error") is False, body
        assert result.get("backend_provider") == LOCAL_PROVIDER_BY_AGENT[agent_id]
        assert result.get("backend_type") == LOCAL_BACKEND_TYPE_BY_AGENT[agent_id]
        assert float((body.get("cost") or {}).get("amount") or 0.0) == 0.0
        assert required.issubset(result), {
            "agent_id": agent_id,
            "missing": sorted(required - set(result)),
        }
        extraction = result.get("structured_extraction") or {}
        assert extraction.get("valid") is True, extraction
        if agent_id == "note-completeness-agent":
            assert 0.0 <= float(result["completeness_score"]) <= 1.0
            assert set(result["present_sections"]).isdisjoint(
                result["missing_sections"]
            )
            assert result["corrected_draft"] == ""
        elif agent_id == "code-validation-agent":
            assert result["review_conclusion"] in {"WARNING", "FAIL"}
            assert result["manual_review_required"] is True
            assert all(
                item["status"] == "valid"
                if item["in_catalog"] and item["assignable"]
                else item["status"] == "invalid"
                for item in result["validated_codes"]
            )
        elif agent_id == "diagnosis-extractor":
            assert result["status"] in {"WARNING", "REQUIRES_REVIEW"}
            assert result["manual_review_required"] is True
            assert all(
                input_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["diagnoses"] + result["non_codable_mentions"]
            )
            assert all(
                item["assertion_status"] == "present"
                for item in result["diagnoses"]
            )
            if "急性前壁心肌梗死" in input_text:
                assert result["diagnoses"][0]["icd10_cn_code"] == "I21.001"
                assert result["diagnoses"][0]["char_span"] == [5, 13]
                assert result["non_codable_mentions"][0]["char_span"] == [14, 22]
        elif agent_id == "discharge-edu":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["education_status"] in {
                "COMPLETED", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["medication_reconciliation_status"] == (
                "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED"
            )
            assert result["translation_status"] == (
                "VERBATIM_DOCUMENTED_CONTENT_ONLY"
            )
            assert result["external_knowledge_used"] is False
            assert result["clinical_interpretation_performed"] is False
            assert result["clinical_recommendations_generated"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
            if result["education_status"] == "PARTIAL":
                assert result["missing_items"]
            if (
                input_text.startswith("出院诊断：慢性心力衰竭")
                and "出院用药：" not in input_text
            ):
                assert result["medication_instructions"] == ""
                assert result["follow_up"] == ""
                assert result["warning_signs"] == ""
                assert result["lifestyle"] == ""
        elif agent_id == "discharge-summary-structuring":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["structuring_status"] in {
                "COMPLETED", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["summary_generation_status"] == (
                "VERBATIM_SECTION_REORGANIZATION_ONLY"
            )
            assert result["icd_codes_assigned"] is False
            assert result["medication_reconciliation_performed"] is False
            assert result["clinical_inference_performed"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
            if result["structuring_status"] == "INPUT_REQUIRED":
                assert result["diagnoses"] == []
                assert result["procedures"] == []
                assert result["discharge_orders"] == []
                assert result["follow_up_recommendations"] == []
                assert result["evidence_items"] == []
        elif agent_id == "referral-gen":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["referral_status"] in {
                "READY_FOR_REVIEW", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["draft_generation_status"] == (
                "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
            )
            assert result["clinical_inference_performed"] is False
            assert result["new_diagnosis_generated"] is False
            assert result["new_treatment_recommended"] is False
            assert result["external_knowledge_used"] is False
            assert result["production_transmission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
            if result["referral_status"] == "INPUT_REQUIRED":
                assert result["missing_required_fields"]
                assert result["referral_letter_draft"] == ""
        elif agent_id == "claim-check":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["review_status"] in {
                "READY_FOR_REVIEW", "POLICY_REQUIRED", "INPUT_REQUIRED",
            }
            assert result["evidence_consistency_status"] == (
                "NOT_ASSESSED_LITERAL_PACKET_ONLY"
            )
            assert result["clinical_support_assessed"] is False
            assert result["medical_necessity_assessed"] is False
            assert result["benefit_eligibility_determined"] is False
            assert result["code_assignment_performed"] is False
            assert result["drg_dip_grouping_performed"] is False
            assert result["external_knowledge_used"] is False
            assert result["production_submission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
        elif agent_id == "denial-appeals":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["appeal_status"] in {
                "READY_FOR_REVIEW", "POLICY_REQUIRED",
                "PATH_REVIEW_REQUIRED", "INPUT_REQUIRED",
            }
            assert result["denial_classification_status"] == (
                "DOCUMENTED_ONLY_NO_INFERENCE"
            )
            assert result["draft_generation_status"] == (
                "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
            )
            assert result["clinical_support_assessed"] is False
            assert result["medical_necessity_assessed"] is False
            assert result["benefit_eligibility_determined"] is False
            assert result["denial_root_cause_inferred"] is False
            assert result["payer_policy_lookup_performed"] is False
            assert result["medical_coding_validation_performed"] is False
            assert result["external_knowledge_used"] is False
            assert result["production_submission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
            if result["appeal_status"] in {"INPUT_REQUIRED", "PATH_REVIEW_REQUIRED"}:
                assert result["appeal_letter_draft"] == ""
                assert result["corrected_claim_checklist"] == []
        elif agent_id == "clinical-education":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["education_status"] in {
                "READY_FOR_REVIEW", "SOURCE_REVIEW_REQUIRED", "INPUT_REQUIRED",
            }
            assert result["content_generation_status"] == (
                "SOURCE_BOUND_TEMPLATE_ONLY"
            )
            assert result["question_classification_performed"] is False
            assert result["clinical_reasoning_performed"] is False
            assert result["diagnostic_advice_generated"] is False
            assert result["treatment_advice_generated"] is False
            assert result["drug_interaction_assessed"] is False
            assert result["medical_calculator_used"] is False
            assert result["pubmed_lookup_performed"] is False
            assert result["web_search_performed"] is False
            assert result["external_knowledge_used"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["text"]
                for item in result["evidence_items"]
            )
            if result["education_status"] == "INPUT_REQUIRED":
                assert result["source_statements"] == []
                assert result["learning_objectives"] == []
                assert result["key_points"] == []
                assert result["evidence_citations"] == []
                assert result["knowledge_checks"] == []
            elif result["education_status"] == "SOURCE_REVIEW_REQUIRED":
                assert result["learning_objectives"] == []
                assert result["key_points"] == []
                assert result["knowledge_checks"] == []
        elif agent_id == "clinical-guidelines":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["guideline_status"] in {
                "READY_FOR_REVIEW", "SOURCE_REVIEW_REQUIRED",
                "APPLICABILITY_REVIEW_REQUIRED", "INPUT_REQUIRED",
            }
            assert result["evaluation_method"] == (
                "DECLARED_RULES_DETERMINISTIC_COMPARISON"
            )
            assert result["source_currency_verified"] is False
            assert result["guideline_retrieval_performed"] is False
            assert result["web_search_performed"] is False
            assert result["clinical_inference_performed"] is False
            assert result["clinical_significance_assessed"] is False
            assert result["treatment_recommendations_generated"] is False
            assert result["external_knowledge_used"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["text"]
                for item in result["evidence_items"]
            )
            if result["guideline_status"] != "READY_FOR_REVIEW":
                assert result["overall_assessment"] == "NOT_ASSESSABLE"
        elif agent_id == "principal-diagnosis-review":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["review_status"] in {
                "READY_FOR_CODER_REVIEW", "EVIDENCE_REVIEW_REQUIRED",
                "INPUT_REQUIRED",
            }
            assert result["review_method"] == (
                "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"
            )
            assert result["diagnosis_extraction_performed"] is False
            assert result["code_assignment_performed"] is False
            assert result["principal_diagnosis_selection_performed"] is False
            assert result["clinical_inference_performed"] is False
            assert result["external_rules_used"] is False
            assert result["production_submission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["text"]
                for item in result["evidence_items"]
            )
        elif agent_id == "drg-analyzer":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["review_status"] in {
                "READY_FOR_CODER_REVIEW", "EVIDENCE_REVIEW_REQUIRED",
                "INPUT_REQUIRED", "RUNTIME_FAILED",
            }
            assert result["review_method"] == (
                "EXPLICIT_CODED_CASE_DETERMINISTIC_UNVERIFIED_RISK_REVIEW"
            )
            assert result["code_extraction_performed"] is False
            assert result["code_assignment_performed"] is False
            assert result["code_validation_performed"] is False
            assert result["clinical_inference_performed"] is False
            assert result["official_grouping_performed"] is False
            assert result["official_dip_scoring_performed"] is False
            assert result["payment_calculation_performed"] is False
            assert result["billing_authoritative"] is False
            assert result["production_submission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["text"]
                for item in result["evidence_items"]
            )
        elif agent_id == "triage":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["assessment_status"] in {
                "READY_FOR_ONSITE_REVIEW", "CONFLICT_REVIEW_REQUIRED",
                "PROTOCOL_INVALID", "INPUT_REQUIRED",
            }
            assert result["review_method"] == (
                "EXPLICIT_ANSWER_DETERMINISTIC_QUESTIONNAIRE_PATH_REVIEW"
            )
            assert result["transcript_extraction_performed"] is False
            assert result["questionnaire_answer_inference_performed"] is False
            assert result["clinical_inference_performed"] is False
            assert result["medical_calculator_used"] is False
            assert result["external_knowledge_used"] is False
            assert result["final_acuity_assignment_performed"] is False
            assert result["production_action_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["text"]
                for item in result["evidence_items"]
            )
            if result["assessment_status"] != "READY_FOR_ONSITE_REVIEW":
                assert result["acuity_level"] == "NOT_ASSIGNED"
                assert result["protocol_candidate"]["reached"] is False
        elif agent_id == "prior-auth":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["authorization_status"] in {
                "READY_FOR_REVIEW", "POLICY_REQUIRED", "INPUT_REQUIRED",
            }
            assert result["medical_necessity_assessment_status"] == (
                "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"
            )
            assert result["draft_generation_status"] == (
                "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
            )
            assert result["clinical_inference_performed"] is False
            assert result["new_diagnosis_generated"] is False
            assert result["new_treatment_recommended"] is False
            assert result["external_knowledge_used"] is False
            assert result["medical_calculator_used"] is False
            assert result["medical_coding_validation_performed"] is False
            assert result["production_submission_blocked"] is True
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
            if result["authorization_status"] == "INPUT_REQUIRED":
                assert result["missing_required_fields"]
                assert result["authorization_packet_draft"] == ""
        elif agent_id == "icd10-navigator":
            assert result["search_status"] in {
                "CANDIDATES_FOUND", "NO_CANDIDATES",
            }
            assert result["manual_review_required"] is True
            assert len(result["candidate_codes"]) <= 3
            assert all(
                item["source_asset_id"] == "cn.icd10cn.catalog"
                and item["instructional_notes_available"] is False
                for item in result["candidate_codes"]
            )
        elif agent_id == "evidence-ranker":
            assert result["ranking_basis"] == "DOCUMENTATION_GROUNDING_ONLY"
            assert result["manual_review_required"] is True
            assert len(result["ranked_evidence"]) <= 50
            assert all(
                0.0 <= float(item["documentation_grounding_score"]) <= 1.0
                for item in result["ranked_evidence"]
            )
        elif agent_id == "evidence-extractor":
            assert result["match_basis"] == "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"
            assert result["manual_review_required"] is True
            assert result["uncoded_findings"] == []
            assert all(
                item["clinical_support_assessed"] is False
                for item in result["located_mentions"]
            )
        elif agent_id == "procedure-extractor":
            assert result["manual_review_required"] is True
            assert result["total_count"] == len(result["procedures"])
            assert all(item["status"] == "performed" for item in result["procedures"])
            assert all(
                input_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["procedures"] + result["non_billable_mentions"]
            )
            if "T12" in input_text:
                assert result["procedures"][0]["code"] == "03.5304"
                assert all(item["code"] != "81.0100" for item in result["procedures"])
        elif agent_id == "rule-explainer":
            assert result["status"] in {"WARNING", "REQUIRES_REVIEW"}
            assert result["catalog_status"] in {
                "ASSIGNABLE", "CATEGORY_OR_PREFIX", "NOT_FOUND", "INPUT_REQUIRED",
            }
            assert result["rule_content_status"] == "UNAVAILABLE_IN_GOVERNED_ASSET"
            assert result["manual_review_required"] is True
            assert result["guideline_basis"]
            assert result["unsupported_scope"]
            if result["catalog_status"] == "CATEGORY_OR_PREFIX":
                assert result["assignable"] is False
                assert len(result["hierarchy"]["children"]) <= 10
        elif agent_id == "med-reconciliation":
            assert result["reconciliation_status"] in {
                "COMPLETED", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["interaction_screening_status"] == (
                "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"
            )
            assert result["interaction_risks"] == []
            assert result["manual_review_required"] is True
            assert all(
                input_text[slice(*item["char_span"])] == item["evidence_text"]
                for field in (
                    "home_medications",
                    "inpatient_medications",
                    "discharge_medications",
                    "unresolved_mentions",
                )
                for item in result[field]
            )
            assert not any(
                phrase in json.dumps(result, ensure_ascii=False)
                for phrase in ("无禁忌", "恢复二甲双胍前确认肾功能")
            )
        elif agent_id == "nursing-handoff":
            assert result["handoff_status"] in {
                "COMPLETED", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["clinical_priority_assessed"] is False
            assert result["medical_calculator_used"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            assert len(result["patient_handoffs"]) <= 10
            assert all(
                len(item["char_span"]) == 2
                and item["char_span"][0] < item["char_span"][1]
                and item["evidence_text"]
                for item in result["evidence_items"]
            )
            serialized = json.dumps(result, ensure_ascii=False)
            assert "感染风险" not in serialized
            assert "立即报告医生" not in serialized
        elif agent_id == "icu-summary":
            from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                redact_payload,
            )

            assert result["summary_status"] in {
                "COMPLETED", "PARTIAL", "INPUT_REQUIRED",
            }
            assert result["clinical_scores_status"] == (
                "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED"
            )
            assert result["medication_screening_status"] == (
                "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED"
            )
            assert result["clinical_recommendations_generated"] is False
            assert result["production_writeback_blocked"] is True
            assert result["manual_review_required"] is True
            redacted_text = redact_payload([
                {"kind": "text", "text": input_text}
            ]).value[0]["text"]
            assert all(
                redacted_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in result["evidence_items"]
            )
        elif agent_id == "surgical-registry":
            assert result["manual_review_required"] is True
            if "腹腔镜胆囊切除术" in input_text:
                assert result["procedure"] == "腹腔镜胆囊切除术"
            if "全麻" in input_text:
                assert result["anesthesia"] == "全麻"
            if "无胆管损伤" in input_text:
                assert "胆管损伤" in result["complications"]
            assert set(result["evidence_spans"]) == {
                field
                for field in (
                    "procedure", "indications", "comorbidities",
                    "operative_details", "anesthesia", "outcomes",
                    "complications",
                )
                if result[field]
            }
            assert all(
                quote in input_text
                for quote in result["evidence_spans"].values()
            )
    else:
        assert body.get("error") is True, body
        assert str(body.get("error_reason") or "").strip()
        assert result.get("contract_output_suppressed") is True
        assert set(result).issubset(SAFE_FAILURE_FIELDS), {
            "agent_id": agent_id,
            "unexpected": sorted(set(result) - SAFE_FAILURE_FIELDS),
        }
        domain_required = required - SAFE_FAILURE_FIELDS
        assert not domain_required.intersection(result), {
            "agent_id": agent_id,
            "leaked_contract_fields": sorted(domain_required.intersection(result)),
        }
        assert not body.get("evidence")

    trace = await client.get(f"/api/runtime/runs/{body['run_id']}/trace")
    assert trace.status_code == 200, (agent_id, trace.text)
    trace_body = trace.json()
    assert trace_body.get("run_id") == body["run_id"]
    if agent_id in LOCAL_ONLY_AGENT_IDS:
        timeline = trace_body.get("timeline") or []
        assert any(
            (event.get("safe_metadata") or event.get("metadata") or {}).get(
                "backend_provider"
            ) == LOCAL_PROVIDER_BY_AGENT[agent_id]
            for event in timeline
        )
        if agent_id in {
            "code-validation-agent",
            "diagnosis-extractor",
            "evidence-extractor",
            "icd10-navigator",
            "procedure-extractor",
            "rule-explainer",
        }:
            catalog_event = next(
                (
                    event
                    for event in timeline
                    if "clinical_asset_integrity_verified" in (
                        event.get("safe_metadata")
                        or event.get("metadata")
                        or {}
                    )
                ),
                None,
            )
            assert catalog_event is not None, timeline
            metadata = (
                catalog_event.get("safe_metadata")
                or catalog_event.get("metadata")
                or {}
            )
            if agent_id == "icd10-navigator":
                assert metadata["clinical_asset_integrity_verified"] is True
                assert metadata["candidate_codes_count"] == len(
                    result["candidate_codes"]
                )
                assert "source_unverified" in metadata[
                    "clinical_asset_authority_statuses"
                ]
            elif agent_id == "evidence-extractor":
                assert metadata["clinical_asset_integrity_verified"] is True
                assert metadata["evidence_input_codes_count"] == len(result["input_codes"])
                assert metadata["evidence_located_mentions_count"] == len(result["located_mentions"])
                assert metadata["evidence_unmatched_codes_count"] == len(result["unmatched_codes"])
                assert "source_unverified" in metadata[
                    "clinical_asset_authority_statuses"
                ]
            elif agent_id == "procedure-extractor":
                assert metadata["clinical_asset_integrity_verified"] is True
                assert metadata["candidate_codes_count"] == sum(
                    1 for item in result["procedures"] if item["code"]
                )
                assert metadata["evidence_items_count"] == (
                    len(result["procedures"])
                    + len(result["non_billable_mentions"])
                )
                assert "source_unverified" in metadata[
                    "clinical_asset_authority_statuses"
                ]
            elif agent_id == "diagnosis-extractor":
                assert metadata["clinical_asset_integrity_verified"] is True
                assert metadata["candidate_codes_count"] == len(result["diagnoses"])
                assert metadata["evidence_items_count"] == (
                    len(result["diagnoses"])
                    + len(result["non_codable_mentions"])
                )
                assert "source_unverified" in metadata[
                    "clinical_asset_authority_statuses"
                ]
            elif agent_id == "rule-explainer":
                if result["catalog_status"] in {
                    "ASSIGNABLE", "CATEGORY_OR_PREFIX", "NOT_FOUND",
                } and result["evidence_refs"]:
                    assert metadata["clinical_asset_integrity_verified"] is True
                    assert "source_unverified" in metadata[
                        "clinical_asset_authority_statuses"
                    ]
                else:
                    assert metadata["clinical_asset_integrity_verified"] is False
            elif result["validated_codes"]:
                assert metadata["semantic_enhancement_used"] is False
                assert metadata["clinical_asset_integrity_verified"] is True
                assert "source_unverified" in metadata[
                    "clinical_asset_authority_statuses"
                ]
            else:
                # Prompt-injection/no-code refusals return before consulting a
                # clinical catalog and must not pretend integrity was checked.
                assert metadata["clinical_asset_integrity_verified"] is False
        elif agent_id == "evidence-ranker":
            metadata = next(
                (
                    event.get("safe_metadata") or event.get("metadata") or {}
                    for event in timeline
                    if "evidence_items_count" in (
                        event.get("safe_metadata") or event.get("metadata") or {}
                    )
                ),
                None,
            )
            assert metadata is not None, timeline
            assert metadata["evidence_items_count"] == len(result["ranked_evidence"])
            assert 0.0 <= metadata["evidence_source_coverage_ratio"] <= 1.0
        elif agent_id == "med-reconciliation":
            metadata = next(
                (
                    event.get("safe_metadata") or event.get("metadata") or {}
                    for event in timeline
                    if "evidence_items_count" in (
                        event.get("safe_metadata") or event.get("metadata") or {}
                    )
                ),
                None,
            )
            assert metadata is not None, timeline
            expected_evidence = sum(
                len(result[field])
                for field in (
                    "home_medications",
                    "inpatient_medications",
                    "discharge_medications",
                    "unresolved_mentions",
                )
            )
            assert metadata["evidence_items_count"] == expected_evidence
            assert metadata["valid_evidence_spans_count"] == expected_evidence
        elif agent_id == "nursing-handoff":
            metadata = next(
                (
                    event.get("safe_metadata") or event.get("metadata") or {}
                    for event in timeline
                    if "evidence_items_count" in (
                        event.get("safe_metadata") or event.get("metadata") or {}
                    )
                ),
                None,
            )
            assert metadata is not None, timeline
            assert metadata["evidence_items_count"] == len(result["evidence_items"])
            assert metadata["valid_evidence_spans_count"] == len(
                result["evidence_items"]
            )
        elif agent_id == "icu-summary":
            metadata = next(
                (
                    event.get("safe_metadata") or event.get("metadata") or {}
                    for event in timeline
                    if "evidence_items_count" in (
                        event.get("safe_metadata") or event.get("metadata") or {}
                    )
                ),
                None,
            )
            assert metadata is not None, timeline
            assert metadata["evidence_items_count"] == len(result["evidence_items"])
            assert metadata["valid_evidence_spans_count"] == len(
                result["evidence_items"]
            )
    return body


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id,pack,input_text", _visible_cases())
async def test_visible_agent_offline_execution_truth(
    client,
    monkeypatch,
    agent_id: str,
    pack: dict,
    input_text: str,
) -> None:
    _configure_offline_runtime(monkeypatch)
    await _run_and_assert_offline_truth(
        client,
        agent_id=agent_id,
        pack=pack,
        input_text=input_text,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id,pack,input_text", _visible_cases())
async def test_visible_agent_project_clone_offline_routability(
    client,
    monkeypatch,
    agent_id: str,
    pack: dict,
    input_text: str,
) -> None:
    """Every Hub card remains executable through its project clone identity."""

    _configure_offline_runtime(monkeypatch)
    clone_response = await client.post(
        f"/api/icoder/agents/{agent_id}/clone",
        json={},
    )
    assert clone_response.status_code in {200, 201}, (
        agent_id,
        clone_response.text,
    )
    clone = clone_response.json()
    project_agent_id = clone["project_agent_id"]
    assert clone["runtime_agent_id"] == project_agent_id
    assert clone["source_runtime_agent_id"] == agent_id

    response = await client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={
            "input": {"text": input_text or "离线安全项目副本端到端测试"},
            "include_trace": True,
            "include_evidence": True,
        },
    )
    assert response.status_code == 200, (agent_id, response.text)
    body = response.json()
    assert body["agent_id"] == project_agent_id
    assert str(body.get("run_id") or "").startswith("run-")
    assert body.get("error_reason") not in {
        "unknown_agent",
        "provider_not_registered",
        "clone_source_not_found",
        "clone_source_unavailable",
        "clone_provenance_invalid",
        "clone_expert_override_unsupported",
    }, body

    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    if agent_id in LOCAL_ONLY_AGENT_IDS:
        assert body.get("error") is False, body
        assert result.get("backend_provider") == LOCAL_PROVIDER_BY_AGENT[agent_id]
        assert body.get("schema_ref") == (
            (pack.get("output_contract") or {}).get("schema_ref") or ""
        )
        assert body.get("result_attestation"), body
    else:
        # Offline external-LLM and native-disabled dedicated routes are
        # expected to fail closed, but they must reach their source runtime.
        assert body.get("error") is True, body
        assert str(body.get("error_reason") or "").strip()

    trace = await client.get(f"/api/runtime/runs/{body['run_id']}/trace")
    assert trace.status_code == 200, (agent_id, trace.text)
    assert (trace.json().get("summary") or {}).get("agent_id") == project_agent_id


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_id,pack,input_text", _adversarial_cases())
async def test_visible_agent_adversarial_offline_safety(
    client,
    monkeypatch,
    agent_id: str,
    pack: dict,
    input_text: str,
) -> None:
    _configure_offline_runtime(monkeypatch)
    body = await _run_and_assert_offline_truth(
        client,
        agent_id=agent_id,
        pack=pack,
        input_text=input_text,
    )
    assert "ICODER_PROMPT_CANARY_9F3A" not in json.dumps(
        body, ensure_ascii=False, default=str,
    )
