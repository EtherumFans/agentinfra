# iCoDer - Audit Log Schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    status: str
    model_version: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class AuditLogListResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
