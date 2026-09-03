"""Add development Agent Run preauthorization settlements.

Revision ID: 043
Revises: 042
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_run_settlements",
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("user_id", sa.String(length=12), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="RESERVED"),
        sa.Column("reserved_amount", sa.Float(), nullable=False),
        sa.Column("settled_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "run_id", name="uq_billing_run_settlement_org_run"
        ),
    )
    op.create_index(
        "ix_billing_run_settlements_organization_id",
        "billing_run_settlements", ["organization_id"],
    )
    op.create_index(
        "ix_billing_run_settlements_user_id",
        "billing_run_settlements", ["user_id"],
    )
    op.create_index(
        "ix_billing_run_settlements_run_id",
        "billing_run_settlements", ["run_id"],
    )
    op.create_index(
        "ix_billing_run_settlements_status",
        "billing_run_settlements", ["status"],
    )


def downgrade() -> None:
    op.drop_table("billing_run_settlements")
