"""Add tenant-scoped Agentic Task feedback.

Revision ID: 046
Revises: 045
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_task_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=True),
        sa.Column("target_key", sa.String(length=72), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("rating_scale", sa.String(length=16), nullable=False, server_default="binary"),
        sa.Column("rating_value", sa.Integer(), nullable=False),
        sa.Column("labels_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reason_encrypted", sa.Text(), nullable=True),
        sa.Column("reason_redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("safe_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating_scale = 'binary'", name="ck_agent_feedback_scale"),
        sa.CheckConstraint("rating_value IN (0, 1)", name="ck_agent_feedback_value"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "context_id", "task_id", "target_key",
            "actor_type", "actor_id", name="uq_agent_feedback_actor_target",
        ),
    )
    op.create_index(
        "ix_agent_feedback_org_context_task_actor",
        "agent_task_feedback",
        ["organization_id", "context_id", "task_id", "actor_type", "actor_id"],
    )
    op.create_index(
        "ix_agent_feedback_retention", "agent_task_feedback", ["retention_until"],
    )


def downgrade() -> None:
    op.drop_table("agent_task_feedback")
