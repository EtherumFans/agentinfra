from __future__ import annotations

import copy

from scripts.corti_parity.evaluate_ccl2026_local_supervised_oof import (
    EvaluationInput,
    TrainingExample,
    _fold_assignments,
    document_features,
    predict_fold,
    validate_aggregate_report,
    validate_persisted_report,
)


def _case(text: str, principal: str) -> dict:
    return {
        "text": text,
        "expected_principal_diagnosis": principal,
        "expected_secondary_diagnoses": [],
        "expected_principal_procedure": "",
        "expected_procedure_codes": [],
    }


def test_stratified_folds_are_deterministic_balanced_and_text_group_safe() -> None:
    cases = [
        _case(f"甲类病历{index}", "A01") for index in range(10)
    ] + [
        _case(f"乙类病历{index}", "B01") for index in range(10)
    ]
    first = _fold_assignments(cases, folds=5, seed="fixed")
    second = _fold_assignments(copy.deepcopy(cases), folds=5, seed="fixed")
    assert first == second
    assert [first.count(index) for index in range(5)] == [4, 4, 4, 4, 4]

    duplicate = copy.deepcopy(cases[0])
    cases.append(duplicate)
    grouped = _fold_assignments(cases, folds=5, seed="fixed")
    assert grouped[0] == grouped[-1]


def test_evaluation_prediction_has_no_gold_label_input() -> None:
    training = [
        TrainingExample(
            text_digest="train-a",
            features=document_features("肺部感染伴咳嗽发热"),
            principal_diagnosis="A01",
            diagnoses=("A01",),
            principal_procedure="",
            procedures=(),
        ),
        TrainingExample(
            text_digest="train-b",
            features=document_features("骨折术后复查"),
            principal_diagnosis="B01",
            diagnoses=("B01",),
            principal_procedure="",
            procedures=(),
        ),
    ]
    item = EvaluationInput(
        text_digest="eval",
        features=document_features("肺部感染复查"),
    )
    first = predict_fold(training, [item])
    second = predict_fold(copy.deepcopy(training), [copy.deepcopy(item)])
    assert first == second
    assert first[0]["principal_diagnosis"] in {"A01", "B01"}


def test_report_validator_rejects_case_level_payload_and_optimistic_claims() -> None:
    report = {
        "schema_version": "icoder.ccl2026-local-supervised-oof/v1",
        "status": "valid_local_supervised_oof_measurement",
        "integrity": {"training_row_self_exposure_count": 0},
        "claim_boundaries": {
            "all_predictions_out_of_fold": True,
            "independent_clinical_gold_proven": False,
            "external_generalization_proven": False,
            "corti_capability_parity_proven": False,
            "clinical_production_readiness_proven": False,
            "external_network_used": False,
            "case_level_artifacts_emitted": False,
        },
    }
    assert validate_aggregate_report(report) == []
    report["predictions"] = [{"text": "must not escape"}]
    assert validate_aggregate_report(report)
    del report["predictions"]
    report["claim_boundaries"]["independent_clinical_gold_proven"] = True
    assert validate_aggregate_report(report)


def test_persisted_report_digest_is_fail_closed() -> None:
    report = {
        "schema_version": "icoder.ccl2026-local-supervised-oof/v1",
        "status": "valid_local_supervised_oof_measurement",
        "integrity": {"training_row_self_exposure_count": 0},
        "claim_boundaries": {
            "all_predictions_out_of_fold": True,
            "independent_clinical_gold_proven": False,
            "external_generalization_proven": False,
            "corti_capability_parity_proven": False,
            "clinical_production_readiness_proven": False,
            "external_network_used": False,
            "case_level_artifacts_emitted": False,
        },
        "report_sha256": "0" * 64,
    }
    assert "aggregate report digest is invalid" in validate_persisted_report(report)
