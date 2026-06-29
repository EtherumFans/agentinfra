"""Agent Hub API — discoverable surface for installed agents.

P1.0-B: 4 endpoints under /api/icoder/agents/* that consolidate the
existing /api/runtime-platform/* and /api/runtime/agents/* surfaces
into one discoverable namespace.

Endpoints
---------
GET /api/icoder/agents                    — list installed agents
GET /api/icoder/agents/{agent_id}/card    — A2A v0.3 Agent Card
GET /api/icoder/agents/{agent_id}/health  — per-agent runtime health
GET /api/icoder/agents/{agent_id}/requirements — declared needs (assets, tools, env, permissions)

Design rules
------------
* Prefer existing infrastructure (RuntimeAgentRegistry, A2A AgentCard,
  MedCodER index health, MCP tool registry). This router is a thin
  consolidation layer, not a parallel implementation.
* Unknown agent_id returns AGENT_NOT_FOUND (404, NOT 500/200-empty).
* No fake data. If a dependency is missing, the field is null and the
  caller learns the truth.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/agents", tags=["agent-hub"])


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_app_state():
    """Return the running FastAPI app.state, or None if not initialized.

    Uses a lazy import to avoid importing app.main at module load time
    (which would create a circular import: main.py imports every api router).
    """
    try:
        from app.main import app as _app
        return _app.state
    except Exception:
        return None


def _get_registry():
    state = _get_app_state()
    return getattr(state, "agent_registry", None) if state else None


def _resolve_agent_ref(agent_id: str) -> Any | None:
    """Resolve ``agent_id`` against RuntimeAgentRegistry.

    Returns the registry record, or None if not found / not loaded.
    The lookup is permissive — the registry may index by ``agent_ref``
    (``icoder/medical-coding-agent@1.0.0``), by raw ``id``, or by name.
    """
    reg = _get_registry()
    if not reg:
        return None
    try:
        # 1. Direct ref lookup (canonical: "namespace/name@version")
        rec = reg.find(agent_id)
        if rec:
            return rec
    except Exception:
        pass
    try:
        # 2. by agent_id field (some packs use a different key)
        rec = reg.get(agent_id)
        if rec:
            return rec
    except Exception:
        pass
    try:
        # 3. Fallback: scan all and match by name or agent_ref substring
        for r in reg.list_all():
            if (
                getattr(r, "agent_id", "") == agent_id
                or getattr(r, "agent_ref", "") == agent_id
                or getattr(r, "name", "") == agent_id
            ):
                return r
    except Exception:
        pass
    return None


def _agent_summary(rec: Any) -> dict[str, Any]:
    """Render a registry record into the Agent Hub list summary."""
    try:
        s = rec.to_summary()
    except Exception:
        s = {
            "id": getattr(rec, "agent_id", ""),
            "name": getattr(rec, "name", ""),
            "version": getattr(rec, "version", ""),
        }
    # Add Agent-Hub-specific fields. Read raw pack_data for tier/agent_type
    # to avoid AgentPackageV1 validation rejecting non-1.1 packs.
    s["agent_ref"] = s.pop("id", getattr(rec, "agent_id", ""))
    s["status"] = getattr(rec, "status", "unknown")
    raw_pack = getattr(rec, "pack_data", None) or {}
    if isinstance(raw_pack, dict):
        agent_type = raw_pack.get("agent_type", "")
        s["tier"] = _tier_from_raw_pack(raw_pack)
        s["tier_label"] = _TIER_LABELS.get(s["tier"], f"Tier {s['tier']} — Unknown")
        s["experimental"] = bool(agent_type == "experimental")
        s["production_ready"] = bool(agent_type in ("certified", "reference"))
    else:
        s["tier"] = None
        s["tier_label"] = None
        s["experimental"] = None
        s["production_ready"] = None
    return s


# ── Raw-pack helpers (no AgentPackageV1 validation) ────────────────────────


_TIER_LABELS = {
    0: "Tier 0 — Pure Prompt",
    1: "Tier 1 — Read-only Tools",
    2: "Tier 2 — Sandbox Code",
    3: "Tier 3 — Network Access",
    4: "Tier 4 — System Write-back",
}


def _tier_from_raw_pack(raw_pack: dict) -> int:
    """Compute security tier from raw pack_data dict (no AgentPackageV1 validation)."""
    code = raw_pack.get("code") or {}
    if code:
        return 2
    tools = raw_pack.get("tools") or []
    for t in tools:
        if not isinstance(t, dict):
            continue
        cat = (t.get("category") or "").lower()
        desc = (t.get("description") or "").lower()
        if any(kw in cat or kw in desc for kw in ("his", "emr", "api", "network", "http", "医保接口")):
            return 3
        if any(kw in cat or kw in desc for kw in ("write", "modify", "update", "delete", "insert", "写")):
            return 4
    return 1 if tools else 0


def _permissions_from_raw_pack(raw_pack: dict) -> dict:
    """Extract permissions from raw pack_data, defensively."""
    p = raw_pack.get("permissions") or {}
    if not isinstance(p, dict):
        return {}
    # Strip tool-level actions we don't surface on the Agent Hub
    return {
        k: v for k, v in p.items() if k in ("key", "name", "description", "production_writeback_blocked")
    }


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("")
async def list_agents() -> dict[str, Any]:
    """List agents discoverable on this Runtime.

    Returns a minimal envelope. Frontend Agent Hub page iterates ``agents``
    and shows name + tier + status. The detailed /card and /requirements
    endpoints fill in on click.
    """
    reg = _get_registry()
    if not reg:
        return {"agents": [], "total": 0, "registry_status": "not_initialized"}
    records = reg.list_all()
    return {
        "agents": [_agent_summary(r) for r in records],
        "total": len(records),
        "registry_status": "ok",
    }


@router.get("/{agent_id}/card")
async def get_agent_card(agent_id: str) -> dict[str, Any]:
    """Return the A2A v0.3 Agent Card for one agent.

    * If the agent is ``icoder/medcoder-coding-review-agent@1.0.0``, returns
      the canonical ``medcoder_coding_review_card()`` (A2A SPEC §8).
    * Otherwise returns a synthesized card derived from the agent pack's
      manifest + skills (so marketplace-discoverable agents always have a
      card, even pre-A2A Discovery completion).
    """
    rec = _resolve_agent_ref(agent_id)
    if not rec:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "agent_id": agent_id,
                "message": f"Agent not found: {agent_id}",
            },
        )

    # Try canonical A2A factory first.
    try:
        from app.icoder.agent_runtime.a2a.agent_card import (
            medcoder_coding_review_card,
        )

        ref = getattr(rec, "agent_ref", "") or ""
        if "medcoder-coding-review" in ref or "medical-coding-agent" in ref:
            card = medcoder_coding_review_card()
            return card.model_dump(by_alias=True, exclude_none=True)
    except Exception as e:
        logger.debug("A2A card factory unavailable for %s: %s", agent_id, e)

    # Synthesize from raw pack_data. We do NOT use AgentPackageV1.from_dict
    # here because:
    #   - the validator may reject packs whose tools omit `tier` (MCP-style)
    #   - the validator may reject format_version="1.2" packs (currently 1.1)
    #   - the discovery path should show what we have, not gate on validation.
    raw_pack = getattr(rec, "pack_data", None) or {}

    manifest = raw_pack.get("manifest", {}) if isinstance(raw_pack, dict) else {}
    experts = raw_pack.get("experts", []) if isinstance(raw_pack, dict) else []
    tools = raw_pack.get("tools", []) if isinstance(raw_pack, dict) else []

    skills: list[dict] = []
    for expert in experts:
        if not isinstance(expert, dict):
            continue
        skills.append({
            "id": expert.get("id", ""),
            "name": expert.get("name", ""),
            "description": expert.get("description", ""),
            "inputSchema": {},
            "outputSchema": {},
        })
    for tool in tools:
        # Tools can be dict (MCP-style: name/type/stage/ref) or string (legacy ID).
        if isinstance(tool, str):
            skills.append({
                "id": tool,
                "name": tool,
                "description": "",
                "inputSchema": {},
                "outputSchema": {},
            })
            continue
        if not isinstance(tool, dict):
            continue
        skills.append({
            "id": tool.get("id", "") or tool.get("name", ""),
            "name": tool.get("name", "") or tool.get("id", ""),
            "description": tool.get("description", ""),
            "inputSchema": {},
            "outputSchema": {},
        })

    return {
        "name": manifest.get("name", "") or getattr(rec, "name", ""),
        "description": manifest.get("description", "") or getattr(rec, "description", ""),
        "version": manifest.get("version", "") or getattr(rec, "version", ""),
        "provider": {"name": "iCoDer", "url": "https://icoder.cloud"},
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
            "extensions": [],
        },
        "skills": skills,
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text", "data"],
        "securitySchemes": [
            {"type": "apiKey", "description": "iCoDer API Client key"}
        ],
        "metadata": {
            "icoder": {
                "agent_ref": getattr(rec, "agent_ref", agent_id),
                "tier": _tier_from_raw_pack(raw_pack),
                "experimental": (raw_pack.get("agent_type", "") == "experimental") if isinstance(raw_pack, dict) else None,
            }
        },
    }


@router.get("/{agent_id}/health")
async def get_agent_health(agent_id: str) -> dict[str, Any]:
    """Return per-agent runtime health.

    Aggregates:
    * Registry presence
    * MedCodER FAISS index readiness (only for MedCodER agents)
    * LLM provider configuration (DeepSeek status from gateway)
    * MCP tools reachability (for agents that declare MCP tool refs)
    * run_trace recorder presence (for agents with recorder_required)

    No fake data: missing dependencies surface as ``"available": false``
    so the Agent Hub UI can render an honest status badge.
    """
    rec = _resolve_agent_ref(agent_id)
    if not rec:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "agent_id": agent_id,
                "message": f"Agent not found: {agent_id}",
            },
        )

    state = _get_app_state()
    ref = getattr(rec, "agent_ref", "") or ""
    is_medcoder = ("medcoder" in ref.lower()) or ("medical-coding" in ref.lower())

    health: dict[str, Any] = {
        "agent_id": agent_id,
        "registry": {"available": True},
        "faiss_index": {"available": False, "applies_to": is_medcoder},
        "llm_provider": {"available": False},
        "mcp_tools": {"available": False},
        "recorder": {"available": False},
        "overall": "unknown",
    }

    # ── FAISS index (MedCodER only) ──
    if is_medcoder and state is not None:
        try:
            ready = getattr(state, "medcoder_index_ready", False)
            err = getattr(state, "medcoder_index_error", None)
            loading = getattr(state, "medcoder_index_loading", False)
            health["faiss_index"] = {
                "available": bool(ready),
                "ready": bool(ready),
                "loading": bool(loading),
                "error": err,
                "applies_to": True,
            }
        except Exception:
            pass

    # ── LLM provider ──
    if state is not None:
        try:
            gateway = getattr(state, "platform_gateway", None)
            if gateway is not None:
                providers = gateway.list_providers()
                deepseek = providers.get("deepseek", {})
                health["llm_provider"] = {
                    "available": deepseek.get("status") == "configured",
                    "status": deepseek.get("status", "unknown"),
                    "model": deepseek.get("model", "unknown"),
                    "provider": "deepseek",
                }
        except Exception:
            pass

    # ── MCP tools (for agents declaring mcp_tools or skills referencing MCP) ──
    try:
        from app.icoder.mcp.tool_registry import TOOL_REGISTRY

        health["mcp_tools"] = {
            "available": True,
            "registered": sorted(TOOL_REGISTRY.keys()),
            "count": len(TOOL_REGISTRY),
        }
    except Exception:
        pass

    # ── Recorder (run_trace) ──
    if state is not None:
        recorder = getattr(state, "m2a_recorder", None)
        if recorder is not None:
            health["recorder"] = {
                "available": True,
                "active": bool(recorder.is_active()),
            }
        else:
            # Fall back to legacy run_history
            history = getattr(state, "run_history", None)
            health["recorder"] = {
                "available": history is not None,
                "kind": "m2a" if recorder is not None else "legacy",
            }

    # ── Aggregate overall status ──
    blockers = []
    if is_medcoder and not health["faiss_index"].get("available"):
        blockers.append("faiss_index_not_ready")
    if not health["llm_provider"].get("available"):
        blockers.append("llm_provider_not_configured")
    if not health["mcp_tools"].get("available"):
        blockers.append("mcp_tools_not_registered")
    if blockers:
        health["overall"] = "degraded" if len(blockers) <= 1 else "blocked"
        health["blockers"] = blockers
    else:
        health["overall"] = "ready"
    return health


@router.get("/{agent_id}/requirements")
async def get_agent_requirements(agent_id: str) -> dict[str, Any]:
    """Return the assets, tools, models, env vars, and permissions an agent needs.

    Drives:
    * Agent Hub UI → "What does this agent need to run?"
    * icoder_doctor.py → "Are all required assets present?"
    * Onboarding docs → which env vars to set, which files to provide.

    No fake data: missing files / unconfigured env vars are returned as
    ``"present": false``. The doctor script is responsible for FAIL/WARN
    on these.
    """
    rec = _resolve_agent_ref(agent_id)
    if not rec:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "agent_id": agent_id,
                "message": f"Agent not found: {agent_id}",
            },
        )

    # Read raw pack_data — discovery path must work even for packs that
    # fail AgentPackageV1.from_dict validation (e.g., format_version 1.2,
    # MCP-style tools without `tier` field).
    raw_pack = getattr(rec, "pack_data", None) or {}
    if not isinstance(raw_pack, dict):
        raise HTTPException(
            status_code=400,
            detail=f"Agent pack_data is invalid (type={type(raw_pack).__name__})",
        )

    ref = getattr(rec, "agent_ref", "") or ""
    is_medcoder = ("medcoder" in ref.lower()) or ("medical-coding" in ref.lower())
    tier = _tier_from_raw_pack(raw_pack)
    agent_type = raw_pack.get("agent_type", "")
    pack_format_version = raw_pack.get("format_version", "")
    raw_experts = raw_pack.get("experts") or []
    raw_tools = raw_pack.get("tools") or []
    raw_reqs = raw_pack.get("requirements") or {}
    raw_permissions = _permissions_from_raw_pack(raw_pack)
    raw_human_review = raw_pack.get("human_review_required_when") or []

    # ── Filesystem assets (MedCodER) ──
    file_assets: list[dict[str, Any]] = []
    if is_medcoder:
        from pathlib import Path

        idx_dir = Path("data/medcoder")
        candidates = [
            ("faiss.index", "ICD-10 BGE-M3 FAISS index"),
            ("faiss_icd9cm3.index", "ICD-9-CM-3 BGE-M3 FAISS index"),
            ("metadata.pkl", "ICD-10 metadata"),
            ("metadata_icd9cm3.pkl", "ICD-9-CM-3 metadata"),
        ]
        for fname, desc in candidates:
            path = idx_dir / fname
            file_assets.append(
                {
                    "kind": "faiss_index" if fname.endswith(".index") else "metadata",
                    "path": str(path),
                    "description": desc,
                    "present": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                }
            )
        models_dir = idx_dir / "models"
        file_assets.append(
            {
                "kind": "embedding_model",
                "path": str(models_dir),
                "description": "BGE-M3 model cache",
                "present": models_dir.exists(),
            }
        )

    # ── MCP tools referenced by this agent ──
    mcp_tools_required: list[dict[str, Any]] = []
    try:
        from app.icoder.mcp.tool_registry import TOOL_REGISTRY

        registered = set(TOOL_REGISTRY.keys())
        for tool in raw_tools:
            if isinstance(tool, str):
                mcp_tools_required.append(
                    {"name": tool, "description": "", "registered": tool in registered, "stage": ""}
                )
                continue
            if not isinstance(tool, dict):
                continue
            name = tool.get("name") or tool.get("id") or tool.get("ref", "")
            mcp_tools_required.append(
                {
                    "name": name,
                    "description": tool.get("description", ""),
                    "registered": name in registered,
                    "stage": tool.get("stage", ""),
                }
            )
    except Exception:
        pass

    # ── Env vars (LLM + feature flags) ──
    env_vars_required: list[dict[str, Any]] = []
    env_var_names = [
        ("ICODER_CREDENTIAL_LLM", "DeepSeek API key (LLM provider)"),
        ("LLM_BASE_URL", "DeepSeek base URL"),
        ("LLM_MODEL", "LLM model name"),
        ("MEDCODER_BGE_DTYPE", "BGE-M3 dtype (float16/float32/bfloat16)"),
        ("MEDCODER_BGE_DEVICE", "BGE-M3 device (cpu/cuda)"),
        ("MEDCODER_SUBPROCESS", "Force subprocess retriever (1/0)"),
        (
            "ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT",
            "E1.8 Stage 1 few-shot (P1.0-A: default off)",
        ),
    ]
    for name, desc in env_var_names:
        env_vars_required.append(
            {
                "name": name,
                "description": desc,
                "set": name in os.environ,
                "value": (
                    "<redacted>" if "CREDENTIAL" in name or "KEY" in name
                    else os.environ.get(name, "")
                ),
            }
        )

    return {
        "agent_id": agent_id,
        "agent_ref": ref,
        "format_version": pack_format_version,
        "agent_type": agent_type,
        "tier": tier,
        "tier_label": _TIER_LABELS.get(tier, f"Tier {tier} — Unknown"),
        "experimental": agent_type == "experimental",
        "production_ready": agent_type in ("certified", "reference"),
        "permissions": raw_permissions,
        "files": file_assets,
        "mcp_tools": mcp_tools_required,
        "env_vars": env_vars_required,
        "experts": [
            {"id": e.get("id"), "role": e.get("role")}
            for e in raw_experts if isinstance(e, dict)
        ],
        "requirements": raw_reqs,
        "human_review_required_when": raw_human_review,
    }


__all__ = ["router"]