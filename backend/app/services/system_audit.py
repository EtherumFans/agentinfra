"""Phase A1A Gate 3.6 — System-level audit sink (MODERN_SYSTEM classification).

Charter §3.6 §3 requirement:

> System Event 不能通过通用布尔参数任意绕过组织门禁.

The old path was to call ``log_action(..., allow_null_org=True)`` for
system events. That created a hole — any caller could pass
``allow_null_org=True`` to bypass the tenancy guard for any action.
Gate 3.6 closes the hole by:

1. Centralising system-scope audit writes in this module.
2. Restricting the action namespace to an explicit allowlist
   (``SYSTEM_AUDIT_ACTIONS`` from ``legacy_tenancy_attribution``).
   Any caller that tries to ``system_audit(...)`` an action outside
   the allowlist gets ``ValueError`` — the call site must justify
   the new action by adding it to the allowlist (and updating the
   classifier to recognise it).
3. Stamping ``tenancy_classification = MODERN_SYSTEM`` on the row
   so the tenant read policy excludes it from normal reads
   (Gate 3.2). Only Security Admin can read these rows back
   (Gate 3.6 §4).
4. Recording ``attribution_source = security_event`` etc. so the
   audit trail explains why this row has no owning org.

Why a separate service (not just ``log_action(allow_null_org=True)``)?

- Fail-closed at the call site: callers can't forget to set the
  flag, can't set the wrong flag, and can't smuggle tenant events
  through the system path.
- One place to change if we ever add per-action rate limiting or
  redaction for system events.
- One place to grep when asking "what system events does this
  system emit?".
"""
from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.tenancy_guard import CLASS_MODERN_SYSTEM
from app.models.audit_log import AuditLog
from app.services.legacy_tenancy_attribution import SYSTEM_AUDIT_ACTIONS

logger = logging.getLogger(__name__)


# ── System action namespace ────────────────────────────────────────


# Phase A1A Gate 3.6 §2 — extend the system action allowlist with
# the new audit coverage charter §3.6 §1 demands:
#   - trace.read.success / trace.read.denied (Console + Security Admin)
#   - sse.denied (org mismatch / invisible classification)
#   - run.cancel / run.timeout / run.complete / run.failed
#   - idempotency.dedup
#   - context.clear (Phase 6 Gate 2 patient context isolation)
#   - api_client.rotate (Phase 7 Gate 5 secret rotation)
#   - security_admin.access (Gate 3.2 forensic read)
#
# We mutate the frozenset from legacy_tenancy_attribution because the
# classifier imports that module to decide whether to classify a row
# as MODERN_SYSTEM. Adding actions here automatically makes the
# classifier recognise them.
_SYSTEM_AUDIT_ACTIONS_EXTRA: frozenset[str] = frozenset({
    # Public registration must never self-assign a privileged platform role.
    "auth.register.denied.role_escalation",
    # Platform-wide user/tenant access administration. These events have no
    # single owning tenant and must remain invisible to tenant audit readers.
    "platform_admin.user_access_updated",
    "platform_admin.user_access_update_denied",
    "platform_admin.organization_updated",
    "org.invite.delivery_succeeded",
    "org.invite.delivery_retry_scheduled",
    "org.invite.delivery_dead_letter",
    # Gate 3.2 — Security Admin forensic reads
    "security_admin.access",
    # Gate 3.4 — SSE denials
    "sse.denied.org_mismatch",
    "sse.denied.invisible_classification",
    # Gate 3.5 — Console / partner trace denials
    "trace.read.denied.org_mismatch",
    "trace.read.denied.invisible_classification",
    # Gate 3R.1 — orphan-run denials (no authoritative RunHistory row)
    "sse.denied.orphan_run",
    "trace.read.denied.orphan_run",
    # Gate 3.6 — explicit run lifecycle events
    "run.cancel",
    "run.timeout",
    "run.complete",
    "run.failed",
    # CDI direct REST failures that occur after the main model stages but
    # before any clinical result is persisted or returned.
    "cdi.run.failed.required_gate_degraded",
    # Feedback never implies model-improvement permission.  These explicit,
    # tenant-owned mutations are the only authorization lifecycle events.
    "agentic.feedback.training_authorization.granted",
    "agentic.feedback.training_authorization.revoked",
    # Gate 3.6 — idempotency dedup event
    "idempotency.dedup",
    # Gate 3.6 — patient context clear (Phase 6 Gate 2)
    "context.clear",
    # Gate 3.6 — API client secret rotation (Phase 7 Gate 5)
    "api_client.rotate",
    # Gate 4.7 — retention purge events (per-tenant and system-scope)
    "retention.purge",
})

ALL_SYSTEM_AUDIT_ACTIONS: frozenset[str] = SYSTEM_AUDIT_ACTIONS | _SYSTEM_AUDIT_ACTIONS_EXTRA


# Action prefixes that accept any suffix — used when the suffix is
# itself a stable label (e.g. ``security_admin.read_quarantined``).
# Listing the prefix here keeps the fail-closed contract (unknown
# actions still raise) while allowing the small set of dynamic
# composites Security Admin emits.
_SYSTEM_AUDIT_ACTION_PREFIXES: tuple[str, ...] = (
    "security_admin.",   # any forensic read (read_quarantined / read_unknown / ...)
)


def _is_allowed_system_action(action: str) -> bool:
    """Allow exact-match or any prefix in ``_SYSTEM_AUDIT_ACTION_PREFIXES``."""
    if action in ALL_SYSTEM_AUDIT_ACTIONS:
        return True
    return any(action.startswith(p) for p in _SYSTEM_AUDIT_ACTION_PREFIXES)


# ── Emit helper ────────────────────────────────────────────────────


async def system_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Record a system-scope audit event.

    The row is written with ``organization_id = NULL`` and
    ``tenancy_classification = MODERN_SYSTEM`` so the tenant read
    policy excludes it from normal reads.

    Raises ``ValueError`` if ``action`` is not in
    ``ALL_SYSTEM_AUDIT_ACTIONS`` — callers MUST justify new actions
    by adding them to the allowlist (and updating the classifier).

    Returns the persisted AuditLog row (with .id populated after
    flush). Callers that don't need the row can ignore the return.
    """
    if not _is_allowed_system_action(action):
        raise ValueError(
            f"system_audit action {action!r} is not in the allowlist. "
            f"Add it to ALL_SYSTEM_AUDIT_ACTIONS in app.services.system_audit "
            f"AND to SYSTEM_AUDIT_ACTIONS in legacy_tenancy_attribution "
            f"(so the classifier recognises it as MODERN_SYSTEM)."
        )

    log_entry = AuditLog(
        organization_id=None,  # system-scope by definition
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        error_message=error_message,
        tenancy_classification=CLASS_MODERN_SYSTEM,
    )
    # Stamp the same attribution provenance as Migration 017 does for
    # MODERN_SYSTEM rows, so future audits can tell "this row was
    # MODERN_SYSTEM from day one" vs "this row was retroactively
    # classified by Migration 017".
    log_entry.tenancy_attribution_source = "security_event"
    log_entry.tenancy_attribution_confidence = "verified"
    log_entry.tenancy_attribution_migration = "018"
    log_entry.tenancy_attributed_at = datetime.now(UTC)
    log_entry.tenancy_candidate_count = 0
    log_entry.tenancy_original_org_id = None
    db.add(log_entry)
    try:
        await db.flush()
    except Exception as e:
        logger.error(
            "system_audit write failed: %s (action=%s resource=%s/%s)",
            e, action, resource_type, resource_id,
        )
        # Don't swallow — the caller may want to know. Re-raise so
        # the surrounding DB transaction rolls back; system events
        # are rare enough that a rollback cost is acceptable.
        raise
    return log_entry


# ── Phase A1A Gate 4.7 — tenant-owned system audit ──────────────────
#
# Some system-scope audit events are emitted BY the platform but
# ABOUT a specific tenant — e.g. a per-tenant scheduled job
# (``tenant_cron.fired``), a per-tenant rate-limit hit
# (``tenant_ratelimit.exceeded``), a per-tenant key-rotation event
# (``phi_key.rotated``), or a per-tenant audit-log purge
# (``retention.purge``). Pre-Gate-4.7 these calls had two bad options:
#
#   1. ``system_audit(...)`` — loses tenant attribution; the row
#      becomes MODERN_SYSTEM with NULL org_id and cannot be surfaced
#      in per-tenant compliance reports.
#   2. ``log_action(..., allow_null_org=False)`` — attaches org_id
#      but loses the MODERN_SYSTEM tag and the action-allowlist
#      guard. Any new action name could slip through without review.
#
# The new ``tenant_owned_system_audit`` helper closes the gap:
# validates the action is in ``ALL_SYSTEM_AUDIT_ACTIONS``, attaches
# the supplied ``organization_id``, and stamps both
# ``tenancy_classification = MODERN_SYSTEM`` (so operator console
# queries can filter by "system events for this tenant") and
# ``tenancy_attribution_source = security_event`` (so future audits
# know this was an intentional system emit, not a retroactive
# classification).
async def tenant_owned_system_audit(
    db: AsyncSession,
    *,
    organization_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Record a system-scope audit event attributed to a specific tenant.

    Use this instead of ``system_audit`` when the event is emitted BY
    the platform (so it needs the MODERN_SYSTEM tag and the action
    allowlist) but ABOUT a specific tenant (so it needs an org_id
    for per-tenant compliance reporting).

    ``organization_id`` MUST be a non-empty string — callers that
    genuinely have no tenant context should call ``system_audit``
    instead.

    Raises ``ValueError`` if:
      - ``organization_id`` is empty/None.
      - ``action`` is not in ``ALL_SYSTEM_AUDIT_ACTIONS``.
    """
    if not organization_id or not isinstance(organization_id, str):
        raise ValueError(
            "tenant_owned_system_audit requires a non-empty organization_id; "
            "use system_audit() for genuine system-scope events"
        )
    if not _is_allowed_system_action(action):
        raise ValueError(
            f"tenant_owned_system_audit action {action!r} is not in the "
            f"allowlist. Add it to ALL_SYSTEM_AUDIT_ACTIONS in "
            f"app.services.system_audit AND to SYSTEM_AUDIT_ACTIONS in "
            f"legacy_tenancy_attribution (so the classifier recognises "
            f"it as MODERN_SYSTEM)."
        )

    log_entry = AuditLog(
        organization_id=organization_id,  # tenant-attributed system event
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        error_message=error_message,
        tenancy_classification=CLASS_MODERN_SYSTEM,
    )
    # Stamp the same attribution provenance as system_audit, but
    # record the tenant attribution explicitly via candidate_count=1
    # and original_org_id=organization_id (the row is intentionally
    # tenant-owned from inception).
    log_entry.tenancy_attribution_source = "security_event"
    log_entry.tenancy_attribution_confidence = "verified"
    log_entry.tenancy_attribution_migration = "021"  # Gate 4.7
    log_entry.tenancy_attributed_at = datetime.now(UTC)
    log_entry.tenancy_candidate_count = 1
    log_entry.tenancy_original_org_id = organization_id
    db.add(log_entry)
    try:
        await db.flush()
    except Exception as e:
        logger.error(
            "tenant_owned_system_audit write failed: %s (action=%s "
            "org=%s resource=%s/%s)",
            e, action, organization_id, resource_type, resource_id,
        )
        raise
    return log_entry


__all__ = [
    "ALL_SYSTEM_AUDIT_ACTIONS",
    "system_audit",
    "tenant_owned_system_audit",
]
