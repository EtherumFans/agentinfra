"""Legacy tenancy reconciliation — 7-class attribution taxonomy (Gate 3.1)

Revision ID: 017
Revises: 016
Create Date: 2026-07-18

Phase A1A Gate 3.1 — Legacy Tenancy Attribution Reconciliation.

Migration 016 introduced the 4-class ``tenancy_classification`` column
and backfilled all NULL-organization rows via a "latest membership
wins" heuristic. Gate 3.1 §3 splits ``LEGACY_TENANT_KNOWN`` into three
sub-classes so future auditors can distinguish rows whose organization
was *verified* by request-level evidence from rows where it was merely
*inferred* via user-membership:

  Before (4 classes)                      After (7 classes)
  --------------------------------------- ---------------------------------
  MODERN                                  MODERN  (unchanged)
  MODERN_SYSTEM  (added by Gate 2 code)   MODERN_SYSTEM
  LEGACY_TENANT_KNOWN (430 rows)          LEGACY_TENANT_VERIFIED     *
                                          LEGACY_TENANT_INFERRED     *
                                          LEGACY_TENANT_AMBIGUOUS    *
  LEGACY_TENANT_UNKNOWN (6 rows)          LEGACY_TENANT_UNKNOWN
                                          MODERN_SYSTEM  (1 row, the
                                           ``api_client.authentication_rejected``
                                           security event)
  QUARANTINED                             QUARANTINED  (unchanged)

This migration also adds six attribution-provenance columns to both
``run_history`` and ``audit_logs`` (charter §3.1 §4):

  - ``tenancy_attribution_source``      — which evidence path was used
  - ``tenancy_attribution_confidence``  — verified | inferred | ambiguous | none
  - ``tenancy_attribution_migration``   — "016" or "017"
  - ``tenancy_attributed_at``           — when the attribution was computed
  - ``tenancy_original_org_id``         — the org_id before backfill (audit trail)
  - ``tenancy_candidate_count``         — how many candidate orgs were considered

The actual classification work is done by
``app.services.legacy_tenancy_attribution.reclassify_table`` — the
classifier reads each row + all join-able evidence and produces a
verdict. The migration is a thin DDL + driver wrapper.

IDEMPOTENT: re-running this migration re-evaluates every legacy row
and updates the columns to match. If a future ``runtime_sessions`` row
is added retroactively with strong evidence, the next run of the
classifier will promote the row from INFERRED → VERIFIED. MODERN rows
written after Gate 2 are skipped (their attribution is "modern_write_path"
by definition and the classifier only acts on legacy rows).

This migration does NOT modify Migration 016. Charter §3.1 §1.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns added to both run_history and audit_logs.
_ATTRIBUTION_COLUMNS: list[tuple[str, sa.types.TypeEngine, str]] = [
    (
        "tenancy_attribution_source",
        sa.String(length=64),
        (
            "modern_write_path | api_client_binding | session_binding | "
            "context_binding | request_correlation | user_membership_latest "
            "| user_membership_at_time | user_single_membership_history | "
            "security_event | no_user_id_no_candidate | user_id_no_membership"
        ),
    ),
    (
        "tenancy_attribution_confidence",
        sa.String(length=16),
        "verified | inferred | ambiguous | none",
    ),
    (
        "tenancy_attribution_migration",
        sa.String(length=8),
        "Which migration last touched this row's attribution (016 or 017).",
    ),
    (
        "tenancy_attributed_at",
        sa.DateTime(timezone=True),
        "When the attribution was last computed.",
    ),
    (
        "tenancy_original_org_id",
        sa.String(length=12),
        "Original organization_id before backfill; NULL means it was always NULL.",
    ),
    (
        "tenancy_candidate_count",
        sa.Integer(),
        "How many candidate orgs were considered.",
    ),
]


def _add_attribution_columns(table: str) -> None:
    for col_name, col_type, comment in _ATTRIBUTION_COLUMNS:
        op.add_column(
            table,
            sa.Column(col_name, col_type, nullable=True, comment=comment),
        )


def _drop_attribution_columns(table: str) -> None:
    # Reverse order for cleanliness (matches typical DROP COLUMN convention).
    for col_name, _type, _comment in reversed(_ATTRIBUTION_COLUMNS):
        op.drop_column(table, col_name)


def upgrade() -> None:
    # ── 1. Add attribution columns to both tables ──────────────────
    _add_attribution_columns("run_history")
    _add_attribution_columns("audit_logs")

    # ── 2. Stamp every MODERN row with provenance ───────────────────
    # MODERN rows were written by the modern write path with non-NULL
    # organization_id; their attribution is implicit. We still record
    # source/confidence/migration so the columns are non-NULL for every
    # classified row.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE run_history SET "
            "  tenancy_attribution_source = 'modern_write_path', "
            "  tenancy_attribution_confidence = 'verified', "
            "  tenancy_attribution_migration = '016', "
            "  tenancy_attributed_at = CURRENT_TIMESTAMP, "
            "  tenancy_original_org_id = organization_id, "
            "  tenancy_candidate_count = 1 "
            "WHERE tenancy_classification = 'MODERN' "
            "  AND tenancy_attribution_source IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE audit_logs SET "
            "  tenancy_attribution_source = 'modern_write_path', "
            "  tenancy_attribution_confidence = 'verified', "
            "  tenancy_attribution_migration = '016', "
            "  tenancy_attributed_at = CURRENT_TIMESTAMP, "
            "  tenancy_original_org_id = organization_id, "
            "  tenancy_candidate_count = 1 "
            "WHERE tenancy_classification = 'MODERN' "
            "  AND tenancy_attribution_source IS NULL"
        )
    )

    # ── 3. Run the evidence-based classifier on every legacy row ────
    # Import here so the migration reloads the latest service module
    # state (idempotent re-runs after classifier updates).
    from app.services.legacy_tenancy_attribution import reclassify_table

    rh_counts = reclassify_table(bind, table="run_history")
    al_counts = reclassify_table(bind, table="audit_logs")

    # Print summary into the alembic log for audit trail.
    print(f"\n[alembic 017] run_history reclassification: {rh_counts}")
    print(f"[alembic 017] audit_logs reclassification:  {al_counts}")


def downgrade() -> None:
    # Drop the new columns. We DO NOT undo the classification changes
    # (LEGACY_TENANT_INFERRED → LEGACY_TENANT_KNOWN, MODERN_SYSTEM →
    # LEGACY_TENANT_UNKNOWN) because (a) the more specific classification
    # is strictly more informative and (b) reverting would re-create
    # the over-stated "KNOWN" claim that Gate 3 was created to fix.
    _drop_attribution_columns("audit_logs")
    _drop_attribution_columns("run_history")
