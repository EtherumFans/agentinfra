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
MIGRATION_066 = (
    BACKEND_ROOT / "alembic" / "versions" / "066_stt_streams_tenant_rls.py"
)
MIGRATION_067 = (
    BACKEND_ROOT / "alembic" / "versions" / "067_agent_connectors_tenant_rls.py"
)
MIGRATION_068 = (
    BACKEND_ROOT / "alembic" / "versions" / "068_identity_access_tenant_rls.py"
)
MIGRATION_069 = (
    BACKEND_ROOT / "alembic" / "versions" / "069_phi_clinical_tenant_rls.py"
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


def test_revision_066_governs_approved_stt_streams_wave() -> None:
    spec = importlib.util.spec_from_file_location("p1_migration_066", MIGRATION_066)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "066"
    assert migration.down_revision == "065"
    assert set(migration.TENANT_TABLES) == {
        "stt_interactions",
        "stt_recordings",
        "stt_transcripts",
        "stt_stream_leases",
        "stt_stream_checkpoints",
        "stt_stream_checkpoint_chunks",
    }
    source = MIGRATION_066.read_text(encoding="utf-8")
    assert "requires evidence-backed STT tenant reconciliation" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "WITH CHECK" in source
    assert "unknown" not in source.lower()


def test_revision_067_governs_approved_agent_connector_wave() -> None:
    spec = importlib.util.spec_from_file_location("p1_migration_067", MIGRATION_067)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "067"
    assert migration.down_revision == "066"
    assert set(migration.TENANT_TABLES) == {
        "agent_connectors",
        "connector_credentials",
        "connector_execution_audit",
    }
    source = MIGRATION_067.read_text(encoding="utf-8")
    assert "requires evidence-backed Connector tenant reconciliation" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "WITH CHECK" in source
    assert "unknown" not in source.lower()


def test_revision_068_governs_identity_and_access_wave() -> None:
    spec = importlib.util.spec_from_file_location("p1_migration_068", MIGRATION_068)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "068"
    assert migration.down_revision == "067"
    assert set(migration.TENANT_TABLES) == {
        "api_keys",
        "oauth_clients",
        "oauth_tokens",
        "organization_invite_deliveries",
        "organization_invites",
        "organization_members",
        "team_invites",
        "team_members",
    }
    assert migration.SPLIT_POLICY_TABLES == ("audit_logs",)
    source = MIGRATION_068.read_text(encoding="utf-8")
    assert "requires evidence-backed identity/access tenant" in source
    assert "reconciliation: " in source
    assert "icoder_write_system_audit" in source
    assert "icoder_resolve_oauth_client_tenant" in source
    assert "icoder_resolve_invite_tenant" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "WITH CHECK" in source


def test_revision_069_governs_phi_clinical_wave() -> None:
    spec = importlib.util.spec_from_file_location("p1_migration_069", MIGRATION_069)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "069"
    assert migration.down_revision == "068"
    assert set(migration.TENANT_TABLES) == {
        "agent_task_feedback", "cdi_cases", "cdi_clinician_responses",
        "cdi_document_versions", "cdi_documentation_gaps",
        "cdi_notification_subscriptions", "cdi_provider_queries",
        "clinical_evidences", "clinical_facts", "code_candidates",
        "coding_review_runs", "coding_reviews", "documents", "encounters",
        "feedback_training_authorizations", "guided_documents",
        "guided_sections",
    }
    source = MIGRATION_069.read_text(encoding="utf-8")
    assert "requires evidence-backed PHI clinical tenant" in source
    assert "run_history" in source and "count(DISTINCT organization_id)=1" in source
    assert "case_or_gap_scope_mismatch" in source
    assert "parent_scope_mismatch" in source
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
    assert "if settings.ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED:" in database_source


def test_production_revision_matches_the_single_alembic_head() -> None:
    """A new migration cannot silently make every cloud instance unbootable."""
    versions = BACKEND_ROOT / "alembic" / "versions"
    revisions: set[str] = set()
    parent_revisions: set[str] = set()

    for path in versions.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assignments: dict[str, object] = {}
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"revision", "down_revision"}
            ):
                assignments[node.targets[0].id] = ast.literal_eval(node.value)
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id in {"revision", "down_revision"}
                and node.value is not None
            ):
                assignments[node.target.id] = ast.literal_eval(node.value)
        revision = assignments.get("revision")
        if revision is None:
            assert path.name == "__init__.py"
            continue
        assert isinstance(revision, str) and revision, path.name
        revisions.add(revision)
        parent = assignments.get("down_revision")
        if isinstance(parent, str):
            parent_revisions.add(parent)
        elif isinstance(parent, (tuple, list)):
            parent_revisions.update(parent)
        else:
            assert parent is None, path.name

    heads = revisions - parent_revisions
    assert heads == {"074"}

    database_tree = ast.parse(
        (BACKEND_ROOT / "app" / "database.py").read_text(encoding="utf-8")
    )
    configured = next(
        ast.literal_eval(node.value)
        for node in database_tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "PRODUCTION_SCHEMA_REVISION"
    )
    assert configured == heads.pop()


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
