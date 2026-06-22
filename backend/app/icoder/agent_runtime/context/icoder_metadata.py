"""iCoDer Context metadata (SPEC §4.4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContextMetadata(BaseModel):
    """iCoDer Context metadata — hard-coded invariants + optional fields."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    production_writeback_blocked: bool = Field(
        default=True,
        frozen=True,
        description="硬红线: 恒 true, 不可改 (G5)",
    )
    phi_redacted: bool = Field(
        default=True,
        frozen=True,
        description="硬红线: 恒 true, 不可改 (PHI 强制脱敏)",
    )
    phi_redacted_entities: list[str] = Field(
        default_factory=list,
        description="脱敏命中的实体类型, e.g. ['NAME', 'ID_CARD']",
    )
    user_id: str | None = None
    tenant_id: str | None = None
    custom: dict = Field(default_factory=dict)

    @field_validator("production_writeback_blocked", "phi_redacted")
    @classmethod
    def _invariants_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("invariant field must remain True")
        return value