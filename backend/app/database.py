# iCoDer Backend - Database Setup
import logging
import sqlite3
from datetime import datetime
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

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
    """Initialize database tables.

    Uses ``Base.metadata.create_all`` — idempotent, only creates tables
    that don't already exist. This is what dev, test, **and prod**
    actually use: ``app/main.py`` lifespan calls ``init_db()`` on every
    uvicorn startup, so the schema is rebuilt-from-missing on each boot.

    Alembic (``alembic upgrade head`` via ``python -m app.database
    migrate``) is a **dev/manual** tool for column-add migrations on an
    existing DB without wiping data. The chain 001→006 is kept in parity
    with ``Base.metadata`` (cycle 24 closed the 5-table gap). Don't run
    alembic in prod unless you've audited the chain against the current
    model state — see ``docs/dev/BACKEND_RECOVERY.md`` §Prevention.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
