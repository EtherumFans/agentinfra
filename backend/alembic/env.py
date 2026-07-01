# Alembic environment configuration for iCoDer
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

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


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
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


async def run_migrations_online():
    """Run migrations in 'online' mode (async)."""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
