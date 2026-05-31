# iCoDer - Organization Schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    plan: str = Field(default="free", pattern="^(free|pro|enterprise)$")


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    settings: Optional[dict] = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrgMemberResponse(BaseModel):
    id: str
    user_id: str
    username: str = ""
    email: str = ""
    full_name: str = ""
    role: str
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|member|viewer)$")
