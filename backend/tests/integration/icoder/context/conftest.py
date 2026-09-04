"""Cross-dialect fixtures for Context repository integration contracts."""

from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy import delete, event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.icoder.agent_runtime.context.db_models import (
    ContextRow,
    OriginalInputAuditRow,
)


CONTEXT_TEST_ORG = "test-org"


def _uses_postgresql() -> bool:
    return os.environ.get("ICODER_DATABASE_URL", "").startswith("postgresql")


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Use Alembic PostgreSQL in the compatibility gate, SQLite otherwise.

    PostgreSQL RLS authority is transaction-local. Repository operations
    commit independently, so the listener rebinds the verified test tenant on
    every new transaction instead of relying on a one-time SET.
    """
    if _uses_postgresql():
        import app.database as database

        async with database.AsyncSessionLocal() as db_session:
            @event.listens_for(db_session.sync_session, "after_begin")
            def _bind_test_tenant(_session, _transaction, connection) -> None:
                connection.execute(
                    text(
                        "SELECT set_config("
                        "'icoder.current_organization_id', :tenant_id, true)"
                    ),
                    {"tenant_id": CONTEXT_TEST_ORG},
                )

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
                event.remove(
                    db_session.sync_session, "after_begin", _bind_test_tenant
                )
        return

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(ContextRow.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()
