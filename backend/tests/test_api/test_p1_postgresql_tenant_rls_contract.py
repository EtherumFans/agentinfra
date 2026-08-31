"""P1 release-gate contracts for PostgreSQL authority and core RLS."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "064_postgresql_tenant_rls.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("p1_migration_064", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_tenant_tables_are_covered_by_force_rls(monkeypatch) -> None:
    migration = _load_migration()
    statements: list[str] = []
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        exec_driver_sql=lambda _statement: SimpleNamespace(scalar_one=lambda: 0),
    )
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: bind,
    )
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    expected = {
        "patient_contexts",
        "run_trace_events",
        "run_history",
        "transactions",
        "contexts",
        "memory_consents",
        "conversation_memories",
    }
    assert set(migration.TENANT_TABLES) == expected
    for table in expected:
        table_statements = [item for item in statements if f'"{table}"' in item]
        assert any("SET NOT NULL" in item for item in table_statements)
        assert any("ENABLE ROW LEVEL SECURITY" in item for item in table_statements)
        assert any("FORCE ROW LEVEL SECURITY" in item for item in table_statements)
        policy = next(item for item in table_statements if "CREATE POLICY" in item)
        assert "current_setting('icoder.current_organization_id', true)" in policy
        assert "USING" in policy and "WITH CHECK" in policy


def test_sqlite_migration_is_intentionally_noop(monkeypatch) -> None:
    migration = _load_migration()
    statements: list[str] = []
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
    )
    monkeypatch.setattr(migration.op, "execute", statements.append)

    migration.upgrade()

    assert statements == []


def test_migration_blocks_unattributed_rows_before_enabling_rls(monkeypatch) -> None:
    migration = _load_migration()
    statements: list[str] = []

    def _count(statement: str):
        count = 2 if '"run_history"' in statement else 0
        return SimpleNamespace(scalar_one=lambda: count)

    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), exec_driver_sql=_count,
    )
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.op, "execute", statements.append)

    with pytest.raises(RuntimeError, match="run_history=2"):
        migration.upgrade()

    assert statements == []


def test_cloud_startup_does_not_use_metadata_create_all() -> None:
    database_source = (BACKEND_ROOT / "app" / "database.py").read_text(
        encoding="utf-8",
    )
    source = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'settings.ICODER_DEPLOYMENT_MODE == "cloud"' in source
    assert "await verify_production_database()" in source
    assert "else:\n        await init_db()" in source
    assert "rolbypassrls" in database_source
    assert "pg_policies" in database_source
    assert "attnotnull" in database_source


@pytest.mark.asyncio
async def test_cloud_sqlite_authority_fails_closed(monkeypatch) -> None:
    from app import database

    monkeypatch.setattr(
        database, "engine", SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
    )
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        await database.verify_production_database()
