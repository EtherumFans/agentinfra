"""Add aggregate synthetic shadow observation and stop-gate state.

Revision ID: 060
Revises: 059
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("clinical_model_shadow_bindings") as batch_op:
        batch_op.add_column(sa.Column(
            "evaluation_gate_status", sa.String(length=20),
            server_default="not_evaluated", nullable=False,
        ))
        batch_op.add_column(
            sa.Column("last_evaluation_id", sa.String(length=36), nullable=True),
        )
        batch_op.add_column(
            sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        )
        batch_op.create_check_constraint(
            "ck_clinical_model_shadow_binding_evaluation_gate",
            "evaluation_gate_status IN ('not_evaluated','passed','stopped')",
        )
    op.create_table(
        "clinical_model_shadow_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("attestation_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("suite_id", sa.String(length=96), nullable=False),
        sa.Column("suite_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("observation_report_sha256", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=48), nullable=False),
        sa.Column("fault_mode", sa.String(length=32), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("vector_observation_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("mismatch_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("latency_p50_ms", sa.Integer(), nullable=False),
        sa.Column("latency_p95_ms", sa.Integer(), nullable=False),
        sa.Column("artifact_reverified", sa.Boolean(), nullable=False),
        sa.Column("rollback_performed", sa.Boolean(), nullable=False),
        sa.Column("binding_version_before", sa.Integer(), nullable=False),
        sa.Column("binding_version_after", sa.Integer(), nullable=False),
        sa.Column("evaluated_by_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('repository_synthetic','synthetic_fault_injection')",
            name="ck_clinical_model_shadow_evaluation_source",
        ),
        sa.CheckConstraint(
            "result IN ('passed','stopped')",
            name="ck_clinical_model_shadow_evaluation_result",
        ),
        sa.CheckConstraint(
            "fault_mode IN ('none','worker_timeout','malformed_response','model_hash_mismatch')",
            name="ck_clinical_model_shadow_evaluation_fault_mode",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["clinical_model_shadow_bindings.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(
            ["attestation_id"], ["clinical_model_artifact_attestations.id"],
        ),
        sa.ForeignKeyConstraint(["evaluated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_clinical_model_shadow_evaluations_org_binding",
        "clinical_model_shadow_evaluations",
        ["organization_id", "binding_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinical_model_shadow_evaluations_org_binding",
        table_name="clinical_model_shadow_evaluations",
    )
    op.drop_table("clinical_model_shadow_evaluations")
    with op.batch_alter_table("clinical_model_shadow_bindings") as batch_op:
        batch_op.drop_constraint(
            "ck_clinical_model_shadow_binding_evaluation_gate", type_="check",
        )
        batch_op.drop_column("last_evaluated_at")
        batch_op.drop_column("last_evaluation_id")
        batch_op.drop_column("evaluation_gate_status")
