# Team schemas
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str
    username: str = ""
    email: str = ""
    role: str = "member"  # owner, admin, member
    joined_at: Optional[datetime] = None


class TeamMemberListResponse(BaseModel):
    members: list[TeamMemberResponse]
    total: int


class TeamInviteRequest(BaseModel):
    email: str
    role: str = "member"


class TeamInviteResponse(BaseModel):
    status: str = "invited"
    email: str
    role: str


class TeamUpdateMemberRequest(BaseModel):
    role: str


class TeamUpdateMemberResponse(BaseModel):
    status: str = "updated"
    member_id: str
    role: str


class TeamRemoveMemberResponse(BaseModel):
    status: str = "removed"
    member_id: str
