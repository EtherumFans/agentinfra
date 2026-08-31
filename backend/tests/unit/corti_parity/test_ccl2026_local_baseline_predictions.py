from __future__ import annotations

from scripts.corti_parity.generate_ccl2026_local_baseline_predictions import (
    _rank_matches,
    _catalog_index,
    build_packet,
    generate_predictions,
)


DX = [
    ("I10.X09", "原发性高血压", ""),
    ("I50.900", "心力衰竭", ""),
    ("I50.901", "心力衰竭", ""),
]
PROC = [
    ("88.5500", "冠状动脉造影", ""),
    ("00.6600", "冠状动脉支架植入术", ""),
]


def _case(**changes):
    value = {
        "encounter_id": "private-id",
        "text": "原发性高血压。后行冠状动脉造影。原发性高血压。",
        "expected_principal_diagnosis": "SHOULD.NOT.BE.READ",
        "expected_secondary_diagnoses": ["ALSO.NOT.READ"],
        "expected_principal_procedure": "NOT.READ",
        "expected_procedure_codes": [],
    }
    value.update(changes)
    return value


def test_exact_catalog_name_baseline_is_deterministic() -> None:
    rows = generate_predictions(
        cases=[_case()], diagnosis_entries=DX, procedure_entries=PROC
    )
    assert rows[0]["status"] == "completed"
    assert rows[0]["principal_diagnosis"] == "I10.X09"
    assert rows[0]["secondary_diagnoses"] == []
    assert rows[0]["principal_procedure"] == "88.5500"


def test_prediction_codes_do_not_depend_on_gold_fields() -> None:
    first = generate_predictions(
        cases=[_case()], diagnosis_entries=DX, procedure_entries=PROC
    )[0]
    second = generate_predictions(
        cases=[_case(
            expected_principal_diagnosis="DIFFERENT",
            expected_secondary_diagnoses=["DIFFERENT"],
            expected_principal_procedure="DIFFERENT",
        )],
        diagnosis_entries=DX,
        procedure_entries=PROC,
    )[0]
    for field in (
        "status",
        "principal_diagnosis",
        "secondary_diagnoses",
        "principal_procedure",
        "other_procedures",
        "failure_category",
    ):
        assert first[field] == second[field]
    assert first["case_digest"] != second["case_digest"]


def test_no_exact_diagnosis_match_is_a_safe_failure() -> None:
    row = generate_predictions(
        cases=[_case(text="没有目录精确词条")],
        diagnosis_entries=DX,
        procedure_entries=PROC,
    )[0]
    assert row["status"] == "failed"
    assert row["principal_diagnosis"] == ""
    assert row["failure_category"] == "validation_error"


def test_repeated_and_recent_exact_names_define_stable_rank() -> None:
    index = _catalog_index(DX)
    ranked = _rank_matches("心力衰竭。原发性高血压。原发性高血压。", index)
    assert ranked[0] == "I10.X09"
    assert ranked[1:] == ["I50.900", "I50.901"]


def test_packet_is_explicitly_non_model_and_no_network() -> None:
    audit = {
        "source_workbook": {"sha256": "a" * 64},
        "report_sha256": "b" * 64,
    }
    packet = build_packet(
        cases=[_case()],
        audit_report=audit,
        audit_file_sha256="c" * 64,
        fixture_sha256="d" * 64,
        diagnosis_entries=DX,
        procedure_entries=PROC,
        catalog_release="test-release",
    )
    metadata = packet["run_metadata"]
    assert metadata["provider_class"] == "local_deterministic_baseline"
    assert metadata["network_used"] is False
    assert metadata["external_provider_used"] is False
    assert metadata["clinical_text_included"] is False
