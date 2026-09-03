"""Add tenant-scoped cross-worker Streams session leases.

Revision ID: 056
Revises: 055
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa


revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stt_stream_leases",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "owner_id",
            "interaction_id",
            name="pk_stt_stream_leases",
        ),
        sa.UniqueConstraint("session_id", name="uq_stt_stream_lease_session"),
    )
    op.create_index(
        "ix_stt_stream_lease_expiry",
        "stt_stream_leases",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stt_stream_lease_expiry", table_name="stt_stream_leases")
    op.drop_table("stt_stream_leases")
