"""Create run_history table (Phase 4-G #3)

Revision ID: 010
Revises: 009
Create Date: 2026-07-10

Promotes per-run summaries to a persistent DB table so AgentChatPage
can hydrate a history dropdown on page load. Closes the "chat result
lost on page refresh" gap from PHASE4F3_REMAINING_BACKLOG.md P0 #3.

Columns mirror AgentRunResponse's most useful summary fields. The
run_id column is unique + indexed for cross-table trace hydration
(GET /api/runtime/runs/{run_id}/trace joins on the same run_id).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_history",
        sa.Column("id", sa.String(length=12), primary_key=True),
        sa.Column("organization_id", sa.String(length=12), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("runtime_mode", sa.String(length=48), nullable=False, server_default=""),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=False),
        sa.Column("error", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_reason", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
    )
    op.create_index(
        "ix_run_history_agent_created",
        "run_history",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "ix_run_history_user_created",
        "run_history",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_run_history_org_created",
        "run_history",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_history_org_created", table_name="run_history")
    op.drop_index("ix_run_history_user_created", table_name="run_history")
    op.drop_index("ix_run_history_agent_created", table_name="run_history")
    op.drop_table("run_history")
