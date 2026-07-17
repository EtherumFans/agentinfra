"""Phase A1A Gate 2 §3 — Cloud-mode fail-closed tenancy guard.

In cloud mode, every tenant-owned row MUST carry a non-null
``organization_id`` at write time. This module is the single chokepoint
enforcing that invariant across the four tenant-owned surfaces:

  - ``run_history``            (via ``run_lifecycle.record_run_start``)
  - ``audit_logs``             (via ``middleware.audit.log_action``)
  - ``idempotency_records``    (via ``idempotency_service.acquire_or_replay``)
  - ``preview_sessions``       (via ``api.preview_sessions.create_preview_session``)

Design:

- ``assert_tenancy_for_write(organization_id, table_name)`` is the guard.
  In local mode it is a no-op (single-tenant dev workflow). In cloud
  mode it raises ``TenancyViolationError`` (mapped to HTTP 500 by the
  FastAPI handlers, since a NULL org_id at write time is always a
  server-side bug, never the caller's fault).
- The guard is called BEFORE the SQLAlchemy ``db.add()`` so the row
  never enters the flush. This means the audit row mirrors the
  invariants of the row it audits — there's no chance of a NULL-org
  audit row slipping into the table.
- The guard is also called at the top of ``log_action`` even though
  some audit events (system-level, no operator context) legitimately
  have NULL org_id. For those, the caller passes
  ``organization_id=""`` explicitly with ``allow_null_org=True`` to
  record a system-scope audit row. Cloud mode then tags the row as
  ``MODERN_SYSTEM`` (still has the classification column populated).
  This closes the "0/17 callers stamp org_id at column level" gap
  (A1A-G2-F03) without rewriting every caller.

See reports/phase-a1a/A1A_GATE2_TENANCY_SURVEY.md §3.2 and §7.1.
"""
from __future__ import annotations

from typing import Optional


# Cloud-mode tenancy classification for rows that intentionally have
# no owning organization (system bootstrap, health checks, etc.).
# Distinct from LEGACY_TENANT_UNKNOWN so operator queries can separate
# "intentional system row" from "pre-Gate-2 historical row".
CLASS_MODERN_SYSTEM = "MODERN_SYSTEM"


def _is_cloud_mode() -> bool:
    """Read deployment mode directly from env (test-safe).

    ``tests/unit/app/test_config_fail_closed.py`` reloads ``app.config``
    via ``importlib.reload`` to verify boot-time policy. That replaces
    the module-level ``settings`` object, leaving any cached reference
    stale. Reading directly from ``os.environ`` keeps the guard in
    sync with whatever env state the currently-running test asserts,
    including after monkeypatch.delenv cleanup.
    """
    import os
    return os.environ.get("ICODER_DEPLOYMENT_MODE", "local") == "cloud"


class TenancyViolationError(RuntimeError):
    """Raised when a tenant-owned write would commit with NULL org_id.

    Mapped to HTTP 500 by the API layer. Always a server-side bug:
    either a caller forgot to resolve org_id, or the auth context
    failed to populate it. The user cannot fix this by retrying.
    """

    def __init__(self, table_name: str, *, hint: str = "") -> None:
        self.table_name = table_name
        self.hint = hint
        msg = (
            f"[A1A Gate 2 fail-closed] cloud mode refuses to commit "
            f"{table_name!r} row with NULL organization_id"
        )
        if hint:
            msg += f" — {hint}"
        super().__init__(msg)


def assert_tenancy_for_write(
    organization_id: Optional[str],
    table_name: str,
    *,
    allow_null_org: bool = False,
) -> None:
    """Refuse NULL org_id writes in cloud mode.

    Parameters
    ----------
    organization_id
        The org_id that will be stamped on the row. May be ``None`` or
        empty string; both are treated as NULL for the purpose of this
        check (the idempotency service normalizes None → "" sentinel
        for UNIQUE semantics, but both are forbidden in cloud mode).
    table_name
        Name of the table being written. Appears in the error message
        so triage can immediately locate the offending write path.
    allow_null_org
        Set to True for system-scope rows that legitimately have no
        owning org (e.g. ``system.startup`` audit events). In cloud
        mode these are tagged ``MODERN_SYSTEM`` rather than rejected.

    Raises
    ------
    TenancyViolationError
        If ``ICODER_DEPLOYMENT_MODE=cloud`` AND ``organization_id`` is
        empty/None AND ``allow_null_org`` is False.
    """
    if not _is_cloud_mode():
        # Local mode: single-tenant dev workflow allows NULL org_id.
        return
    org_id = (organization_id or "").strip()
    if org_id:
        return  # Happy path: caller supplied a real org_id.
    if allow_null_org:
        return  # Caller asserted this is a system-scope row.
    raise TenancyViolationError(
        table_name,
        hint=(
            "caller must resolve organization_id from "
            "current_org / current_client before writing"
        ),
    )


def classify_modern_write(
    organization_id: Optional[str],
    *,
    allow_null_org: bool = False,
) -> Optional[str]:
    """Return the tenancy_classification to stamp on a new row.

    - Non-empty ``organization_id`` → ``MODERN``
    - Empty/None ``organization_id`` + ``allow_null_org=True`` →
      ``MODERN_SYSTEM`` (intentional system row)
    - Empty/None ``organization_id`` without ``allow_null_org`` →
      ``assert_tenancy_for_write`` raises before this returns. But
      for local mode (no guard), we return None so the column stays
      NULL, preserving the single-tenant dev workflow.

    This ensures every NEW row written in cloud mode is explicitly
    classified, leaving no ambiguity for future audits.
    """
    org_id = (organization_id or "").strip()
    if org_id:
        return "MODERN"
    if allow_null_org:
        return CLASS_MODERN_SYSTEM
    return None  # local mode, single-tenant NULL allowed


__all__ = [
    "CLASS_MODERN_SYSTEM",
    "TenancyViolationError",
    "assert_tenancy_for_write",
    "classify_modern_write",
]
