"""Add durable A2A v1 Artifact update event fields.

Revision ID: 051
Revises: 050
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("a2a_task_events") as batch:
        batch.add_column(
            sa.Column("artifact_id", sa.String(length=128), nullable=True)
        )
        batch.add_column(sa.Column("artifact_append", sa.Boolean(), nullable=True))
        batch.add_column(
            sa.Column("artifact_last_chunk", sa.Boolean(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("a2a_task_events") as batch:
        batch.drop_column("artifact_last_chunk")
        batch.drop_column("artifact_append")
        batch.drop_column("artifact_id")
