"""A2A Discovery endpoints (SPEC §7.4).

Four GET endpoints:

1. ``GET /.well-known/agent.json`` — A2A v0.3 standard discovery doc.
2. ``GET /llms.txt`` — LLM-friendly Markdown.
3. ``GET /api/icoder/agents`` — agent list (with optional capability filter).
4. ``GET /api/icoder/agents/{agent_id}/card`` — single AgentCard.

The agent provider is a callable injected by the caller (same pattern
as the inbound route) so tests can supply a stub.
"""

from __future__ import annotations

from typing import Any, Callable, Union

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .agent_card import (
    AgentCard,
    AgentListResponse,
    medcoder_coding_review_card,
    medical_coding_agent_card,
    code_validation_agent_card,
    compliance_guardrail_agent_card,
    note_completeness_agent_card,
)
from .envelope import make_error_response
from .errors import A2AError, A2AErrorCode, agent_not_found
from .version import A2A_PROTOCOL_HEADER, A2A_PROTOCOL_VERSION


# Callable contract for agent lookup. Phase 1 is in-memory; Phase 4
# plugs in a DB-backed Registry.
AgentProvider = Callable[[str], Union[AgentCard | None, dict[str, Any] | None]]


def build_discovery_router(
    agent_provider: AgentProvider,
    base_url: str = "",
) -> tuple[APIRouter, APIRouter, APIRouter]:
    """Build the three discovery routers.

    Returns:
        (:root_router, :agents_router, :card_router)

    The root router carries ``/.well-known/agent.json`` and ``/llms.txt``
    — these must be mounted at the app root (no prefix).

    The agents router carries ``/api/icoder/agents`` (list + capability
    filter) and ``/api/icoder/agents/{id}/card``.
    """
    root = APIRouter(tags=["a2a-discovery"])
    agents = APIRouter(prefix="/api/icoder/agents", tags=["a2a-discovery"])

    @root.get("/.well-known/agent.json", operation_id="a2a_well_known_agent_json_v0_3")
    async def well_known_agent_json(request: Request):
        """A2A v0.3 standard discovery endpoint."""
        cards = _list_all_cards(agent_provider)
        body = AgentListResponse(agents=cards).model_dump(by_alias=True)
        return _json(body)

    @root.get("/llms.txt", operation_id="a2a_llms_txt_v0_3")
    async def llms_txt(request: Request):
        """LLM-friendly Markdown listing of available agents."""
        cards = _list_all_cards(agent_provider)
        md = _render_llms_txt(cards)
        return PlainTextResponse(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        )

    @agents.get("", operation_id="a2a_list_agents_v0_3")
    async def list_agents(
        request: Request,
        capability: str | None = Query(default=None),
    ):
        """List agents, optionally filtered by capability."""
        cards = _list_all_cards(agent_provider)
        if capability:
            cards = _filter_by_capability(cards, capability)
        # Return simplified shape per SPEC §7.4.3
        simplified = [
            {
                "id": _agent_id(c),
                "name": c.name,
                "description": c.description,
                "version": c.version,
                "capabilities": c.capabilities.model_dump(by_alias=True),
                "url": c.url,
            }
            for c in cards
        ]
        return _json({"agents": simplified})

    @agents.get("/{agent_id}/card", operation_id="a2a_get_agent_card_v0_3")
    async def get_agent_card(request: Request, agent_id: str):
        """Single agent's full AgentCard (SPEC §7.4.2)."""
        card = _resolve_card(agent_provider, agent_id)
        if card is None:
            err = agent_not_found(agent_id)
            return JSONResponse(
                status_code=err.http_status,
                headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
                content=make_error_response(None, err),
            )
        return _json(card.model_dump(by_alias=True))

    return root, agents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _list_all_cards(provider: AgentProvider) -> list[AgentCard]:
    """List all AgentCards the provider knows about.

    Phase 3-B1 (2026-07-04): enumerate both public runnable agents —
    ``medcoder-coding-review`` (internal engine, but card exists for
    orchestrator internal use) AND ``medical-coding-agent`` (the user-facing
    Corti-style MVP). The provider is consulted first; if it returns None
    for either, we fall back to the fixture.

    Phase 3-D1 Task 5 (2026-07-06): added 3 simple runnable agents
    (code-validation / compliance-guardrail / note-completeness). Same
    fallback pattern — provider first, fixture second.

    metadata-only packs and expert-stubs do NOT get cards here — they
    have no run path. They appear in the Hub (``/api/icoder/agents/hub``)
    with Coming Soon badges instead.
    """
    cards: list[AgentCard] = []
    for agent_id, factory in [
        ("medcoder-coding-review", medcoder_coding_review_card),
        ("medical-coding-agent", medical_coding_agent_card),
        ("code-validation-agent", code_validation_agent_card),
        ("compliance-guardrail-agent", compliance_guardrail_agent_card),
        ("note-completeness-agent", note_completeness_agent_card),
    ]:
        card = _resolve_card(provider, agent_id)
        if card is None:
            card = factory()
        cards.append(card)
    return cards


def _resolve_card(provider: AgentProvider, agent_id: str) -> AgentCard | None:
    raw = provider(agent_id)
    if raw is None:
        return None
    if isinstance(raw, AgentCard):
        return raw
    if isinstance(raw, dict):
        return AgentCard.model_validate(raw)
    raise TypeError(
        f"agent_provider must return AgentCard or dict, got {type(raw).__name__}"
    )


def _filter_by_capability(
    cards: list[AgentCard], capability: str
) -> list[AgentCard]:
    """Filter by skill id or capability match."""
    out = []
    for c in cards:
        # Check skills
        for s in c.skills:
            if s.id == capability:
                out.append(c)
                break
        else:
            # Fall back to a metadata.icoder.rule_sets match
            icoder_meta = (c.metadata or {}).get("icoder", {})
            rule_sets = icoder_meta.get("rule_sets", []) or []
            if capability in rule_sets:
                out.append(c)
    return out


def _agent_id(card: AgentCard) -> str:
    """Extract a stable agent_id from an AgentCard.

    Convention: the URL path contains ``/agents/{id}/v1/message:send``;
    the segment between ``/agents/`` and ``/v1/`` is the agent_id.
    """
    url = card.url or ""
    if "/agents/" in url:
        try:
            seg = url.split("/agents/", 1)[1]
            return seg.split("/v1/", 1)[0]
        except (IndexError, ValueError):
            pass
    return ""


def _render_llms_txt(cards: list[AgentCard]) -> str:
    """Render LLM-friendly Markdown (SPEC §7.4.4)."""
    lines = [
        "# iCoDer v1 Agent Runtime",
        "",
        "iCoDer is an AI platform for hospital revenue compliance (China).",
        "",
        "## Available Agents",
        "",
    ]
    for c in cards:
        lines.append(f"### {c.name} (v{c.version})")
        lines.append(f"- **URL**: POST {c.url}")
        lines.append(f"- **Description**: {c.description}")
        lines.append(f"- **Inputs**: {', '.join(c.defaultInputModes)}")
        lines.append(f"- **Outputs**: {', '.join(c.defaultOutputModes)}")
        skills = ", ".join(s.id for s in c.skills) or "(none)"
        lines.append(f"- **Skills**: {skills}")
        icoder_meta = (c.metadata or {}).get("icoder", {})
        if icoder_meta.get("production_writeback_blocked"):
            lines.append("- **Note**: does not write back to EMR/HIS")
        if icoder_meta.get("phi_redaction") == "required":
            lines.append("- **PHI**: redacted before LLM calls")
        lines.append("")
    return "\n".join(lines)


def _json(body: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=body,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
    )


__all__ = [
    "AgentProvider",
    "build_discovery_router",
]