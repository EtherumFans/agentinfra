from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "corti_parity"
    / "validate_agent_hub_external_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_agent_hub_external_artifacts", MODULE_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _arguments(tmp_path: Path) -> argparse.Namespace:
    examples = _write(tmp_path / "examples.json", {"passed": 26})
    adversarial = _write(tmp_path / "adversarial.json", {"passed": 26})
    reference = _write(tmp_path / "reference.json", {"passed": 26})
    stability = _write(tmp_path / "stability.json", {"passed": 156})
    bundle = _write(
        tmp_path / "bundle.json",
        {
            "valid": True,
            "summary": {"semantic_live_e2e_verified": 26},
        },
    )
    matrix = _write(
        tmp_path / "matrix.json",
        {
            "semantic_evidence": {"valid": True},
            "summary": {
                "visible_semantic_live_e2e_verified": 26,
                "visible_semantic_live_e2e_pending": [],
                "visible_external_semantic_live_e2e_pending": [],
            },
        },
    )
    return argparse.Namespace(
        examples=examples,
        adversarial=adversarial,
        reference=reference,
        stability=stability,
        bundle=bundle,
        matrix=matrix,
        expected_agent_count=26,
        stability_expected=156,
        clinical_calibration=None,
    )


def test_validator_emits_small_content_free_valid_summary(tmp_path: Path) -> None:
    report = MODULE.validate(_arguments(tmp_path))

    assert report["valid"] is True
    assert report["failed_checks"] == []
    assert report["metrics"] == {
        "examples_passed": 26,
        "adversarial_passed": 26,
        "reference_passed": 26,
        "stability_passed": 156,
        "bundle_verified": 26,
        "matrix_verified": 26,
    }
    assert set(report["source_artifacts"]) == {
        "examples",
        "adversarial",
        "reference",
        "stability",
        "bundle",
        "matrix",
    }
    assert "rows" not in report


def test_validator_fails_closed_on_count_or_pending_agent_drift(
    tmp_path: Path,
) -> None:
    args = _arguments(tmp_path)
    _write(args.adversarial, {"passed": 25})
    _write(
        args.matrix,
        {
            "semantic_evidence": {"valid": True},
            "summary": {
                "visible_semantic_live_e2e_verified": 26,
                "visible_semantic_live_e2e_pending": ["triage"],
                "visible_external_semantic_live_e2e_pending": [],
            },
        },
    )

    report = MODULE.validate(args)

    assert report["valid"] is False
    assert "adversarial_passed" in report["failed_checks"]
    assert "matrix_pending_empty" in report["failed_checks"]


def test_independent_gold_claim_requires_governed_review_snapshot(
    tmp_path: Path,
) -> None:
    args = _arguments(tmp_path)
    args.clinical_calibration = _write(
        tmp_path / "clinical.json",
        {
            "quality_scope": (
                "development_calibration_with_independently_reviewed_bilingual_coding_gold"
            ),
            "summary": {
                "execution_valid": True,
                "calibration_targets_passed": False,
                "failed_targets": ["coding_principal_exact_rate_ge_0_8"],
            },
            "rows": [{} for _ in range(50)],
            "claim_boundaries": {
                "independent_gold_used": True,
                "production_ready_proven": False,
            },
        },
    )

    report = MODULE.validate(args)

    assert report["valid"] is False
    assert "clinical_independent_gold_claim_is_governed" in report["failed_checks"]


def test_governed_independent_gold_summary_remains_non_production(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "validate_clinical_calibration_report_file",
        lambda _path: [],
    )
    args = _arguments(tmp_path)
    args.clinical_calibration = _write(
        tmp_path / "clinical.json",
        {
            "quality_scope": (
                "development_calibration_with_independently_reviewed_bilingual_coding_gold"
            ),
            "summary": {
                "execution_valid": True,
                "calibration_targets_passed": False,
                "failed_targets": ["coding_principal_exact_rate_ge_0_8"],
            },
            "rows": [{} for _ in range(50)],
            "gold_review_snapshot": {"validation_passed": True},
            "claim_boundaries": {
                "independent_gold_used": True,
                "production_ready_proven": False,
            },
        },
    )

    report = MODULE.validate(args)

    assert report["valid"] is True
    assert report["clinical_calibration"]["independent_gold_used"] is True
    assert report["clinical_calibration"]["production_ready_proven"] is False


def test_clinical_summary_cannot_bypass_authoritative_artifact_validation(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "validate_clinical_calibration_report_file",
        lambda _path: ["gold review adjudication digest mismatch"],
    )
    args = _arguments(tmp_path)
    args.clinical_calibration = _write(
        tmp_path / "clinical.json",
        {
            "quality_scope": (
                "development_calibration_with_independently_reviewed_bilingual_coding_gold"
            ),
            "summary": {
                "execution_valid": True,
                "calibration_targets_passed": False,
                "failed_targets": [],
            },
            "rows": [{} for _ in range(50)],
            "gold_review_snapshot": {"validation_passed": True},
            "claim_boundaries": {
                "independent_gold_used": True,
                "production_ready_proven": False,
            },
        },
    )

    report = MODULE.validate(args)

    assert report["valid"] is False
    assert "clinical_artifact_integrity_valid" in report["failed_checks"]
    assert report["clinical_calibration"]["artifact_validation_errors"] == [
        "gold review adjudication digest mismatch"
    ]
