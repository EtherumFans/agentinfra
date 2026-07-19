"""Phase A1A Gate 3R.3 — Trace capture status state machine.

Disambiguates the four meanings currently conflated by NULL
``run_history.trace_capture_status``:

  NULL (pre-3R.3) — could mean any of:
    (a) pre-Gate-3.3 historical row that never had trace_capture_status set
    (b) post-Gate-3.3 row that hasn't emitted any event yet
    (c) post-Gate-3.3 row whose first event emit is in-flight
    (d) row that will never have trace events (memory-mode dev test)

After 3R.3, NULL is reserved for (a) "pre-Gate-3.3 historical row" until
Migration 020 (Gate 3R.4) backfills all 244 NULLs to NEVER_CAPTURED_LEGACY.
New rows written after Gate 3R.3 carry one of:

  NEVER_CAPTURED_LEGACY  — pre-Gate-3.3 historical row (Migration 020 backfill)
  CAPTURE_PENDING        — record_run_start wrote the row; awaiting first emit
  CAPTURED               — at least one DbRunTraceStore.append succeeded
  FAILED                 — at least one DB write raised; events may be lost
  FALLBACK_MEMORY        — store was InMemoryRunTraceStore (dev/test only)

DB CHECK constraint widening from {PERSISTED, FAILED, FALLBACK_MEMORY}
to the full 5-class set lands in Migration 020 (Gate 3R.4). Until then,
``_mark_trace_capture_status`` is best-effort: writes of the new values
are logged at WARNING if SQLite's CHECK rejects them, and the run itself
is allowed to continue.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TraceCaptureState:
    """The 5-class taxonomy for ``run_history.trace_capture_status``.

    Stored as plain strings (not Python enums) so they round-trip
    through SQLite + JSON without serialization glue. Keep the string
    values stable — auditors + the Console RunTrace page may switch
    on them.
    """

    # Historical rows that predate Gate 3.3. Migration 020 backfills
    # all 244 NULLs to this value in one pass.
    NEVER_CAPTURED_LEGACY = "NEVER_CAPTURED_LEGACY"

    # record_run_start stamped this row; no trace events yet. This is
    # the value the row carries between INSERT and the first
    # DbRunTraceStore.append (or the InMemoryRunTraceStore equivalent).
    CAPTURE_PENDING = "CAPTURE_PENDING"

    # At least one DbRunTraceStore.append succeeded for this run.
    # Supersedes the Gate 3.3-era PERSISTED literal — Migration 020
    # does NOT rename existing rows; the literal "PERSISTED" is kept
    # in the allowlist for backwards compat. New rows use CAPTURED.
    CAPTURED = "CAPTURED"
    PERSISTED = "PERSISTED"  # deprecated alias — Gate 3.3-era literal

    # At least one DbRunTraceStore.append raised; events may be lost.
    FAILED = "FAILED"

    # Store was InMemoryRunTraceStore (dev/test only). Cloud-mode
    # Settings validation refuses to boot when RUNTRACE_STORE=memory,
    # so this value should never appear on a production row.
    FALLBACK_MEMORY = "FALLBACK_MEMORY"

    # Canonical allowlist for the new state machine. The DB CHECK
    # constraint widening (Migration 020) uses this tuple.
    ALL_STATES: frozenset[str] = frozenset({
        NEVER_CAPTURED_LEGACY,
        CAPTURE_PENDING,
        CAPTURED,
        PERSISTED,        # backwards compat with Gate 3.3 rows
        FAILED,
        FALLBACK_MEMORY,
    })

    # States considered "answered" — the run reached a definite
    # capture outcome, the auditor can interpret the row without
    # further context. NULL and CAPTURE_PENDING are NOT answered.
    ANSWERED_STATES: frozenset[str] = frozenset({
        NEVER_CAPTURED_LEGACY,
        CAPTURED,
        PERSISTED,
        FAILED,
        FALLBACK_MEMORY,
    })

    @classmethod
    def is_answered(cls, status: Optional[str]) -> bool:
        """True if the status represents a definite capture outcome.

        NULL → False (pre-3R.3 row, will be backfilled by Migration 020).
        CAPTURE_PENDING → False (awaiting first emit).
        All others → True.
        """
        if status is None:
            return False
        return status in cls.ANSWERED_STATES

    @classmethod
    def is_lost(cls, status: Optional[str]) -> bool:
        """True if trace events for this run are known to be unavailable.

        Used by the RunTrace page + the audit dashboard to decide
        whether to show "trace unavailable" vs "trace pending".
        """
        return status in {
            cls.NEVER_CAPTURED_LEGACY,
            cls.FAILED,
            cls.FALLBACK_MEMORY,
        }

    @classmethod
    def normalize(cls, status: Optional[str]) -> Optional[str]:
        """Map legacy literals to the canonical form.

        - PERSISTED → CAPTURED (canonical form post-3R.3)
        - Other values pass through unchanged
        - None passes through (handled separately by callers)

        Note: Migration 020 will rewrite existing PERSISTED rows to
        CAPTURED. Until then, readers should treat both literals as
        equivalent. ``normalize`` exists so new code can use the
        canonical form without breaking on legacy rows.
        """
        if status == cls.PERSISTED:
            return cls.CAPTURED
        return status


__all__ = ["TraceCaptureState"]
