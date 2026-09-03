"""Add quarantined managed objects and one-time download grants.

Revision ID: 053
Revises: 052
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa


revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "a2a_artifact_objects",
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("context_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("filename_encrypted", sa.Text(), nullable=False),
        sa.Column("declared_media_type", sa.String(length=128), nullable=False),
        sa.Column("detected_media_type", sa.String(length=128), nullable=True),
        sa.Column("data_classification", sa.String(length=32), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("malware_scan_status", sa.String(length=16), nullable=False),
        sa.Column("dlp_scan_status", sa.String(length=16), nullable=False),
        sa.Column("scan_engine", sa.String(length=64), nullable=False),
        sa.Column("scan_findings_json", sa.Text(), nullable=False),
        sa.Column("rejection_code", sa.String(length=64), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["context_id", "task_id", "artifact_id"],
            [
                "a2a_task_artifacts.context_id",
                "a2a_task_artifacts.task_id",
                "a2a_task_artifacts.artifact_id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("object_id"),
        sa.CheckConstraint("size_bytes > 0", name="ck_a2a_artifact_object_size"),
        sa.CheckConstraint(
            "status IN ('quarantined', 'available', 'rejected')",
            name="ck_a2a_artifact_object_status",
        ),
        sa.CheckConstraint(
            "malware_scan_status IN ('pending', 'clean', 'infected', 'error')",
            name="ck_a2a_artifact_object_malware_status",
        ),
        sa.CheckConstraint(
            "dlp_scan_status IN ('pending', 'clear', 'restricted', 'blocked', 'error')",
            name="ck_a2a_artifact_object_dlp_status",
        ),
        sa.CheckConstraint(
            "data_classification IN ('deidentified', 'clinical-sensitive')",
            name="ck_a2a_artifact_object_classification",
        ),
    )
    op.create_index(
        "ix_a2a_artifact_object_owner",
        "a2a_artifact_objects",
        ["organization_id", "context_id", "task_id", "artifact_id", "created_at"],
    )
    op.create_index(
        "ix_a2a_artifact_object_status",
        "a2a_artifact_objects",
        ["status", "created_at"],
    )

    op.create_table(
        "a2a_artifact_download_grants",
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose_of_use", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["object_id"], ["a2a_artifact_objects.object_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("grant_id"),
        sa.CheckConstraint(
            "purpose_of_use IN ('treatment', 'payment', 'healthcare_operations')",
            name="ck_a2a_artifact_grant_purpose",
        ),
    )
    op.create_index(
        "ix_a2a_artifact_grant_object_expiry",
        "a2a_artifact_download_grants",
        ["object_id", "expires_at"],
    )
    op.create_index(
        "ix_a2a_artifact_grant_expiry",
        "a2a_artifact_download_grants",
        ["expires_at", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_table("a2a_artifact_download_grants")
    op.drop_table("a2a_artifact_objects")
