"""Isolated SQLite / Alembic PostgreSQL fixtures for promoted contracts."""

from contextlib import asynccontextmanager
import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@asynccontextmanager
async def compatibility_engine():
    if os.environ.get("ICODER_DATABASE_URL", "").startswith("postgresql"):
        import app.database as database

        assert os.environ.get("ICODER_TEST_USE_PREMIGRATED_SCHEMA") == "1", (
            "PostgreSQL compatibility tests require an Alembic-built test database"
        )
        yield database.engine
        return

    from app.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def tenant_session(engine, tenant_id):
    """Rebind the fixture tenant on every transaction, including after commits.

    This models a verified request's database scope, not authentication itself.
    Separate sessions are required when testing a different tenant.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        def _bind_tenant(_session, _transaction, connection):
            connection.execute(
                text("SELECT set_config('icoder.current_organization_id', :tenant, true)"),
                {"tenant": tenant_id or ""},
            )

        is_postgresql = engine.dialect.name == "postgresql"
        if is_postgresql:
            event.listen(session.sync_session, "after_begin", _bind_tenant)
        try:
            yield session
        finally:
            await session.rollback()
            if is_postgresql:
                event.remove(session.sync_session, "after_begin", _bind_tenant)
