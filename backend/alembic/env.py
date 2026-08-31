# Alembic environment configuration for iCoDer
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.database import Base

# Import all models so Base.metadata is populated.
# Cycle 24: app.models.__init__ now imports Organization too (previously
# only imported via API routers, so env.py's target_metadata was missing
# the 3 organization tables). The context_* db_models import was removed
# — those 5 tables are deprecated (dropped by migration 006) and should
# NOT be in target_metadata or autogenerate would propose re-creating them.
from app.models import *  # noqa: F401, F403
from app.models.runtime_persistence import (  # noqa: F401
    RuntimeSession, RuntimeTransition, RuntimeAuditRecord, DUCDecision,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url(url: str) -> str:
    """Use deterministic synchronous drivers for Alembic operations."""
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = _migration_url(settings.DATABASE_URL)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations with a synchronous, short-lived migration engine."""
    connectable = create_engine(
        _migration_url(settings.DATABASE_URL),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
