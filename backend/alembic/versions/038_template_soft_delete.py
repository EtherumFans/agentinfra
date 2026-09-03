"""Add soft-delete lifecycle to tenant Templates.

Revision ID: 038
Revises: 037
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_templates_deleted_at",
        "templates",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_templates_deleted_at", table_name="templates")
    op.drop_column("templates", "deleted_at")
