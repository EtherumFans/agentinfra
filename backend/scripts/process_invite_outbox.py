"""Operator CLI for the encrypted invitation-delivery outbox.

The default is a read-only summary. ``--execute`` explicitly claims and
delivers a bounded batch. Output contains aggregate counts only and never
prints recipients, invite credentials, webhook credentials, or row IDs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os


async def _run(*, execute: bool, limit: int) -> dict:
    os.environ["DEBUG"] = "false"
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationInviteDelivery
    from app.services.invite_delivery import (
        claim_due_deliveries,
        process_delivery_claim,
        validate_webhook_configuration,
    )

    validate_webhook_configuration()
    bounded_limit = max(1, min(int(limit), 100))
    if not execute:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(
                        OrganizationInviteDelivery.status,
                        func.count(OrganizationInviteDelivery.id),
                    ).group_by(OrganizationInviteDelivery.status)
                )
            ).all()
        return {
            "schema_version": "icoder.invite-outbox-processor/v1",
            "mode": "dry_run",
            "limit": bounded_limit,
            "status_counts": {str(status): int(count) for status, count in rows},
        }

    async with AsyncSessionLocal() as db:
        claims = await claim_due_deliveries(db, limit=bounded_limit)
    outcomes: dict[str, int] = {}
    for claim in claims:
        async with AsyncSessionLocal() as db:
            outcome = await process_delivery_claim(db, claim)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {
        "schema_version": "icoder.invite-outbox-processor/v1",
        "mode": "execute",
        "limit": bounded_limit,
        "claimed": len(claims),
        "outcomes": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or process the encrypted invitation-delivery outbox."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Deliver a bounded batch. Omit for a read-only summary.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Batch size, 1-100.")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(_run(execute=bool(args.execute), limit=args.limit)),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
