# Memory / Conversation schemas
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


MemoryPurpose = Literal[
    "treatment", "healthcare_operations", "quality_improvement",
]


class MemoryConsentGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose_of_use: MemoryPurpose = "treatment"
    retention_days: int = Field(default=30, ge=1, le=90)
    expires_in_days: int = Field(default=30, ge=1, le=90)
    acknowledgement: Literal[True]


class MemoryConsentResponse(BaseModel):
    id: str
    agent_id: str
    user_id: str
    purpose_of_use: MemoryPurpose
    legal_basis: Literal["user-consent"]
    authority_class: Literal["authenticated_user_self_service"]
    patient_authority_verified: Literal[False]
    phi_storage_allowed: Literal[False]
    retention_days: int
    status: Literal["active", "revoked", "expired"]
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MemoryReadinessResponse(BaseModel):
    """Aggregate-only operational state; never returns stored memory content."""

    agent_id: str
    purpose_of_use: MemoryPurpose
    consent_status: Literal["missing", "active", "revoked", "expired"]
    persisted_memory_count: int = Field(ge=0)
    retention_days: int | None = None
    expires_at: datetime | None = None
    encryption_enabled: bool
    semantic_required: bool
    semantic_provider: dict
    lexical_fallback_available: Literal[True]
    native_ml_in_api_process: Literal[False]
    patient_authority_verified: Literal[False]
    phi_storage_allowed: Literal[False]
    operationally_configured: bool


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
