"""Add durable Context and Task owned A2A Artifact payloads.

Revision ID: 050
Revises: 049
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "a2a_task_artifacts",
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["context_id", "task_id"],
            ["context_task_refs.context_id", "context_task_refs.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("context_id", "task_id", "artifact_id"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_a2a_task_artifact_size"),
    )
    op.create_index(
        "ix_a2a_task_artifact_task_created",
        "a2a_task_artifacts",
        ["context_id", "task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("a2a_task_artifacts")
