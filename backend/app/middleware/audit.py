# iCoDer - Audit Logging Middleware
import logging
import os
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware.tenancy_guard import (
    assert_tenancy_for_write,
    classify_modern_write,
)
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    user_id: Optional[str],
    username: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    model_input_summary: Optional[str] = None,
    model_output_summary: Optional[str] = None,
    model_version: Optional[str] = None,
    tool_calls_made: Optional[dict] = None,
    tokens_used: Optional[int] = None,
    organization_id: Optional[str] = None,
    allow_null_org: bool = False,
    *,
    policy_decision: Optional[dict] = None,
    purpose_of_use: Optional[str] = None,
) -> AuditLog | None:
    """Record an audit log entry.

    Phase A1A Gate 2 §3 — cloud mode fail-closed: refuses to commit
    a NULL org_id audit row unless ``allow_null_org=True`` (system-
    scope events like ``system.startup``).

    Phase A1D.3 (A1C-B-010 + A1C-B-011) — keyword-only ``policy_decision``
    and ``purpose_of_use`` parameters. Merged into ``details`` after the
    A1A Gate 4.3 redactor. Existing 40+ call sites continue to work
    (both default to ``None``); Pilot env wiring will opt-in per route.

    ``policy_decision`` expected shape::

        {
            "decision": "allow" | "deny",
            "decision_reason": str,
            "rbac_role": str,            # UserRole.value or "system"
            "abac_purpose_match": str,    # "match" | "mismatch" | "n/a"
            "tenant_match": str,          # "match" | "mismatch"
        }
    """
    # Phase A1A Gate 2 §3: fail-closed guard fires BEFORE the try/except
    # so a tenancy violation propagates to the caller (it's a server-
    # side bug, not a "couldn't write audit" error).
    assert_tenancy_for_write(
        organization_id, "audit_logs",
        allow_null_org=allow_null_org,
    )
    # Phase A1D.2 (A1C-B-018) — operator-driven audit pause.
    # RB-3 PITR rollback scenarios need the operator to PAUSE audit
    # writes during the recovery window without stopping the service.
    # When ICODER_AUDIT_WRITE_PAUSED=true, skip the DB write but warn
    # so the operator sees the pause in logs. The fail-closed tenancy
    # guard above fires FIRST — pause must NEVER bypass tenancy.
    if os.environ.get("ICODER_AUDIT_WRITE_PAUSED", "false").lower() == "true":
        logger.warning(
            "audit_write_paused action=%r resource_type=%r resource_id=%r "
            "organization_id=%r — ICODER_AUDIT_WRITE_PAUSED=true (RB-3 PITR window)",
            action, resource_type, resource_id, organization_id,
        )
        return
    # Phase A1D.3 (A1C-B-010 + A1C-B-011) — merge policy_decision + purpose_of_use
    # into the caller-supplied details BEFORE redaction. Redactor only
    # scrubs PHI patterns; structured fields pass through.
    merged_details = dict(details) if details else {}
    if policy_decision:
        merged_details.update(policy_decision)
    if purpose_of_use is not None:
        merged_details["purpose_of_use"] = purpose_of_use
    # Phase A1A Gate 4.3 — minimum-necessary-data chokepoint.
    # Regardless of what the caller passes, the audit row is scrubbed
    # before persist. This closes the live-path leak where an emit
    # site writes e.g. details={"patient_name": "张三"} and the
    # patient name lands in the audit_log.details JSON column.
    # See app/services/audit_detail_redactor.py for the policy.
    from app.services.audit_detail_redactor import (
        redact_audit_details, redact_audit_summary,
    )
    safe_details = redact_audit_details(merged_details or None)
    safe_input_summary = redact_audit_summary(model_input_summary)
    safe_output_summary = redact_audit_summary(model_output_summary)
    try:
        log_entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=safe_details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            error_message=error_message,
            model_input_summary=safe_input_summary,
            model_output_summary=safe_output_summary,
            model_version=model_version,
            tool_calls_made=tool_calls_made,
            tokens_used=tokens_used,
            tenancy_classification=classify_modern_write(
                organization_id, allow_null_org=allow_null_org,
            ),
        )
        db.add(log_entry)
        return log_entry
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        return None
