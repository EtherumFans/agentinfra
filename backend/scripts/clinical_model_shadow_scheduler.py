"""Fenced scheduler for aggregate-only clinical shadow maintenance."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import uuid
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


async def _cycle(owner: str) -> dict[str, int | bool | str]:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.services.clinical_model_shadow_job import finalize_exhausted_shadow_jobs
    from app.services.clinical_model_shadow_scheduler import (
        acquire_shadow_scheduler_lease,
        complete_shadow_scheduler_cycle,
        evaluate_persistent_shadow_alerts,
    )

    async with AsyncSessionLocal() as db:
        lease = await acquire_shadow_scheduler_lease(
            db,
            owner=owner,
            lease_seconds=settings.ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_LEASE_SECONDS,
        )
    if lease is None:
        return {
            "lease_acquired": False,
            "finalized_exhausted_count": 0,
            "organizations_evaluated": 0,
            "alerts_fired": 0,
            "alerts_resolved": 0,
        }
    succeeded = False
    try:
        async with AsyncSessionLocal() as db:
            finalized = await finalize_exhausted_shadow_jobs(db, limit=1000)
        async with AsyncSessionLocal() as db:
            transitions = await evaluate_persistent_shadow_alerts(
                db,
                queue_alert_count=settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_QUEUE_ALERT_COUNT,
                max_queue_age_seconds=(
                    settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_MAX_QUEUE_AGE_SECONDS
                ),
                expired_lease_alert_count=(
                    settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_EXPIRED_LEASE_ALERT_COUNT
                ),
                dead_letter_alert_count=(
                    settings.ICODER_CLINICAL_MODEL_SHADOW_DEAD_LETTER_ALERT_COUNT
                ),
            )
        succeeded = True
        return {
            "lease_acquired": True,
            "finalized_exhausted_count": finalized,
            "organizations_evaluated": transitions["organizations_evaluated"],
            "alerts_fired": transitions["alerts_fired"],
            "alerts_resolved": transitions["alerts_resolved"],
        }
    finally:
        async with AsyncSessionLocal() as db:
            await complete_shadow_scheduler_cycle(
                db, lease, succeeded=succeeded,
            )


async def _run(*, execute: bool, watch: bool, max_cycles: int, owner: str) -> dict:
    from app.config import settings

    bounded_cycles = max(0, min(int(max_cycles), 100000))
    if not execute:
        return {
            "schema_version": "icoder.clinical-shadow-scheduler/v1",
            "mode": "dry_run",
            "scheduler_enabled": settings.ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_ENABLED,
            "aggregate_only": True,
            "patient_data_used": False,
            "identifiers_emitted": False,
        }
    if not settings.ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_ENABLED:
        raise RuntimeError("SHADOW_SCHEDULER_DISABLED")
    interval = max(
        0.25,
        min(float(settings.ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_INTERVAL_SECONDS), 300.0),
    )
    totals = {
        "cycles": 0,
        "lease_contended_cycles": 0,
        "finalized_exhausted_count": 0,
        "organizations_evaluated": 0,
        "alerts_fired": 0,
        "alerts_resolved": 0,
    }
    while bounded_cycles == 0 or totals["cycles"] < bounded_cycles:
        result = await _cycle(owner)
        totals["cycles"] += 1
        if not result["lease_acquired"]:
            totals["lease_contended_cycles"] += 1
        for key in (
            "finalized_exhausted_count", "organizations_evaluated",
            "alerts_fired", "alerts_resolved",
        ):
            totals[key] += int(result[key])
        if not watch:
            break
        await asyncio.sleep(interval)
    return {
        "schema_version": "icoder.clinical-shadow-scheduler/v1",
        "mode": "execute",
        **totals,
        "aggregate_only": True,
        "patient_data_used": False,
        "identifiers_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fenced shadow maintenance cycles.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--owner")
    args = parser.parse_args()
    if args.watch and not args.execute:
        parser.error("--watch requires --execute")
    owner = args.owner or (
        f"scheduler-{socket.gethostname()[:18]}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    result = asyncio.run(_run(
        execute=bool(args.execute),
        watch=bool(args.watch),
        max_cycles=args.max_cycles,
        owner=owner,
    ))
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
