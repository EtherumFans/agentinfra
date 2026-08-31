"""Durable encrypted STT recordings and transcript job state.

Revision ID: 031
Revises: 030
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stt_interactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "owner_id", "interaction_id", name="uq_stt_interaction_scope"),
    )
    for column in ("organization_id", "owner_id", "interaction_id"):
        op.create_index(f"ix_stt_interactions_{column}", "stt_interactions", [column])

    op.create_table(
        "stt_recordings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(160), nullable=False),
        sa.Column("recording_id", sa.String(240), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "owner_id", "interaction_id", "recording_id", name="uq_stt_recording_scope"),
    )
    for column in ("organization_id", "owner_id", "interaction_id", "recording_id"):
        op.create_index(f"ix_stt_recordings_{column}", "stt_recordings", [column])

    op.create_table(
        "stt_transcripts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("interaction_id", sa.String(160), nullable=False),
        sa.Column("transcript_id", sa.String(64), nullable=False),
        sa.Column("recording_id", sa.String(240), nullable=False),
        sa.Column("encrypted_text", sa.Text(), nullable=True),
        sa.Column("encrypted_request_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("participant_roles_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "owner_id", "interaction_id", "transcript_id", name="uq_stt_transcript_scope"),
    )
    for column in ("organization_id", "owner_id", "interaction_id", "transcript_id", "recording_id"):
        op.create_index(f"ix_stt_transcripts_{column}", "stt_transcripts", [column])


def downgrade() -> None:
    op.drop_table("stt_transcripts")
    op.drop_table("stt_recordings")
    op.drop_table("stt_interactions")
