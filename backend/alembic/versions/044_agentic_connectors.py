"""Add Agentic v2 connector resources and secret-reference metadata.

Revision ID: 044
Revises: 043
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_connectors",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("agent_id", sa.String(length=12), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("credential_ref", sa.String(length=512), nullable=True),
        sa.Column("target_agent_id", sa.String(length=12), nullable=True),
        sa.Column("normalized_url", sa.String(length=2048), nullable=True),
        sa.Column("schema_ref", sa.String(length=512), nullable=True),
        sa.Column("schema_digest", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "type IN ('registry','mcp','agent','a2a','schema')",
            name="ck_agent_connector_type",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["target_agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "agent_id", "name",
            name="uq_agent_connector_org_agent_name",
        ),
    )
    for column in ("organization_id", "agent_id", "type", "enabled", "target_agent_id", "deleted_at"):
        op.create_index(f"ix_agent_connectors_{column}", "agent_connectors", [column])

    op.create_table(
        "connector_credentials",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("connector_id", sa.String(length=12), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("secret_ref", sa.String(length=512), nullable=False),
        sa.Column("fingerprint", sa.String(length=16), nullable=False),
        sa.Column("secret_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["connector_id"], ["agent_connectors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", name="uq_connector_credential_connector"),
    )
    op.create_index("ix_connector_credentials_organization_id", "connector_credentials", ["organization_id"])
    op.create_index("ix_connector_credentials_connector_id", "connector_credentials", ["connector_id"])

    op.create_table(
        "connector_execution_audit",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("connector_id", sa.String(length=12), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("policy_decision", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_status_class", sa.String(length=8), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("trace_span_id", sa.String(length=64), nullable=True),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["connector_id"], ["agent_connectors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "connector_id", "task_id", "run_id"):
        op.create_index(
            f"ix_connector_execution_audit_{column}",
            "connector_execution_audit", [column],
        )


def downgrade() -> None:
    op.drop_table("connector_execution_audit")
    op.drop_table("connector_credentials")
    op.drop_table("agent_connectors")
