"""Add synthetic clinical model artifact attestations and shadow bindings.

Revision ID: 059
Revises: 058
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_model_artifact_attestations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("bundle_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("verification_report_sha256", sa.String(length=64), nullable=False),
        sa.Column("trust_key_id", sa.String(length=96), nullable=False),
        sa.Column("trust_store_sha256", sa.String(length=64), nullable=False),
        sa.Column("sbom_sha256", sa.String(length=64), nullable=False),
        sa.Column("model_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_class", sa.String(length=32), nullable=False),
        sa.Column("model_format", sa.String(length=64), nullable=False),
        sa.Column("runtime_contract", sa.String(length=96), nullable=False),
        sa.Column("verifier_version", sa.String(length=24), nullable=False),
        sa.Column("content_scan_status", sa.String(length=40), nullable=False),
        sa.Column("probe_status", sa.String(length=16), nullable=False),
        sa.Column("test_vector_count", sa.Integer(), nullable=False),
        sa.Column("verified_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "artifact_class = 'development_synthetic'",
            name="ck_clinical_model_artifact_class",
        ),
        sa.CheckConstraint(
            "model_format = 'icoder.synthetic-json/v1'",
            name="ck_clinical_model_artifact_format",
        ),
        sa.CheckConstraint(
            "content_scan_status = 'clean_development_scanner'",
            name="ck_clinical_model_artifact_scan_status",
        ),
        sa.CheckConstraint(
            "probe_status = 'passed'",
            name="ck_clinical_model_artifact_probe_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "package_id", "bundle_content_sha256",
            name="uq_clinical_model_artifact_attestation_digest",
        ),
    )
    op.create_index(
        "ix_clinical_model_artifact_attestations_org_package",
        "clinical_model_artifact_attestations",
        ["organization_id", "package_id", "created_at"],
    )
    op.create_table(
        "clinical_model_shadow_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("attestation_id", sa.String(length=36), nullable=False),
        sa.Column("previous_package_id", sa.String(length=36), nullable=True),
        sa.Column("previous_attestation_id", sa.String(length=36), nullable=True),
        sa.Column("mode", sa.String(length=16), server_default="shadow_only", nullable=False),
        sa.Column("record_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("bound_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_shadow_binding_use_case",
        ),
        sa.CheckConstraint("mode = 'shadow_only'", name="ck_clinical_model_shadow_binding_mode"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["attestation_id"], ["clinical_model_artifact_attestations.id"]),
        sa.ForeignKeyConstraint(["previous_package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["previous_attestation_id"], ["clinical_model_artifact_attestations.id"]),
        sa.ForeignKeyConstraint(["bound_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "use_case",
            name="uq_clinical_model_shadow_binding_org_use_case",
        ),
    )
    op.create_index(
        "ix_clinical_model_shadow_bindings_org_package",
        "clinical_model_shadow_bindings",
        ["organization_id", "package_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clinical_model_shadow_bindings_org_package",
        table_name="clinical_model_shadow_bindings",
    )
    op.drop_table("clinical_model_shadow_bindings")
    op.drop_index(
        "ix_clinical_model_artifact_attestations_org_package",
        table_name="clinical_model_artifact_attestations",
    )
    op.drop_table("clinical_model_artifact_attestations")
