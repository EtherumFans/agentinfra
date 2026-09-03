# OAuth schemas — client + token response validation
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class OAuthClientResponse(BaseModel):
    id: str
    client_id: str
    client_name: str = ""
    client_type: str = "confidential"
    grant_types: list[str] = Field(default_factory=list)
    redirect_uris: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OAuthClientListResponse(BaseModel):
    clients: list[OAuthClientResponse]
    total: int


class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str = ""


class OAuthClientCreateRequest(BaseModel):
    client_name: str
    grant_types: list[str] = Field(default_factory=lambda: ["client_credentials"])
    redirect_uris: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=lambda: ["api:read", "api:write"])
