"""Agent Card schemas — Corti public §6 contract shape.

A1B-AE.4 introduces a Corti-compatible Agent Card surface. The Card
is a READ-ONLY projection of an Agent designed for A2A discovery and
for Corti-Console-style "customize after create" workflows.

Shape (CLEAN_ROOM_PUBLIC — Corti public docs §6):

    {
      "id": "...",
      "name": "...",
      "description": "...",
      "systemPrompt": "...",
      "agentType": "expert" | "orchestrator" | "interviewing-expert",
      "experts": [
        {
          "id": "...",
          "name": "...",
          "canonical_key": "...",
          "origin": "CLEAN_ROOM_PUBLIC" | "REVERSE_ENGINEERED" |
                    "ICODER_INTERNAL" | "PACK_DECLARED",
          "mcpServers": [
            {
              "id": "...",
              "name": "...",
              "transportType": "streamable_http",
              "authorizationType": "none"|"inherit"|"bearer"|"oauth2.0",
              "url": "..."
            }
          ]
        }
      ],
      "mcpServers": [
        {
          "id": "...",
          "name": "...",
          "transportType": "streamable_http",
          "authorizationType": "none"|"inherit"|"bearer"|"oauth2.0",
          "url": "..."
        }
      ],
      "canonical_key": "...",
      "aliases": ["...", "..."],
      "version": "1.0.0",
      "status": "draft" | "published" | "archived"
    }

This is the shape Corti's A2A protocol expects when a client GETs
``/agents/{id}/card``. The field naming is camelCase to match Corti
public docs verbatim; the underlying iCoDer DB columns are
snake_case (canonical_key, agent_type) per Python convention.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AgentCardMcpServer(BaseModel):
    """Corti §6 McpServer shape (Expert-config schema)."""
    id: str
    name: str
    transportType: str = "streamable_http"
    authorizationType: str = "none"
    url: str


class AgentCardExpert(BaseModel):
    """Corti §6 Expert shape (inline-expandable from expert_ids[])."""
    id: str
    name: str
    canonical_key: Optional[str] = None
    origin: str = "ICODER_INTERNAL"
    corti_alignment: str = "UNKNOWN"
    mcpServers: list[AgentCardMcpServer] = Field(default_factory=list)


class AgentCard(BaseModel):
    """Corti §6 Agent Card — READ-ONLY A2A discovery projection."""
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str = ""
    systemPrompt: str = ""
    agentType: str = "orchestrator"
    experts: list[AgentCardExpert] = Field(default_factory=list)
    mcpServers: list[AgentCardMcpServer] = Field(default_factory=list)

    # iCoDer extensions (do not collide with Corti field names)
    canonical_key: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    status: str = "draft"
    organization_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentQuickCreate(BaseModel):
    """Corti Console 'Create agent' modal — name-only first step.

    A1B-AE.3 Console observation (session 2026-07-22T0739-UTC step 03)
    confirmed Corti Console's Create-then-Customize UX:

        modal "Name your agent"
          ↳ Agent Name * (required)
          ↳ Create Agent button (disabled when input empty)

    All other fields (description, systemPrompt, agentType, experts[],
    mcpServers[]) are configured AFTER creation on the Agent detail
    page. This endpoint mirrors that flow.

    A1B-AE-R.2 (2026-07-23): when ``from_preset`` query parameter is
    provided, ``name`` becomes optional (defaults to the preset's name).
    """
    name: str | None = None


class AgentQuickCreateResponse(BaseModel):
    """Response for POST /api/v1/agents/quick — minimal, ID-first."""
    id: str
    name: str
    canonical_key: Optional[str] = None
    agent_type: str = "orchestrator"
    status: str = "draft"
    version: str = "1.0.0"
    next_step: str = "customize"
