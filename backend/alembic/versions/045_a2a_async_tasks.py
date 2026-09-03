"""Add durable A2A asynchronous Task execution and event rows.

Revision ID: 045
Revises: 044
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "a2a_task_executions",
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint(
            "organization_id",
            "agent_id",
            "message_id",
            name="uq_a2a_task_execution_org_agent_message",
        ),
    )
    op.create_index(
        "ix_a2a_task_execution_org_agent",
        "a2a_task_executions",
        ["organization_id", "agent_id"],
    )
    op.create_index(
        "ix_a2a_task_execution_lease",
        "a2a_task_executions",
        ["lease_expires_at"],
    )

    op.create_table(
        "a2a_task_events",
        sa.Column("sequence_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["context_id"], ["contexts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sequence_id"),
    )
    op.create_index(
        "ix_a2a_task_event_task_sequence",
        "a2a_task_events",
        ["task_id", "sequence_id"],
    )
    op.create_index(
        "ix_a2a_task_event_org_agent",
        "a2a_task_events",
        ["organization_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_table("a2a_task_events")
    op.drop_table("a2a_task_executions")
