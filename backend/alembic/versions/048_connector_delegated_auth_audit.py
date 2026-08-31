"""Persist delegated connector authorization context.

Revision ID: 048
Revises: 047
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("connector_execution_audit") as batch:
        batch.add_column(
            sa.Column(
                "actor_type", sa.String(length=24),
                nullable=False, server_default="unknown",
            )
        )
        batch.add_column(sa.Column("actor_id", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column("delegated_subject_id", sa.String(length=128), nullable=True)
        )
        batch.add_column(
            sa.Column("granted_scopes", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.create_index(
            "ix_connector_execution_audit_actor_id", ["actor_id"]
        )
        batch.create_index(
            "ix_connector_execution_audit_delegated_subject_id",
            ["delegated_subject_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("connector_execution_audit") as batch:
        batch.drop_index("ix_connector_execution_audit_delegated_subject_id")
        batch.drop_index("ix_connector_execution_audit_actor_id")
        batch.drop_column("granted_scopes")
        batch.drop_column("delegated_subject_id")
        batch.drop_column("actor_id")
        batch.drop_column("actor_type")
