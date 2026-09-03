"""Enforce PostgreSQL row-level tenant isolation on P1 core resources.

Revision ID: 064
Revises: 063
Create Date: 2026-08-31

SQLite is intentionally unchanged: it remains a local/test convenience and
is forbidden by cloud configuration. PostgreSQL is the production authority.
Legacy NULL-tenant rows remain retained but are invisible through these
policies until an evidence-backed reconciliation assigns an organization.
"""

from alembic import op


revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "patient_contexts",
    "run_trace_events",
    "run_history",
    "transactions",
    "contexts",
    "memory_consents",
    "conversation_memories",
)
PREVIOUSLY_NULLABLE_TABLES = (
    "run_trace_events",
    "run_history",
    "transactions",
    "conversation_memories",
)
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    bind = op.get_bind()
    unattributed: dict[str, int] = {}
    for table in TENANT_TABLES:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        ).scalar_one()
        if count:
            unattributed[table] = int(count)
    if unattributed:
        details = ", ".join(
            f"{table}={count}" for table, count in sorted(unattributed.items())
        )
        raise RuntimeError(
            "migration 064 requires evidence-backed tenant reconciliation: "
            + details
        )

    for table in TENANT_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id SET NOT NULL'
        )
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON "{table}" '
            f"USING ({TENANT_EXPRESSION}) WITH CHECK ({TENANT_EXPRESSION})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    for table in PREVIOUSLY_NULLABLE_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id DROP NOT NULL'
        )
