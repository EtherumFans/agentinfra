"""Agent Registry Compatibility API (P1.1-B).

Single endpoint that exposes the per-pack compatibility report
(via :mod:`icoder_runtime.core.registry_status`).

Endpoints
---------
GET /api/icoder/registry/compatibility
    → full report: 16 packs + summary counters

The Agent Hub page consumes this to surface the per-pack
"loader status + registered-in-legacy-registry" view, with a
"Why not executable?" panel for non-executable packs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from icoder_runtime.core.registry_status import (
    RegistryCompatibilityReport,
    compute_compatibility,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/registry", tags=["registry-compat"])


def _official_agents_dir() -> Path:
    """Locate the official_agents/ directory."""
    # backend/app/api/icoder_registry_compat.py → backend/official_agents
    return Path(__file__).resolve().parents[2] / "official_agents"


def _get_registry():
    """Read the RuntimeAgentRegistry from app.state if available."""
    try:
        from app.main import app as _app
        return getattr(_app.state, "agent_registry", None)
    except Exception:
        return None


def _build_report() -> RegistryCompatibilityReport:
    return compute_compatibility(_official_agents_dir(), registry=_get_registry())


@router.get("/compatibility")
def get_compatibility(
    agent_ref: str = Query("", description="Filter to a single agent_ref"),
) -> dict[str, Any]:
    """Per-pack compatibility report.

    Each entry carries:
    * ``status`` (executable / metadata_only / invalid) — the loader's view
    * ``registered`` (bool) — whether the legacy RuntimeAgentRegistry has it
    * ``production_ready`` — true only for certified-with-real-wiring and reference
    * ``why_not_executable`` — human-readable list (empty for executable)
    * ``validation_errors`` / ``validation_warnings`` — from the loader
    """
    report = _build_report()
    if agent_ref:
        entries = [e for e in report.entries if e.agent_ref == agent_ref]
        if not entries:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "AGENT_NOT_FOUND",
                    "message": f"No pack with agent_ref={agent_ref!r}",
                    "agent_ref": agent_ref,
                },
            )
        return {
            "entry": entries[0].to_dict(),
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
    return report.to_dict()


@router.get("/compatibility/summary")
def get_compatibility_summary() -> dict[str, Any]:
    """Counts only (no per-pack entries). Cheap for dashboard polling."""
    report = _build_report()
    return {
        "total_discovered": report.total_discovered,
        "total_registered": report.total_registered,
        "production_ready": report.production_ready,
        "metadata_only": report.metadata_only,
        "invalid": report.invalid,
        "by_status": report.by_status,
        "by_type": report.by_type,
        "by_format": report.by_format,
    }