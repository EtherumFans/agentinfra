"""Add tenancy_classification to run_history + audit_logs (Phase A1A Gate 2)

Revision ID: 016
Revises: 015
Create Date: 2026-07-17

Phase A1A Gate 2 — Tenancy and Data Isolation. Adds a
`tenancy_classification` column to both `run_history` and `audit_logs`
so historical NULL-organization rows can be categorized per the A1A
charter §3 rules:

  - MODERN                — row was written with non-null organization_id
                            (the modern write path; the only state that
                            NEW data should ever be in).
  - LEGACY_TENANT_KNOWN   — row has NULL organization_id but a reliable
                            user_id → organization_id mapping exists via
                            `organization_members`. The mapping is used
                            to BACKFILL organization_id at migration time
                            so the row becomes tenant-scoped.
  - LEGACY_TENANT_UNKNOWN — row has NULL organization_id and no reliable
                            user_id → org mapping. organization_id stays
                            NULL; tenant-scoped queries will continue to
                            exclude this row.
  - QUARANTINED           — row flagged for manual review (sensitive
                            content, ambiguous provenance). Not set by
                            this migration; reserved for future operator
                            action.

Backfill evidence (data/icoder.db, 2026-07-17):
  run_history  235 NULL → 230 LEGACY_TENANT_KNOWN + 5 LEGACY_TENANT_UNKNOWN
  audit_logs   201 NULL → 200 LEGACY_TENANT_KNOWN + 1 LEGACY_TENANT_UNKNOWN

After backfill, every NULL-organization row is tagged so it can be:
  - included in tenant-scoped queries (LEGACY_TENANT_KNOWN), or
  - excluded from tenant-scoped queries but retained for audit
    (LEGACY_TENANT_UNKNOWN), or
  - quarantined for human review (QUARANTINED).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Classification constants (mirror app.models.run_history / audit_log) ──
CLASS_MODERN = "MODERN"
CLASS_LEGACY_KNOWN = "LEGACY_TENANT_KNOWN"
CLASS_LEGACY_UNKNOWN = "LEGACY_TENANT_UNKNOWN"
CLASS_QUARANTINED = "QUARANTINED"


def upgrade() -> None:
    # ── 1. Add tenancy_classification column to run_history ──────────
    op.add_column(
        "run_history",
        sa.Column(
            "tenancy_classification",
            sa.String(32),
            nullable=True,
            comment=(
                "MODERN | LEGACY_TENANT_KNOWN | LEGACY_TENANT_UNKNOWN | "
                "QUARANTINED. See alembic 016."
            ),
        ),
    )
    op.create_index(
        "ix_run_history_tenancy_classification",
        "run_history",
        ["tenancy_classification"],
    )

    # ── 2. Add tenancy_classification column to audit_logs ───────────
    op.add_column(
        "audit_logs",
        sa.Column(
            "tenancy_classification",
            sa.String(32),
            nullable=True,
            comment=(
                "MODERN | LEGACY_TENANT_KNOWN | LEGACY_TENANT_UNKNOWN | "
                "QUARANTINED. See alembic 016."
            ),
        ),
    )
    op.create_index(
        "ix_audit_logs_tenancy_classification",
        "audit_logs",
        ["tenancy_classification"],
    )

    # ── 3. Backfill run_history ──────────────────────────────────────
    # 3a. Rows with non-NULL organization_id → MODERN.
    op.execute(
        sa.text(
            "UPDATE run_history SET tenancy_classification = :cls "
            "WHERE organization_id IS NOT NULL "
            "AND tenancy_classification IS NULL"
        ).bindparams(cls=CLASS_MODERN)
    )
    # 3b. Rows with NULL organization_id but resolvable via
    # organization_members → BACKFILL organization_id + tag
    # LEGACY_TENANT_KNOWN. We pick the most recent membership if
    # multiple exist (MAX(created_at)).
    op.execute(
        sa.text(
            """
            UPDATE run_history
            SET organization_id = (
                    SELECT om.organization_id
                    FROM organization_members om
                    WHERE om.user_id = run_history.user_id
                    ORDER BY om.created_at DESC
                    LIMIT 1
                ),
                tenancy_classification = :cls
            WHERE organization_id IS NULL
              AND user_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM organization_members om
                WHERE om.user_id = run_history.user_id
              )
            """
        ).bindparams(cls=CLASS_LEGACY_KNOWN)
    )
    # 3c. Remaining NULL organization_id rows → LEGACY_TENANT_UNKNOWN.
    op.execute(
        sa.text(
            "UPDATE run_history SET tenancy_classification = :cls "
            "WHERE organization_id IS NULL "
            "AND tenancy_classification IS NULL"
        ).bindparams(cls=CLASS_LEGACY_UNKNOWN)
    )

    # ── 4. Backfill audit_logs (same pattern) ────────────────────────
    op.execute(
        sa.text(
            "UPDATE audit_logs SET tenancy_classification = :cls "
            "WHERE organization_id IS NOT NULL "
            "AND tenancy_classification IS NULL"
        ).bindparams(cls=CLASS_MODERN)
    )
    op.execute(
        sa.text(
            """
            UPDATE audit_logs
            SET organization_id = (
                    SELECT om.organization_id
                    FROM organization_members om
                    WHERE om.user_id = audit_logs.user_id
                    ORDER BY om.created_at DESC
                    LIMIT 1
                ),
                tenancy_classification = :cls
            WHERE organization_id IS NULL
              AND user_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM organization_members om
                WHERE om.user_id = audit_logs.user_id
              )
            """
        ).bindparams(cls=CLASS_LEGACY_KNOWN)
    )
    op.execute(
        sa.text(
            "UPDATE audit_logs SET tenancy_classification = :cls "
            "WHERE organization_id IS NULL "
            "AND tenancy_classification IS NULL"
        ).bindparams(cls=CLASS_LEGACY_UNKNOWN)
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_logs_tenancy_classification", table_name="audit_logs"
    )
    op.drop_column("audit_logs", "tenancy_classification")
    op.drop_index(
        "ix_run_history_tenancy_classification", table_name="run_history"
    )
    op.drop_column("run_history", "tenancy_classification")
    # NOTE: the upgrade() migration also backfilled organization_id on
    # LEGACY_TENANT_KNOWN rows. The downgrade does NOT undo that
    # backfill because (a) the values are correct and (b) re-nulling
    # them would re-create the G9-00 tenancy leak this migration closes.
