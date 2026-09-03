"""Validate strict external Agent Hub artifacts without shell JSON parsing.

Windows PowerShell 5.1's ``ConvertFrom-Json`` rejects some valid, deeply nested
Agent Hub reports.  This validator keeps the large artifacts in Python's JSON
parser and emits one small, content-free summary for the release wrapper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.corti_parity.run_agent_hub_clinical_calibration_e2e import (
    validate_report_file as validate_clinical_calibration_report_file,
)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    raise ValueError(f"expected integer count, got {type(value).__name__}")


def validate(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "examples": args.examples.resolve(),
        "adversarial": args.adversarial.resolve(),
        "reference": args.reference.resolve(),
        "stability": args.stability.resolve(),
        "bundle": args.bundle.resolve(),
        "matrix": args.matrix.resolve(),
    }
    documents = {name: _load_object(path) for name, path in paths.items()}
    examples = documents["examples"]
    adversarial = documents["adversarial"]
    reference = documents["reference"]
    stability = documents["stability"]
    bundle = documents["bundle"]
    matrix = documents["matrix"]

    checks = {
        "examples_passed": _as_count(examples.get("passed"))
        == args.expected_agent_count,
        "adversarial_passed": _as_count(adversarial.get("passed"))
        == args.expected_agent_count,
        "reference_passed": _as_count(reference.get("passed"))
        == args.expected_agent_count,
        "stability_passed": _as_count(stability.get("passed"))
        == args.stability_expected,
        "bundle_valid": bundle.get("valid") is True,
        "bundle_verified_count": _as_count(
            (bundle.get("summary") or {}).get("semantic_live_e2e_verified")
        )
        == args.expected_agent_count,
        "matrix_semantic_evidence_valid": (
            (matrix.get("semantic_evidence") or {}).get("valid") is True
        ),
        "matrix_verified_count": _as_count(
            (matrix.get("summary") or {}).get(
                "visible_semantic_live_e2e_verified"
            )
        )
        == args.expected_agent_count,
        "matrix_pending_empty": len(
            (matrix.get("summary") or {}).get(
                "visible_semantic_live_e2e_pending"
            )
            or []
        )
        == 0,
        "matrix_external_pending_empty": len(
            (matrix.get("summary") or {}).get(
                "visible_external_semantic_live_e2e_pending"
            )
            or []
        )
        == 0,
    }

    clinical_summary: dict[str, Any] = {
        "included": bool(args.clinical_calibration),
        "execution_valid": False,
        "calibration_targets_passed": False,
        "failed_targets": [],
        "row_count": 0,
        "independent_gold_used": False,
        "independent_gold_governance_valid": False,
        "production_ready_proven": False,
        "artifact_validation_errors": [],
    }
    if args.clinical_calibration:
        clinical_path = args.clinical_calibration.resolve()
        clinical = _load_object(clinical_path)
        clinical_validation_errors = validate_clinical_calibration_report_file(
            clinical_path
        )
        paths["clinical_calibration"] = clinical_path
        summary = clinical.get("summary") or {}
        boundaries = clinical.get("claim_boundaries") or {}
        rows = clinical.get("rows") or []
        clinical_summary.update(
            {
                "execution_valid": summary.get("execution_valid") is True,
                "calibration_targets_passed": (
                    summary.get("calibration_targets_passed") is True
                ),
                "failed_targets": list(summary.get("failed_targets") or []),
                "row_count": len(rows),
                "independent_gold_used": boundaries.get(
                    "independent_gold_used"
                ),
                "independent_gold_governance_valid": (
                    boundaries.get("independent_gold_used") is True
                    and clinical.get("quality_scope")
                    == "development_calibration_with_independently_reviewed_bilingual_coding_gold"
                    and (clinical.get("gold_review_snapshot") or {}).get(
                        "validation_passed"
                    )
                    is True
                ),
                "production_ready_proven": boundaries.get(
                    "production_ready_proven"
                ),
                "artifact_validation_errors": clinical_validation_errors,
            }
        )
        checks.update(
            {
                "clinical_execution_valid": clinical_summary[
                    "execution_valid"
                ],
                "clinical_artifact_integrity_valid": not clinical_summary[
                    "artifact_validation_errors"
                ],
                "clinical_row_count": clinical_summary["row_count"] == 50,
                "clinical_independent_gold_claim_is_governed": (
                    clinical_summary["independent_gold_used"] is False
                    or clinical_summary["independent_gold_governance_valid"] is True
                ),
                "clinical_no_production_ready_claim": (
                    clinical_summary["production_ready_proven"] is False
                ),
            }
        )

    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "icoder.agent-hub-external-artifact-validation/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "valid": not failed_checks,
        "expected_agent_count": args.expected_agent_count,
        "stability_expected": args.stability_expected,
        "metrics": {
            "examples_passed": examples.get("passed"),
            "adversarial_passed": adversarial.get("passed"),
            "reference_passed": reference.get("passed"),
            "stability_passed": stability.get("passed"),
            "bundle_verified": (bundle.get("summary") or {}).get(
                "semantic_live_e2e_verified"
            ),
            "matrix_verified": (matrix.get("summary") or {}).get(
                "visible_semantic_live_e2e_verified"
            ),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "clinical_calibration": clinical_summary,
        "source_artifacts": {
            name: {
                "path": str(path),
                "sha256": _sha256(path),
            }
            for name, path in paths.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--adversarial", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--expected-agent-count", type=int, default=26)
    parser.add_argument("--stability-expected", type=int, default=156)
    parser.add_argument("--clinical-calibration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = validate(args)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "valid": report["valid"],
                "failed_checks": report["failed_checks"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
