# Expert schemas — request/response validation
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ExpertResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    name: str
    description: str = ""
    category: str = ""
    icon: str = "Bot"
    system_prompt: str = ""
    tools: list[dict] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExpertListResponse(BaseModel):
    experts: list[ExpertResponse]
    total: int


class ExpertCategoryResponse(BaseModel):
    name: str
    count: int


class ExpertCapabilityResponse(BaseModel):
    capability: str
    experts: list[ExpertResponse]
    total: int
