"""Phase A1A Gate 3.2 — Tenant Read Policy + Quarantine enforcement.

Charter §3.2 requirements:

1. Rows classified as ``LEGACY_TENANT_UNKNOWN``, ``LEGACY_TENANT_AMBIGUOUS``,
   or ``QUARANTINED`` are **invisible to normal tenant reads**. They are
   excluded from list / aggregate / usage / trace / SSE responses —
   not returned with a "deny" flag, simply absent, as if they did not
   exist for the calling tenant.

2. The denial is **exact 404, not 403**. Charter §3.2 §4: "普通租户读取
   Unknown → 404; 普通租户读取 Ambiguous → 404; 普通租户读取
   Quarantined → 404". No existence leak.

3. A separate Security Admin authorization path can read
   quarantined / unknown rows for forensics, but every access is
   audited via ``system_audit`` (Gate 3.6).

This module supplies:

- ``TENANT_VISIBLE_CLASSIFICATIONS`` — the allowlist.
- ``is_tenant_visible(classification)`` — predicate.
- ``apply_tenant_visibility_filter(stmt, classification_column)``
  — SQLAlchemy helper that adds the WHERE clause.
- ``enforce_tenant_visible_or_404(row, classification)``
  — point-read guard; raises HTTPException(404) on invisible rows.
- ``assert_security_admin_access(user, db, *, action, resource)``
  — role check + audit emit.

The helpers do NOT short-circuit the org-scope filter. Tenant
visibility is enforced IN ADDITION to org scoping. A MODERN row in
Org B remains invisible to an Org A Console JWT — that's already
handled by the store's ``get_run_scoped`` / RunHistory
``organization_id == org_id`` filter. This policy's job is the
orthogonal "what if the row's *own* classification is non-visible"
case.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import Column, Select
from sqlalchemy.sql.elements import ColumnClause

from app.middleware.tenancy_guard import (
    CLASS_LEGACY_AMBIGUOUS,
    CLASS_LEGACY_INFERRED,
    CLASS_LEGACY_VERIFIED,
    CLASS_MODERN_SYSTEM,
)

logger = logging.getLogger(__name__)


# ── Classification visibility set ───────────────────────────────────────


# Tenant-visible: rows that can appear in normal tenant reads.
# Includes both MODERN and the two "trusted legacy" classes that
# carry an organization_id we are willing to commit to.
TENANT_VISIBLE_CLASSIFICATIONS: frozenset[str] = frozenset({
    "MODERN",
    CLASS_LEGACY_VERIFIED,
    CLASS_LEGACY_INFERRED,
})

# Tenant-INVISIBLE: rows that must never appear in normal tenant reads.
# Map to exact-404 on point lookup, excluded on list/aggregate lookup.
TENANT_INVISIBLE_CLASSIFICATIONS: frozenset[str] = frozenset({
    "LEGACY_TENANT_UNKNOWN",
    CLASS_LEGACY_AMBIGUOUS,
    "QUARANTINED",
    CLASS_MODERN_SYSTEM,  # system-scope; no owning tenant
})


def is_tenant_visible(classification: Optional[str]) -> bool:
    """Should a row with this ``tenancy_classification`` appear in a
    normal tenant-scoped read?

    ``None`` (legacy NULL — e.g. rows written before Gate 2 on tables
    other than ``run_history`` / ``audit_logs``) is treated as
    **invisible**. Charter §3.2 §2 explicitly forbids "不可见" rows
    from being treated as visible by default.
    """
    if classification is None:
        return False
    return classification in TENANT_VISIBLE_CLASSIFICATIONS


# ── SQLAlchemy filter helper ────────────────────────────────────────────


def apply_tenant_visibility_filter(
    stmt: Select,
    classification_column: ColumnClause | Column,
    *,
    also_exclude_null: bool = True,
) -> Select:
    """Return ``stmt`` with a WHERE clause restricting rows to the
    tenant-visible classification set.

    Parameters
    ----------
    stmt
        The SQLAlchemy SELECT statement to filter.
    classification_column
        The column expression for ``tenancy_classification``.
    also_exclude_null
        If True (default), also exclude rows where the classification
        is NULL. This matters for tables that have not yet been
        migrated (e.g. ``encounters``, ``cdi_cases`` in the current
        schema) — a NULL classification should never appear in tenant
        reads.
    """
    stmt = stmt.where(
        classification_column.in_(tuple(TENANT_VISIBLE_CLASSIFICATIONS))
    )
    if also_exclude_null:
        stmt = stmt.where(classification_column.is_not(None))
    return stmt


# ── Point-read guard ────────────────────────────────────────────────────


def enforce_tenant_visible_or_404(
    *,
    classification: Optional[str],
    run_id: Optional[str] = None,
    resource: str = "resource",
) -> None:
    """Raise ``HTTPException(404)`` if the row is not tenant-visible.

    Use after fetching a single row by id — if the row's
    classification is invisible, return a uniform 404 that does NOT
    leak existence. The 404 message is the same as for a genuinely
    absent row.

    Charter §3.2 §4: exact 404, no existence leak.
    """
    if is_tenant_visible(classification):
        return
    # Don't echo the classification, run_id, or resource type in the
    # message — that would leak existence. Use a generic message.
    detail = f"no {resource} found"
    if run_id:
        # Adding run_id in the message would leak. We log internally
        # but do NOT echo to the client.
        logger.info(
            "tenant_read_policy 404: run_id=%s classification=%s resource=%s",
            run_id, classification, resource,
        )
    raise HTTPException(status_code=404, detail=detail)


# ── Security Admin authorization ───────────────────────────────────────


# Role that can read quarantined / unknown / ambiguous rows.
# Distinct from org-level ``admin`` (which is a hospital administrator
# scoped to one tenant). ``security_admin`` is a platform-level role
# that can see cross-tenant forensics.
SECURITY_ADMIN_ROLE = "security_admin"

# Users with these roles can pass the Security Admin gate.
SECURITY_ADMIN_ROLES: frozenset[str] = frozenset({
    SECURITY_ADMIN_ROLE,
    "platform_security_admin",
    "platform_auditor",
})


async def assert_security_admin_access(
    user: Any,
    db: Any,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Authorize a Security Admin read of quarantined / unknown data.

    Raises ``HTTPException(403)`` if the user lacks the role. On
    success, emits a ``security_admin.access`` audit event via
    ``system_audit`` (Gate 3.6).

    Callers MUST pass the resource being accessed so the audit row
    carries enough forensics to answer "who read what when".
    """
    role = _resolve_role(user)
    if role not in SECURITY_ADMIN_ROLES:
        logger.warning(
            "security_admin access DENIED user=%s role=%s action=%s resource=%s/%s",
            getattr(user, "id", None), role, action, resource_type, resource_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Security Admin role required for this action.",
        )

    # Audit the access. Imported lazily so the policy module has no
    # circular dependency on audit / system_audit.
    if db is None:
        # Caller has no DB session (typically a unit test). Fall back
        # to logger.warning so the access is still recorded.
        logger.warning(
            "security_admin access (db unavailable) user=%s action=%s resource=%s/%s reason=%s",
            getattr(user, "id", None), action, resource_type, resource_id, reason,
        )
    else:
        try:
            from app.services.system_audit import system_audit  # Gate 3.6
            await system_audit(
                db,
                action=f"security_admin.{action}",
                resource_type=resource_type,
                resource_id=resource_id,
                details={
                    "reason": reason,
                    "admin_user_id": getattr(user, "id", None),
                    "admin_role": role,
                },
            )
        except ImportError:
            # system_audit not yet wired (Gate 3.6 not done). Fall back to
            # logger.warning so the access is at least recorded in app logs.
            logger.warning(
                "security_admin access (audit unavailable) user=%s action=%s resource=%s/%s reason=%s",
                getattr(user, "id", None), action, resource_type, resource_id, reason,
            )


def _resolve_role(user: Any) -> Optional[str]:
    """Extract a role string from the user object.

    Supports both the legacy ``user.role`` attribute (string) and the
    org-membership-based role used by ``require_org_role`` (returns
    an ``OrganizationMember`` with a ``.role.value``). Returns None
    if no role can be resolved.
    """
    if user is None:
        return None
    # OrganizationMember path
    role_obj = getattr(user, "role", None)
    if role_obj is not None:
        # enum or string
        value = getattr(role_obj, "value", role_obj)
        return str(value)
    return None


__all__ = [
    "TENANT_VISIBLE_CLASSIFICATIONS",
    "TENANT_INVISIBLE_CLASSIFICATIONS",
    "SECURITY_ADMIN_ROLE",
    "SECURITY_ADMIN_ROLES",
    "is_tenant_visible",
    "apply_tenant_visibility_filter",
    "enforce_tenant_visible_or_404",
    "assert_security_admin_access",
]
