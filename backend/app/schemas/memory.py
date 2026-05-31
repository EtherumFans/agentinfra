# Memory / Conversation schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MemoryResponse(BaseModel):
    id: str
    key: str
    value: str
    metadata: dict = Field(default_factory=dict)
    importance: float = 0.0
    access_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int


class MemoryUpsertRequest(BaseModel):
    key: str
    value: str
    metadata: dict = Field(default_factory=dict)
    importance: float = 0.0


class MemoryDeleteResponse(BaseModel):
    status: str = "deleted"
