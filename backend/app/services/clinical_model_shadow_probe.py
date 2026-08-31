"""Bounded subprocess probe for an already verified synthetic bundle."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.services.clinical_model_bundle import VerifiedClinicalModelBundle


PROBE_SCHEMA = "icoder.synthetic-shadow-probe/v1"
WORKER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "clinical_model_shadow_probe_worker.py"
)


class ClinicalModelShadowProbeError(RuntimeError):
    pass


def probe_verified_synthetic_bundle(
    verified: VerifiedClinicalModelBundle,
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    report = verified.report
    if (
        report.get("signature_verified") is not True
        or report.get("artifact_class") != "development_synthetic"
        or report.get("model_format") != "icoder.synthetic-json/v1"
        or report.get("shadow_only") is not True
        or report.get("code_execution_allowed") is not False
        or report.get("network_allowed") is not False
        or report.get("patient_data_included") is not False
        or report.get("production_inference_approved") is not False
    ):
        raise ClinicalModelShadowProbeError("SHADOW_PROBE_POLICY_DENIED")
    if not 1.0 <= timeout_seconds <= 30.0:
        raise ClinicalModelShadowProbeError("SHADOW_PROBE_TIMEOUT_INVALID")
    safe_env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    safe_env["PYTHONHASHSEED"] = "0"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.TemporaryDirectory(prefix="icoder-shadow-probe-") as directory:
        model_path = Path(directory) / "verified-model.json"
        model_path.write_bytes(verified.entrypoint_bytes)
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-S", str(WORKER_PATH), str(model_path)],
                cwd=directory,
                env=safe_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ClinicalModelShadowProbeError("SHADOW_PROBE_PROCESS_FAILED") from exc
    if completed.returncode != 0 or len(completed.stdout) > 16_384:
        raise ClinicalModelShadowProbeError("SHADOW_PROBE_VALIDATION_FAILED")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClinicalModelShadowProbeError("SHADOW_PROBE_RESPONSE_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != PROBE_SCHEMA
        or payload.get("passed") is not True
        or payload.get("network_used") is not False
        or payload.get("patient_data_used") is not False
        or payload.get("predictions_emitted") is not False
        or payload.get("model_sha256") != hashlib.sha256(verified.entrypoint_bytes).hexdigest()
        or payload.get("test_vector_count") != payload.get("test_vectors_passed")
    ):
        raise ClinicalModelShadowProbeError("SHADOW_PROBE_RESPONSE_INVALID")
    return payload


__all__ = ["ClinicalModelShadowProbeError", "probe_verified_synthetic_bundle"]
