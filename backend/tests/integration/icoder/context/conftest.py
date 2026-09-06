"""Cross-dialect fixtures for Context repository integration contracts."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fixtures.database_compat import compatibility_engine, tenant_session

from app.icoder.agent_runtime.context.db_models import (
    ContextRow,
    OriginalInputAuditRow,
)


CONTEXT_TEST_ORG = "test-org"


@pytest_asyncio.fixture
async def engine():
    async with compatibility_engine() as test_engine:
        yield test_engine


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    """Use Alembic PostgreSQL in the compatibility gate, SQLite otherwise.

    PostgreSQL RLS authority is transaction-local. Repository operations
    commit independently, so the listener rebinds the verified test tenant on
    every new transaction instead of relying on a one-time SET.
    """
    async with tenant_session(engine, CONTEXT_TEST_ORG) as db_session:
        try:
            yield db_session
        finally:
            await db_session.rollback()
            await db_session.execute(
                delete(OriginalInputAuditRow).where(
                    OriginalInputAuditRow.organization_id == CONTEXT_TEST_ORG
                )
            )
            await db_session.execute(
                delete(ContextRow).where(
                    ContextRow.organization_id == CONTEXT_TEST_ORG
                )
            )
            await db_session.commit()
