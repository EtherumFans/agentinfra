"""Create preview_sessions table (Phase 7 Gate 13A-1)

Revision ID: 015
Revises: 014
Create Date: 2026-07-14

Phase 7 Gate 13A — Embedded Preview Security Hardening. The Console's
/ai-studio/embedded-assistant page issues a short-lived (60s) signed
Bootstrap Ticket per PDF Checkpoint C (one-time preview authentication).
The DB row mirrors the ticket claims and tracks single-use consumption,
revocation, and audit.

The unique constraint on jti prevents two concurrent ticket-issue calls
from minting the same ticket ID. The status column transitions:
  PENDING → EXCHANGED (single_use=True normal path)
  PENDING → REVOKED (admin/user disabled)
  PENDING → EXPIRED (TTL passed before exchange)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "preview_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "preview_session_id",
            sa.String(64),
            nullable=False,
            comment="Opaque UUID exposed in iframe URL (NOT the JWT)",
        ),
        sa.Column(
            "organization_id",
            sa.String(12),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "api_client_id",
            sa.String(64),
            nullable=True,
            comment="NULL for Console sessions; set for partner preview sessions",
        ),
        sa.Column(
            "expected_parent_origin",
            sa.String(255),
            nullable=False,
            comment="The Console origin (e.g. http://localhost:3000)",
        ),
        sa.Column(
            "expected_iframe_origin",
            sa.String(255),
            nullable=False,
            comment="The iframe origin (always backend origin — same-host)",
        ),
        sa.Column(
            "nonce",
            sa.String(64),
            nullable=False,
            comment="Random hex; both sides must prove knowledge via MessageChannel",
        ),
        sa.Column(
            "allowed_agent_ids",
            sa.JSON(),
            nullable=True,
            comment="JSON list of agent_ref strings; empty/NULL = all agents allowed",
        ),
        sa.Column(
            "allowed_scopes",
            sa.JSON(),
            nullable=True,
            comment="JSON list of scope strings granted to the Runtime Token",
        ),
        sa.Column(
            "jti",
            sa.String(64),
            nullable=False,
            unique=True,
            comment="JWT ID; unique per ticket; included in signature payload",
        ),
        sa.Column(
            "single_use",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="1 = ticket consumed on first successful exchange",
        ),
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="PENDING",
            comment="PENDING | EXCHANGED | REVOKED | EXPIRED",
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "exchanged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "exchanged_from_ip",
            sa.String(64),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_preview_sessions_preview_session_id",
        "preview_sessions",
        ["preview_session_id"],
    )
    op.create_index(
        "ix_preview_sessions_organization_id",
        "preview_sessions",
        ["organization_id"],
    )
    op.create_index(
        "ix_preview_sessions_user_id",
        "preview_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_preview_sessions_expires_at",
        "preview_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_preview_sessions_expires_at", table_name="preview_sessions")
    op.drop_index("ix_preview_sessions_user_id", table_name="preview_sessions")
    op.drop_index("ix_preview_sessions_organization_id", table_name="preview_sessions")
    op.drop_index("ix_preview_sessions_preview_session_id", table_name="preview_sessions")
    op.drop_table("preview_sessions")
