"""Enforce PostgreSQL tenant isolation for Agent Connectors.

Revision ID: 067
Revises: 066
Create Date: 2026-09-01
"""

from alembic import op


revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "agent_connectors",
    "connector_credentials",
    "connector_execution_audit",
)
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


def _validate_ownership() -> None:
    bind = op.get_bind()
    invalid: dict[str, int] = {}
    for table in TENANT_TABLES:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        ).scalar_one()
        if count:
            invalid[f"{table}:null_tenant"] = int(count)

    orphan_queries = {
        "agent_connectors:missing_agent_scope": (
            "SELECT count(*) FROM agent_connectors c LEFT JOIN agents a "
            "ON a.organization_id=c.organization_id AND a.id=c.agent_id "
            "WHERE a.id IS NULL"
        ),
        "agent_connectors:missing_target_agent_scope": (
            "SELECT count(*) FROM agent_connectors c LEFT JOIN agents a "
            "ON a.organization_id=c.organization_id AND a.id=c.target_agent_id "
            "WHERE c.target_agent_id IS NOT NULL AND a.id IS NULL"
        ),
        "connector_credentials:missing_connector_scope": (
            "SELECT count(*) FROM connector_credentials c "
            "LEFT JOIN agent_connectors a ON a.organization_id=c.organization_id "
            "AND a.id=c.connector_id WHERE a.id IS NULL"
        ),
        "connector_execution_audit:missing_connector_scope": (
            "SELECT count(*) FROM connector_execution_audit e "
            "LEFT JOIN agent_connectors a ON a.organization_id=e.organization_id "
            "AND a.id=e.connector_id WHERE a.id IS NULL"
        ),
    }
    for key, statement in orphan_queries.items():
        count = bind.exec_driver_sql(statement).scalar_one()
        if count:
            invalid[key] = int(count)
    if invalid:
        details = ", ".join(
            f"{key}={count}" for key, count in sorted(invalid.items())
        )
        raise RuntimeError(
            "migration 067 requires evidence-backed Connector tenant reconciliation: "
            + details
        )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _validate_ownership()

    op.create_unique_constraint(
        "uq_agents_org_id", "agents", ["organization_id", "id"]
    )
    op.create_unique_constraint(
        "uq_agent_connectors_org_id",
        "agent_connectors",
        ["organization_id", "id"],
    )
    for constraint, table in (
        ("agent_connectors_agent_id_fkey", "agent_connectors"),
        ("agent_connectors_target_agent_id_fkey", "agent_connectors"),
        ("connector_credentials_connector_id_fkey", "connector_credentials"),
        ("connector_execution_audit_connector_id_fkey", "connector_execution_audit"),
    ):
        op.drop_constraint(constraint, table, type_="foreignkey")

    op.create_foreign_key(
        "fk_agent_connectors_agent_scope",
        "agent_connectors",
        "agents",
        ["organization_id", "agent_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_agent_connectors_target_agent_scope",
        "agent_connectors",
        "agents",
        ["organization_id", "target_agent_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_connector_credentials_connector_scope",
        "connector_credentials",
        "agent_connectors",
        ["organization_id", "connector_id"],
        ["organization_id", "id"],
    )
    op.create_foreign_key(
        "fk_connector_execution_audit_connector_scope",
        "connector_execution_audit",
        "agent_connectors",
        ["organization_id", "connector_id"],
        ["organization_id", "id"],
    )

    for table in TENANT_TABLES:
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

    for constraint, table in (
        ("fk_connector_execution_audit_connector_scope", "connector_execution_audit"),
        ("fk_connector_credentials_connector_scope", "connector_credentials"),
        ("fk_agent_connectors_target_agent_scope", "agent_connectors"),
        ("fk_agent_connectors_agent_scope", "agent_connectors"),
    ):
        op.drop_constraint(constraint, table, type_="foreignkey")

    op.create_foreign_key(
        "agent_connectors_agent_id_fkey",
        "agent_connectors",
        "agents",
        ["agent_id"],
        ["id"],
    )
    op.create_foreign_key(
        "agent_connectors_target_agent_id_fkey",
        "agent_connectors",
        "agents",
        ["target_agent_id"],
        ["id"],
    )
    op.create_foreign_key(
        "connector_credentials_connector_id_fkey",
        "connector_credentials",
        "agent_connectors",
        ["connector_id"],
        ["id"],
    )
    op.create_foreign_key(
        "connector_execution_audit_connector_id_fkey",
        "connector_execution_audit",
        "agent_connectors",
        ["connector_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_agent_connectors_org_id", "agent_connectors", type_="unique"
    )
    op.drop_constraint("uq_agents_org_id", "agents", type_="unique")
