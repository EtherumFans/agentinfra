"""Add organization-scoped clinical model package governance.

Revision ID: 058
Revises: 057
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_model_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("package_key", sa.String(length=64), nullable=False),
        sa.Column("package_version", sa.String(length=64), nullable=False),
        sa.Column("package_sha256", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("model_kind", sa.String(length=64), nullable=False),
        sa.Column("runtime_contract", sa.String(length=96), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), server_default="CN", nullable=False),
        sa.Column(
            "training_data_scope", sa.String(length=32),
            server_default="aggregate_manifest_only", nullable=False,
        ),
        sa.Column("training_dataset_sha256", sa.String(length=64), nullable=False),
        sa.Column("training_case_count", sa.Integer(), nullable=False),
        sa.Column("evaluation_evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "license_status", sa.String(length=32),
            server_default="external_review_required", nullable=False,
        ),
        sa.Column("redistribution_authorized", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("cloud_use_authorized", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("hospital_use_authorized", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("independent_gold_validated", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("independent_reviewer_approved", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("record_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("review_reference_sha256", sa.String(length=64), nullable=True),
        sa.Column("decision_reason_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft','submitted','approved','active','retired','rejected')",
            name="ck_clinical_model_package_status",
        ),
        sa.CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_package_use_case",
        ),
        sa.CheckConstraint("jurisdiction = 'CN'", name="ck_clinical_model_package_jurisdiction"),
        sa.CheckConstraint(
            "training_data_scope = 'aggregate_manifest_only'",
            name="ck_clinical_model_training_scope",
        ),
        sa.CheckConstraint(
            "license_status IN ('unknown','external_review_required','verified','restricted')",
            name="ck_clinical_model_license_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "package_key", "package_version",
            name="uq_clinical_model_package_org_key_version",
        ),
    )
    op.create_index(
        "ix_clinical_model_packages_org_use_status",
        "clinical_model_packages",
        ["organization_id", "use_case", "status"],
    )
    op.create_table(
        "clinical_model_activations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("previous_package_id", sa.String(length=36), nullable=True),
        sa.Column("deployment_mode", sa.String(length=24), nullable=False),
        sa.Column("record_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("activated_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_activation_use_case",
        ),
        sa.CheckConstraint(
            "deployment_mode IN ('development','hospital_private','cloud')",
            name="ck_clinical_model_activation_deployment_mode",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["previous_package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "use_case",
            name="uq_clinical_model_activation_org_use_case",
        ),
    )
    op.create_index(
        "ix_clinical_model_activations_org_package",
        "clinical_model_activations",
        ["organization_id", "package_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinical_model_activations_org_package",
        table_name="clinical_model_activations",
    )
    op.drop_table("clinical_model_activations")
    op.drop_index(
        "ix_clinical_model_packages_org_use_status",
        table_name="clinical_model_packages",
    )
    op.drop_table("clinical_model_packages")
