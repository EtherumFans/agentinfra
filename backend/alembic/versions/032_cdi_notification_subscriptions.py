"""Durable tenant-scoped CDI notification subscriptions.

Revision ID: 032
Revises: 031
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cdi_notification_subscriptions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(12), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=True),
        sa.Column("user_role", sa.String(32), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id", "created_by_user_id", "user_role", "channel", "active",
    ):
        op.create_index(
            f"ix_cdi_notification_subscriptions_{column}",
            "cdi_notification_subscriptions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("cdi_notification_subscriptions")
