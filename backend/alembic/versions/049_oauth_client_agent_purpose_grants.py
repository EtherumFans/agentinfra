"""Add explicit OAuth Client Agent and purpose delegation grants.

Revision ID: 049
Revises: 048
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("oauth_clients") as batch:
        batch.add_column(
            sa.Column("allowed_agent_ids", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(
            sa.Column("allowed_purposes", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("run_history") as batch:
        batch.add_column(
            sa.Column("delegated_subject_id", sa.String(length=128), nullable=True)
        )
        batch.add_column(sa.Column("purpose_of_use", sa.String(length=32), nullable=True))
        batch.create_index("ix_run_history_delegated_subject_id", ["delegated_subject_id"])
        batch.create_index("ix_run_history_purpose_of_use", ["purpose_of_use"])

    with op.batch_alter_table("connector_execution_audit") as batch:
        batch.add_column(
            sa.Column("granted_purposes", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("connector_execution_audit") as batch:
        batch.drop_column("granted_purposes")

    with op.batch_alter_table("run_history") as batch:
        batch.drop_index("ix_run_history_purpose_of_use")
        batch.drop_index("ix_run_history_delegated_subject_id")
        batch.drop_column("purpose_of_use")
        batch.drop_column("delegated_subject_id")

    with op.batch_alter_table("oauth_clients") as batch:
        batch.drop_column("allowed_purposes")
        batch.drop_column("allowed_agent_ids")
