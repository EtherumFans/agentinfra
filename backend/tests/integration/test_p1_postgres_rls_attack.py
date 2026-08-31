"""Live PostgreSQL attack test for the P1 tenant RLS release gate.

Set ``P1_POSTGRES_TEST_DATABASE_URL`` to a disposable database migrated to
head and accessed through the real, non-superuser application role.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine


DATABASE_URL = os.getenv("P1_POSTGRES_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith(("postgresql://", "postgresql+asyncpg://")),
    reason="P1_POSTGRES_TEST_DATABASE_URL is not configured",
)


@pytest.mark.asyncio
async def test_trace_rls_blocks_cross_tenant_read_write_and_delete() -> None:
    engine = create_async_engine(DATABASE_URL)
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"p1a_{suffix}", f"p1b_{suffix}"
    event_a, event_b = f"ea{suffix}", f"eb{suffix}"

    async def _tenant(connection, organization_id: str) -> None:
        await connection.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": "icoder.current_organization_id", "value": organization_id},
        )

    try:
        async with engine.begin() as connection:
            role = (
                await connection.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).one()
            assert not role.rolsuper and not role.rolbypassrls
            state = (
                await connection.execute(
                    text(
                        "SELECT relrowsecurity, relforcerowsecurity "
                        "FROM pg_class WHERE oid = 'run_trace_events'::regclass"
                    )
                )
            ).one()
            assert state == (True, True)
            for organization_id in (org_a, org_b):
                await connection.execute(
                    text(
                        "INSERT INTO organizations "
                        "(id, name, slug, plan, settings, is_active) "
                        "VALUES (:id, :name, :slug, 'free', CAST('{}' AS json), true)"
                    ),
                    {
                        "id": organization_id,
                        "name": f"P1 RLS {organization_id}",
                        "slug": organization_id,
                    },
                )

        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            async with engine.begin() as connection:
                await _tenant(connection, organization_id)
                await connection.execute(
                    text(
                        "INSERT INTO run_trace_events "
                        "(id, run_id, organization_id, step, status, duration_ms, ts) "
                        "VALUES (:id, :run_id, :org, 'start', 'ok', 0, 0)"
                    ),
                    {"id": event_id, "run_id": f"run-{event_id}", "org": organization_id},
                )

        async with engine.begin() as connection:
            visible_without_context = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM run_trace_events "
                        "WHERE id IN (:a, :b)"
                    ),
                    {"a": event_a, "b": event_b},
                )
            ).scalar_one()
            assert visible_without_context == 0

        async with engine.begin() as connection:
            await _tenant(connection, org_a)
            visible = (
                await connection.execute(
                    text(
                        "SELECT id FROM run_trace_events WHERE id IN (:a, :b) ORDER BY id"
                    ),
                    {"a": event_a, "b": event_b},
                )
            ).scalars().all()
            assert visible == [event_a]
            deleted = await connection.execute(
                text("DELETE FROM run_trace_events WHERE id = :id"), {"id": event_b},
            )
            assert deleted.rowcount == 0

        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await _tenant(connection, org_a)
                await connection.execute(
                    text(
                        "INSERT INTO run_trace_events "
                        "(id, run_id, organization_id, step, status, duration_ms, ts) "
                        "VALUES (:id, :run_id, :org, 'start', 'ok', 0, 0)"
                    ),
                    {
                        "id": f"x{suffix}",
                        "run_id": f"cross-{suffix}",
                        "org": org_b,
                    },
                )
    finally:
        for organization_id, event_id in ((org_a, event_a), (org_b, event_b)):
            try:
                async with engine.begin() as connection:
                    await _tenant(connection, organization_id)
                    await connection.execute(
                        text("DELETE FROM run_trace_events WHERE id = :id"), {"id": event_id},
                    )
            except Exception:
                pass
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM organizations WHERE id IN (:a, :b)"),
                    {"a": org_a, "b": org_b},
                )
        finally:
            await engine.dispose()
