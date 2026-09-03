"""A2A mounting point.

Aggregates the A2A routers (inbound, outbound, discovery, task state machine)
and exposes :func:`mount_a2a` for the application to call once at startup.

Mounting layout:

- ``/.well-known/agent.json``     — root (app-level prefix)
- ``/llms.txt``                    — root
- ``/api/icoder/agents``           — agent list + capability filter
- ``/api/icoder/agents/{id}/card`` — single AgentCard
- ``/api/icoder/agents/{id}/v1/message:send`` — inbound message/send
- ``/api/icoder/agents/{id}/v1/message:stream`` — inbound SSE message/stream
- ``/api/icoder/internal/experts/{id}/v1/message:send`` — outbound
- ``/api/icoder/tasks/{id}``       — A1B-AE-R.1.a real Task state machine
- ``/api/icoder/tasks/{id}/cancel`` — A1B-AE-R.1.a real Task cancel
- ``/api/v2/agentic/agents/{id}/a2a`` — A2A v1.0 JSON-RPC binding
- ``/api/v2/agentic/agents/{id}/message:send`` — A2A v1.0 HTTP+JSON binding
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from ..orchestrator.inbound_handler import InboundHandler
from .routes_context import build_context_router
from .routes_discovery import AgentProvider, build_discovery_router
from .routes_inbound import build_inbound_router
from .routes_outbound import ExpertCaller, build_outbound_router
from .routes_task import build_task_router
from .v1 import build_v1_router


def build_a2a_routers(
    *,
    handler: InboundHandler,
    agent_provider: AgentProvider,
    expert_caller: ExpertCaller,
) -> dict[str, Any]:
    """Build all A2A routers without mounting.

    Returns a dict keyed by mount-point category:

    - ``"inbound"`` — APIRouter for ``/api/icoder/agents/{agent_id}``
    - ``"outbound"`` — APIRouter for ``/api/icoder/internal/experts``
    - ``"discovery_root"`` — APIRouter for root-level (well-known, llms.txt)
    - ``"discovery_agents"`` — APIRouter for ``/api/icoder/agents``
    - ``"task"`` — APIRouter for ``/api/icoder/tasks``
    - ``"context"`` — APIRouter for ``/api/icoder/contexts`` (R.1.b)
    - ``"v1"`` — APIRouter for A2A v1.0 JSON-RPC + HTTP+JSON bindings
    """
    return {
        "inbound": build_inbound_router(handler),
        "outbound": build_outbound_router(expert_caller),
        "discovery_root": build_discovery_router(agent_provider)[0],
        "discovery_agents": build_discovery_router(agent_provider)[1],
        "task": build_task_router(),
        "context": build_context_router(),
        "v1": build_v1_router(handler, agent_provider),
    }


def mount_a2a(
    app: FastAPI,
    *,
    handler: InboundHandler,
    agent_provider: AgentProvider,
    expert_caller: ExpertCaller,
) -> dict[str, APIRouter]:
    """Mount all A2A routers onto ``app`` (idempotent).

    Returns the same dict as :func:`build_a2a_routers` for callers
    that want direct router references (e.g., tests).

    TD-004 fix: idempotent — if the A2A routes are already mounted
    (e.g. lifespan re-ran across TestClient sessions), skip re-mounting
    to avoid duplicate operation_id warnings.
    """
    if getattr(app.state, "_a2a_mounted", False):
        # Already mounted — return the cached routers
        return app.state._a2a_routers

    routers = build_a2a_routers(
        handler=handler,
        agent_provider=agent_provider,
        expert_caller=expert_caller,
    )
    # Inbound: agent_id is a path param. We wrap with a parent router
    # so callers don't need to know the per-agent path layout.
    inbound_parent = APIRouter(prefix="/api/icoder/agents/{agent_id}")
    inbound_parent.include_router(routers["inbound"])
    app.include_router(inbound_parent)

    # Outbound (Orchestrator → Expert): wrap with /api/icoder parent prefix
    # so the spec-aligned path is /api/icoder/internal/experts/{id}/v1/...
    outbound_parent = APIRouter(prefix="/api/icoder")
    outbound_parent.include_router(routers["outbound"])
    app.include_router(outbound_parent)

    # Discovery root (no prefix) — /.well-known/agent.json, /llms.txt
    app.include_router(routers["discovery_root"])

    # Discovery agents — /api/icoder/agents (already prefixed)
    app.include_router(routers["discovery_agents"])

    # Task — /api/icoder/tasks (already prefixed)
    app.include_router(routers["task"])

    # Context — /api/icoder/contexts (already prefixed, R.1.b)
    app.include_router(routers["context"])

    # A2A v1.0 — independent adapters; v0.3 routes above remain unchanged.
    app.include_router(routers["v1"])
    app.state.a2a_task_runtime = getattr(
        routers["v1"], "a2a_task_runtime", None
    )

    # Mark as mounted (idempotency guard)
    app.state._a2a_mounted = True
    app.state._a2a_routers = routers

    return routers


__all__ = [
    "build_a2a_routers",
    "mount_a2a",
]
