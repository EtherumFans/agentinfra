"""Tool-surface agent run endpoint — the Corti `message:send` analog for prose agents.

  POST /api/agents/{agent_id}/run   -> run a tool-surface agent, return its prose report

The atomic *tool* agents (index navigation / code validation / compliance guardrail /
document standardization) run on the LLM tool-calling executor and answer in prose Markdown
(no terminal submit_findings). Unlike /api/coding/extract, there is NO deterministic offline
fallback: prose synthesis cannot be faithfully faked without a model, so with no LLM key this
endpoint returns a clean 503 (mirrors the coding-review red line — a tool agent must have an LLM).

Red lines preserved: PHI is redacted server-side inside the executor BEFORE any model call;
nothing is written back; the 503 carries no credentials.
"""
from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..experts.coding_expert import CodingExpert
from ..experts.registry import default_expert_registry
from ..runtime.executor import AgentExecutor
from ..runtime.gateway import LLMGateway, ProviderError
from ..runtime.registry import default_registry, effective_surface
from .auth import require_auth

router = APIRouter(prefix="/api/agents", tags=["agent-run"])

_experts = default_expert_registry()
_agents = default_registry()


class AgentRunRequest(BaseModel):
    text: str


@router.post("/{agent_id:path}/run")
def run_agent(agent_id: str, body: AgentRunRequest, auth: dict = Depends(require_auth)):
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text is required")
    agent = _agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="unknown agent")
    # Each surface owns its own endpoint: extract -> /api/coding/extract,
    # coding-review -> /api/coding-review/run. Only tool agents run here.
    if effective_surface(agent) != "tool":
        raise HTTPException(status_code=404, detail="agent is not a tool-surface agent")

    expert = cast(CodingExpert, _experts.get(CodingExpert.id))
    provider = LLMGateway.from_env(expert.lexicon()).provider
    # A tool agent must have an external LLM: the deterministic provider has no `chat`,
    # and we do NOT fake prose research offline. No key -> clean 503 (no key leaked).
    if not hasattr(provider, "chat"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "llm_credential_missing",
                "message": "tool-surface agents require an external LLM (set ICODER_CREDENTIAL_LLM); no deterministic fallback",
            },
        )

    try:
        result = AgentExecutor(provider).run(agent, body.text, submit_findings=False)
    except ProviderError as exc:
        # endpoint unreachable / non-2xx — surface plainly (no key leaked), never 500.
        raise HTTPException(status_code=503,
                            detail={"code": "llm_unavailable", "message": str(exc)})

    return {
        "provider": provider.name,
        "redaction": {
            "spans": sum(p["count"] for p in result.phi),
            "by_type": result.phi,
            "text": result.redaction_text,
        },
        "report": result.final_message,
        "stages": result.stages,
        "usage": result.usage,
    }
