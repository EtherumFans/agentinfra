from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.clinical_model_bundle import verify_bundle_directory
from app.services.clinical_model_shadow_observation import (
    ClinicalModelShadowObservationError,
    SUITE_SHA256,
    build_fault_observation,
    evaluate_shadow_stop_policy,
    run_verified_shadow_suite,
    validate_shadow_observation,
)


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "clinical_model_bundle_v1"
)


def _verified():
    return verify_bundle_directory(FIXTURE, environment="test")


def test_fixed_synthetic_suite_is_aggregate_only_and_repeatable() -> None:
    verified = _verified()
    model_sha256 = hashlib.sha256(verified.entrypoint_bytes).hexdigest()

    def fixed_probe(_bundle):
        return {
            "model_sha256": model_sha256,
            "test_vector_count": 2,
            "test_vectors_passed": 2,
        }

    first = run_verified_shadow_suite(verified, probe_runner=fixed_probe)
    second = run_verified_shadow_suite(verified, probe_runner=fixed_probe)
    for report in (first, second):
        assert report["result"] == "passed"
        assert report["required_action"] == "keep_shadow_only"
        assert report["suite_sha256"] == SUITE_SHA256
        assert report["run_count"] == 3
        assert report["vector_observation_count"] == 6
        assert report["success_count"] == 6
        assert report["patient_data_used"] is False
        assert report["raw_input_stored"] is False
        assert report["predictions_emitted"] is False
        assert report["production_inference_enabled"] is False
        validate_shadow_observation(report)
    comparable = {
        key: value for key, value in first.items()
        if key not in {"latency_p50_ms", "latency_p95_ms", "observation_report_sha256"}
    }
    assert comparable == {
        key: value for key, value in second.items()
        if key not in {"latency_p50_ms", "latency_p95_ms", "observation_report_sha256"}
    }


@pytest.mark.parametrize(
    ("fault_mode", "reason"),
    [
        ("worker_timeout", "worker_timeout"),
        ("malformed_response", "malformed_response"),
        ("model_hash_mismatch", "model_hash_mismatch"),
    ],
)
def test_controlled_faults_stop_and_require_rollback(fault_mode: str, reason: str) -> None:
    report = build_fault_observation(
        fault_mode,
        artifact_sha256="a" * 64,
        model_sha256="b" * 64,
    )
    assert report["result"] == "stopped"
    assert report["reason_code"] == reason
    assert report["required_action"] == "stop_and_rollback"
    assert report["source"] == "synthetic_fault_injection"
    assert report["artifact_reverified"] is False
    validate_shadow_observation(report)


def test_policy_stops_phi_network_prediction_and_threshold_violations() -> None:
    base = {
        "patient_data_used": False,
        "network_used": False,
        "predictions_emitted": False,
        "fault_mode": "none",
        "error_count": 0,
        "mismatch_count": 0,
        "vector_observation_count": 6,
        "success_count": 6,
        "latency_p95_ms": 1,
    }
    for field, reason in (
        ("patient_data_used", "patient_data_policy_violation"),
        ("network_used", "network_policy_violation"),
        ("predictions_emitted", "prediction_emission_policy_violation"),
    ):
        report = {**base, field: True}
        assert evaluate_shadow_stop_policy(report)["reason_code"] == reason
    assert evaluate_shadow_stop_policy({**base, "error_count": 1})["result"] == "stopped"
    assert evaluate_shadow_stop_policy({**base, "mismatch_count": 1})["result"] == "stopped"
    assert evaluate_shadow_stop_policy({**base, "vector_observation_count": 5})[
        "result"
    ] == "stopped"
    assert evaluate_shadow_stop_policy({**base, "latency_p95_ms": 5_001})[
        "result"
    ] == "stopped"


def test_observation_report_tamper_and_invalid_fault_fail_closed() -> None:
    report = build_fault_observation(
        "worker_timeout", artifact_sha256="a" * 64, model_sha256="b" * 64,
    )
    report["error_count"] = 0
    with pytest.raises(
        ClinicalModelShadowObservationError,
        match="SHADOW_OBSERVATION_REPORT_INVALID",
    ):
        validate_shadow_observation(report)
    with pytest.raises(
        ClinicalModelShadowObservationError,
        match="SHADOW_OBSERVATION_FAULT_INVALID",
    ):
        build_fault_observation(
            "unexpected", artifact_sha256="a" * 64, model_sha256="b" * 64,
        )
    invalid_digest = build_fault_observation(
        "worker_timeout", artifact_sha256="a" * 64, model_sha256="b" * 64,
    )
    invalid_digest["model_sha256"] = "not-a-digest"
    with pytest.raises(
        ClinicalModelShadowObservationError,
        match="SHADOW_OBSERVATION_REPORT_INVALID",
    ):
        validate_shadow_observation(invalid_digest)
    invalid_combination = build_fault_observation(
        "worker_timeout", artifact_sha256="a" * 64, model_sha256="b" * 64,
    )
    invalid_combination["source"] = "repository_synthetic"
    with pytest.raises(
        ClinicalModelShadowObservationError,
        match="SHADOW_OBSERVATION_REPORT_INVALID",
    ):
        validate_shadow_observation(invalid_combination)
