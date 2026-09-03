from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.corti_parity.audit_ccl2026_local_dataset import (
    _canonical_sha256,
    build_report,
    validate_report,
)


def _case() -> dict:
    return {
        "encounter_id": "private-encounter-id",
        "department": "",
        "diagnosis_group": "",
        "specialty": "",
        "difficulty": "medium",
        "risk_tags": [],
        "admission_reason": "private chief complaint",
        "expected_principal_diagnosis": "I20.000",
        "expected_principal_diag_name": "",
        "expected_principal_procedure": "00.6600X008",
        "expected_principal_proc_name": "",
        "expected_secondary_diagnoses": ["I10.X09"],
        "expected_procedure_codes": ["88.5500"],
        "expected_drg_group": None,
        "acceptable_alternatives": [],
        "reasoning_expectations": [],
        "evidence_spans": [],
        "text": "private clinical chart",
        "source": "CCL2026",
    }


def _paths(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    root = tmp_path / "authorized"
    root.mkdir()
    workbook = root / "train.xlsx"
    workbook.write_bytes(b"test-workbook")
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([_case()], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.corti_parity.audit_ccl2026_local_dataset.load_ccl_cases",
        lambda _path: ([_case()], list(__import__(
            "scripts.corti_parity.audit_ccl2026_local_dataset",
            fromlist=["EXPECTED_HEADERS"],
        ).EXPECTED_HEADERS)),
    )
    return root, workbook, fixture


def test_exact_source_fixture_match_emits_only_aggregate_governance(
    tmp_path: Path, monkeypatch
) -> None:
    root, workbook, fixture = _paths(tmp_path, monkeypatch)
    report = build_report(
        workbook_path=workbook,
        fixture_path=fixture,
        authorized_root=root,
        authorization_acknowledged=True,
        expected_case_count=1,
        diagnosis_catalog={"I20.000", "I10.X09"},
        procedure_catalog={"00.6600X008", "88.5500"},
        catalog_status={
            "schema_version": "test",
            "catalog_release": "test-release",
            "integrity_verified": True,
            "diagnosis_count": 2,
            "procedure_count": 2,
        },
    )
    assert validate_report(report) == []
    assert report["status"] == "ready_for_local_isolated_benchmark"
    assert report["equivalence"]["exact_ordered_canonical_match"] is True
    assert report["governance"]["external_provider_egress_allowed"] is False
    serialized = json.dumps(report, ensure_ascii=False)
    assert "private-encounter-id" not in serialized
    assert "private clinical chart" not in serialized
    assert "I20.000" not in serialized


def test_mismatch_and_catalog_gap_fail_closed(tmp_path: Path, monkeypatch) -> None:
    root, workbook, fixture = _paths(tmp_path, monkeypatch)
    changed = _case()
    changed["text"] = "different private chart"
    fixture.write_text(json.dumps([changed], ensure_ascii=False), encoding="utf-8")
    report = build_report(
        workbook_path=workbook,
        fixture_path=fixture,
        authorized_root=root,
        authorization_acknowledged=True,
        expected_case_count=1,
        diagnosis_catalog={"I20.000"},
        procedure_catalog=set(),
        catalog_status={},
    )
    assert report["status"] == "blocked"
    assert report["equivalence"]["exact_ordered_canonical_match"] is False
    assert report["aggregate_label_coverage"][
        "diagnosis_catalog_unmatched_assignment_count"
    ] == 1
    assert report["aggregate_label_coverage"][
        "procedure_catalog_unmatched_assignment_count"
    ] == 2


def test_authorized_root_and_report_digest_are_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    root, workbook, fixture = _paths(tmp_path, monkeypatch)
    report = build_report(
        workbook_path=workbook,
        fixture_path=fixture,
        authorized_root=tmp_path / "different-root",
        authorization_acknowledged=False,
        expected_case_count=1,
        diagnosis_catalog={"I20.000", "I10.X09"},
        procedure_catalog={"00.6600X008", "88.5500"},
        catalog_status={},
    )
    assert report["status"] == "blocked"
    assert "source workbook escapes" in " ".join(report["errors"])
    assert "authorization acknowledgement" in " ".join(report["errors"])
    tampered = copy.deepcopy(report)
    tampered["governance"]["external_provider_egress_allowed"] = True
    assert "canonical report digest mismatch" in validate_report(tampered)
    assert any("external_provider_egress_allowed" in item for item in validate_report(tampered))


def test_report_digest_is_canonical() -> None:
    payload = {"b": 2, "a": 1}
    assert _canonical_sha256(payload) == _canonical_sha256({"a": 1, "b": 2})
