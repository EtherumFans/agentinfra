"""Agentic REST surface — a small A2A-style nod (Agent discovery + Agent Card).

  GET /agents                      -> list registered thin agents
  GET /agents/{agent_id}/card      -> A2A-style Agent Card (discovery)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..runtime.registry import default_registry
from .auth import require_auth

router = APIRouter(prefix="/agents", tags=["agentic"])
_agents = default_registry()


@router.get("")
def list_agents(auth: dict = Depends(require_auth)):
    return {
        "agents": [
            {"id": a.id, "name": a.name, "version": a.version,
             "category": a.category, "experts": a.experts}
            for a in _agents.list()
        ]
    }


@router.get("/{agent_id:path}/card")
def agent_card(agent_id: str, auth: dict = Depends(require_auth)):
    agent = _agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    return {
        "schemaVersion": "a2a/0.1",
        "id": agent.id,
        "name": agent.name,
        "version": agent.version,
        "description": agent.output_contract,
        "capabilities": {"streaming": False, "humanInTheLoop": True, "evidenceLinked": True},
        "skills": [{"id": e} for e in agent.experts],
        "nonGoals": agent.non_goals,
        "endpoints": {"run": "/api/coding-review/run"},
        "x-icoder": {
            "deployment": "on-prem",
            "data_residency": "in-hospital",
            "coding_systems": ["ICD-10-CN", "ICD-9-CM-3"],
            "production_writeback_blocked": True,
        },
    }
