from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.corti_parity.audit_ccl2026_local_dataset import _canonical_sha256
from scripts.corti_parity.evaluate_ccl2026_local_predictions import (
    _exact_code,
    build_oracle_test_packet,
    evaluate,
    validate_aggregate_report,
)


DX = {"I20.000", "I10.X09", "A00.001", "A00.002"}
PROC = {"00.6600X008", "88.5500", "01.0100", "01.0200"}
CATALOG_STATUS = {
    "schema_version": "test",
    "catalog_release": "test-release",
    "integrity_verified": True,
    "diagnosis_count": len(DX),
    "procedure_count": len(PROC),
}


def _cases() -> list[dict]:
    return [
        {
            "encounter_id": "private-one",
            "text": "private chart one",
            "admission_reason": "private reason one",
            "expected_principal_diagnosis": "I20.000",
            "expected_secondary_diagnoses": ["I10.X09"],
            "expected_principal_procedure": "00.6600X008",
            "expected_procedure_codes": ["88.5500"],
        },
        {
            "encounter_id": "private-two",
            "text": "private chart two",
            "admission_reason": "private reason two",
            "expected_principal_diagnosis": "A00.001",
            "expected_secondary_diagnoses": [],
            "expected_principal_procedure": None,
            "expected_procedure_codes": [],
        },
    ]


def _artifacts(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict]:
    isolated = tmp_path / "isolated"
    isolated.mkdir(parents=True)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(_cases(), ensure_ascii=False), encoding="utf-8")
    fixture_sha = __import__("hashlib").sha256(fixture.read_bytes()).hexdigest()
    audit = {
        "schema_version": "icoder.ccl2026-local-dataset-audit/v1",
        "generated_at": "2026-08-27T00:00:00+00:00",
        "status": "ready_for_local_isolated_benchmark",
        "source_workbook": {"sha256": "a" * 64},
        "bound_repository_fixture": {"sha256": fixture_sha, "case_count": 2},
        "equivalence": {"exact_ordered_canonical_match": True},
        "aggregate_label_coverage": {},
        "catalog_snapshot": {},
        "governance": {
            "user_authorization_acknowledged": True,
            "aggregate_only_report": True,
            "raw_clinical_text_emitted": False,
            "encounter_identifiers_emitted": False,
            "case_level_labels_emitted": False,
            "external_provider_egress_allowed": False,
            "source_workbook_copy_allowed": False,
            "redistribution_rights_proven": False,
            "independent_clinical_gold_proven": False,
            "production_accuracy_claim_allowed": False,
            "local_isolated_benchmark_allowed": True,
        },
        "errors": [],
    }
    audit["report_sha256"] = _canonical_sha256(audit)
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(audit), encoding="utf-8")
    audit_sha = __import__("hashlib").sha256(audit_path.read_bytes()).hexdigest()
    packet = build_oracle_test_packet(
        cases=_cases(),
        audit_report=audit,
        audit_file_sha256=audit_sha,
        fixture_sha256=fixture_sha,
    )
    predictions = isolated / "predictions.json"
    predictions.write_text(json.dumps(packet), encoding="utf-8")
    return audit_path, fixture, predictions, isolated, packet


def _evaluate(tmp_path: Path, packet_mutator=None):
    audit, fixture, predictions, isolated, packet = _artifacts(tmp_path)
    if packet_mutator:
        packet_mutator(packet)
        predictions.write_text(json.dumps(packet), encoding="utf-8")
    return evaluate(
        audit_report_path=audit,
        fixture_path=fixture,
        predictions_path=predictions,
        isolated_root=isolated,
        expected_case_count=2,
        diagnosis_catalog=DX,
        procedure_catalog=PROC,
        catalog_status=CATALOG_STATUS,
    )


def test_oracle_packet_scores_one_and_emits_only_aggregates(tmp_path: Path) -> None:
    report = _evaluate(tmp_path)
    assert validate_aggregate_report(report) == []
    assert report["status"] == "valid_local_training_set_measurement"
    assert report["metrics"]["principal_diagnosis_exact_accuracy"] == 1.0
    assert report["metrics"]["all_diagnosis"]["f1"] == 1.0
    assert report["metrics"]["principal_procedure_exact_accuracy"] == 1.0
    assert report["metrics"][
        "principal_procedure_exact_accuracy_when_gold_present"
    ] == 1.0
    assert report["metrics"]["full_code_set_exact_match_rate"] == 1.0
    assert report["claim_boundaries"]["model_capability_proven"] is False
    serialized = json.dumps(report, ensure_ascii=False)
    for private_value in ("private-one", "private chart one", "I20.000", "88.5500"):
        assert private_value not in serialized


def test_wrong_prediction_has_exact_micro_metrics(tmp_path: Path) -> None:
    def mutate(packet):
        row = packet["predictions"][0]
        row["principal_diagnosis"] = "A00.002"
        row["secondary_diagnoses"] = []
        row["principal_procedure"] = "01.0100"
        row["other_procedures"] = []

    report = _evaluate(tmp_path, mutate)
    assert validate_aggregate_report(report) == []
    assert report["metrics"]["principal_diagnosis_exact_accuracy"] == 0.5
    assert report["metrics"]["all_diagnosis"] == {
        "true_positive_count": 1,
        "false_positive_count": 1,
        "false_negative_count": 2,
        "precision": 0.5,
        "recall": 0.333333,
        "f1": 0.4,
    }
    assert report["metrics"]["principal_procedure_exact_accuracy"] == 0.5
    assert report["metrics"][
        "principal_procedure_exact_accuracy_when_gold_present"
    ] == 0.0


def test_parent_child_codes_are_not_collapsed() -> None:
    assert _exact_code(" I20.000 ") == "I20.000"
    assert _exact_code("i20.000") == "I20.000"
    assert _exact_code("I20") != _exact_code("I20.000")
    assert _exact_code("I20.00") != _exact_code("I20.000")


def test_tamper_duplicate_and_missing_binding_fail_closed(tmp_path: Path) -> None:
    def mutate(packet):
        packet["dataset_binding"]["fixture_sha256"] = "0" * 64
        packet["predictions"][1]["case_digest"] = packet["predictions"][0]["case_digest"]

    report = _evaluate(tmp_path, mutate)
    assert report["status"] == "invalid"
    assert report["metrics"] == {}
    assert report["integrity"]["duplicate_case_digest_count"] == 1
    assert report["integrity"]["missing_case_digest_count"] == 1


def test_forbidden_case_payload_and_out_of_catalog_code_fail_closed(tmp_path: Path) -> None:
    def mutate(packet):
        packet["predictions"][0]["text"] = "private chart leak"
        packet["predictions"][1]["principal_diagnosis"] = "Z99.999"

    report = _evaluate(tmp_path, mutate)
    assert report["status"] == "invalid"
    assert report["metrics"] == {}
    assert report["integrity"]["malformed_prediction_row_count"] == 1
    assert report["integrity"]["invalid_diagnosis_assignment_count"] == 1
    assert "private chart leak" not in json.dumps(report)
    assert "Z99.999" not in json.dumps(report)


def test_invalid_metadata_cannot_leak_free_text_into_aggregate_report(
    tmp_path: Path,
) -> None:
    private_text = "private chart content in metadata"

    def mutate(packet):
        packet["run_metadata"]["model_id"] = private_text

    report = _evaluate(tmp_path, mutate)
    assert report["status"] == "invalid"
    assert report["metrics"] == {}
    assert report["run_metadata"]["model_id"] == ""
    assert private_text not in json.dumps(report)


def test_external_egress_attestation_and_path_escape_fail_closed(tmp_path: Path) -> None:
    report = _evaluate(
        tmp_path,
        lambda packet: packet["run_metadata"].update({"network_used": True}),
    )
    assert report["status"] == "invalid"
    audit, fixture, predictions, isolated, _packet = _artifacts(tmp_path / "second")
    escaped = tmp_path / "escaped.json"
    escaped.write_bytes(predictions.read_bytes())
    escaped_report = evaluate(
        audit_report_path=audit,
        fixture_path=fixture,
        predictions_path=escaped,
        isolated_root=isolated,
        expected_case_count=2,
        diagnosis_catalog=DX,
        procedure_catalog=PROC,
        catalog_status=CATALOG_STATUS,
    )
    assert escaped_report["status"] == "invalid"
    assert escaped_report["metrics"] == {}


def test_safe_failure_is_scored_without_fallback_success(tmp_path: Path) -> None:
    def mutate(packet):
        row = packet["predictions"][0]
        row.update({
            "status": "failed",
            "principal_diagnosis": "",
            "secondary_diagnoses": [],
            "principal_procedure": None,
            "other_procedures": [],
            "failure_category": "model_error",
        })

    report = _evaluate(tmp_path, mutate)
    assert report["status"] == "valid_local_training_set_measurement"
    assert report["metrics"]["execution_coverage"] == 0.5
    assert report["metrics"]["safe_failure_case_count"] == 1
    assert report["metrics"]["principal_diagnosis_exact_accuracy"] == 0.5


def test_aggregate_report_tampering_is_detected(tmp_path: Path) -> None:
    report = _evaluate(tmp_path)
    tampered = copy.deepcopy(report)
    tampered["per_case"] = [{"encounter_id": "leak"}]
    errors = validate_aggregate_report(tampered)
    assert "canonical aggregate report digest mismatch" in errors
    assert "aggregate report contains prohibited case-level fields" in errors
