"""Add API Client attribution to run_history + allowed_origins on oauth_clients
(Phase 7 Gate 5)

Revision ID: 014
Revises: 013
Create Date: 2026-07-14

Phase 7 §10:
  - RunHistory gains attribution columns: api_client_id,
    embedded_app_id, session_id, context_id, request_id,
    idempotency_key. (organization_id already exists.)
  - OAuthClient gains allowed_origins (JSON array) and
    embedded_app_id (partner app identifier for embedded widgets).

§10.1: "每个 Embedded Run 都能归因到 API Client". Old rows stay
NULL; new rows MUST have api_client_id when the caller is an API
Client (vs a Console JWT user).

§10.3 Secret rules: secrets are already hashed (sha256) in
oauth_clients.client_secret_hash — we only add allowed_origins.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── RunHistory attribution columns ───────────────────────────────
    op.add_column(
        "run_history",
        sa.Column(
            "api_client_id",
            sa.String(128),
            nullable=True,
            index=True,
            comment="Partner OAuth client_id (NULL for Console JWT users)",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "embedded_app_id",
            sa.String(128),
            nullable=True,
            comment="Embedded widget app identifier (per OAuthClient)",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "session_id",
            sa.String(64),
            nullable=True,
            index=True,
            comment="Client-side session id (Phase 6 Gate 2 sessionId)",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "context_id",
            sa.String(64),
            nullable=True,
            index=True,
            comment="Patient/encounter context id",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "request_id",
            sa.String(64),
            nullable=True,
            comment="X-Request-Id header (if provided) for cross-system tracing",
        ),
    )
    op.add_column(
        "run_history",
        sa.Column(
            "idempotency_key",
            sa.String(255),
            nullable=True,
            index=True,
            comment="Client-supplied Idempotency-Key (Phase 7 Gate 3)",
        ),
    )

    # ── OAuthClient: allowed_origins + embedded_app_id ───────────────
    op.add_column(
        "oauth_clients",
        sa.Column(
            "allowed_origins",
            sa.JSON(),
            nullable=True,
            comment=(
                "JSON array of exact Origin strings permitted to embed "
                "this client's widget (Phase 7 §11.1). NULL = no embed "
                "allowed; [] = none; ['https://partner.example'] = allow."
            ),
        ),
    )
    op.add_column(
        "oauth_clients",
        sa.Column(
            "embedded_app_id",
            sa.String(128),
            nullable=True,
            comment="Public embedded-widget app id (sent to the browser)",
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth_clients", "embedded_app_id")
    op.drop_column("oauth_clients", "allowed_origins")

    op.drop_index("ix_run_history_idempotency_key", table_name="run_history")
    op.drop_column("run_history", "idempotency_key")
    op.drop_index("ix_run_history_request_id", table_name="run_history")
    op.drop_column("run_history", "request_id")
    op.drop_index("ix_run_history_context_id", table_name="run_history")
    op.drop_column("run_history", "context_id")
    op.drop_index("ix_run_history_session_id", table_name="run_history")
    op.drop_column("run_history", "session_id")
    op.drop_column("run_history", "embedded_app_id")
    op.drop_index("ix_run_history_api_client_id", table_name="run_history")
    op.drop_column("run_history", "api_client_id")
