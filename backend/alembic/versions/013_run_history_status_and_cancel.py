"""Add status + cancel tracking columns to run_history (Phase 7 Gate 4)

Revision ID: 013
Revises: 012
Create Date: 2026-07-14

Phase 7 §9 (Gate 4 — Run cancel/timeout/backend status):

  - status (PENDING | RUNNING | COMPLETED | FAILED | CANCELLED |
            CLIENT_ABORTED | CANCELLATION_REQUESTED |
            CANCEL_NOT_SUPPORTED | COMPLETED_AFTER_CLIENT_ABORT)
  - cancel_reason (free-form reason for cancel)
  - cancelled_at (timestamp when cancel was requested)
  - cancelled_by_user_id (who requested the cancel)

§9.4 Cost: cancelled-before-Provider = cost stays 0; cancelled-after-
Provider = real partial cost already recorded. We don't add a separate
'billable' column here — the existing cost_usd column reflects actual
provider cost; billing reports decide how to treat cancelled runs.

§9.3 Timeout: SDK 90s timeout doesn't write any row; the SDK polls
GET /api/v1/runs/{run_id} for the real status. The lifecycle states
above are what that endpoint returns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "run_history",
        sa.Column(
            "status",
            sa.String(48),
            nullable=False,
            server_default="COMPLETED",
            comment=(
                "Run lifecycle state — "
                "PENDING|RUNNING|COMPLETED|FAILED|CANCELLED|"
                "CLIENT_ABORTED|CANCELLATION_REQUESTED|"
                "CANCEL_NOT_SUPPORTED|COMPLETED_AFTER_CLIENT_ABORT"
            ),
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "cancel_reason",
            sa.String(255),
            nullable=True,
            comment="Free-form reason captured at cancel time",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the cancel request was received",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "cancelled_by_user_id",
            sa.String(64),
            nullable=True,
            comment="User ID that requested the cancel (for audit)",
        ),
    )
    op.create_index(
        "ix_run_history_status",
        "run_history",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_history_status", table_name="run_history")
    op.drop_column("run_history", "cancelled_by_user_id")
    op.drop_column("run_history", "cancelled_at")
    op.drop_column("run_history", "cancel_reason")
    op.drop_column("run_history", "status")
