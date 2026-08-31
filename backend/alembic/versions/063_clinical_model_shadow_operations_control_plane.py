"""Add dead-letter, persistent alert and scheduler lease control planes.

Revision ID: 063
Revises: 062
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa


revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_model_shadow_dead_letters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("source_job_id", sa.String(length=36), nullable=False),
        sa.Column("binding_id", sa.String(length=36), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("attestation_id", sa.String(length=36), nullable=False),
        sa.Column("binding_record_version", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="available", nullable=False),
        sa.Column("replayed_job_id", sa.String(length=36), nullable=True),
        sa.Column("replay_idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replayed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('available','replayed','discarded')",
            name="ck_clinical_model_shadow_dead_letter_status",
        ),
        sa.CheckConstraint(
            "((status = 'replayed' AND replayed_job_id IS NOT NULL "
            "AND replay_idempotency_key IS NOT NULL AND replayed_at IS NOT NULL "
            "AND replayed_by_user_id IS NOT NULL) OR "
            "(status <> 'replayed' AND replayed_job_id IS NULL "
            "AND replay_idempotency_key IS NULL AND replayed_at IS NULL "
            "AND replayed_by_user_id IS NULL))",
            name="ck_clinical_model_shadow_dead_letter_replay_shape",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_job_id"], ["clinical_model_shadow_evaluation_jobs.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["clinical_model_shadow_bindings.id"]),
        sa.ForeignKeyConstraint(["package_id"], ["clinical_model_packages.id"]),
        sa.ForeignKeyConstraint(["attestation_id"], ["clinical_model_artifact_attestations.id"]),
        sa.ForeignKeyConstraint(["replayed_job_id"], ["clinical_model_shadow_evaluation_jobs.id"]),
        sa.ForeignKeyConstraint(["replayed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_job_id", name="uq_clinical_model_shadow_dead_letter_source"),
        sa.UniqueConstraint(
            "organization_id", "replay_idempotency_key",
            name="uq_clinical_model_shadow_dead_letter_replay_key",
        ),
    )
    op.create_index(
        "ix_clinical_model_shadow_dead_letters_org_status_created",
        "clinical_model_shadow_dead_letters",
        ["organization_id", "status", "created_at"],
    )
    op.create_table(
        "clinical_model_shadow_alert_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=12), nullable=False),
        sa.Column("alert_code", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "alert_code IN ('queue_backlog','queue_age_exceeded','expired_leases',"
            "'exhausted_jobs','dead_letter_backlog')",
            name="ck_clinical_model_shadow_alert_code",
        ),
        sa.CheckConstraint("state IN ('firing','resolved')", name="ck_clinical_model_shadow_alert_state"),
        sa.CheckConstraint("occurrence_count >= 1", name="ck_clinical_model_shadow_alert_occurrences"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "alert_code", name="uq_clinical_model_shadow_alert_org_code"),
    )
    op.create_index(
        "ix_clinical_model_shadow_alert_states_state",
        "clinical_model_shadow_alert_states",
        ["state", "last_evaluated_at"],
    )
    op.create_table(
        "clinical_model_shadow_scheduler_leases",
        sa.Column("scheduler_name", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=64), nullable=False),
        sa.Column("lease_token", sa.String(length=36), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("last_cycle_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cycle_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cycle_status", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("generation >= 1", name="ck_clinical_model_shadow_scheduler_generation"),
        sa.CheckConstraint(
            "last_cycle_status IS NULL OR last_cycle_status IN ('succeeded','failed')",
            name="ck_clinical_model_shadow_scheduler_cycle_status",
        ),
        sa.PrimaryKeyConstraint("scheduler_name"),
    )


def downgrade() -> None:
    op.drop_table("clinical_model_shadow_scheduler_leases")
    op.drop_index(
        "ix_clinical_model_shadow_alert_states_state",
        table_name="clinical_model_shadow_alert_states",
    )
    op.drop_table("clinical_model_shadow_alert_states")
    op.drop_index(
        "ix_clinical_model_shadow_dead_letters_org_status_created",
        table_name="clinical_model_shadow_dead_letters",
    )
    op.drop_table("clinical_model_shadow_dead_letters")
