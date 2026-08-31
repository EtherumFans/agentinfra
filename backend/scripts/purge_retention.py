"""Operator CLI for auditable, bounded retention purges.

Dry-run is the default. A destructive purge requires the explicit
``--execute`` flag and is still limited to rows selected by RetentionPolicy.
The command emits only aggregate counts and never prints run IDs or PHI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os


async def _run(*, execute: bool, organization_id: str | None) -> dict:
    # stdout is an operator/API boundary: keep it to one machine-readable JSON
    # document even when the surrounding development shell has DEBUG=true.
    os.environ["DEBUG"] = "false"
    from app.database import AsyncSessionLocal
    from app.services.retention import (
        RetentionPolicy,
        purge_expired_conversation_memory,
        purge_expired_run_trace_events,
    )

    policy = RetentionPolicy.from_env()
    async with AsyncSessionLocal() as db:
        counts = await purge_expired_run_trace_events(
            db,
            policy,
            dry_run=not execute,
            organization_id=organization_id,
        )
        memory_count = await purge_expired_conversation_memory(
            db,
            dry_run=not execute,
            organization_id=organization_id,
        )
    return {
        "schema_version": "icoder.retention-purge/v1",
        "scope": "run_trace_events_and_governed_memory",
        "mode": "execute" if execute else "dry_run",
        "retention_days": policy.run_trace_events_ttl_days,
        "organization_scoped": organization_id is not None,
        **counts,
        "conversation_memories": memory_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute the auditable RunTrace retention purge."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete eligible rows. Omit for a read-only dry run.",
    )
    parser.add_argument(
        "--organization-id",
        default=None,
        help="Optionally restrict the purge to one exact organization ID.",
    )
    args = parser.parse_args()
    organization_id = (args.organization_id or "").strip() or None
    report = asyncio.run(
        _run(execute=bool(args.execute), organization_id=organization_id)
    )
    print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
