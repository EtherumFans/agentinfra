"""Create idempotency_records table (Phase 7 Gate 3 — server-side dedup)

Revision ID: 012
Revises: 011
Create Date: 2026-07-14

Phase 7 §8.1: server-side Idempotency-Key dedup. The unique constraint
on (organization_id, api_client_id, idempotency_key) is the database-
level guarantee that two concurrent requests with the same key cannot
both create Runs. Application-level "SELECT then INSERT" is forbidden
by §8.3 ("不得仅用先查询、再插入").

Schema per Phase 7 §8.1:
  - id (PK)
  - organization_id (nullable for local dev single-org mode)
  - api_client_id (nullable; Console JWT auth has none)
  - idempotency_key (the client-supplied UUID)
  - agent_ref (which agent was invoked)
  - context_id (which patient/encounter context)
  - request_hash (SHA-256 of normalized request body)
  - run_id (FK to the actual Run)
  - status (PENDING / IN_PROGRESS / COMPLETED / FAILED)
  - response_snapshot (JSON column — the full AgentRunResponse dict)
  - created_at, expires_at (TTL for old records)

Indexes:
  - UNIQUE (organization_id, api_client_id, idempotency_key) — the dedup key
  - INDEX (expires_at) — for periodic cleanup
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.String(12),
            sa.ForeignKey("organizations.id"),
            nullable=True,
            comment="NULL in local dev single-org mode",
        ),
        sa.Column(
            "api_client_id",
            sa.String(64),
            nullable=True,
            index=True,
            comment="NULL when auth is Console JWT; set for partner client_credentials",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(255),
            nullable=False,
            comment="Client-supplied Idempotency-Key (typically UUID v4)",
        ),
        sa.Column(
            "agent_ref",
            sa.String(255),
            nullable=False,
            comment="Which agent was invoked (e.g. medical-coding-agent)",
        ),
        sa.Column(
            "context_id",
            sa.String(64),
            nullable=True,
            comment="Patient/encounter context (Phase 6 Gate 2 session contextId)",
        ),
        sa.Column(
            "request_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 of normalized request body (agent_id + input + runtime_mode)",
        ),
        sa.Column(
            "run_id",
            sa.String(64),
            nullable=True,
            comment="Bound Run ID (set immediately after PENDING)",
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="PENDING",
            comment="PENDING | IN_PROGRESS | COMPLETED | FAILED",
        ),
        sa.Column(
            "response_snapshot",
            sa.JSON(),
            nullable=True,
            comment="Full AgentRunResponse dict (returned on dedup replay)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="TTL — old records can be cleaned up after this",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "api_client_id",
            "idempotency_key",
            name="uq_idempotency_org_client_key",
        ),
    )
    # Index for periodic cleanup
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")
