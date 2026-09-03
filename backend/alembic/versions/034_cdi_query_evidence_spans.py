"""Persist multiple independently-verifiable evidence spans per CDI query.

Revision ID: 034
Revises: 033
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cdi_provider_queries",
        sa.Column("evidence_spans", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("cdi_provider_queries", "evidence_spans")
