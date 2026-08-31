"""Validate a tamper-evident shadow-control-plane resilience report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    "resilience_runner": ROOT / "backend/scripts/corti_parity/run_clinical_shadow_resilience.py",
    "job_service": ROOT / "backend/app/services/clinical_model_shadow_job.py",
    "scheduler_service": ROOT / "backend/app/services/clinical_model_shadow_scheduler.py",
}
SECRET = re.compile(r"(?i)(?:sk-[a-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*[^\s\"']+)")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate(
    report: dict[str, object], *, minimum_cycles: int, minimum_seconds: float,
) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    if digest != _sha(_canonical(unsigned)):
        raise RuntimeError("SHADOW_RESILIENCE_REPORT_DIGEST_INVALID")
    expected_sources = {name: _sha(path.read_bytes()) for name, path in SOURCES.items()}
    if report.get("source_sha256") != expected_sources:
        raise RuntimeError("SHADOW_RESILIENCE_SOURCE_DIGEST_INVALID")
    isolation = report.get("isolation", {})
    worker = report.get("worker_process_crash", {})
    scheduler = report.get("scheduler_crash", {})
    alerts = report.get("alert_recovery", {})
    duplicate = report.get("duplicate_delivery", {})
    database_lock = report.get("transient_database_lock", {})
    soak = report.get("soak", {})
    clock = report.get("database_clock", {})
    if not isinstance(isolation, dict) or not isinstance(worker, dict):
        raise RuntimeError("SHADOW_RESILIENCE_REPORT_SHAPE_INVALID")
    checks = (
        report.get("schema_version") == "icoder.clinical-shadow-resilience/v1",
        report.get("passed") is True,
        isolation.get("temporary_database") is True,
        isolation.get("temporary_database_removed") is True,
        isolation.get("application_database_used") is False,
        isolation.get("model_runtime_used") is False,
        isolation.get("network_used") is False,
        isolation.get("patient_data_used") is False,
        isolation.get("child_credential_environment_scrubbed") is True,
        clock.get("lease_authority") == "database",
        clock.get("application_host_clock_used") is False,
        worker.get("injected_exit_code") == 91,
        worker.get("recovered_attempt_count") == 2,
        worker.get("stale_fence_blocked") is True,
        scheduler.get("generation_after", 0) > scheduler.get("generation_before", 0),
        scheduler.get("stale_fence_blocked") is True,
        scheduler.get("recovery_cycle_completed") is True,
        scheduler.get("final_cycle_completed") is True,
        alerts.get("fired_transitions", 0) >= 1,
        alerts.get("resolved_transitions", 0) >= 1,
        alerts.get("all_states_resolved") is True,
        duplicate.get("delivery_count", 0) >= 2,
        duplicate.get("claim_winner_count") == 1,
        database_lock.get("claim_recovered") is True,
        soak.get("completed_cycles", 0) >= minimum_cycles,
        soak.get("elapsed_seconds", 0) >= minimum_seconds,
        soak.get("stuck_active_jobs") == 0,
        soak.get("final_health") == "healthy",
    )
    if not all(checks):
        raise RuntimeError("SHADOW_RESILIENCE_EVIDENCE_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-cycles", type=int, default=100)
    parser.add_argument("--minimum-seconds", type=float, default=30.0)
    args = parser.parse_args()
    payload = args.report.resolve().read_bytes()
    if SECRET.search(payload.decode("utf-8", errors="replace")):
        raise RuntimeError("SHADOW_RESILIENCE_CREDENTIAL_LEAK")
    report = json.loads(payload)
    validate(
        report, minimum_cycles=args.minimum_cycles,
        minimum_seconds=args.minimum_seconds,
    )
    print("Clinical shadow resilience evidence validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
