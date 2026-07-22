# Expert schemas — request/response validation
"""Expert schemas — A1B-AE.3 extended with provenance fields.

The new ``ExpertResponse`` shape exposes the Charter Amendment 1 §7
provenance columns so API consumers can tell at a glance whether a
given Expert came from a CLEAN_ROOM_PUBLIC or REVERSE_ENGINEERED
source, what Corti-public Expert it aligns with (if any), and which
Pack directory declares it.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.models.expert import (
    EXPERT_ORIGIN_VALUES,
    EXPERT_CORTI_ALIGNMENT_VALUES,
    MCP_AUTHORIZATION_TYPE_VALUES,
)


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

    # A1B-AE.3 provenance (Charter Amendment 1 §7)
    canonical_key: Optional[str] = None
    origin: str = "ICODER_INTERNAL"
    corti_alignment: str = "UNKNOWN"
    pack_dir: Optional[str] = None
    provenance: Optional[dict] = None


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


class McpServerResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    expert_id: str
    name: str
    url: str
    transport_type: str = "streamable_http"
    description: str = ""
    authorization_type: str = "none"
    auth_type: str = "none"
    is_active: bool = True


# ── A1B-AE.3 Registry reconcile response shape ─────────────────────
class ExpertRegistryReconcileEntry(BaseModel):
    db_id: Optional[str] = None
    db_name: Optional[str] = None
    catalog_key: str
    catalog_origin: str
    catalog_corti_alignment: str
    catalog_pack_dir: Optional[str] = None
    catalog_source_file: Optional[str] = None
    db_status: str  # "PRESENT" | "MISSING" | "DIVERGENT"
    divergences: list[str] = Field(default_factory=list)


class ExpertRegistryReconcileResponse(BaseModel):
    charter: str = "A1B-AE.3"
    catalog_path: str
    catalog_count: int
    db_count_total: int
    db_count_canonical_keyed: int
    entries: list[ExpertRegistryReconcileEntry]
    summary: dict
