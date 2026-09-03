"""Create and finish a synthetic long-running Run for local SDK E2E.

This script is intentionally limited to development test orchestration. It
uses the configured temporary database and never invokes an LLM or handles
clinical input.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from app.config import settings
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceEvent,
    get_default_store,
    to_sync_database_url,
)
from app.models.run_history import RunHistoryModel
from app.models.run_trace import RunTraceEventModel
from app.services.database_tenancy import bind_tenant_to_sync_session
from app.services.trace_token import DEFAULT_TTL_SECONDS, issue_trace_token


def _sync_database_url() -> str:
    return to_sync_database_url(settings.DATABASE_URL)


def _append(run_id: str, organization_id: str, step: str) -> None:
    get_default_store().append(RunTraceEvent(
        run_id=run_id,
        step=step,
        status="ok",
        ts=time.time(),
        duration_ms=5.0,
        safe_metadata={
            "agent_id": "note-completeness-agent",
            "stage": "sdk_sse_e2e",
            "_organization_id": organization_id,
        },
    ))


def seed(run_id: str, organization_id: str, *, expired: bool = False) -> None:
    engine = create_engine(_sync_database_url())
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            bind_tenant_to_sync_session(db, organization_id)
            db.execute(delete(RunTraceEventModel).where(
                RunTraceEventModel.run_id == run_id
            ))
            db.execute(delete(RunHistoryModel).where(
                RunHistoryModel.run_id == run_id
            ))
            db.add(RunHistoryModel(
                run_id=run_id,
                agent_id="note-completeness-agent",
                organization_id=organization_id,
                user_id="sdk-sse-e2e",
                tenancy_classification="MODERN",
                status="RUNNING",
                input_text="Synthetic SDK SSE contract only.",
                output_summary="",
                error=False,
                created_at=now,
                updated_at=now,
            ))
            db.commit()
        _append(run_id, organization_id, "ingest")
        print(json.dumps({
            "run_id": run_id,
            "trace_token": issue_trace_token(
                run_id=run_id,
                organization_id=organization_id,
                ttl_seconds=-1 if expired else DEFAULT_TTL_SECONDS,
            ),
        }))
    finally:
        engine.dispose()


def finish(run_id: str, organization_id: str, delay_seconds: float) -> None:
    time.sleep(delay_seconds)
    _append(run_id, organization_id, "completion")
    engine = create_engine(_sync_database_url())
    try:
        with Session(engine) as db:
            bind_tenant_to_sync_session(db, organization_id)
            db.execute(
                update(RunHistoryModel)
                .where(RunHistoryModel.run_id == run_id)
                .values(status="COMPLETED", updated_at=datetime.now(UTC))
            )
            db.commit()
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    finish_parser = subparsers.add_parser("finish")
    for child in (seed_parser, finish_parser):
        child.add_argument("--run-id", required=True)
        child.add_argument("--organization-id", required=True)
    finish_parser.add_argument("--delay-seconds", type=float, default=0.75)
    seed_parser.add_argument("--expired", action="store_true")
    args = parser.parse_args()

    if args.command == "seed":
        seed(args.run_id, args.organization_id, expired=args.expired)
    else:
        finish(args.run_id, args.organization_id, args.delay_seconds)


if __name__ == "__main__":
    main()
