"""Create run_trace_events table (Phase 3-D2 Task 1)

Revision ID: 009
Revises: 008
Create Date: 2026-07-06

Promotes RunTrace from in-memory to persistent DB. Closes the
"RunTrace in-memory only — not auditable across workers/restarts"
gap from PHASE3D_GAP_CLOSURE_MATRIX.md.

Columns mirror RunTraceEvent dataclass + organization_id / project_id
/ user_id / actor_id for tenant-scoped audit queries. The
``safe_metadata_json`` column is ALREADY redacted at write time
(DbRunTraceStore.append runs a defensive scan before insert).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_trace_events",
        sa.Column("id", sa.String(length=12), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=True),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("agent_id", sa.String(length=128), nullable=True),
        sa.Column("step", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ts", sa.Float(), nullable=False, server_default="0"),
        sa.Column("safe_metadata_json", sa.JSON(), nullable=True),
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
        "ix_run_trace_events_run_id",
        "run_trace_events",
        ["run_id"],
    )
    op.create_index(
        "ix_run_trace_events_org_created",
        "run_trace_events",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_run_trace_events_agent_id",
        "run_trace_events",
        ["agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_trace_events_agent_id", table_name="run_trace_events")
    op.drop_index("ix_run_trace_events_org_created", table_name="run_trace_events")
    op.drop_index("ix_run_trace_events_run_id", table_name="run_trace_events")
    op.drop_table("run_trace_events")
