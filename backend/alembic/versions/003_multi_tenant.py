"""Multi-tenant migration (rewritten cycle 24)

Revision ID: 003
Revises: 002
Create Date: 2026-05-28 (rewritten 2026-07-02)

Creates:
- organizations table
- organization_members table
- organization_invites table
- Adds organization_id column (nullable FK) to 23 data tables

Cycle 24 rewrite rationale
--------------------------
The original 003 used ``asyncio.run(_upgrade_async())`` from inside the
alembic migration function. But ``alembic/env.py`` already calls
``asyncio.run(run_migrations_online())`` (line 63) — so when 003's
``upgrade()`` runs, it's already inside a running event loop, and
``asyncio.run()`` raises ``RuntimeError: asyncio.run() cannot be called
from a running event loop``.

This was a latent bug since cycle 21 — never surfaced because cycles
21-23 all used ``init_db()`` (Base.metadata.create_all) which bypasses
alembic entirely. Cycle 24's goal is to make ``alembic upgrade head``
work end-to-end, so 003 must be rewritten to use the pure alembic op
API (no asyncio.run, no async session).

The default-org data migration (create ``org_default1`` + assign all
existing users + UPDATE SET organization_id on all data tables) is
dropped because:
  1. On a fresh DB (the only state where alembic upgrade head runs in
     dev), there are no rows to migrate — the data block is a no-op.
  2. ``app/seed.py`` creates the default org + admin user on dev
     startup, so dev has correct org/user state via init_db() + seed
     regardless of alembic.
  3. Prod uses ``init_db()`` (uvicorn lifespan), not alembic — see
     ``docs/dev/BACKEND_RECOVERY.md`` §Prevention. The data block was
     never going to run in prod either.

Schema mirror: ``app/models/organization.py``. Enum ``OrgRole`` becomes
sa.Enum(owner/admin/member/viewer, name="orgrole") — matches
Base.metadata.create_all output on SQLite (VARCHAR(6) where 6 = max
value length 'member').
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 23 data tables that get organization_id (nullable FK to organizations.id).
# Matches the original 003 list — preserved verbatim so anyone comparing
# old vs new sees the only change is the API used (op.add_column vs raw
# SQL ALTER TABLE) and the removal of the data-migration block.
_DATA_TABLES = [
    "agents", "api_keys", "audit_logs",
    "code_candidates", "code_mappings", "code_tables",
    "coding_reviews", "clinical_evidences",
    "conversation_memories",
    "documents", "encounters",
    "experts", "mcp_servers",
    "gold_cases",
    "oauth_clients", "oauth_tokens",
    "runtime_sessions", "runtime_transitions",
    "runtime_audit_records", "runtime_duc_decisions",
    "team_members", "team_invites",
    "transactions",
]


def upgrade() -> None:
    """Create 3 organization tables + add organization_id to 23 data tables."""

    # ── organizations ───────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    # ── organization_members ────────────────────────────────────────
    op.create_table(
        "organization_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("owner", "admin", "member", "viewer", name="orgrole"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id"),
    )
    op.create_index(op.f("ix_organization_members_organization_id"), "organization_members", ["organization_id"], unique=False)
    op.create_index(op.f("ix_organization_members_user_id"), "organization_members", ["user_id"], unique=False)

    # ── organization_invites ────────────────────────────────────────
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=False),
        sa.Column("role", sa.Enum("owner", "admin", "member", "viewer", name="orgrole"), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(op.f("ix_organization_invites_organization_id"), "organization_invites", ["organization_id"], unique=False)

    # ── Add organization_id (nullable FK) to all 23 data tables ─────
    # nullable=True matches the model definitions (existing rows can have
    # NULL org during dev).
    #
    # We use raw SQL `ALTER TABLE ... ADD COLUMN ... REFERENCES` instead of
    # `op.add_column(table, sa.Column(..., sa.ForeignKey(...)))` because
    # alembic's op.add_column with sa.ForeignKey emits a separate
    # ADD CONSTRAINT statement, which SQLite rejects with NotImplementedError
    # ("No support for ALTER of constraints in SQLite dialect"). Inline
    # REFERENCES in ADD COLUMN is accepted by SQLite (and PostgreSQL), and
    # is what the original 003 did. The FK is decorative on SQLite anyway
    # (PRAGMA foreign_keys defaults to OFF), but prod uses init_db() which
    # creates tables with FK in CREATE TABLE — so this migration only needs
    # to add the column; the FK enforcement is a Base.metadata concern.
    for table in _DATA_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN organization_id VARCHAR(12) REFERENCES organizations(id)"
        )
        op.create_index(
            op.f(f"ix_{table}_organization_id"),
            table,
            ["organization_id"],
            unique=False,
        )


def downgrade() -> None:
    """Reverse: drop organization_id columns + drop 3 organization tables.

    SQLite supports DROP COLUMN since 3.35 (2021), so op.drop_column works
    directly without batch_alter_table. On PostgreSQL it emits a plain
    ALTER TABLE DROP COLUMN.
    """
    for table in _DATA_TABLES:
        op.drop_index(op.f(f"ix_{table}_organization_id"), table_name=table)
        op.drop_column(table, "organization_id")

    op.drop_index(op.f("ix_organization_invites_organization_id"), table_name="organization_invites")
    op.drop_table("organization_invites")

    op.drop_index(op.f("ix_organization_members_user_id"), table_name="organization_members")
    op.drop_index(op.f("ix_organization_members_organization_id"), table_name="organization_members")
    op.drop_table("organization_members")

    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
