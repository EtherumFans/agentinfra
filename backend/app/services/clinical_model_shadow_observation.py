"""Aggregate-only synthetic shadow observation and fail-closed policy."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from typing import Any, Literal

from app.services.clinical_model_bundle import (
    VerifiedClinicalModelBundle,
    validate_verification_report,
)
from app.services.clinical_model_shadow_probe import probe_verified_synthetic_bundle


OBSERVATION_SCHEMA = "icoder.clinical-model-shadow-observation/v1"
SUITE_ID = "icoder.repository-synthetic-shadow-observation/v1"
RUN_COUNT = 3
MINIMUM_VECTOR_OBSERVATIONS = 6
MAX_P95_MS = 5_000
FAULT_MODES = {
    "worker_timeout",
    "malformed_response",
    "model_hash_mismatch",
}
POLICY = {
    "schema_version": "icoder.clinical-model-shadow-stop-policy/v1",
    "minimum_vector_observations": MINIMUM_VECTOR_OBSERVATIONS,
    "maximum_error_count": 0,
    "maximum_mismatch_count": 0,
    "maximum_p95_ms": MAX_P95_MS,
    "patient_data_allowed": False,
    "network_allowed": False,
    "predictions_allowed": False,
}


class ClinicalModelShadowObservationError(RuntimeError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


SUITE_SHA256 = _sha256(_canonical_json({
    "suite_id": SUITE_ID,
    "run_count": RUN_COUNT,
    "policy": POLICY,
}))


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    report["observation_report_sha256"] = _sha256(_canonical_json(report))
    validate_shadow_observation(report)
    return report


def _base_report(*, artifact_sha256: str, source: str, fault_mode: str) -> dict[str, Any]:
    if len(artifact_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in artifact_sha256):
        raise ClinicalModelShadowObservationError("SHADOW_OBSERVATION_ARTIFACT_DIGEST_INVALID")
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "suite_id": SUITE_ID,
        "suite_sha256": SUITE_SHA256,
        "policy_sha256": _sha256(_canonical_json(POLICY)),
        "artifact_sha256": artifact_sha256,
        "source": source,
        "fault_mode": fault_mode,
        "patient_data_used": False,
        "raw_input_stored": False,
        "predictions_emitted": False,
        "network_used": False,
        "production_inference_enabled": False,
    }


def run_verified_shadow_suite(
    verified: VerifiedClinicalModelBundle,
    *,
    probe_runner: Callable[[VerifiedClinicalModelBundle], dict[str, Any]] = (
        probe_verified_synthetic_bundle
    ),
) -> dict[str, Any]:
    """Run the fixed suite repeatedly and retain only aggregate observations."""

    validate_verification_report(verified.report)
    latencies: list[int] = []
    vector_count = 0
    success_count = 0
    model_sha256: str | None = None
    for _ in range(RUN_COUNT):
        started = time.perf_counter()
        result = probe_runner(verified)
        elapsed = max(0, round((time.perf_counter() - started) * 1000))
        latencies.append(elapsed)
        if model_sha256 is None:
            model_sha256 = result["model_sha256"]
        elif model_sha256 != result["model_sha256"]:
            raise ClinicalModelShadowObservationError("SHADOW_OBSERVATION_MODEL_DRIFT")
        vector_count += result["test_vector_count"]
        success_count += result["test_vectors_passed"]
    report = _base_report(
        artifact_sha256=verified.report["bundle_content_sha256"],
        source="repository_synthetic",
        fault_mode="none",
    )
    report.update({
        "model_sha256": model_sha256,
        "run_count": RUN_COUNT,
        "vector_observation_count": vector_count,
        "success_count": success_count,
        "mismatch_count": 0,
        "error_count": 0,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "artifact_reverified": True,
    })
    report.update(evaluate_shadow_stop_policy(report))
    return _finalize(report)


def build_fault_observation(
    fault_mode: Literal[
        "worker_timeout", "malformed_response", "model_hash_mismatch"
    ],
    *,
    artifact_sha256: str,
    model_sha256: str,
) -> dict[str, Any]:
    """Build a controlled fault result without executing or accepting patient input."""

    if fault_mode not in FAULT_MODES:
        raise ClinicalModelShadowObservationError("SHADOW_OBSERVATION_FAULT_INVALID")
    report = _base_report(
        artifact_sha256=artifact_sha256,
        source="synthetic_fault_injection",
        fault_mode=fault_mode,
    )
    report.update({
        "model_sha256": model_sha256,
        "run_count": 1,
        "vector_observation_count": 2 if fault_mode == "model_hash_mismatch" else 0,
        "success_count": 0,
        "mismatch_count": 1 if fault_mode == "model_hash_mismatch" else 0,
        "error_count": 0 if fault_mode == "model_hash_mismatch" else 1,
        "latency_p50_ms": MAX_P95_MS + 1 if fault_mode == "worker_timeout" else 0,
        "latency_p95_ms": MAX_P95_MS + 1 if fault_mode == "worker_timeout" else 0,
        "artifact_reverified": False,
    })
    report.update(evaluate_shadow_stop_policy(report))
    return _finalize(report)


def evaluate_shadow_stop_policy(report: dict[str, Any]) -> dict[str, str]:
    reason = "passed"
    if report.get("patient_data_used") is not False:
        reason = "patient_data_policy_violation"
    elif report.get("network_used") is not False:
        reason = "network_policy_violation"
    elif report.get("predictions_emitted") is not False:
        reason = "prediction_emission_policy_violation"
    elif report.get("fault_mode") == "worker_timeout":
        reason = "worker_timeout"
    elif report.get("fault_mode") == "malformed_response":
        reason = "malformed_response"
    elif report.get("fault_mode") == "model_hash_mismatch":
        reason = "model_hash_mismatch"
    elif int(report.get("error_count", -1)) > POLICY["maximum_error_count"]:
        reason = "probe_error_threshold_exceeded"
    elif int(report.get("mismatch_count", -1)) > POLICY["maximum_mismatch_count"]:
        reason = "mismatch_threshold_exceeded"
    elif int(report.get("vector_observation_count", -1)) < MINIMUM_VECTOR_OBSERVATIONS:
        reason = "insufficient_observations"
    elif report.get("success_count") != report.get("vector_observation_count"):
        reason = "incomplete_success_count"
    elif int(report.get("latency_p95_ms", -1)) > MAX_P95_MS:
        reason = "latency_threshold_exceeded"
    return {
        "result": "passed" if reason == "passed" else "stopped",
        "reason_code": reason,
        "required_action": (
            "keep_shadow_only" if reason == "passed" else "stop_and_rollback"
        ),
    }


def validate_shadow_observation(report: dict[str, Any]) -> None:
    expected = {
        "artifact_reverified", "artifact_sha256", "error_count", "fault_mode",
        "latency_p50_ms", "latency_p95_ms", "mismatch_count", "model_sha256",
        "network_used", "observation_report_sha256", "patient_data_used",
        "policy_sha256", "predictions_emitted", "production_inference_enabled",
        "raw_input_stored", "reason_code", "required_action", "result", "run_count",
        "schema_version", "source", "success_count", "suite_id", "suite_sha256",
        "vector_observation_count",
    }
    if set(report) != expected:
        raise ClinicalModelShadowObservationError("SHADOW_OBSERVATION_REPORT_INVALID")
    unsigned = dict(report)
    digest = unsigned.pop("observation_report_sha256", None)
    integer_fields = {
        "run_count", "vector_observation_count", "success_count", "mismatch_count",
        "error_count", "latency_p50_ms", "latency_p95_ms",
    }
    digest_fields = {
        "artifact_sha256", "model_sha256", "observation_report_sha256",
        "policy_sha256", "suite_sha256",
    }
    source_and_fault_are_consistent = (
        (
            report.get("source") == "repository_synthetic"
            and report.get("fault_mode") == "none"
            and report.get("artifact_reverified") is True
        )
        or (
            report.get("source") == "synthetic_fault_injection"
            and report.get("fault_mode") in FAULT_MODES
            and report.get("artifact_reverified") is False
        )
    )
    if (
        report.get("schema_version") != OBSERVATION_SCHEMA
        or report.get("suite_id") != SUITE_ID
        or report.get("suite_sha256") != SUITE_SHA256
        or report.get("policy_sha256") != _sha256(_canonical_json(POLICY))
        or any(
            not isinstance(report.get(field), int)
            or isinstance(report.get(field), bool)
            or report[field] < 0
            for field in integer_fields
        )
        or report.get("source") not in {
            "repository_synthetic", "synthetic_fault_injection",
        }
        or report.get("fault_mode") not in FAULT_MODES | {"none"}
        or not source_and_fault_are_consistent
        or any(
            not isinstance(report.get(field), str)
            or len(report[field]) != 64
            or any(ch not in "0123456789abcdef" for ch in report[field])
            for field in digest_fields
        )
        or report.get("patient_data_used") is not False
        or report.get("raw_input_stored") is not False
        or report.get("predictions_emitted") is not False
        or report.get("network_used") is not False
        or report.get("production_inference_enabled") is not False
        or report.get("result") not in {"passed", "stopped"}
        or report.get("required_action")
        != ("keep_shadow_only" if report.get("result") == "passed" else "stop_and_rollback")
        or evaluate_shadow_stop_policy(report) != {
            "result": report.get("result"),
            "reason_code": report.get("reason_code"),
            "required_action": report.get("required_action"),
        }
        or not isinstance(digest, str)
        or digest != _sha256(_canonical_json(unsigned))
    ):
        raise ClinicalModelShadowObservationError("SHADOW_OBSERVATION_REPORT_INVALID")


__all__ = [
    "ClinicalModelShadowObservationError",
    "OBSERVATION_SCHEMA",
    "POLICY",
    "RUN_COUNT",
    "SUITE_ID",
    "SUITE_SHA256",
    "build_fault_observation",
    "evaluate_shadow_stop_policy",
    "run_verified_shadow_suite",
    "validate_shadow_observation",
]
