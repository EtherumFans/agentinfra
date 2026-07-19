"""Phase A1A Gate 3R.4 — Stable trace event identity + capture state widening.

Revision ID: 020
Revises: 019
Create Date: 2026-07-19

This migration closes two gaps surfaced by Gate 3R.0 baseline:

§1 STABLE EVENT IDENTITY (charter §3R.4)

  The pre-3R.4 identity was the composite UNIQUE (run_id, step, ts)
  added by Migration 019. ``ts`` is ``time.time()`` — float seconds
  with microsecond precision. Two problems:

    a) Floats aren't reliably sortable across process restarts (NTP
       slew, wall vs monotonic). The RunTrace page orders by ts and
       can render events out of order if the clock moves backwards.
    b) Same-step events at the same microsecond collide and the
       second INSERT raises IntegrityError. The 9-step Corti
       timeline makes this unlikely per-run, but multi-stage
       orchestrators (e.g. MedCodER's 5-stage rerank) emit
       multiple TOOLS_CALL events that can land in the same
       microsecond.

  Fix: add ``event_id`` (UUID string, canonical identity) and
  ``sequence_number`` (int per trace_id, monotonic ordering). The
  UNIQUE (run_id, step, ts) constraint is kept as a defensive
  dedup, but the canonical identity is now event_id — readers
  sort by sequence_number when present, else fall back to ts.

  A ``trace_id`` column is also added so events can be grouped
  across multi-trace runs (e.g. parent orchestrator trace + child
  agent traces). run_history already has a trace_id column; this
  migration propagates it to events.

§2 CAPTURE STATE WIDENING (Gate 3R.3 carry-over)

  Migration 019 added a CHECK constraint on
  run_history.trace_capture_status limiting it to {PERSISTED, FAILED,
  FALLBACK_MEMORY}. Gate 3R.3 introduced three new literals
  (NEVER_CAPTURED_LEGACY, CAPTURE_PENDING, CAPTURED) plus the
  deprecated PERSISTED alias. This migration widens the CHECK to
  include all 6 values.

§3 BACKFILL — NULL → NEVER_CAPTURED_LEGACY

  All 244 NULL trace_capture_status rows predate Gate 3.3. They are
  backfilled to NEVER_CAPTURED_LEGACY in one pass. After backfill,
  NULL is reserved for "trace_capture_status has not yet been
  computed" (e.g. a row written by a future migration that hasn't
  populated the column yet).

§4 EXISTING PERSISTED ROWS → CAPTURED

  Optional canonicalization. TraceCaptureState.normalize() maps
  PERSISTED → CAPTURED at read time, so this rewrite is NOT load-
  bearing. We do it anyway so DB-level queries (GROUP BY, COUNT)
  see one literal instead of two. Zero rows have PERSISTED today
  (Gate 3R.0 §14 confirms all 244 are NULL), so the rewrite is a
  no-op on the dev DB. Production DBs that ran Gate 3.3 before
  Gate 3R.4 may have PERSISTED rows — this clause cleans them up.

Backwards compatibility:

  - All four new columns are nullable. Old readers that don't know
    about event_id / sequence_number / trace_id continue to work.
  - The CHECK widening accepts every value the old CHECK accepted,
    plus the new literals. No row is invalidated.
  - The backfill is idempotent: re-running only updates rows where
    trace_capture_status IS NULL, which after first run is zero.

Downgrade:

  Reversing the column drops is straightforward. The CHECK narrowing
  is more delicate — we drop the wide CHECK then re-add the narrow
  one (which would fail if any row carries a new-literal status).
  Production downgrade therefore requires first rewriting all
  NEVER_CAPTURED_LEGACY / CAPTURE_PENDING / CAPTURED rows back to
  PERSISTED or NULL. The downgrade here does NOT do that rewrite
  automatically; operators downgrading from 3R.4 → 3R.3 must do it
  manually. The narrow CHECK allows NULL, so setting all new-literal
  rows to NULL is the safest downgrade path.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Single source of truth — must mirror the constants in
# app/services/trace_capture_state.py::TraceCaptureState.ALL_STATES.
_TRACE_CAPTURE_STATUS_VALUES = (
    "'NEVER_CAPTURED_LEGACY'",
    "'CAPTURE_PENDING'",
    "'CAPTURED'",
    "'PERSISTED'",          # deprecated alias
    "'FAILED'",
    "'FALLBACK_MEMORY'",
)
_TRACE_CAPTURE_STATUS_LIST = ", ".join(_TRACE_CAPTURE_STATUS_VALUES)


def upgrade() -> None:
    # ── §0 Defensive cleanup — DROP IF EXISTS stale batch_alter_table
    # temp tables left over from an interrupted Migration 019 (or this
    # migration). SQLite's batch_alter_table recreates the target table
    # via a temp `_alembic_tmp_<table>` shadow; if a previous run was
    # killed mid-migration, the shadow lingers and the next attempt
    # fails with "table _alembic_tmp_X already exists". This is the
    # exact failure Gate 3.7 hit during Migration 019.
    #
    # DROP IF EXISTS is a no-op on Postgres (uses IF EXISTS clause) and
    # on SQLite (since we use raw execute). It only fires when the
    # shadow actually exists.
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_trace_events")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_run_history")

    # ── §1 Add stable identity columns to run_trace_events ───────
    # All four columns are nullable so the upgrade is online — old
    # readers ignore them, new readers populate them on INSERT.
    with op.batch_alter_table("run_trace_events") as batch_op:
        batch_op.add_column(sa.Column(
            "event_id",
            sa.String(length=64),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "sequence_number",
            sa.Integer(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "trace_id",
            sa.String(length=64),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            "identity_source",
            sa.String(length=32),
            nullable=True,
        ))
        # Canonical identity is event_id. Pre-3R.4 rows have NULL
        # event_id; readers fall back to (run_id, step, ts).
        batch_op.create_index(
            "ix_run_trace_events_event_id",
            ["event_id"],
            unique=True,
            postgresql_where=sa.text("event_id IS NOT NULL"),
        )
        # Monotonic ordering within a trace
        batch_op.create_index(
            "ix_run_trace_events_trace_seq",
            ["trace_id", "sequence_number"],
        )
        # Trace lookup (also covers run_id index but trace_id is
        # the canonical grouping post-3R.4)
        batch_op.create_index(
            "ix_run_trace_events_trace_id",
            ["trace_id"],
        )

    # ── §2 Widen CHECK on run_history.trace_capture_status ───────
    # Migration 019 added chk_run_history_trace_cap with the narrow
    # set {PERSISTED, FAILED, FALLBACK_MEMORY}. Drop + re-add with
    # the widened set so 3R.3's new literals are accepted.
    with op.batch_alter_table("run_history") as batch_op:
        batch_op.drop_constraint(
            "chk_run_history_trace_cap", type_="check",
        )
        batch_op.create_check_constraint(
            "chk_run_history_trace_cap",
            condition=(
                f"trace_capture_status IS NULL OR "
                f"trace_capture_status IN ({_TRACE_CAPTURE_STATUS_LIST})"
            ),
        )

    # ── §3 Backfill NULL → NEVER_CAPTURED_LEGACY ─────────────────
    # Idempotent — re-running only updates rows where status IS NULL.
    op.execute(
        "UPDATE run_history SET trace_capture_status = 'NEVER_CAPTURED_LEGACY' "
        "WHERE trace_capture_status IS NULL"
    )

    # ── §4 Optional canonicalization: PERSISTED → CAPTURED ───────
    # No-op on the dev DB (Gate 3R.0 §14 confirmed zero PERSISTED
    # rows). Production DBs may have PERSISTED rows from Gate 3.3.
    op.execute(
        "UPDATE run_history SET trace_capture_status = 'CAPTURED' "
        "WHERE trace_capture_status = 'PERSISTED'"
    )


def downgrade() -> None:
    # Reverse the backfill: NEVER_CAPTURED_LEGACY → NULL so the
    # narrow CHECK (added back below) accepts the rows. CAPTURED
    # is rewritten to PERSISTED so the narrow CHECK accepts it too.
    # CAPTURE_PENDING and FAILED/FALLBACK_MEMORY are not rewritten —
    # operators downgrading must do that manually if any rows carry
    # those literals. FAILED and FALLBACK_MEMORY are in BOTH the
    # wide and narrow CHECK allowlists, so they're left alone.
    op.execute(
        "UPDATE run_history SET trace_capture_status = NULL "
        "WHERE trace_capture_status = 'NEVER_CAPTURED_LEGACY'"
    )
    op.execute(
        "UPDATE run_history SET trace_capture_status = 'PERSISTED' "
        "WHERE trace_capture_status = 'CAPTURED'"
    )

    # Restore narrow CHECK (fails if any CAPTURE_PENDING rows exist
    # — see comment above)
    with op.batch_alter_table("run_history") as batch_op:
        batch_op.drop_constraint(
            "chk_run_history_trace_cap", type_="check",
        )
        batch_op.create_check_constraint(
            "chk_run_history_trace_cap",
            condition=(
                "trace_capture_status IS NULL OR "
                "trace_capture_status IN ('PERSISTED', 'FAILED', 'FALLBACK_MEMORY')"
            ),
        )

    # Drop the new columns + indexes
    with op.batch_alter_table("run_trace_events") as batch_op:
        batch_op.drop_index("ix_run_trace_events_trace_id")
        batch_op.drop_index("ix_run_trace_events_trace_seq")
        batch_op.drop_index("ix_run_trace_events_event_id")
        batch_op.drop_column("identity_source")
        batch_op.drop_column("trace_id")
        batch_op.drop_column("sequence_number")
        batch_op.drop_column("event_id")
