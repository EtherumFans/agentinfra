# iCoDer - Audit Logging Middleware
import logging
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
):
    """Record an audit log entry.

    Phase A1A Gate 2 §3 — cloud mode fail-closed: refuses to commit
    a NULL org_id audit row unless ``allow_null_org=True`` (system-
    scope events like ``system.startup``).
    """
    # Phase A1A Gate 2 §3: fail-closed guard fires BEFORE the try/except
    # so a tenancy violation propagates to the caller (it's a server-
    # side bug, not a "couldn't write audit" error).
    assert_tenancy_for_write(
        organization_id, "audit_logs",
        allow_null_org=allow_null_org,
    )
    try:
        log_entry = AuditLog(
            organization_id=organization_id,
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
            model_input_summary=model_input_summary,
            model_output_summary=model_output_summary,
            model_version=model_version,
            tool_calls_made=tool_calls_made,
            tokens_used=tokens_used,
            tenancy_classification=classify_modern_write(
                organization_id, allow_null_org=allow_null_org,
            ),
        )
        db.add(log_entry)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
