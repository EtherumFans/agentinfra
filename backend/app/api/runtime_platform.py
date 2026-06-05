"""Runtime Platform API — PlatformRuntime status, registry health, agent lifecycle.

These endpoints expose the NEW PlatformRuntime (icoder_runtime).
They are separate from the old DeterministicRuntime endpoints (app/api/runtime.py).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_admin_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runtime-platform", tags=["runtime-platform"])


def _compute_tier(record) -> int:
    """Compute security tier from an installed agent record."""
    try:
        from icoder_runtime.core.agent_pack_v1 import AgentPackageV1
        pack = AgentPackageV1.from_dict(record.pack_data)
        return pack.security_tier
    except Exception:
        return 0


def _get_runtime():
    """Get PlatformRuntime from app state. Returns None if not available."""
    try:
        from app.main import app as _app
        return _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    except Exception:
        return None


def _get_registry():
    """Get RuntimeAgentRegistry from app state."""
    try:
        from app.main import app as _app
        return _app.state.agent_registry if hasattr(_app.state, "agent_registry") else None
    except Exception:
        return None


# ── Status ──

@router.get("/status")
async def platform_runtime_status():
    """Get PlatformRuntime health, config, and provider status."""
    rt = _get_runtime()
    if not rt:
        return {"started": False, "error": "PlatformRuntime not initialized"}
    status = rt.status()
    # Add worker safety check
    reg = _get_registry()
    if reg:
        status["registry_safety"] = reg.check_worker_safety()
    return status


# ── Registry Health ──

@router.get("/registry/health")
async def registry_health(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Check RuntimeAgentRegistry ↔ DB Agent table consistency."""
    from app.services.agent_registry_sync_service import AgentRegistrySyncService

    reg = _get_registry()
    if not reg:
        return {"healthy": False, "error": "Registry not initialized"}

    svc = AgentRegistrySyncService(reg)
    report = await svc.check_consistency(db)
    return {
        "healthy": report.consistent,
        **report.to_dict(),
        "registry_path": reg.registry_path,
        "schema_version": reg.SCHEMA_VERSION,
    }


@router.get("/registry/inconsistencies")
async def registry_inconsistencies(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all inconsistencies between Registry and DB."""
    from app.services.agent_registry_sync_service import AgentRegistrySyncService

    reg = _get_registry()
    if not reg:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    svc = AgentRegistrySyncService(reg)
    report = await svc.check_consistency(db)
    return report.to_dict()


class RepairRequest(BaseModel):
    direction: str = "registry_to_db"  # registry_to_db | db_to_registry


@router.post("/registry/repair")
async def registry_repair(
    body: RepairRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Repair inconsistencies. Default: repair DB from Registry (Registry is authoritative)."""
    from app.services.agent_registry_sync_service import AgentRegistrySyncService

    reg = _get_registry()
    if not reg:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    svc = AgentRegistrySyncService(reg)
    if body.direction == "registry_to_db":
        result = await svc.repair_from_registry(db)
    else:
        result = await svc.repair_from_db(db)
    return result


# ── Agent Lifecycle ──

class AgentAction(BaseModel):
    action: str  # enable | disable | uninstall | rollback
    version: str = ""  # for rollback: target version


@router.post("/agents/{agent_ref}/lifecycle")
async def agent_lifecycle(
    agent_ref: str,
    body: AgentAction,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manage agent lifecycle: enable/disable (user), uninstall/rollback (admin only)."""
    rt = _get_runtime()
    reg = _get_registry()
    if not rt or not reg:
        raise HTTPException(status_code=503, detail="Runtime not available")

    try:
        record = reg.get(agent_ref)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_ref}")

    action = body.action

    # Admin-only actions
    if action in ("uninstall", "rollback"):
        if user.role.value not in ("admin", "superadmin") if hasattr(user.role, 'value') else True:
            raise HTTPException(status_code=403, detail="Admin role required for uninstall/rollback")

    if action == "enable":
        record.status = "enabled"
    elif action == "disable":
        record.status = "disabled"
    elif action == "uninstall":
        reg.remove(agent_ref)
        # Also remove from DB
        from app.models.agent import Agent as AgentModel
        result = await db.execute(select(AgentModel).where(AgentModel.id == agent_ref))
        db_agent = result.scalar_one_or_none()
        if db_agent:
            await db.delete(db_agent)
            await db.commit()

        logger.info(f"Agent uninstalled: {agent_ref}")
        return {"agent_ref": agent_ref, "status": "uninstalled", "removed_from_registry": True, "removed_from_db": True}
    elif action == "rollback":
        # Find previous version
        all_agents = reg.list_all()
        base_name = record.name
        versions = [a for a in all_agents if a.name == base_name and a.agent_id != agent_ref]
        target_ver = body.version
        if target_ver:
            versions = [a for a in versions if a.version == target_ver]
        versions.sort(key=lambda a: a.installed_at or "", reverse=True)
        if not versions:
            raise HTTPException(status_code=400, detail="No previous version found for rollback")
        record.status = "disabled"  # Disable current
        versions[0].status = "enabled"  # Enable target
        return {"agent_ref": agent_ref, "status": "disabled", "rollback_to": versions[0].agent_id}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    logger.info(f"Agent lifecycle: {agent_ref} → {action} (status={record.status})")
    return {"agent_ref": agent_ref, "status": record.status, "action": action}


# ── Agent Run via canonical ref ──

class AgentRunInput(BaseModel):
    input: str
    provider: str = ""  # optional: LLM provider to use


@router.post("/agents/{agent_ref}/run")
async def run_agent_by_ref(
    agent_ref: str,
    body: AgentRunInput,
    user: User = Depends(get_current_user),
):
    """Run an installed agent by canonical reference."""
    rt = _get_runtime()
    reg = _get_registry()
    if not rt or not reg:
        raise HTTPException(status_code=503, detail="Runtime not available")

    rec = reg.find(agent_ref)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_ref}")

    if rec.status == "disabled":
        raise HTTPException(status_code=403, detail=f"Agent is disabled: {agent_ref}")

    try:
        result = await rt.run_agent(rec.agent_id, body.input)
        from icoder_runtime.core.runtime_result import RuntimeRunResult
        return RuntimeRunResult.from_runner_output(result, agent_ref=rec.agent_id).to_api_response()
    except Exception as e:
        logger.error(f"Agent run failed: {agent_ref}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Installed Agent List (supports canonical ref) ──

@router.get("/agents")
async def list_runtime_agents(
    agent_type: str = Query(""),
):
    """List all agents installed in PlatformRuntime via Registry."""
    reg = _get_registry()
    if not reg:
        return {"agents": [], "total": 0}

    records = reg.list_all(agent_type=agent_type) if agent_type else reg.list_all()
    result = []
    for r in records:
        s = r.to_summary()
        s["agent_ref"] = s.pop("id")
        s["tier"] = _compute_tier(r)
        s["usage_count"] = 0
        result.append(s)
    return {"agents": result, "total": len(result)}


# ═══════════════════════════════════════════════════════════════
# Standard /api/runtime/* router (deprecates /api/runtime-platform/*)
# ═══════════════════════════════════════════════════════════════

runtime_router = APIRouter(prefix="/api/runtime", tags=["runtime"])


@runtime_router.get("/status")
async def runtime_status_standard():
    """Standard Runtime status — includes data_policy, observability, registry info."""
    return await platform_runtime_status()


@runtime_router.get("/registry/health")
async def registry_health_standard(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await registry_health(admin=admin, db=db)


@runtime_router.get("/registry/inconsistencies")
async def registry_inconsistencies_standard(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await registry_inconsistencies(admin=admin, db=db)


@runtime_router.post("/registry/repair")
async def registry_repair_standard(
    body: RepairRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await registry_repair(body=body, admin=admin, db=db)


@runtime_router.post("/agents/{agent_ref}/lifecycle")
async def agent_lifecycle_standard(
    agent_ref: str,
    body: AgentAction,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await agent_lifecycle(agent_ref=agent_ref, body=body, admin=admin, db=db)


@runtime_router.post("/agents/{agent_ref}/run")
async def run_agent_by_ref_standard(
    agent_ref: str,
    body: AgentRunInput,
    user: User = Depends(get_current_user),
):
    return await run_agent_by_ref(agent_ref=agent_ref, body=body, user=user)


@runtime_router.get("/agents")
async def list_runtime_agents_standard(
    agent_type: str = Query(""),
):
    return await list_runtime_agents(agent_type=agent_type)


# ── Public evaluation endpoint (development use) ──

class EvalRunRequest(BaseModel):
    encounter_text: str = ""

@runtime_router.post("/evaluation/run-single")
async def evaluation_run_single(body: EvalRunRequest):
    """Public evaluation endpoint — runs medical-coding-agent via PlatformRuntime without auth."""
    rt = _get_runtime()
    reg = _get_registry()
    if not rt or not reg:
        raise HTTPException(status_code=503, detail="Runtime not available")

    rec = reg.find(AGENT_REF)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Agent not found")

    if rec.status == "disabled":
        raise HTTPException(status_code=403, detail="Agent is disabled")

    result = await rt.run_agent(rec.agent_id, body.encounter_text)
    from icoder_runtime.core.runtime_result import RuntimeRunResult
    return RuntimeRunResult.from_runner_output(result, agent_ref=rec.agent_id).to_api_response()


class InstallRequest(BaseModel):
    agent_name: str = ""
    agent_version: str = "1.0.0"
    agent_type: str = "community"  # certified | community

@runtime_router.post("/agents/install")
async def install_agent_to_runtime(body: InstallRequest):
    """Quick-install an agent from DB to the Runtime Registry. No auth required for dev."""
    rt = _get_runtime()
    reg = _get_registry()
    if not rt or not reg:
        raise HTTPException(status_code=503, detail="Runtime not available")

    clean = body.agent_name.lower().replace(' ', '-').replace('(copy)', '').strip('-')
    agent_ref = f"{clean}-{body.agent_version}"

    # Check if already installed
    existing = reg.find(agent_ref)
    if existing:
        existing.status = "enabled"
        return {"agent_ref": existing.agent_id, "status": "enabled", "action": "already_installed"}

    # Try to fetch agent details from DB for system_prompt
    system_prompt = "You are a helpful medical coding assistant."
    description = ""
    category = "general"
    icon = "Bot"
    try:
        from sqlalchemy import select
        from app.database import async_session_factory
        from app.models.agent import Agent as AgentModel
        async with async_session_factory() as db:
            result = await db.execute(select(AgentModel).where(AgentModel.name == body.agent_name))
            agent = result.scalar_one_or_none()
            if agent:
                system_prompt = agent.system_prompt or system_prompt
                description = agent.description or ""
                category = agent.category or "general"
                icon = agent.icon or "Bot"
    except Exception:
        pass

    # Create pack and install
    pack = {
        "format_version": "1.1", "agent_type": body.agent_type,
        "manifest": {"name": body.agent_name, "version": body.agent_version, "description": description, "category": category, "icon": icon},
        "system_prompt": system_prompt, "experts": [], "tools": [], "permissions": {},
        "requirements": {"min_runtime_version": "1.0.0"}, "llm_capabilities": {},
    }
    try:
        result = rt.install_agent(pack, publisher_name="iCoDer")
        return {"agent_ref": result["agent_id"], "status": "enabled", "action": "installed"}
    except Exception as e:
        detail = e.detail if hasattr(e, 'detail') else str(e)
        raise HTTPException(status_code=400, detail=detail)


AGENT_REF = "icoder/medical-coding-agent@1.0.0"

# ── Observability ──

@runtime_router.get("/runs")
async def list_runs(agent_ref: str = Query(""), limit: int = Query(50, le=200)):
    """List recent agent run history."""
    try:
        from app.main import app as _app
        history = _app.state.run_history if hasattr(_app.state, "run_history") else None
    except Exception:
        history = None
    if not history:
        return {"runs": [], "total": 0}
    runs = history.query(agent_ref=agent_ref, limit=limit)
    return {"runs": runs, "total": len(runs)}


@runtime_router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get a single run by run_id."""
    try:
        from app.main import app as _app
        history = _app.state.run_history if hasattr(_app.state, "run_history") else None
    except Exception:
        history = None
    if not history:
        raise HTTPException(status_code=404, detail="Run history not available")
    entry = history.get(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return entry


@runtime_router.get("/observability/fallback")
async def fallback_stats(hours: int = Query(24, ge=1, le=168)):
    """Get fallback statistics."""
    try:
        from app.main import app as _app
        tracker = _app.state.fallback_tracker if hasattr(_app.state, "fallback_tracker") else None
    except Exception:
        tracker = None
    if not tracker:
        return {"total_fallbacks": 0, "available": False}
    return tracker.stats(hours=hours)


@runtime_router.get("/observability/shadow")
async def shadow_stats(hours: int = Query(24, ge=1, le=168)):
    """Get shadow diff statistics."""
    try:
        from app.main import app as _app
        diff_svc = _app.state.shadow_diff_service if hasattr(_app.state, "shadow_diff_service") else None
    except Exception:
        diff_svc = None
    if not diff_svc:
        return {"total_comparisons": 0, "available": False}
    return diff_svc.stats(hours=hours)


@runtime_router.get("/audit-log")
async def audit_log_events(
    event_type: str = Query(""),
    limit: int = Query(100, le=500),
    admin: User = Depends(get_admin_user),
):
    """Query runtime audit log."""
    try:
        from app.main import app as _app
        audit = _app.state.runtime_audit_logger if hasattr(_app.state, "runtime_audit_logger") else None
    except Exception:
        audit = None
    if not audit:
        return {"events": [], "total": 0}
    events = audit.query(event_type=event_type, limit=limit)
    return {"events": events, "total": len(events)}


@runtime_router.get("/data-policy")
async def get_data_policy():
    """Return current RuntimeDataPolicy."""
    try:
        from app.main import app as _app
        policy = _app.state.data_policy if hasattr(_app.state, "data_policy") else None
    except Exception:
        policy = None
    if not policy:
        from icoder_runtime.core.data_policy import RuntimeDataPolicy
        policy = RuntimeDataPolicy.from_env()
    return policy.to_dict()


# ── Medical Coding API ──

@runtime_router.get("/medical-coding/status")
async def medical_coding_status():
    """Get MedicalCodingLLMProvider status, mode, provider_mode (real vs mock), DeepSeek config."""
    try:
        from app.main import app as _app
        gateway = _app.state.platform_gateway if hasattr(_app.state, "platform_gateway") else None
        data_policy = _app.state.data_policy if hasattr(_app.state, "data_policy") else None
        runtime_cfg = _app.state.runtime_config if hasattr(_app.state, "runtime_config") else None
    except Exception:
        gateway = None; data_policy = None; runtime_cfg = None

    providers = gateway.list_providers() if gateway else {}
    mc_health = providers.get("medical_coding", {"mode": "unknown"})
    ds_health = providers.get("deepseek", {"status": "not_configured"})

    # Determine actual provider mode
    mc_mode = mc_health.get("mode", "unknown")
    deepseek_configured = ds_health.get("status") == "configured"
    provider_mode = "real" if (mc_mode == "real" and deepseek_configured) else "mock"
    if mc_mode == "real" and not deepseek_configured:
        provider_mode = "degraded"  # Has adapter but no API key

    engine_info = mc_health.get("engine", {})
    if isinstance(engine_info, dict):
        active_model = engine_info.get("model", ds_health.get("model", "unknown"))
    else:
        active_model = ds_health.get("model", "unknown")

    return {
        "provider": "medical_coding",
        "mode": mc_mode,
        "provider_mode": provider_mode,
        "deepseek_configured": deepseek_configured,
        "model": active_model,
        "deepseek_status": ds_health.get("status", "unknown"),
        "data_policy": data_policy.to_dict() if data_policy else {},
        "external_llm_allowed": data_policy.allow_external_llm if data_policy else False,
        "pii_redaction_enabled": data_policy.pii_redaction_required if data_policy else True,
        "execution_mode": runtime_cfg.execution_mode if runtime_cfg else "unknown",
    }


class MedicalCodingTestRequest:
    def __init__(self, encounter_text: str = "", mode: str = ""):
        self.encounter_text = encounter_text
        self.mode = mode


@runtime_router.post("/medical-coding/test")
async def medical_coding_test(body: EvalRunRequest):
    """Test medical coding with a sample encounter."""
    encounter_text = body.encounter_text
    if not encounter_text:
        raise HTTPException(status_code=400, detail="encounter_text or input is required")

    try:
        from app.main import app as _app
        gateway = _app.state.platform_gateway if hasattr(_app.state, "platform_gateway") else None
        data_policy = _app.state.data_policy if hasattr(_app.state, "data_policy") else None
    except Exception:
        gateway = None
        data_policy = None

    if not gateway:
        raise HTTPException(status_code=503, detail="LLM Gateway not available")

    # Check data policy
    if data_policy and not data_policy.allow_external_llm:
        raise HTTPException(
            status_code=403,
            detail="External LLM blocked by data_policy. Set ICODER_ALLOW_EXTERNAL_LLM=true to enable."
        )

    # Apply PII redaction
    messages = [{"role": "user", "content": encounter_text}]
    redaction_result = None
    if data_policy and data_policy.pii_redaction_required:
        from icoder_runtime.core.pii_redaction import PIIRedactor
        redactor = PIIRedactor(enabled=True)
        messages, redaction_result = redactor.redact_messages(messages)

    # Use HybridCodingAdapter
    from icoder_runtime.providers.medical_coding import HybridCodingAdapter
    adapter = HybridCodingAdapter(gateway=gateway, mode="hybrid")
    result = await adapter.infer_async(messages)

    response = result.to_dict()
    if redaction_result:
        response["redaction"] = redaction_result.to_dict()

    return response


# ── Rule Engine API ──

@runtime_router.get("/rule-engine/status")
async def rule_engine_status():
    """Get RuleEngine status."""
    from icoder_runtime.providers.medical_coding.rule_engine_adapter import RuleEngineAdapter
    engine = RuleEngineAdapter()
    return engine.health_check()


class RuleValidateRequest(BaseModel):
    rule_set: str = "medical_coding"
    structured_output: dict
    context: dict = {}


@runtime_router.post("/rule-engine/validate")
async def rule_engine_validate(body: RuleValidateRequest):
    """Validate a MedicalCodingOutputSchema against all rules."""
    from icoder_runtime.core.coding_schema import MedicalCodingOutputSchema
    from icoder_runtime.providers.medical_coding.rule_engine_adapter import RuleEngineAdapter

    schema = MedicalCodingOutputSchema.from_dict(body.structured_output, provider="api")
    engine = RuleEngineAdapter()
    result = engine.validate(schema)
    return result.to_dict()


@runtime_router.get("/rule-engine/rules")
async def rule_engine_rules():
    """List all rule engine rules."""
    from icoder_runtime.providers.medical_coding.rule_engine_adapter import RuleEngineAdapter
    engine = RuleEngineAdapter()
    return {
        "rules": engine.rules,
        "summary": engine.rules_summary,
    }
