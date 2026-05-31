# Agent schemas — request/response validation
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    category: str = "编码"
    icon: str = "Bot"
    expert_ids: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    expert_ids: Optional[list[str]] = None
    config: Optional[dict] = None


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    name: str
    description: str = ""
    system_prompt: str = ""
    category: str = "编码"
    icon: str = "Bot"
    expert_ids: list[str] = Field(default_factory=list)
    default_expert_id: str = ""
    a2a_enabled: bool = False
    config: dict = Field(default_factory=dict)
    is_prebuilt: bool = False
    is_published: bool = False
    usage_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None


class AgentTemplateResponse(BaseModel):
    id: str
    title: str
    description: str = ""
    category: str = "编码"
    icon: str = "Bot"
    expert_ids: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    system_prompt: str = ""


class AgentTemplatesResponse(BaseModel):
    templates: list[AgentTemplateResponse]


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int


class AgentCategoryResponse(BaseModel):
    name: str
    count: int
