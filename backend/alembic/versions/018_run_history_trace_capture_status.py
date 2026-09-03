"""Phase A1A Gate 3.3 — add trace_capture_status to run_history.

Revision ID: 018
Revises: 017
Create Date: 2026-07-19

Adds two columns:

  trace_capture_status          VARCHAR(16), nullable, indexed
  trace_capture_failure_reason  VARCHAR(255), nullable

``trace_capture_status`` records whether the run's trace events
actually reached the persistent ``run_trace_events`` table. Values:

  PERSISTED       — DbRunTraceStore.append succeeded for all events
  FAILED          — at least one DB write raised; events may be lost
  FALLBACK_MEMORY — store was InMemoryRunTraceStore (dev/test only)
  NULL            — row written before Gate 3.3 (backwards compat)

When ``settings.RUNTRACE_FAIL_CLOSED=True`` and a write fails, the
exception is propagated to the caller instead of being swallowed;
this migration supplies the column that records the failure mode
for the audit trail when settings allow continuation.

Backwards compatibility: existing 240 run_history rows are left
NULL — they predate Gate 3.3. NULL is treated by readers as
"unknown — do not fail the read", so the migration is safe to
replay. New rows written after Gate 3.3 will be stamped
PERSISTED / FAILED / FALLBACK_MEMORY by the emit path.

The down migration drops both columns. No data is preserved on
downgrade — the columns only existed for audit provenance.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "run_history"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "trace_capture_status",
            sa.String(length=16),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "trace_capture_failure_reason",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_run_history_trace_capture_status",
        _TABLE,
        ["trace_capture_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_history_trace_capture_status", table_name=_TABLE)
    op.drop_column(_TABLE, "trace_capture_failure_reason")
    op.drop_column(_TABLE, "trace_capture_status")
