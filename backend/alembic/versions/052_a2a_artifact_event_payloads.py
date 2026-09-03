"""Persist exact encrypted A2A Artifact update payloads.

Revision ID: 052
Revises: 051
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("a2a_task_events") as batch:
        batch.add_column(
            sa.Column("artifact_payload_json", sa.Text(), nullable=True)
        )
        batch.add_column(
            sa.Column("artifact_payload_sha256", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("artifact_payload_size_bytes", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("a2a_task_events") as batch:
        batch.drop_column("artifact_payload_size_bytes")
        batch.drop_column("artifact_payload_sha256")
        batch.drop_column("artifact_payload_json")
