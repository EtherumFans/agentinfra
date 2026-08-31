"""Bounded worker for repository-fixture clinical shadow evaluation jobs.

The worker is deliberately disabled outside local/test/development environments
and requires the explicit simulation switch. Its JSON output contains aggregate
outcome counts only: no job, tenant, lease, artifact or patient identifiers.
"""
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


async def _run(
    *,
    execute: bool,
    watch: bool,
    max_jobs: int,
    lease_seconds: int,
    poll_seconds: float,
    worker_id: str,
) -> dict[str, object]:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.services.clinical_model_shadow_job import (
        claim_next_shadow_job,
        execute_claimed_repository_shadow_job,
        finalize_exhausted_shadow_jobs,
    )
    from app.services.clinical_model_shadow_queue import build_shadow_queue_adapter

    if settings.APP_ENV.lower() not in {"local", "test", "development", "dev"}:
        raise RuntimeError("SHADOW_JOB_WORKER_DEVELOPMENT_ONLY")
    if execute and not settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED:
        raise RuntimeError("SHADOW_JOB_SIMULATION_DISABLED")

    bounded_max = max(1, min(int(max_jobs), 1000))
    bounded_poll = max(0.1, min(float(poll_seconds), 60.0))
    outcomes: dict[str, int] = {}
    claimed = 0
    empty_polls = 0
    finalized_exhausted = 0
    queue_adapter = build_shadow_queue_adapter(
        backend=settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_BACKEND,
        redis_url=settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_REDIS_URL,
        allow_insecure_redis=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_ALLOW_INSECURE_REDIS
        ),
    )

    if not execute:
        return {
            "schema_version": "icoder.clinical-shadow-job-worker/v1",
            "mode": "dry_run",
            "max_jobs": bounded_max,
            "repository_fixture_only": True,
            "aggregate_only": True,
            "patient_data_used": False,
            "network_used": False,
            "durable_queue_authority": "database",
            "notification_backend": queue_adapter.name,
        }

    async with AsyncSessionLocal() as db:
        finalized_exhausted = await finalize_exhausted_shadow_jobs(db, limit=1000)

    try:
        while claimed < bounded_max:
            async with AsyncSessionLocal() as db:
                claim = await claim_next_shadow_job(
                    db,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
            if claim is None:
                empty_polls += 1
                if not watch:
                    break
                await queue_adapter.wait(bounded_poll)
                continue
            claimed += 1
            outcome = await execute_claimed_repository_shadow_job(claim)
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
    finally:
        await queue_adapter.close()

    return {
        "schema_version": "icoder.clinical-shadow-job-worker/v1",
        "mode": "execute",
        "claimed": claimed,
        "empty_polls": empty_polls,
        "outcomes": outcomes,
        "finalized_exhausted_count": finalized_exhausted,
        "repository_fixture_only": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "network_used": False,
        "durable_queue_authority": "database",
        "notification_backend": queue_adapter.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process bounded, aggregate-only clinical shadow jobs.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=1)
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--worker-id")
    args = parser.parse_args()
    if args.watch and not args.execute:
        parser.error("--watch requires --execute")
    worker_id = args.worker_id or (
        f"shadow-{socket.gethostname()[:20]}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    result = asyncio.run(
        _run(
            execute=bool(args.execute),
            watch=bool(args.watch),
            max_jobs=args.max_jobs,
            lease_seconds=args.lease_seconds,
            poll_seconds=args.poll_seconds,
            worker_id=worker_id,
        )
    )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
