"""Bind Context/A2A child rows to tenants and enforce PostgreSQL RLS.

Revision ID: 065
Revises: 064
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


ADDED_TENANT_COLUMNS = (
    "context_messages",
    "context_task_refs",
    "context_artifact_refs",
    "original_input_audit",
    "a2a_task_artifacts",
)
TENANT_TABLES = (
    *ADDED_TENANT_COLUMNS,
    "a2a_task_executions",
    "a2a_task_events",
    "a2a_artifact_objects",
    "a2a_artifact_download_grants",
)
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


DIRECT_BACKFILLS = {
    "context_messages": "context_id",
    "context_task_refs": "context_id",
    "context_artifact_refs": "context_id",
    "original_input_audit": "context_id",
}


def _backfill_added_columns() -> None:
    bind = op.get_bind()
    for table, context_column in DIRECT_BACKFILLS.items():
        bind.exec_driver_sql(
            f'UPDATE "{table}" SET organization_id = ('
            f'SELECT c.organization_id FROM contexts c '
            f'WHERE c.id = "{table}"."{context_column}") '
            "WHERE organization_id IS NULL"
        )
    bind.exec_driver_sql(
        "UPDATE a2a_task_artifacts SET organization_id = ("
        "SELECT r.organization_id FROM context_task_refs r "
        "WHERE r.context_id = a2a_task_artifacts.context_id "
        "AND r.task_id = a2a_task_artifacts.task_id) "
        "WHERE organization_id IS NULL"
    )


def _validate_tenant_ownership() -> None:
    bind = op.get_bind()
    invalid: dict[str, int] = {}
    for table in ADDED_TENANT_COLUMNS:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        ).scalar_one()
        if count:
            invalid[table] = int(count)

    mismatch_queries = {
        "a2a_task_executions": (
            "SELECT count(*) FROM a2a_task_executions x JOIN contexts c "
            "ON c.id=x.context_id WHERE x.organization_id<>c.organization_id"
        ),
        "a2a_task_events": (
            "SELECT count(*) FROM a2a_task_events x JOIN contexts c "
            "ON c.id=x.context_id WHERE x.organization_id<>c.organization_id"
        ),
        "a2a_artifact_objects": (
            "SELECT count(*) FROM a2a_artifact_objects o "
            "JOIN a2a_task_artifacts a ON a.context_id=o.context_id "
            "AND a.task_id=o.task_id AND a.artifact_id=o.artifact_id "
            "WHERE o.organization_id<>a.organization_id"
        ),
        "a2a_artifact_download_grants": (
            "SELECT count(*) FROM a2a_artifact_download_grants g "
            "JOIN a2a_artifact_objects o ON o.object_id=g.object_id "
            "WHERE g.organization_id<>o.organization_id"
        ),
    }
    for table, statement in mismatch_queries.items():
        count = bind.exec_driver_sql(statement).scalar_one()
        if count:
            invalid[f"{table}:tenant_mismatch"] = int(count)
    if invalid:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(invalid.items())
        )
        raise RuntimeError(
            "migration 065 requires evidence-backed tenant reconciliation: "
            + details
        )


def _create_postgresql_constraints() -> None:
    op.create_unique_constraint("uq_contexts_org_id", "contexts", ["organization_id", "id"])
    op.create_unique_constraint(
        "uq_context_task_refs_org_context_task", "context_task_refs",
        ["organization_id", "context_id", "task_id"],
    )
    op.create_unique_constraint(
        "uq_a2a_task_artifacts_org_context_task_artifact", "a2a_task_artifacts",
        ["organization_id", "context_id", "task_id", "artifact_id"],
    )
    op.create_unique_constraint(
        "uq_a2a_artifact_objects_org_object", "a2a_artifact_objects",
        ["organization_id", "object_id"],
    )
    foreign_keys = (
        ("fk_context_messages_org_context", "context_messages", "contexts", ["organization_id", "context_id"], ["organization_id", "id"]),
        ("fk_context_task_refs_org_context", "context_task_refs", "contexts", ["organization_id", "context_id"], ["organization_id", "id"]),
        ("fk_context_artifact_refs_org_context", "context_artifact_refs", "contexts", ["organization_id", "context_id"], ["organization_id", "id"]),
        ("fk_a2a_task_executions_org_context", "a2a_task_executions", "contexts", ["organization_id", "context_id"], ["organization_id", "id"]),
        ("fk_a2a_task_events_org_context", "a2a_task_events", "contexts", ["organization_id", "context_id"], ["organization_id", "id"]),
        ("fk_a2a_task_artifacts_org_task", "a2a_task_artifacts", "context_task_refs", ["organization_id", "context_id", "task_id"], ["organization_id", "context_id", "task_id"]),
        ("fk_a2a_artifact_objects_org_artifact", "a2a_artifact_objects", "a2a_task_artifacts", ["organization_id", "context_id", "task_id", "artifact_id"], ["organization_id", "context_id", "task_id", "artifact_id"]),
        ("fk_a2a_artifact_download_grants_org_object", "a2a_artifact_download_grants", "a2a_artifact_objects", ["organization_id", "object_id"], ["organization_id", "object_id"]),
    )
    for name, source, target, local, remote in foreign_keys:
        op.create_foreign_key(name, source, target, local, remote, ondelete="CASCADE")


def upgrade() -> None:
    for table in ADDED_TENANT_COLUMNS:
        op.add_column(table, sa.Column("organization_id", sa.String(12), nullable=True))
    _backfill_added_columns()
    _validate_tenant_ownership()

    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ADDED_TENANT_COLUMNS:
        op.alter_column(table, "organization_id", existing_type=sa.String(12), nullable=False)
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    _create_postgresql_constraints()
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON "{table}" '
            f"USING ({TENANT_EXPRESSION}) WITH CHECK ({TENANT_EXPRESSION})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(TENANT_TABLES):
            op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
            op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        # Compatibility for pre-baseline development databases that briefly
        # applied an early 065 draft. The final revision deliberately keeps
        # retained audit rows independent of Context deletion.
        op.execute(
            "ALTER TABLE original_input_audit DROP CONSTRAINT IF EXISTS "
            "fk_original_input_audit_org_context"
        )
        foreign_keys = (
            ("a2a_artifact_download_grants", "fk_a2a_artifact_download_grants_org_object"),
            ("a2a_artifact_objects", "fk_a2a_artifact_objects_org_artifact"),
            ("a2a_task_artifacts", "fk_a2a_task_artifacts_org_task"),
            ("a2a_task_events", "fk_a2a_task_events_org_context"),
            ("a2a_task_executions", "fk_a2a_task_executions_org_context"),
            ("context_artifact_refs", "fk_context_artifact_refs_org_context"),
            ("context_task_refs", "fk_context_task_refs_org_context"),
            ("context_messages", "fk_context_messages_org_context"),
        )
        for table, name in foreign_keys:
            op.drop_constraint(name, table, type_="foreignkey")
        op.drop_constraint("uq_a2a_artifact_objects_org_object", "a2a_artifact_objects", type_="unique")
        op.drop_constraint("uq_a2a_task_artifacts_org_context_task_artifact", "a2a_task_artifacts", type_="unique")
        op.drop_constraint("uq_context_task_refs_org_context_task", "context_task_refs", type_="unique")
        op.drop_constraint("uq_contexts_org_id", "contexts", type_="unique")
        for table in ADDED_TENANT_COLUMNS:
            op.drop_index(f"ix_{table}_organization_id", table_name=table)
    for table in reversed(ADDED_TENANT_COLUMNS):
        op.drop_column(table, "organization_id")
