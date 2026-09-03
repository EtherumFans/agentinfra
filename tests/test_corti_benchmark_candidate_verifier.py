"""Tests for the offline, no-model Corti benchmark verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.corti_parity.verify_benchmark_candidate import verify_candidate


REPO_ROOT = Path(__file__).resolve().parents[1]
FROZEN_CANDIDATE = (
    REPO_ROOT / "reports" / "track_h" / "h4_benchmark_candidate_rc5"
)


def _write_minimal_candidate(root: Path, relative_path: str = "per_case/case.json") -> Path:
    artifact = root / relative_path
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "case_id": "CASE-synthetic",
                "patient_ref": "DEID",
                "encounter_ref": "DEID",
            }
        ),
        encoding="utf-8",
    )
    payload = artifact.read_bytes()
    metrics = {
        "section_9_9_cross_platform": {
            "agreement_rate_delta_le_1": 1.0,
            "avg_abs_query_count_delta": 0.0,
            "icoder_range_conformance": {"rate": 1.0},
        },
        "section_9_10_icoder_safety": {
            "over_query_complete_chart": {"rate": 0.0},
            "under_query_clear_gap": {"rate": 0.0},
            "multi_dimension_query_rate": 0.0,
        },
    }
    manifest = {
        "candidate_version": "synthetic",
        "case_count": 1,
        "file_count_total": 1,
        "files": [],
        "per_case_files": [
            {
                "path": relative_path,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        "cross_platform_normalizer": metrics,
        "h4_1_quality_summary": {
            "evidence_quote_verbatim_rate": 1.0,
            "response_options_4plus_rate": 1.0,
            "non_leading_query_rate": 1.0,
        },
        "h4_1_safety_summary": {"unsupported_query_rate": 0.0},
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return artifact


def test_frozen_candidate_integrity_passes_and_gaps_remain_explicit() -> None:
    result = verify_candidate(FROZEN_CANDIDATE)

    assert result["integrity"] == "passed"
    assert result["verified_case_files"] == 40
    assert result["unique_case_ids"] == 40
    assert result["parity_status"] == "partial"
    assert {gap["metric"] for gap in result["gaps"]} == {
        "agreement_rate_delta_le_1",
        "avg_abs_query_count_delta",
        "clear_gap_under_query_rate",
        "unsupported_query_rate",
    }


def test_synthetic_candidate_can_meet_all_metrics(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)

    result = verify_candidate(tmp_path)

    assert result["integrity"] == "passed"
    assert result["parity_status"] == "passed"
    assert result["gaps"] == []


def test_checksum_mismatch_fails_integrity(tmp_path: Path) -> None:
    artifact = _write_minimal_candidate(tmp_path)
    artifact.write_text("tampered", encoding="utf-8")

    result = verify_candidate(tmp_path)

    assert result["integrity"] == "failed"
    assert any("sha256 mismatch" in error for error in result["errors"])


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    _write_minimal_candidate(tmp_path)
    manifest_path = tmp_path / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["per_case_files"][0]["path"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verify_candidate(tmp_path)

    assert result["integrity"] == "failed"
    assert any("escapes the candidate directory" in error for error in result["errors"])
