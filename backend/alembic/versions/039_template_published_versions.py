"""Add immutable published versions for tenant templates.

Revision ID: 039
Revises: 038
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("template_id", sa.String(length=12), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("generation_json", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("published_by_user_id", sa.String(length=12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id", "version_number", name="uq_template_version_number"
        ),
    )
    op.create_index(
        "ix_template_versions_org_template",
        "template_versions",
        ["organization_id", "template_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_template_versions_org_template", table_name="template_versions"
    )
    op.drop_table("template_versions")
