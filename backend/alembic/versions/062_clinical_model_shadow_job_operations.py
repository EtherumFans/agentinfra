"""Add governed cancellation provenance to clinical shadow jobs.

Revision ID: 062
Revises: 061
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("clinical_model_shadow_evaluation_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("cancellation_reason", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancelled_by_user_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_clinical_model_shadow_job_cancelled_by_user",
            "users",
            ["cancelled_by_user_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_clinical_model_shadow_job_cancellation_shape",
            "((status = 'cancelled' AND cancellation_reason IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancellation_reason IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL))",
        )
        batch_op.create_check_constraint(
            "ck_clinical_model_shadow_job_cancellation_reason",
            "cancellation_reason IS NULL OR cancellation_reason IN "
            "('operator_request','maintenance','safety_stop')",
        )


def downgrade() -> None:
    with op.batch_alter_table("clinical_model_shadow_evaluation_jobs") as batch_op:
        batch_op.drop_constraint(
            "ck_clinical_model_shadow_job_cancellation_reason", type_="check"
        )
        batch_op.drop_constraint(
            "ck_clinical_model_shadow_job_cancellation_shape", type_="check"
        )
        batch_op.drop_constraint(
            "fk_clinical_model_shadow_job_cancelled_by_user", type_="foreignkey"
        )
        batch_op.drop_column("cancelled_by_user_id")
        batch_op.drop_column("cancelled_at")
        batch_op.drop_column("cancellation_reason")
