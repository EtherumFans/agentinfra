"""Standardize id and FK column lengths to varchar(12)

Phase A1C.2 (2026-07-25): closes A1C.1 schema drift finding where 32 tables
declared `id` and foreign-key columns with bare `sa.String()` (DB emits
unbounded `varchar`) while the ORM models correctly use `String(12)`. The
divergence was detected by `backend/tests/unit/scripts/test_schema_drift.py`
at HEAD 8b8d649 (post A1C.1 partial fix).

This Migration 027 ALTERs each affected column to `sa.String(length=12)`,
reconciling DB with ORM. Safe for SQLite (type affinity only) and PostgreSQL
(VARCHAR length is enforced).

Downgrade restores unbounded varchar (matches pre-A1C.2 baseline).

Tables altered (32):
  agents, api_keys, audit_logs, clinical_evidences, code_candidates,
  code_mappings, code_tables, coding_reviews, conversation_memories,
  customers, documents, encounters, experts, gold_cases, mcp_servers,
  oauth_clients, oauth_tokens, organization_invites, organization_members,
  organizations, password_reset_tokens, runtime_audit_records,
  runtime_duc_decisions, runtime_sessions, runtime_transitions,
  team_invites, team_members, templates, tickets, token_blacklist,
  transactions, users

Columns altered (40):
  32 × id (PK)
  + 8 × organization_id / user_id / invited_by / created_by_id (FK to organizations.id / users.id)

Revision ID: 027
Revises: 026
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


# (table, column) pairs to ALTER to String(12)
AFFECTED = [
    ("agents", "id"),
    ("api_keys", "id"),
    ("audit_logs", "id"),
    ("clinical_evidences", "id"),
    ("code_candidates", "id"),
    ("code_mappings", "id"),
    ("code_tables", "id"),
    ("coding_reviews", "id"),
    ("conversation_memories", "id"),
    ("customers", "id"),
    ("customers", "organization_id"),
    ("documents", "id"),
    ("encounters", "id"),
    ("experts", "id"),
    ("gold_cases", "id"),
    ("mcp_servers", "id"),
    ("oauth_clients", "id"),
    ("oauth_tokens", "id"),
    ("organization_invites", "id"),
    ("organization_invites", "invited_by"),
    ("organization_invites", "organization_id"),
    ("organization_members", "id"),
    ("organization_members", "organization_id"),
    ("organization_members", "user_id"),
    ("organizations", "id"),
    ("password_reset_tokens", "id"),
    ("runtime_audit_records", "id"),
    ("runtime_duc_decisions", "id"),
    ("runtime_sessions", "id"),
    ("runtime_transitions", "id"),
    ("team_invites", "id"),
    ("team_members", "id"),
    ("templates", "id"),
    ("templates", "organization_id"),
    ("tickets", "created_by_id"),
    ("tickets", "id"),
    ("tickets", "organization_id"),
    ("token_blacklist", "id"),
    ("transactions", "id"),
    ("users", "id"),
]


def upgrade() -> None:
    # A1C.2 interrupted-recovery guard (canonical pattern from A1A Gate 3R):
    # if a prior run crashed mid-batch_alter_table, alembic leaves a stale
    # `_alembic_tmp_*` shadow table. DROP IF EXISTS so the next batch rebuild
    # does not collide with the orphan. Safe no-op on a clean DB.
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        bind.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '_alembic_tmp_%'"
        )).fetchall()  # introspect only; actual drops via raw exec below
        # SQLite cannot parameterize DROP TABLE inside batch_alter_table;
        # enumerate via Python and DROP IF EXISTS each.
        rows = bind.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '\\_alembic\\_tmp\\_%' ESCAPE '\\'"
        )).fetchall()
        for (tmp_name,) in rows:
            bind.execute(sa.text(f"DROP TABLE IF EXISTS \"{tmp_name}\""))
    else:
        # PostgreSQL: alembic batch_alter_table uses a temp shadow table only
        # on SQLite. On PG, ALTER COLUMN proceeds in place; no shadow cleanup
        # needed. Defensive belt-and-suspenders:
        rows = bind.execute(sa.text(
            "SELECT to_regclass('public._alembic_tmp_%')"
        )).fetchall()
        # to_regclass returns NULL for non-existent; skip if all NULL
        for (rel,) in rows:
            if rel:
                bind.execute(sa.text(f"DROP TABLE IF EXISTS {rel} CASCADE"))

    # Batch alter — required for SQLite (cannot ALTER COLUMN directly);
    # harmless on PostgreSQL.
    bind = op.get_bind()
    dialect = bind.dialect.name

    for table, column in AFFECTED:
        if dialect == "sqlite":
            # SQLite needs batch_alter_table for type change; do per-table batch.
            # We defer to a single batch per table below to keep this loop simple.
            continue
        # PostgreSQL / others: direct ALTER COLUMN ... TYPE
        op.alter_column(
            table_name=table,
            column_name=column,
            type_=sa.String(length=12),
            existing_type=sa.String(),
            existing_nullable=False if column == "id" else True,
        )

    if dialect == "sqlite":
        # Per-table batch rebuild (SQLite cannot ALTER COLUMN directly).
        tables_to_rebuild = sorted({t for t, _ in AFFECTED})
        for table in tables_to_rebuild:
            cols_in_table = [c for t, c in AFFECTED if t == table]
            with op.batch_alter_table(table) as batch_op:
                for col in cols_in_table:
                    batch_op.alter_column(
                        column_name=col,
                        type_=sa.String(length=12),
                        existing_type=sa.String(),
                        existing_nullable=False if col == "id" else True,
                    )


def downgrade() -> None:
    """Restore unbounded varchar (matches pre-A1C.2 baseline)."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    for table, column in AFFECTED:
        if dialect == "sqlite":
            continue
        op.alter_column(
            table_name=table,
            column_name=column,
            type_=sa.String(),
            existing_type=sa.String(length=12),
            existing_nullable=False if column == "id" else True,
        )

    if dialect == "sqlite":
        tables_to_rebuild = sorted({t for t, _ in AFFECTED})
        for table in tables_to_rebuild:
            cols_in_table = [c for t, c in AFFECTED if t == table]
            with op.batch_alter_table(table) as batch_op:
                for col in cols_in_table:
                    batch_op.alter_column(
                        column_name=col,
                        type_=sa.String(),
                        existing_type=sa.String(length=12),
                        existing_nullable=False if col == "id" else True,
                    )
