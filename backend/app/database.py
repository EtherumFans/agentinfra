# iCoDer Backend - Database Setup
import logging
import sqlite3
from datetime import datetime
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

# Production schema changes are applied exclusively through Alembic.  Keeping
# the expected revision explicit makes an application image fail closed when
# it is started before (or against a database behind) its migration job.
PRODUCTION_SCHEMA_REVISION = "064"
TENANT_POLICY_NAME = "icoder_tenant_isolation"
PROTECTED_TENANT_TABLES = (
    "patient_contexts",
    "run_trace_events",
    "run_history",
    "transactions",
    "contexts",
    "memory_consents",
    "conversation_memories",
)

_is_sqlite = "sqlite" in settings.DATABASE_URL

# SQL echo used to follow the broad DEBUG switch.  In local Compose this wrote
# bound parameters, including complete clinical notes, to stdout.  Statement
# logging is now an explicit local diagnostic switch and parameters remain
# hidden even when another logger enables sqlalchemy.engine at INFO level.
_engine_kwargs: dict = {
    "echo": settings.ICODER_DATABASE_SQL_ECHO,
    "hide_parameters": True,
}
if _is_sqlite:
    # Python 3.12 deprecated sqlite3's implicit datetime adapter. Register an
    # explicit ISO-8601 adapter for local/test SQLite so timestamp persistence
    # remains deterministic across Python upgrades. SQLAlchemy continues to
    # own result conversion for its DateTime columns.
    sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
    # Local development and offline E2E can issue several Agent runs at once.
    # SQLite's default rollback journal + 5s busy timeout turns ordinary
    # concurrent run_history/audit writes into ``database is locked`` errors.
    # WAL permits readers alongside the single writer, while the longer busy
    # timeout lets short write transactions serialize instead of failing.
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30,
    }
else:
    _engine_kwargs["pool_size"] = 20
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["pool_recycle"] = 3600
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

if _is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

logger.info(f"Database: {'SQLite' if _is_sqlite else 'PostgreSQL'}")
if not _is_sqlite:
    logger.info(f"Connection pool: size=20, overflow=10, recycle=3600s")


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Export as factory for background tasks that need their own sessions
async_session_factory = AsyncSessionLocal


async def init_db():
    """Initialize local/test tables from ORM metadata.

    Cloud startup never calls this function. Production schema ownership is
    Alembic-only and is verified by :func:`verify_production_database`.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def verify_production_database() -> None:
    """Verify that cloud runtime is attached to the governed PostgreSQL schema.

    The application role must not be a PostgreSQL superuser or carry
    ``BYPASSRLS``; either capability would silently defeat FORCE RLS.  Every
    protected table must have RLS enabled and forced before the API accepts
    traffic.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError("cloud runtime requires PostgreSQL as authoritative storage")

    async with engine.connect() as connection:
        revision = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
        if revision != PRODUCTION_SCHEMA_REVISION:
            raise RuntimeError(
                "database schema is not at the production revision: "
                f"expected {PRODUCTION_SCHEMA_REVISION}, found {revision!r}"
            )

        role = (
            await connection.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one_or_none()
        if role is None or bool(role.rolsuper) or bool(role.rolbypassrls):
            raise RuntimeError(
                "application database role must exist and must not have "
                "SUPERUSER or BYPASSRLS"
            )

        rows = await connection.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "a.attnotnull "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "AND a.attname = 'organization_id' AND NOT a.attisdropped "
                "WHERE n.nspname = current_schema() "
                "AND c.relname = ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(PROTECTED_TENANT_TABLES)},
        )
        state = {
            row.relname: (
                bool(row.relrowsecurity),
                bool(row.relforcerowsecurity),
                bool(row.attnotnull),
            )
            for row in rows
        }
        invalid = [
            table for table in PROTECTED_TENANT_TABLES
            if state.get(table) != (True, True, True)
        ]
        if invalid:
            raise RuntimeError(
                "tenant RLS/NOT NULL enforcement is incomplete for: "
                + ", ".join(invalid)
            )

        policy_rows = await connection.execute(
            text(
                "SELECT tablename FROM pg_policies "
                "WHERE schemaname = current_schema() "
                "AND policyname = :policy_name AND cmd = 'ALL' "
                "AND qual IS NOT NULL AND with_check IS NOT NULL"
            ),
            {"policy_name": TENANT_POLICY_NAME},
        )
        policy_tables = set(policy_rows.scalars())
        missing_policies = sorted(set(PROTECTED_TENANT_TABLES) - policy_tables)
        if missing_policies:
            raise RuntimeError(
                "tenant RLS policy is missing or incomplete for: "
                + ", ".join(missing_policies)
            )



def run_migrations():
    """Run Alembic migrations from the command line.

    Usage: python -m app.database migrate
    """
    from alembic.config import Config
    from alembic import command
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        run_migrations()
