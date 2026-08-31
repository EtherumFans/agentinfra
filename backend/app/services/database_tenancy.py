"""Transaction-scoped PostgreSQL tenant authority.

Application filters remain useful for clear query intent, but PostgreSQL RLS
is the final boundary.  The tenant value is installed only after the auth
layer validates current membership or OAuth-client ownership.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


TENANT_SETTING = "icoder.current_organization_id"
_ORGANIZATION_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


async def bind_tenant_to_transaction(
    session: AsyncSession,
    organization_id: str,
) -> None:
    """Bind a verified organization to the current DB transaction.

    ``set_config(..., true)`` is transaction-local, so pooled connections do
    not leak tenant state to the next request. SQLite remains available only
    for local development and hermetic unit tests.
    """
    normalized = str(organization_id or "").strip()
    if not _ORGANIZATION_ID.fullmatch(normalized):
        raise ValueError("organization_id is empty or contains invalid characters")

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config(:setting_name, :tenant_id, true)"),
        {"setting_name": TENANT_SETTING, "tenant_id": normalized},
    )


__all__ = ["TENANT_SETTING", "bind_tenant_to_transaction"]
