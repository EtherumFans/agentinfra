"""Live PostgreSQL proof for the cloud startup database release gate."""
from __future__ import annotations

import os

import pytest


APP_URL = os.getenv("P1_POSTGRES_APP_DATABASE_URL", "")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not APP_URL.startswith("postgresql"),
    reason="requires the least-privilege PostgreSQL application role URL",
)
async def test_migrated_head_passes_cloud_startup_database_gate() -> None:
    """Revision head, RLS, app-role and PHI gates agree after a clean migrate."""
    from app import database

    assert database.engine.dialect.name == "postgresql"
    assert database.PRODUCTION_SCHEMA_REVISION == "074"
    await database.verify_production_database()
