"""Add independent feedback training authorizations.

Revision ID: 054
Revises: 053
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_training_authorizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("feedback_id", sa.String(length=36), nullable=False),
        sa.Column(
            "purpose_of_use", sa.String(length=32),
            server_default="quality_improvement", nullable=False,
        ),
        sa.Column(
            "data_scope", sa.String(length=32),
            server_default="feedback_metadata_only", nullable=False,
        ),
        sa.Column("feedback_digest", sa.String(length=64), nullable=False),
        sa.Column("approval_reference_hash", sa.String(length=64), nullable=False),
        sa.Column("authorized_by_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="active", nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose_of_use = 'quality_improvement'",
            name="ck_feedback_training_purpose",
        ),
        sa.CheckConstraint(
            "data_scope = 'feedback_metadata_only'",
            name="ck_feedback_training_data_scope",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_feedback_training_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["agent_task_feedback.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "feedback_id",
            name="uq_feedback_training_org_feedback",
        ),
    )
    op.create_index(
        "ix_feedback_training_org_context_task_status",
        "feedback_training_authorizations",
        ["organization_id", "context_id", "task_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_feedback_training_org_context_task_status",
        table_name="feedback_training_authorizations",
    )
    op.drop_table("feedback_training_authorizations")
