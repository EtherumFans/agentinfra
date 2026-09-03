"""One-time, passwordless platform-administrator bootstrap.

The public registration API only creates ``coder`` users. A new deployment
therefore needs an explicit operator action to establish the first platform
administrator. This command is dry-run by default, refuses to run once any
active platform admin exists, revokes the selected user's sessions, and emits
a MODERN_SYSTEM audit event.

Usage from ``backend/``::

    python scripts/bootstrap_platform_admin.py --identifier ops@example.cn \
        --ticket-id IAM-0001
    python scripts/bootstrap_platform_admin.py --identifier ops@example.cn \
        --ticket-id IAM-0001 --execute
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.system_audit import system_audit  # noqa: E402

_TICKET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


async def bootstrap_platform_admin(
    db: AsyncSession,
    *,
    identifier: str,
    ticket_id: str,
    execute: bool,
) -> dict:
    identifier = identifier.strip()
    if not identifier:
        raise ValueError("identifier is required")
    if not _TICKET_RE.fullmatch(ticket_id):
        raise ValueError("ticket_id must be 1-64 safe identifier characters")

    active_admins = (
        await db.execute(
            select(func.count()).select_from(User).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
    ).scalar_one()
    if active_admins:
        raise RuntimeError("bootstrap refused: an active platform administrator already exists")

    target = (
        await db.execute(
            select(User).where(
                or_(User.username == identifier, User.email == identifier)
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise RuntimeError("bootstrap target user not found")
    if not target.is_active:
        raise RuntimeError("bootstrap target user is inactive")

    result = {
        "mode": "execute" if execute else "dry_run",
        "user_id": target.id,
        "username": target.username,
        "old_role": target.role.value,
        "new_role": UserRole.ADMIN.value,
        "ticket_id": ticket_id,
        "token_version_before": target.token_version,
        "token_version_after": target.token_version + (1 if execute else 0),
    }
    if not execute:
        return result

    target.role = UserRole.ADMIN
    target.token_version += 1
    await system_audit(
        db,
        action="platform_admin.user_access_updated",
        resource_type="user",
        resource_id=target.id,
        details={
            "target_user_id": target.id,
            "old_role": result["old_role"],
            "new_role": UserRole.ADMIN.value,
            "old_active": True,
            "new_active": True,
            "reason_code": "initial_bootstrap",
            "ticket_id": ticket_id,
            "tokens_revoked": 1,
            "clients_disabled": 0,
        },
        username="bootstrap-cli",
    )
    await db.commit()
    return result


async def _main(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        result = await bootstrap_platform_admin(
            db,
            identifier=args.identifier,
            ticket_id=args.ticket_id,
            execute=args.execute,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identifier", required=True, help="Exact username or email of an existing active user")
    parser.add_argument("--ticket-id", required=True, help="Approved IAM/change ticket identifier")
    parser.add_argument("--execute", action="store_true", help="Apply the bootstrap; default is dry-run")
    args = parser.parse_args()
    try:
        return asyncio.run(_main(args))
    except (RuntimeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
