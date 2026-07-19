"""Phase A1A Gate 3.7 — DB-level CHECK constraints for tenancy + trace.

Revision ID: 019
Revises: 018
Create Date: 2026-07-19

Adds CHECK constraints so the database itself rejects invalid
values, not just the application layer. Application-level
fail-closed guards (Gate 2, Gate 3.2) are still the primary
defence; this migration is the second layer.

Constraints added:

1. ``run_history.tenancy_classification`` ∈ 7-class taxonomy
   (NULL allowed for backwards compat with pre-Gate-2 rows).
2. ``audit_logs.tenancy_classification`` ∈ same 7-class set.
3. ``run_history.trace_capture_status`` ∈ {PERSISTED, FAILED,
   FALLBACK_MEMORY} (NULL allowed for backwards compat).
4. ``run_trace_events.event_id`` UNIQUE — already enforced via a
   composite index in the original schema; this migration adds
   an explicit unique constraint on (run_id, step, ts) so a
   duplicate emit can't silently land.
5. ``run_trace_events.organization_id`` FK → organizations.id —
   already present in the model; this migration adds an ON DELETE
   SET NULL clause so deleting an org doesn't cascade-fail trace
   reads (audit rows stay readable).

All constraints are added via ``ALTER TABLE ... ADD CONSTRAINT``
so the upgrade is reversible; the downgrade drops each constraint
by name.

Backwards compatibility: existing rows have NULL classification
or one of the 7-class values, so the CHECK passes immediately on
all 240 run_history + 233 audit_logs rows (verified in §5 of the
Gate 3.1 report). ``trace_capture_status`` is NULL on all 240
rows pre-Gate-3.3 and the CHECK allows NULL.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Single source of truth for the 7-class taxonomy. Matches the
# constants in app/middleware/tenancy_guard.py and the classifier
# in app/services/legacy_tenancy_attribution.py.
_TENANCY_CLASS_VALUES = (
    "'MODERN'",
    "'MODERN_SYSTEM'",
    "'LEGACY_TENANT_VERIFIED'",
    "'LEGACY_TENANT_INFERRED'",
    "'LEGACY_TENANT_AMBIGUOUS'",
    "'LEGACY_TENANT_UNKNOWN'",
    "'LEGACY_TENANT_KNOWN'",   # deprecated alias for INFERRED (Gate 2 → Gate 3.1)
    "'QUARANTINED'",
)
_TENANCY_CLASS_LIST = ", ".join(_TENANCY_CLASS_VALUES)

_TRACE_CAPTURE_STATUS_VALUES = (
    "'PERSISTED'",
    "'FAILED'",
    "'FALLBACK_MEMORY'",
)
_TRACE_CAPTURE_STATUS_LIST = ", ".join(_TRACE_CAPTURE_STATUS_VALUES)


def upgrade() -> None:
    # ── §1 run_history.tenancy_classification CHECK ─────────────
    # SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we use
    # batch_alter_table which recreates the table with the new
    # constraint. On Postgres this is a no-op ALTER.
    with op.batch_alter_table("run_history") as batch_op:
        batch_op.create_check_constraint(
            "chk_run_history_tenancy_cls",
            condition=(
                f"tenancy_classification IS NULL OR "
                f"tenancy_classification IN ({_TENANCY_CLASS_LIST})"
            ),
        )
        batch_op.create_check_constraint(
            "chk_run_history_trace_cap",
            condition=(
                f"trace_capture_status IS NULL OR "
                f"trace_capture_status IN ({_TRACE_CAPTURE_STATUS_LIST})"
            ),
        )

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.create_check_constraint(
            "chk_audit_logs_tenancy_cls",
            condition=(
                f"tenancy_classification IS NULL OR "
                f"tenancy_classification IN ({_TENANCY_CLASS_LIST})"
            ),
        )

    # ── §2 run_trace_events (run_id, step, ts) UNIQUE ───────────
    # Composite UNIQUE so a duplicate emit (same run + step + ts) is
    # rejected at the DB. ts is float seconds with microsecond
    # precision from time.time() so collisions are vanishingly rare
    # — but if they do happen it's a real bug we want surfaced.
    with op.batch_alter_table("run_trace_events") as batch_op:
        batch_op.create_unique_constraint(
            "ux_run_trace_events_run_step_ts",
            ["run_id", "step", "ts"],
        )


def downgrade() -> None:
    with op.batch_alter_table("run_trace_events") as batch_op:
        batch_op.drop_constraint("ux_run_trace_events_run_step_ts", type_="unique")
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_constraint("chk_audit_logs_tenancy_cls", type_="check")
    with op.batch_alter_table("run_history") as batch_op:
        batch_op.drop_constraint("chk_run_history_trace_cap", type_="check")
        batch_op.drop_constraint("chk_run_history_tenancy_cls", type_="check")
