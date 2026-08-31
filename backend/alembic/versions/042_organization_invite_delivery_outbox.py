"""Add encrypted organization invitation delivery outbox.

Revision ID: 042
Revises: 041
Create Date: 2026-08-15
"""

from alembic import op
import sqlalchemy as sa


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_invite_deliveries",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("invite_id", sa.String(length=12), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_id", sa.String(length=64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("provider_message_id_hash", sa.String(length=64), nullable=True),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["invite_id"], ["organization_invites.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invite_id"),
    )
    op.create_index(
        "ix_organization_invite_deliveries_organization_id",
        "organization_invite_deliveries",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_invite_deliveries_invite_id",
        "organization_invite_deliveries",
        ["invite_id"],
        unique=False,
    )
    op.create_index(
        "ix_organization_invite_deliveries_status",
        "organization_invite_deliveries",
        ["status"],
    )
    op.create_index(
        "ix_organization_invite_deliveries_next_attempt_at",
        "organization_invite_deliveries",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_organization_invite_deliveries_lock_id",
        "organization_invite_deliveries",
        ["lock_id"],
    )


def downgrade() -> None:
    op.drop_table("organization_invite_deliveries")
