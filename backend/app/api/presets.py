# iCoDer - Preset Agents API (A1B-AE.9)
"""Preset Agents REST endpoints — A1B-AE.9 tech-debt liquidation.

Exposes the 5 iCoDer Preset Agent Cards filed in A1B-AE.8 via REST.
Read-only by design; preset authoring happens in
``backend/agent_catalog/icoder_preset_agents.json`` (clean-room authored).

Endpoints:
- ``GET /api/v1/presets`` — list all 5 presets (canonical_key, name,
  name_zh, agent_type, corti_alignment, delegates_to_pack).
- ``GET /api/v1/presets/{canonical_key}`` — full PresetAgent.
- ``GET /api/v1/presets/{canonical_key}/card`` — Corti §6 camelCase
  Agent Card + icoder_ext block.

Provenance: ICODER_INTERNAL (the catalog + service are iCoDer-authored;
no Corti proprietary content is reproduced).
"""
from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import get_current_user, get_current_organization
from app.models.user import User
from app.models.organization import Organization
from app.services.preset_agents import (
    all_presets,
    get_preset,
    corti_agent_card,
)


router = APIRouter(prefix="/api/v1/presets", tags=["A1B-AE.9 Preset Agents"])


@router.get("")
async def list_presets(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """List all 5 iCoDer Preset Agents (summary view)."""
    return {
        "presets": [
            {
                "canonical_key": p.canonical_key,
                "name": p.name,
                "name_zh": p.name_zh,
                "agent_type": p.agent_type,
                "corti_alignment": p.corti_alignment,
                "delegates_to_pack": p.delegates_to_pack,
                "expert_count": len(p.experts),
            }
            for p in all_presets()
        ],
        "total": len(all_presets()),
    }


@router.get("/{canonical_key}")
async def get_preset_detail(
    canonical_key: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Full PresetAgent detail."""
    p = get_preset(canonical_key)
    if p is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {
        "canonical_key": p.canonical_key,
        "name": p.name,
        "name_zh": p.name_zh,
        "description": p.description,
        "agent_type": p.agent_type,
        "system_prompt": p.system_prompt,
        "experts": [
            {"canonical_key": e.canonical_key, "role": e.role} for e in p.experts
        ],
        "mcp_servers": list(p.mcp_servers),
        "corti_alignment": p.corti_alignment,
        "delegates_to_pack": p.delegates_to_pack,
        "red_lines": dict(p.red_lines),
        "default_runtime_mode": p.default_runtime_mode,
        "available_runtime_modes": list(p.available_runtime_modes),
    }


@router.get("/{canonical_key}/card")
async def get_preset_card(
    canonical_key: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Corti §6 Agent Card (camelCase) + icoder_ext block."""
    card = corti_agent_card(canonical_key)
    if card is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return card


__all__ = ["router"]
