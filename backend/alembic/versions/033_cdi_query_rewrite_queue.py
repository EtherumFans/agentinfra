"""Persist CDI multi-axis query rewrite work items.

Revision ID: 033
Revises: 032
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cdi_cases",
        sa.Column(
            "query_rewrite_queue",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("cdi_cases", "query_rewrite_queue")
