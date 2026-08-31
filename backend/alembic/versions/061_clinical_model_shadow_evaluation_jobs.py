"""Add fenced asynchronous clinical-model shadow evaluation jobs.

Revision ID: 061
Revises: 060
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_model_shadow_evaluation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("active_binding_id", sa.String(length=36), nullable=True),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("attestation_id", sa.String(length=36), nullable=False),
        sa.Column("binding_record_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("fault_mode", sa.String(length=32), server_default="none", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_attempt_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("evaluation_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("rollback_performed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','passed','stopped','failed','cancelled')",
            name="ck_clinical_model_shadow_job_status",
        ),
        sa.CheckConstraint(
            "fault_mode IN ('none','worker_timeout','malformed_response','model_hash_mismatch')",
            name="ck_clinical_model_shadow_job_fault_mode",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts",
            name="ck_clinical_model_shadow_job_attempts",
        ),
        sa.CheckConstraint(
            "((status IN ('queued','running') AND active_binding_id = binding_id) OR "
            "(status IN ('passed','stopped','failed','cancelled') AND active_binding_id IS NULL))",
            name="ck_clinical_model_shadow_job_active_slot",
        ),
        sa.CheckConstraint(
            "((status = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND lease_owner IS NULL AND lease_token IS NULL "
            "AND lease_expires_at IS NULL))",
            name="ck_clinical_model_shadow_job_lease_shape",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["clinical_model_shadow_bindings.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(
            ["attestation_id"], ["clinical_model_artifact_attestations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["clinical_model_shadow_evaluations.id"],
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key",
            name="uq_clinical_model_shadow_job_org_idempotency",
        ),
        sa.UniqueConstraint(
            "active_binding_id", name="uq_clinical_model_shadow_job_active_binding",
        ),
    )
    op.create_index(
        "ix_clinical_model_shadow_jobs_dispatch",
        "clinical_model_shadow_evaluation_jobs",
        ["status", "next_attempt_at", "lease_expires_at", "created_at"],
    )
    op.create_index(
        "ix_clinical_model_shadow_jobs_org_binding",
        "clinical_model_shadow_evaluation_jobs",
        ["organization_id", "binding_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinical_model_shadow_jobs_org_binding",
        table_name="clinical_model_shadow_evaluation_jobs",
    )
    op.drop_index(
        "ix_clinical_model_shadow_jobs_dispatch",
        table_name="clinical_model_shadow_evaluation_jobs",
    )
    op.drop_table("clinical_model_shadow_evaluation_jobs")
