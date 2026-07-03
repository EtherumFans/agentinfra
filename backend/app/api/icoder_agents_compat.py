# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy compat shim. Phase 2 删. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.3.
"""Per-agent validation + compatibility endpoints (P1.1-C).

Endpoints
---------
GET /api/icoder/agents/{agent_id}/validation
    → loader view for one pack: status, validation errors/warnings,
      why_not_executable. Cheap (no registry cross-ref).

GET /api/icoder/agents/{agent_id}/compatibility
    → full AgentCompatibilityEntry for one pack, including
      ``registered`` (whether the legacy RuntimeAgentRegistry has it),
      ``registry_agent_id``, and the global report summary counters.

Both endpoints are agent-scoped (URL nested under Hub) so the front-end
can fetch validation details from a card click without leaving
``/runtime/agent-hub`` semantics. The flat ``/api/icoder/registry/compatibility``
endpoint (P1.1-B) remains the report-style listing surface.

Design rules
------------
* Loader is the SSOT for "is this pack loadable?". Registry cross-ref
  is a derived field, not a gate.
* Unknown ``agent_id`` returns ``AGENT_NOT_FOUND`` (404, NOT 200-null).
* No fake data — fields surface what the loader actually computed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from icoder_runtime.core.registry_status import compute_compatibility

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/agents", tags=["agent-hub-compat"])


def _official_agents_dir() -> Path:
    # backend/app/api/icoder_agents_compat.py → backend/official_agents
    return Path(__file__).resolve().parents[2] / "official_agents"


def _get_registry():
    try:
        from app.main import app as _app
        return getattr(_app.state, "agent_registry", None)
    except Exception:
        return None


def _find_entry(agent_id: str):
    """Return ``(entry, report)`` for *agent_id* or raise 404 AGENT_NOT_FOUND."""
    report = compute_compatibility(_official_agents_dir(), registry=_get_registry())
    for e in report.entries:
        if e.agent_ref == agent_id:
            return e, report
    raise HTTPException(
        status_code=404,
        detail={
            "error_code": "AGENT_NOT_FOUND",
            "agent_id": agent_id,
            "message": f"Agent not found: {agent_id}",
        },
    )


@router.get("/{agent_id:path}/validation")
def get_agent_validation(agent_id: str) -> dict[str, Any]:
    """Loader-only view of one pack's validation state.

    Use this for the "Why not executable?" panel — it returns the raw
    reasons without involving the registry.
    """
    entry, _ = _find_entry(agent_id)
    return {
        "agent_id": agent_id,
        "agent_ref": entry.agent_ref,
        "name": entry.name,
        "version": entry.version,
        "format_version": entry.format_version,
        "agent_type": entry.agent_type,
        "status": entry.status,
        "production_ready": entry.production_ready,
        "experimental": entry.experimental,
        "enabled_by_default": entry.enabled_by_default,
        "tier": entry.tier,
        "validation_errors": list(entry.validation_errors),
        "validation_warnings": list(entry.validation_warnings),
        "why_not_executable": list(entry.why_not_executable),
        "expert_count": entry.expert_count,
        "tool_count": entry.tool_count,
        "source_path": entry.source_path,
    }


@router.get("/{agent_id:path}/compatibility")
def get_agent_compatibility(agent_id: str) -> dict[str, Any]:
    """Full AgentCompatibilityEntry for one pack + global report summary.

    Use this for the Hub "Compatibility" tab — it tells you everything
    the loader knows about the pack AND whether the legacy
    RuntimeAgentRegistry has it installed.
    """
    entry, report = _find_entry(agent_id)
    return {
        "entry": entry.to_dict(),
        "report_summary": {
            "total_discovered": report.total_discovered,
            "total_registered": report.total_registered,
            "production_ready": report.production_ready,
            "metadata_only": report.metadata_only,
            "invalid": report.invalid,
            "by_status": report.by_status,
            "by_type": report.by_type,
            "by_format": report.by_format,
        },
    }


__all__ = ["router"]
