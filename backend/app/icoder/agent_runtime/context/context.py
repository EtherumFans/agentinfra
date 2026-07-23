"""Context / ContextMessage / ContextTaskRef / ContextArtifactRef (SPEC §4.1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .context_id import is_valid_context_id
from .context_status import ContextStatus
from .icoder_metadata import ContextMetadata


class ContextMessage(BaseModel):
    """Short-term message (simplified A2A Message)."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    role: str = Field(description="user / agent / orchestrator / expert")
    parts: list[dict] = Field(default_factory=list)
    timestamp: datetime
    redacted: bool = Field(
        default=True,
        frozen=True,
        description="G5: 恒 true, ContextMessage 强制脱敏",
    )
    metadata: dict = Field(default_factory=dict)

    @field_validator("redacted")
    @classmethod
    def _redacted_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("redacted must remain True")
        return value


class ContextTaskRef(BaseModel):
    """Task reference (Task body lives in Task spec)."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    state: str
    started_at: datetime
    completed_at: datetime | None = None


class ContextArtifactRef(BaseModel):
    """Artifact reference (artifact body lives outside Context)."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    name: str
    mime_type: str
    url: str


class Context(BaseModel):
    """A2A Context — server-side, per-session, strict isolation (Q4)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="contextId (UUID v4, server-generated)")
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    agent_id: str
    organization_id: str = Field(
        description=(
            "A1B-AE-RV.2 — tenant scope. Cross-tenant reads return "
            "404 (no leak). No default: callers MUST pass the JWT's "
            "current_org.id explicitly. Test-bypass paths inject "
            "'org_default1' via the mock user."
        ),
    )
    status: ContextStatus
    messages: list[ContextMessage] = Field(default_factory=list)
    tasks: list[ContextTaskRef] = Field(default_factory=list)
    artifacts: list[ContextArtifactRef] = Field(default_factory=list)
    metadata: ContextMetadata = Field(default_factory=ContextMetadata)
    redacted_input_hash: str = ""
    original_input_ref: str = ""

    @field_validator("id")
    @classmethod
    def _id_must_be_canonical_uuid_v4(cls, value: str) -> str:
        if not is_valid_context_id(value):
            raise ValueError(
                f"id must be canonical UUID v4, got {value!r}"
            )
        return value