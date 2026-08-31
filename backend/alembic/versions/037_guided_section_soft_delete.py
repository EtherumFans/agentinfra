"""Add soft-delete lifecycle to tenant Guided Sections.

Revision ID: 037
Revises: 036
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guided_sections",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_guided_sections_deleted_at",
        "guided_sections",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_guided_sections_deleted_at", table_name="guided_sections")
    op.drop_column("guided_sections", "deleted_at")
