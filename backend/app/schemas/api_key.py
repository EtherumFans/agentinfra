# API Key schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["api:read", "api:write"])
    expires_in_days: Optional[int] = None


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str = ""
    full_key: Optional[str] = None  # Only returned once at creation
    scopes: list[str] = Field(default_factory=list)
    is_active: bool = True
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyResponse]
    total: int


class ApiKeyDeleteResponse(BaseModel):
    status: str = "deleted"
