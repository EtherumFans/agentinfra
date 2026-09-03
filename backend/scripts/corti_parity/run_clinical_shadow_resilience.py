"""Fault-injection and bounded-soak proof for the shadow control plane.

All mutations are confined to a newly-created temporary SQLite database.  No
model runtime, patient row, external network, or application database is used.
The child mode exists only so the parent can prove recovery after an abrupt
worker process exit.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make direct execution independent of the caller's current directory and
# PYTHONPATH.  Child fault-injection processes inherit the same deterministic
# import root.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.audit_log import AuditLog
from app.models.clinical_model_package import (
    ClinicalModelArtifactAttestation,
    ClinicalModelPackage,
    ClinicalModelShadowAlertState,
    ClinicalModelShadowBinding,
    ClinicalModelShadowDeadLetter,
    ClinicalModelShadowEvaluation,
    ClinicalModelShadowEvaluationJob,
    ClinicalModelShadowSchedulerLease,
)
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.clinical_model_shadow_job import (
    ClaimedShadowJob,
    cancel_shadow_job,
    claim_shadow_job,
    database_utc_now,
    fail_claimed_shadow_job,
    summarize_shadow_job_health,
)
from app.services.clinical_model_shadow_scheduler import (
    acquire_shadow_scheduler_lease,
    complete_shadow_scheduler_cycle,
    evaluate_persistent_shadow_alerts,
)


ORG_ID = "resilience01"
USER_ID = "00000000-0000-0000-0000-000000000001"
PACKAGE_ID = "00000000-0000-0000-0000-000000000002"
ATTESTATION_ID = "00000000-0000-0000-0000-000000000003"
BINDING_ID = "00000000-0000-0000-0000-000000000004"
USE_CASE = "clinical_coding_decision_support"


def _engine(database_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _configure(connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def _tables() -> list[Any]:
    return [
        Organization.__table__,
        User.__table__,
        ClinicalModelPackage.__table__,
        ClinicalModelArtifactAttestation.__table__,
        ClinicalModelShadowBinding.__table__,
        ClinicalModelShadowEvaluation.__table__,
        ClinicalModelShadowEvaluationJob.__table__,
        ClinicalModelShadowDeadLetter.__table__,
        ClinicalModelShadowAlertState.__table__,
        ClinicalModelShadowSchedulerLease.__table__,
        AuditLog.__table__,
    ]


async def _seed(session_factory: async_sessionmaker[AsyncSession], engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, tables=_tables(),
            )
        )
    digest = "a" * 64
    async with session_factory() as db:
        db.add(Organization(
            id=ORG_ID, name="Resilience evidence", slug="resilience-evidence",
            plan="enterprise", settings={}, is_active=True,
        ))
        db.add(User(
            id=USER_ID, username="resilience-owner",
            email="resilience@example.invalid", hashed_password="not-a-credential",
            full_name="Resilience Owner", role=UserRole.ADMIN,
            department="", is_active=True, is_verified=True,
        ))
        await db.commit()
        db.add(ClinicalModelPackage(
            id=PACKAGE_ID, organization_id=ORG_ID,
            package_key="cn.icoder.resilience.synthetic", package_version="1.0.0",
            package_sha256=digest, use_case=USE_CASE,
            model_kind="synthetic-shadow-fixture",
            runtime_contract="icoder.clinical-coding-shadow/v1",
            jurisdiction="CN", training_data_scope="aggregate_manifest_only",
            training_dataset_sha256="b" * 64, training_case_count=2,
            evaluation_evidence_sha256="c" * 64, license_status="verified",
            redistribution_authorized=False, cloud_use_authorized=False,
            hospital_use_authorized=False, independent_gold_validated=True,
            independent_reviewer_approved=True, status="approved",
            record_version=1, created_by_user_id=USER_ID,
        ))
        await db.commit()
        db.add(ClinicalModelArtifactAttestation(
            id=ATTESTATION_ID, organization_id=ORG_ID, package_id=PACKAGE_ID,
            bundle_content_sha256="d" * 64, manifest_sha256="e" * 64,
            verification_report_sha256="f" * 64,
            trust_key_id="resilience-development-key",
            trust_store_sha256="1" * 64, sbom_sha256="2" * 64,
            model_sha256=digest, artifact_class="development_synthetic",
            model_format="icoder.synthetic-json/v1",
            runtime_contract="icoder.clinical-coding-shadow/v1",
            verifier_version="1.0.0",
            content_scan_status="clean_development_scanner",
            probe_status="passed", test_vector_count=2,
            verified_by_user_id=USER_ID,
        ))
        await db.commit()
        db.add(ClinicalModelShadowBinding(
            id=BINDING_ID, organization_id=ORG_ID, use_case=USE_CASE,
            package_id=PACKAGE_ID, attestation_id=ATTESTATION_ID,
            mode="shadow_only", record_version=1,
            bound_by_user_id=USER_ID, evaluation_gate_status="not_evaluated",
        ))
        await db.commit()


async def _enqueue(
    session_factory: async_sessionmaker[AsyncSession], label: str,
) -> str:
    async with session_factory() as db:
        current = await database_utc_now(db)
        job_id = str(uuid.uuid4())
        db.add(ClinicalModelShadowEvaluationJob(
            id=job_id, organization_id=ORG_ID, binding_id=BINDING_ID,
            active_binding_id=BINDING_ID, use_case=USE_CASE,
            package_id=PACKAGE_ID, attestation_id=ATTESTATION_ID,
            binding_record_version=1, idempotency_key=f"resilience-{label}-{job_id}",
            request_sha256=hashlib.sha256(label.encode("utf-8")).hexdigest(),
            fault_mode="none", status="queued", attempt_count=0,
            max_attempts=3, next_attempt_at=current,
            created_by_user_id=USER_ID, created_at=current, updated_at=current,
        ))
        await db.commit()
        return job_id


def _claim_from_json(payload: dict[str, Any]) -> ClaimedShadowJob:
    payload = dict(payload)
    payload["lease_expires_at"] = datetime.fromisoformat(payload["lease_expires_at"])
    return ClaimedShadowJob(**payload)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_child_environment() -> dict[str, str]:
    forbidden = ("KEY", "TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")
    return {
        name: value for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in forbidden)
    }


async def _child_claim_and_crash(database_path: Path, job_id: str) -> None:
    engine = _engine(database_path)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as db:
            claim = await claim_shadow_job(
                db, job_id, "fault-worker-a", lease_seconds=5,
            )
            if claim is None:
                raise RuntimeError("FAULT_CHILD_CLAIM_FAILED")
            payload = asdict(claim)
            payload["lease_expires_at"] = claim.lease_expires_at.isoformat()
            print("ICODER_CRASH_CLAIM=" + json.dumps(payload, sort_keys=True), flush=True)
    finally:
        await engine.dispose()


async def _cancel(
    session_factory: async_sessionmaker[AsyncSession], job_id: str,
) -> None:
    async with session_factory() as db:
        outcome, _ = await cancel_shadow_job(
            db, organization_id=ORG_ID, job_id=job_id,
            cancelled_by_user_id=USER_ID,
            cancelled_by_username="resilience-owner",
            reason="maintenance",
        )
        if outcome != "cancelled":
            raise RuntimeError(f"FAULT_JOB_CANCEL_FAILED:{outcome}")


async def _parent(args: argparse.Namespace) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="icoder-shadow-resilience-") as temp_root:
        database_path = Path(temp_root) / "control-plane.sqlite3"
        engine = _engine(database_path)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await _seed(factory, engine)

        async with factory() as db:
            scheduler_a = await acquire_shadow_scheduler_lease(
                db, owner="fault-scheduler-a", lease_seconds=5,
            )
        if scheduler_a is None:
            raise RuntimeError("FAULT_SCHEDULER_INITIAL_CLAIM_FAILED")

        crash_job_id = await _enqueue(factory, "process-crash")
        command = [
            sys.executable, str(Path(__file__).resolve()), "--child-crash",
            "--database-path", str(database_path), "--job-id", crash_job_id,
        ]
        child = subprocess.run(
            command, cwd=str(Path(__file__).resolve().parents[2]),
            env=_safe_child_environment(), capture_output=True, text=True,
            timeout=60, check=False,
        )
        claim_line = next(
            (line for line in child.stdout.splitlines()
             if line.startswith("ICODER_CRASH_CLAIM=")),
            None,
        )
        if child.returncode != 91 or claim_line is None:
            raise RuntimeError(
                f"FAULT_CHILD_EXIT_UNEXPECTED:{child.returncode}:"
                f"{child.stderr[-500:]}"
            )
        stale_claim = _claim_from_json(json.loads(claim_line.split("=", 1)[1]))

        wait_seconds = max(5.2, float(args.lease_wait_seconds))
        await asyncio.sleep(wait_seconds)

        async with factory() as db:
            scheduler_b = await acquire_shadow_scheduler_lease(
                db, owner="fault-scheduler-b", lease_seconds=5,
            )
            if scheduler_b is None:
                raise RuntimeError("FAULT_SCHEDULER_RECOVERY_FAILED")
            alert_open = await evaluate_persistent_shadow_alerts(
                db, expired_lease_alert_count=1,
            )
            stale_scheduler_blocked = not await complete_shadow_scheduler_cycle(
                db, scheduler_a, succeeded=True,
            )
            scheduler_b_completed = await complete_shadow_scheduler_cycle(
                db, scheduler_b, succeeded=True,
            )

        async with factory() as db:
            recovered_claim = await claim_shadow_job(
                db, crash_job_id, "fault-worker-b", lease_seconds=30,
            )
        if recovered_claim is None or recovered_claim.attempt_count != 2:
            raise RuntimeError("FAULT_WORKER_RECOVERY_FAILED")
        async with factory() as db:
            stale_result = await fail_claimed_shadow_job(
                db, stale_claim, error_code="INTERNAL_WORKER_ERROR",
                retryable=False,
            )
        stale_worker_blocked = stale_result is None
        await _cancel(factory, crash_job_id)

        duplicate_job_id = await _enqueue(factory, "duplicate-delivery")

        async def contender(number: int):
            async with factory() as db:
                return await claim_shadow_job(
                    db, duplicate_job_id, f"duplicate-worker-{number}",
                    lease_seconds=30,
                )

        duplicate_results = await asyncio.gather(
            *(contender(index) for index in range(args.duplicate_deliveries))
        )
        duplicate_winners = [claim for claim in duplicate_results if claim is not None]
        if len(duplicate_winners) != 1:
            raise RuntimeError(f"FAULT_DUPLICATE_WINNERS:{len(duplicate_winners)}")
        await _cancel(factory, duplicate_job_id)

        lock_job_id = await _enqueue(factory, "database-lock")
        locker = sqlite3.connect(str(database_path), timeout=30, check_same_thread=False)
        locker.execute("PRAGMA busy_timeout=30000")
        locker.execute("BEGIN IMMEDIATE")
        release_timer = threading.Timer(0.5, locker.rollback)
        release_timer.start()
        lock_started = time.perf_counter()
        try:
            async with factory() as db:
                lock_claim = await claim_shadow_job(
                    db, lock_job_id, "database-recovery-worker", lease_seconds=30,
                )
        finally:
            release_timer.join(timeout=5)
            locker.close()
        database_recovery_seconds = time.perf_counter() - lock_started
        if lock_claim is None:
            raise RuntimeError("FAULT_DATABASE_LOCK_RECOVERY_FAILED")
        await _cancel(factory, lock_job_id)

        tracemalloc.start()
        soak_started = time.perf_counter()
        soak_latencies_ms: list[float] = []
        soak_cycles = 0
        while (
            soak_cycles < args.minimum_cycles
            or time.perf_counter() - soak_started < args.soak_seconds
        ):
            cycle_started = time.perf_counter()
            soak_job_id = await _enqueue(factory, f"soak-{soak_cycles}")
            async with factory() as db:
                soak_claim = await claim_shadow_job(
                    db, soak_job_id, "soak-worker", lease_seconds=30,
                )
            if soak_claim is None:
                raise RuntimeError(f"FAULT_SOAK_CLAIM_FAILED:{soak_cycles}")
            await _cancel(factory, soak_job_id)
            soak_latencies_ms.append((time.perf_counter() - cycle_started) * 1000)
            soak_cycles += 1
        current_allocated, peak_allocated = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        async with factory() as db:
            scheduler_c = await acquire_shadow_scheduler_lease(
                db, owner="fault-scheduler-c", lease_seconds=30,
            )
            if scheduler_c is None:
                raise RuntimeError("FAULT_SCHEDULER_FINAL_CLAIM_FAILED")
            alert_close = await evaluate_persistent_shadow_alerts(
                db, expired_lease_alert_count=1,
            )
            scheduler_c_completed = await complete_shadow_scheduler_cycle(
                db, scheduler_c, succeeded=True,
            )
            health = await summarize_shadow_job_health(db, organization_id=ORG_ID)
            alert_states = list((await db.scalars(
                select(ClinicalModelShadowAlertState)
            )).all())

        active_count = health["status_counts"]["queued"] + health["status_counts"]["running"]
        all_alerts_resolved = all(row.state == "resolved" for row in alert_states)
        passed = all([
            child.returncode == 91,
            recovered_claim.attempt_count == 2,
            stale_worker_blocked,
            stale_scheduler_blocked,
            scheduler_b_completed,
            scheduler_c_completed,
            alert_open["alerts_fired"] >= 1,
            alert_close["alerts_resolved"] >= 1,
            len(duplicate_winners) == 1,
            database_recovery_seconds >= 0.35,
            active_count == 0,
            health["status"] == "healthy",
            all_alerts_resolved,
        ])
        result = {
            "schema_version": "icoder.clinical-shadow-resilience/v1",
            "passed": passed,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "isolation": {
                "temporary_database": True,
                "temporary_database_removed": True,
                "application_database_used": False,
                "model_runtime_used": False,
                "network_used": False,
                "patient_data_used": False,
                "child_credential_environment_scrubbed": True,
            },
            "database_clock": {
                "lease_authority": "database",
                "application_host_clock_used": False,
            },
            "worker_process_crash": {
                "injected_exit_code": child.returncode,
                "lease_wait_seconds": round(wait_seconds, 3),
                "recovered_attempt_count": recovered_claim.attempt_count,
                "stale_fence_blocked": stale_worker_blocked,
            },
            "scheduler_crash": {
                "generation_before": scheduler_a.generation,
                "generation_after": scheduler_b.generation,
                "stale_fence_blocked": stale_scheduler_blocked,
                "recovery_cycle_completed": scheduler_b_completed,
                "final_cycle_completed": scheduler_c_completed,
            },
            "alert_recovery": {
                "fired_transitions": alert_open["alerts_fired"],
                "resolved_transitions": alert_close["alerts_resolved"],
                "all_states_resolved": all_alerts_resolved,
            },
            "duplicate_delivery": {
                "delivery_count": args.duplicate_deliveries,
                "claim_winner_count": len(duplicate_winners),
            },
            "transient_database_lock": {
                "lock_seconds": 0.5,
                "claim_recovered": lock_claim is not None,
                "recovery_seconds": round(database_recovery_seconds, 3),
            },
            "soak": {
                "requested_seconds": args.soak_seconds,
                "minimum_cycles": args.minimum_cycles,
                "completed_cycles": soak_cycles,
                "elapsed_seconds": round(time.perf_counter() - soak_started, 3),
                "latency_p50_ms": round(statistics.median(soak_latencies_ms), 3),
                "latency_p95_ms": round(
                    sorted(soak_latencies_ms)[max(0, int(len(soak_latencies_ms) * 0.95) - 1)],
                    3,
                ),
                "python_allocated_bytes": current_allocated,
                "python_peak_bytes": peak_allocated,
                "stuck_active_jobs": active_count,
                "final_health": health["status"],
            },
            "limitations": [
                "This proves control-plane recovery on the SQLite development backend.",
                "It does not replace multi-node PostgreSQL/Redis infrastructure chaos testing.",
                "The bounded soak duration is not a 24-hour production endurance result.",
            ],
        }
        source_root = Path(__file__).resolve().parents[2]
        result["source_sha256"] = {
            "resilience_runner": _sha256(Path(__file__).resolve()),
            "job_service": _sha256(
                source_root / "app/services/clinical_model_shadow_job.py"
            ),
            "scheduler_service": _sha256(
                source_root / "app/services/clinical_model_shadow_scheduler.py"
            ),
        }
        result["report_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
        await engine.dispose()
        return result


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child-crash", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--database-path", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--job-id", help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--soak-seconds", type=float, default=30.0)
    parser.add_argument("--minimum-cycles", type=int, default=100)
    parser.add_argument("--duplicate-deliveries", type=int, default=16)
    parser.add_argument("--lease-wait-seconds", type=float, default=5.2)
    args = parser.parse_args()
    if args.soak_seconds < 0 or not 1 <= args.minimum_cycles <= 100000:
        parser.error("invalid soak bounds")
    if not 2 <= args.duplicate_deliveries <= 128:
        parser.error("duplicate deliveries must be between 2 and 128")
    return args


def main() -> int:
    args = _arguments()
    if args.child_crash:
        if args.database_path is None or not args.job_id:
            raise SystemExit("child mode requires database path and job id")
        asyncio.run(_child_claim_and_crash(args.database_path, args.job_id))
        os._exit(91)
    result = asyncio.run(_parent(args))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
