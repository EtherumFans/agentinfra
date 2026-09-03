from __future__ import annotations

import json

from scripts.corti_parity.agent_hub_live_evidence import canonical_sha256
from scripts.corti_parity.build_agent_hub_clinical_calibration_plan import (
    BILINGUAL_FIXTURE,
)
from scripts.corti_parity.run_agent_hub_clinical_calibration_e2e import (
    _execution_checks,
    apply_adjudicated_coding_gold,
    aggregate,
    score_cdi_response,
    score_coding_response,
    validate_report_file,
)
from scripts.corti_parity.run_agent_hub_examples_e2e import _evaluate


def test_cdi_scoring_recomputes_multi_dimension_final_queries() -> None:
    case = {
        "case_id": "CDI-1",
        "category": "clear_gap",
        "chart_zh": "病历记载肺炎，但严重程度和病原体未明确。",
        "expected": {"query_count_min": 1, "query_count_max": 2},
    }
    response = {
        "result": {
            "documentation_gaps": [],
            "proposed_provider_queries": [
                {
                    "query_id": "q1",
                    "gap_id": "g1",
                    "topic": "肺炎严重程度和病原体",
                    "reason": "需要澄清",
                    "query_text": "请明确肺炎的严重程度和病原体。",
                    "response_options": ["轻", "中", "重", "无法确定"],
                    "evidence_span": {
                        "quote": "肺炎",
                        "char_start": 4,
                        "char_end": 6,
                    },
                    "nlq_gate_verdict": "PASS",
                }
            ],
            "human_review": {
                "cdi_specialist_review_required": True,
                "clinician_response_required": True,
            },
        }
    }

    score = score_cdi_response(case=case, response=response)

    assert score["multi_dimension_final_query_count"] == 1
    assert score["final_queries_single_dimension"] is False
    assert score["evidence_exact_anchor_rate"] == 1.0


def test_bilingual_coding_score_uses_exact_cn_codes_and_evidence() -> None:
    case = {
        "case_id": "CODE-1",
        "chart_zh": "诊断：急性阑尾炎。行腹腔镜阑尾切除术。",
        "chart_en": "Diagnosis: acute appendicitis. Laparoscopic appendectomy performed.",
        "expected_principal_diagnosis": {"code": "K35.900"},
        "expected_secondary_diagnoses": [],
        "expected_primary_procedure": {"code": "47.0100"},
    }
    response = {
        "manual_review_required": True,
        "result": {
            "manual_review_required": True,
            "code_assignment": {
                "primary_diagnosis": {
                    "code": "K35.900",
                    "evidence": [{"text": "急性阑尾炎"}],
                },
                "secondary_diagnoses": [],
                "procedures": [
                    {
                        "code": "47.0100",
                        "evidence": [{"text": "腹腔镜阑尾切除术"}],
                    }
                ],
            },
            "validation_summary": {"manual_review_required": True},
            "human_review": {"review_required": True},
        },
    }

    score = score_coding_response(case=case, language="zh-CN", response=response)

    assert score["principal_diagnosis_exact_match"] is True
    assert score["primary_procedure_exact_match"] is True
    assert score["assigned_code_evidence_exact_anchor_rate"] == 1.0
    assert score["human_review_enforced"] is True


def test_validated_adjudication_replaces_engineering_gold_without_changing_charts() -> None:
    fixture = json.loads(BILINGUAL_FIXTURE.read_text(encoding="utf-8"))
    cases = fixture["cases"]
    decisions = []
    for case in cases:
        principal = dict(case["expected_principal_diagnosis"])
        if case["case_id"] == "HOBV1-001":
            principal["code"] = "S22.000x003"
        decisions.append(
            {
                "case_id": case["case_id"],
                "principal_diagnosis": principal,
                "secondary_diagnoses": case["expected_secondary_diagnoses"],
                "primary_procedure": case["expected_primary_procedure"],
            }
        )

    reviewed = apply_adjudicated_coding_gold(
        cases, {"final_decisions": decisions}
    )

    assert reviewed[0]["chart_zh"] == cases[0]["chart_zh"]
    assert reviewed[0]["chart_en"] == cases[0]["chart_en"]
    assert reviewed[0]["expected_principal_diagnosis"] == {
        "code": "S22.000x003"
    }
    assert reviewed[0]["calibration_gold_source"] == (
        "independent_bilingual_coding_adjudication"
    )
    assert cases[0]["expected_principal_diagnosis"]["code"] == "S22.000"


def test_execution_checks_require_real_signed_non_degraded_model_trace() -> None:
    common = {"passed": True}
    evidence = {
        "result_attestation": {"signature_verified": True},
        "trace": {
            "http_status": 200,
            "run_id_matches": True,
            "trace_attestation_signature_verified": True,
            "model_call_observed": True,
            "mock_detected": False,
            "degraded_detected": False,
        },
    }

    assert all(_execution_checks(common, evidence).values())

    evidence["trace"]["model_call_observed"] = False
    assert _execution_checks(common, evidence)["real_model_call_observed"] is False


def test_common_evaluation_uses_current_calibration_input_for_quantity_grounding() -> None:
    pack = {
        "agent_ref": "icoder/test-agent@1.0.0",
        "manifest": {"human_review": "required"},
        "permissions": {"production_writeback_blocked": True},
        "output_contract": {
            "schema_ref": "icoder/Test/v1",
            "required_fields": ["summary", "manual_review_required"],
            "optional_fields": [],
            "field_schemas": {
                "summary": {"type": "string"},
                "manual_review_required": {"type": "boolean"},
            },
        },
        "example_inputs": [{"input_text": "示例病程1天"}],
    }
    response = {
        "_http_status": 200,
        "error": False,
        "run_id": "run-current-input",
        "trace_id": "trace-current-input",
        "manual_review_required": True,
        "result": {
            "summary": "本次病程3天",
            "manual_review_required": True,
        },
    }

    stale_example = _evaluate(pack, response)
    current_case = _evaluate(pack, response, input_text="本次病程3天")

    assert stale_example["checks"]["clinical_quantities_grounded"] is False
    assert current_case["checks"]["clinical_quantities_grounded"] is True
    assert current_case["ungrounded_clinical_quantities"] == []


def test_partial_rows_can_never_pass_the_full_calibration_gate() -> None:
    result = aggregate([])

    assert result["execution_valid"] is False
    assert result["calibration_targets_passed"] is False
    assert "cdi_case_count_40" in result["failed_targets"]
    assert "coding_invocation_count_10" in result["failed_targets"]


def test_report_validator_rejects_overstated_claim_even_with_recomputed_digest(
    tmp_path,
) -> None:
    report = {
        "schema_version": "icoder.agent-hub-clinical-calibration-e2e/v1",
        "quality_scope": "synthetic_development_calibration_not_independent_clinical_gold",
        "rows": [],
        "summary": aggregate([]),
        "fixture_snapshot": {},
        "claim_boundaries": {
            "clinical_accuracy_proven": True,
            "independent_gold_used": False,
            "corti_parity_proven": False,
            "hospital_acceptance_proven": False,
            "production_ready_proven": False,
        },
    }
    report["report_sha256"] = canonical_sha256(report)
    path = tmp_path / "agent_hub_clinical_calibration_e2e.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    errors = validate_report_file(path)

    assert (
        "clinical calibration claim boundary must be false: clinical_accuracy_proven"
        in errors
    )
    assert "clinical calibration must contain exactly 50 rows" in errors
