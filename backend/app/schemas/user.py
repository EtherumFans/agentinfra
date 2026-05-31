# iCoDer - User Schemas (Multi-Tenant)
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.models.user import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=64)
    full_name: str = Field(..., min_length=1, max_length=128)
    role: UserRole = UserRole.CODER
    department: str = ""
    organization_name: str = Field(default="", max_length=256)


class UserLogin(BaseModel):
    username: str
    password: str


class OrgInfo(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    role: str  # owner/admin/member/viewer
    is_default: bool


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    department: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserMeResponse(UserResponse):
    organizations: list[OrgInfo] = []
    current_org_id: str = ""


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
    organizations: list[OrgInfo] = []
    current_org_id: str = ""


class TokenRefresh(BaseModel):
    refresh_token: str


class SwitchOrgRequest(BaseModel):
    org_id: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=64)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=64)


class RevokeTokensRequest(BaseModel):
    """Revoke all tokens for current user (logout all devices)."""
    reason: str = "logout"  # logout | password_change
