"""Add encrypted resumable checkpoints for retained Streams interactions.

Revision ID: 057
Revises: 056
Create Date: 2026-08-25
"""

from alembic import op
import sqlalchemy as sa


revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stt_stream_checkpoints",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=240), nullable=False),
        sa.Column("encrypted_state_json", sa.Text(), nullable=False),
        sa.Column("state_sha256", sa.String(length=64), nullable=False),
        sa.Column("audio_bytes", sa.Integer(), nullable=False),
        sa.Column("audio_chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "owner_id",
            "interaction_id",
            name="pk_stt_stream_checkpoints",
        ),
    )
    op.create_index(
        "ix_stt_stream_checkpoint_updated",
        "stt_stream_checkpoints",
        ["updated_at"],
        unique=False,
    )
    op.create_table(
        "stt_stream_checkpoint_chunks",
        sa.Column("organization_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id", "interaction_id"],
            [
                "stt_stream_checkpoints.organization_id",
                "stt_stream_checkpoints.owner_id",
                "stt_stream_checkpoints.interaction_id",
            ],
            name="fk_stt_stream_checkpoint_chunk_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "owner_id",
            "interaction_id",
            "sequence",
            name="pk_stt_stream_checkpoint_chunks",
        ),
    )
    op.create_index(
        "ix_stt_stream_checkpoint_chunk_scope",
        "stt_stream_checkpoint_chunks",
        ["organization_id", "owner_id", "interaction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stt_stream_checkpoint_chunk_scope",
        table_name="stt_stream_checkpoint_chunks",
    )
    op.drop_table("stt_stream_checkpoint_chunks")
    op.drop_index(
        "ix_stt_stream_checkpoint_updated",
        table_name="stt_stream_checkpoints",
    )
    op.drop_table("stt_stream_checkpoints")
