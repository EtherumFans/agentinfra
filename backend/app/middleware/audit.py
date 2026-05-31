# iCoDer - Audit Logging Middleware
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
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
):
    """Record an audit log entry."""
    try:
        log_entry = AuditLog(
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
        )
        db.add(log_entry)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
