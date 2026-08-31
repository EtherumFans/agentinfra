"""Dry-run-by-default operator CLI for bounded Agentic feedback retention."""

from __future__ import annotations

import argparse
import asyncio
import json
import os


async def _run(*, execute: bool, organization_id: str | None) -> dict:
    os.environ["DEBUG"] = "false"
    from app.database import AsyncSessionLocal
    from app.services.retention import purge_expired_agent_feedback

    async with AsyncSessionLocal() as db:
        count = await purge_expired_agent_feedback(
            db, dry_run=not execute, organization_id=organization_id,
        )
    return {
        "schema_version": "icoder.retention-purge/v1",
        "scope": "agent_task_feedback",
        "mode": "execute" if execute else "dry_run",
        "organization_scoped": organization_id is not None,
        "rows": count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute the Agentic Task-feedback retention purge."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--organization-id", default=None)
    args = parser.parse_args()
    organization_id = (args.organization_id or "").strip() or None
    print(json.dumps(asyncio.run(_run(
        execute=bool(args.execute), organization_id=organization_id,
    )), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
