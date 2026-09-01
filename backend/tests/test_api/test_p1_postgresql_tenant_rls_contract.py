"""P1 release-gate contracts for PostgreSQL authority and core RLS."""
from __future__ import annotations

import importlib.util
import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = BACKEND_ROOT / "alembic" / "versions" / "064_postgresql_tenant_rls.py"
MIGRATION_065 = (
    BACKEND_ROOT / "alembic" / "versions" / "065_context_a2a_tenant_rls.py"
)


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


def test_revision_065_governs_approved_context_a2a_wave() -> None:
    spec = importlib.util.spec_from_file_location("p1_migration_065", MIGRATION_065)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "065"
    assert migration.down_revision == "064"
    assert set(migration.TENANT_TABLES) == {
        "context_messages",
        "context_task_refs",
        "context_artifact_refs",
        "original_input_audit",
        "a2a_task_executions",
        "a2a_task_events",
        "a2a_task_artifacts",
        "a2a_artifact_objects",
        "a2a_artifact_download_grants",
    }
    source = MIGRATION_065.read_text(encoding="utf-8")
    assert "requires evidence-backed tenant reconciliation" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "WITH CHECK" in source
    assert "unknown" not in source.lower()


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


def test_alembic_decouples_migrations_from_async_runtime_drivers() -> None:
    source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert '"postgresql+asyncpg://", "postgresql+psycopg://"' in source
    assert '"sqlite+aiosqlite://", "sqlite://"' in source
    assert "create_engine(" in source
    assert "create_async_engine" not in source


def test_boolean_migration_defaults_are_cross_dialect() -> None:
    versions = BACKEND_ROOT / "alembic" / "versions"
    forbidden = re.compile(
        r"server_default\s*=\s*(?:sa\.text\()?['\"](?:0|1)['\"]"
    )
    violations: list[str] = []
    for path in versions.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or not isinstance(node.func, ast.Attribute)
                or node.func.attr != "Column"
            ):
                continue
            segment = ast.get_source_segment(source, node) or ""
            if "sa.Boolean" in segment and forbidden.search(segment):
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_trace_capture_state_column_fits_longest_literal() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions"
        / "020_trace_event_identity_and_capture_state.py"
    ).read_text(encoding="utf-8")
    model = (BACKEND_ROOT / "app" / "models" / "run_history.py").read_text(
        encoding="utf-8",
    )
    assert 'type_=sa.String(length=32)' in migration
    assert 'String(32), nullable=True, index=True' in model
    assert len("NEVER_CAPTURED_LEGACY") <= 32


def test_clinical_tenant_migration_never_defaults_unknown_rows() -> None:
    migration = (
        BACKEND_ROOT / "alembic" / "versions"
        / "021_clinical_tables_tenant_not_null.py"
    ).read_text(encoding="utf-8")
    assert "requires evidence-backed clinical tenant" in migration
    assert '"reconciliation: " + details' in migration
    assert "SET organization_id = :org" not in migration
    assert "except Exception" not in migration
    assert "sa.inspect(bind).get_indexes" in migration


def test_registry_migrations_use_cross_dialect_introspection() -> None:
    for filename in (
        "022_expert_registry_provenance.py",
        "023_agent_canonical_key_and_alias.py",
    ):
        source = (BACKEND_ROOT / "alembic" / "versions" / filename).read_text(
            encoding="utf-8",
        )
        assert "PRAGMA" not in source
        assert "except Exception" not in source
        assert "sa.inspect(bind)" in source


def test_context_table_migration_uses_cross_dialect_types() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions"
        / "024_context_task_state_check.py"
    ).read_text(encoding="utf-8")
    assert "DATETIME" not in source
    assert "CREATE TABLE" not in source
    assert "sa.DateTime()" in source
    assert "server_default=sa.true()" in source
    assert "sa.inspect(bind)" in source
    assert "except Exception" not in source


def test_a2a_state_constraint_does_not_recreate_postgresql_table() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions"
        / "055_a2a_v1_interrupted_task_states.py"
    ).read_text(encoding="utf-8")
    assert 'bind.dialect.name == "postgresql"' in source
    assert 'op.drop_constraint(' in source
    assert 'op.create_check_constraint(' in source
    assert 'op.batch_alter_table("context_task_refs"' in source


@pytest.mark.asyncio
async def test_cloud_sqlite_authority_fails_closed(monkeypatch) -> None:
    from app import database

    monkeypatch.setattr(
        database, "engine", SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
    )
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        await database.verify_production_database()
