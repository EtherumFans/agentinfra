"""Add durable RunTrace retention tombstones.

Revision ID: 040
Revises: 039
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_history",
        sa.Column("trace_events_purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "trace_events_purged_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("run_history", "trace_events_purged_count")
    op.drop_column("run_history", "trace_events_purged_at")
