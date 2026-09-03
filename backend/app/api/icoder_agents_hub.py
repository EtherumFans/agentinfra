"""Phase 3-B1 — Corti-style Agent Hub endpoint.

Restored 2026-07-04 (Phase 3-B1 Section B). The Phase 2.1-B deletion of
``icoder_agents_hub.py`` (1029 LOC) left the frontend AgentsPage with no
pack-mastered data source. This router rebuilds the Hub with
``official_agents/**/agent_pack.json`` as the canonical source.

Contract (per Phase 3-B1 prompt §B):

- ``GET /api/icoder/agents/hub`` — Corti-style Hub card list, no auth,
  read-only, pack-mastered.
- hidden_from_hub=true packs do NOT appear.
- metadata-only, invalid, unresolved, or otherwise non-launch-candidate Packs
  do NOT appear. The public Hub contains only runnable development candidates.
- stub packs (``agent_type=expert-stub``) do NOT appear.
- internal_engine packs do NOT appear.
- Runnable agents appear with an explicit engineering launch-candidate badge;
  the obsolete MVP label is not presented to users.
- production_ready=false is always surfaced — never displayed as
  production-ready.
- No run path (empty ``experts[]``) ⇒ ``runnable=false``.

Phase 3-B2 Loop 1 (2026-07-05): Added ``POST /{agent_id}/clone`` endpoint
and ``clone_url``/``chat_url``/``customize_url``/``run_url`` fields to
each Hub card. Cloning copies a prebuilt Agent (organization_id=NULL)
into the requesting user's org as a custom Agent (is_prebuilt=False).
Conflict strategy: idempotent — if a clone already exists for
``(org, source_agent_ref)``, return 200 OK with the existing record's
URLs (no duplicate created). First clone returns 201 Created.

This router does NOT execute agents — it only describes them. Execution
lives in A2A mainline (Section D) and the compatibility shim (Section E).
"""
from __future__ import annotations

import json
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import (
    get_current_organization,
    get_current_user,
    require_org_membership,
)
from app.middleware.audit import log_action
from app.models.agent import Agent
from app.models.user import User
from app.models.organization import Organization, OrganizationMember
from app.services.agent_display_status import project_pack_to_display_status
from app.services.model_catalog import build_model_catalog
from app.services.model_readiness import (
    latest_tenant_canary_evidence,
    tenant_cached_probe,
)
from app.services.tenant_model_routing import selection_from_settings
from icoder_runtime.backends.registry import get_default_registry
from icoder_runtime.core.agent_execution_paths import (
    DEDICATED_AGENT_EXECUTION_PATHS,
    EXTERNAL_LLM_EXECUTION_TARGETS,
    resolve_agent_execution,
    runtime_dependencies_for_target,
)
from icoder_runtime.core.data_policy import RuntimeDataPolicy
from icoder_runtime.core.agent_pack_loader import load_pack
from icoder_runtime.core.agent_pack_schema import NormalizedPack, PackStatus

router = APIRouter(prefix="/api/icoder/agents", tags=["agent-hub"])


class AgentHubRuntimeReadiness(BaseModel):
    """Public, secret-free readiness axes for one Hub Agent."""

    model_config = ConfigDict(extra="forbid")

    structural_status: Literal["ready", "blocked"]
    configuration_status: Literal[
        "not_checked",
        "local_ready",
        "configured_not_live_verified",
        "unavailable",
    ]
    run_action_enabled: bool
    reason: str
    runtime_dependencies: list[str]
    external_llm_required: bool
    live_health_verified: bool
    semantic_validation_status: Literal["verified", "not_verified"]
    production_approval_status: Literal["approved", "not_approved"]


class AgentHubOutputContractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_ref: str | None = None
    required_fields: list[str]
    optional_fields: list[str]
    field_types: dict[str, str]
    field_schemas: dict[str, Any]
    field_relations: list[dict[str, Any]]
    evidence_bindings: list[dict[str, Any]]
    cross_agent_relations: list[dict[str, Any]]


class AgentHubCardResponse(BaseModel):
    """Versioned public Hub card; additions require an explicit schema bump."""

    model_config = ConfigDict(extra="forbid")

    agent_ref: str
    agent_id: str
    name: str
    display_name: str
    category: str
    category_display: str
    use_case: str
    icon: str
    version: str
    description: str
    maturity: str
    production_ready: bool
    pack_status: str
    launch_candidate_ready: bool
    launch_candidate_blockers: list[str]
    external_release_gates: list[str]
    execution_path: str
    execution_target: str
    runtime_readiness: AgentHubRuntimeReadiness
    human_review: str
    hidden_from_hub: bool
    runnable: bool
    badge: str
    display_status: str
    display_badges: list[dict[str, Any]]
    usage_boundaries: list[str]
    display_status_internal: dict[str, Any]
    tags: list[str]
    workflow: str
    red_lines: dict[str, bool]
    requirements: dict[str, Any]
    output_contract: AgentHubOutputContractResponse
    non_goals: list[str]
    human_review_required_when: list[str]
    a2a_endpoint: str | None
    run_endpoint: str | None
    clone_url: str | None
    chat_url: str | None
    customize_url: str | None
    run_url: str | None
    created_at: str
    creator: str
    default_runtime_mode: str
    available_runtime_modes: list[str]
    example_inputs: list[dict[str, Any]]
    example_outputs: list[dict[str, Any]]
    built_by: str


class AgentHubListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentHubCardResponse]
    total: int
    source: Literal["official_agents/agent_pack.json"]
    schema_version: Literal["1.3"]


class AgentHubTenantRuntimeReadiness(BaseModel):
    """Authenticated readiness for the current tenant's effective model route."""

    model_config = ConfigDict(extra="forbid")

    structural_status: Literal["ready", "blocked"]
    configuration_status: Literal["local_ready", "configured", "unavailable"]
    run_action_enabled: bool
    reason: str
    runtime_dependencies: list[str]
    llm_required: bool
    live_health_verified: bool
    connectivity_status: Literal[
        "not_applicable", "not_run", "verified", "expired", "failed"
    ]
    semantic_validation_status: Literal["verified", "not_verified"]
    production_approval_status: Literal["approved", "not_approved"]


class AgentHubTenantReadinessEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["tenant_configuration_and_connectivity"]
    selection_mode: Literal["inherit", "pinned"]
    selection_version: int
    deployment_id: str | None
    provider_id: str | None
    configuration_probe_status: str
    canary_checked_at: str | None
    canary_expires_at: str | None


class AgentHubTenantReadinessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    execution_target: str
    runtime_readiness: AgentHubTenantRuntimeReadiness
    evidence: AgentHubTenantReadinessEvidence


class AgentHubTenantReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentHubTenantReadinessItem]
    total: int
    generated_at: str
    schema_version: Literal["1.0"]


# ---------------------------------------------------------------------------
# Pack discovery
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_AGENTS_DIR = _REPO_ROOT / "official_agents"


def _load_packs() -> list[dict[str, Any]]:
    """Read every ``agent_pack.json`` under ``official_agents/``."""
    packs: list[dict[str, Any]] = []
    if not OFFICIAL_AGENTS_DIR.exists():
        return packs
    for path in sorted(OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                pack = json.load(f)
            # Phase 4-D (D-6): inject file mtime as fallback created_at
            # for the Corti-style card metadata (DD-Mon-YYYY · Creator).
            try:
                import datetime as _dt
                st = path.stat()
                pack["_pack_mtime_iso"] = _dt.datetime.fromtimestamp(
                    st.st_mtime, tz=_dt.timezone.utc,
                ).strftime("%d-%b-%Y")
            except Exception:
                pack["_pack_mtime_iso"] = ""
            packs.append(pack)
        except Exception:
            # Skip malformed packs silently — Section A.5 audit catches them
            continue
    return packs


# ---------------------------------------------------------------------------
# Visibility + runnability derivation
# ---------------------------------------------------------------------------

def _is_visible(pack: dict[str, Any]) -> bool:
    """Fail closed unless a Pack is a resolvable launch candidate.

    ``hidden_from_hub=false`` is only an intent declaration. It cannot make a
    placeholder, invalid contract, or unknown Provider user-visible.
    """
    manifest = pack.get("manifest") or {}
    if manifest.get("hidden_from_hub") is True:
        return False
    agent_type = pack.get("agent_type")
    if agent_type in ("expert-stub", "internal_engine"):
        return False
    try:
        normalized = load_pack(pack)
        if not _is_runnable(pack, normalized) or not normalized.launch_candidate_ready:
            return False
        agent_id = _agent_id_from_ref(normalized.agent_ref)
        if agent_id in DEDICATED_AGENT_EXECUTION_PATHS:
            return True
        get_default_registry().resolve_from_agent_pack(normalized.raw)
        return True
    except Exception:
        # Browsing must never publish a card that the execution registry cannot
        # resolve. Release tooling reports the exact blocker out of band.
        return False


def load_visible_launch_candidate_packs() -> list[dict[str, Any]]:
    """Return the canonical Pack set published on the user-facing Hub.

    Other user-facing projections (for example the New Agent template picker)
    must call this helper instead of reimplementing visibility and runnability
    rules.
    """

    return [pack for pack in _load_packs() if _is_visible(pack)]


def _is_runnable(
    pack: dict[str, Any], normalized: NormalizedPack | None = None,
) -> bool:
    """Return runtime runnability from the canonical pack loader.

    The Hub previously inferred runnability from raw ``experts`` and
    ``maturity`` fields.  That could advertise an invalid or unwired pack as
    runnable even though the runtime registry rejected it.  Loader status is
    now mandatory; maturity remains the user-facing lifecycle gate.
    """
    normalized = normalized or load_pack(pack)
    if normalized.status != PackStatus.EXECUTABLE:
        return False
    manifest = pack.get("manifest") or {}
    maturity = manifest.get("maturity")
    if maturity in ("metadata-only", "stub", None):
        return False
    if maturity not in ("runnable", "production-ready", "production"):
        return False
    return bool(
        normalized.backend_provider
        or normalized.a2a.get("endpoint")
        or normalized.experts
        or normalized.code
    )


def _badge(pack: dict[str, Any], runnable: bool) -> str:
    """Corti-style badge shown on the Hub card."""
    manifest = pack.get("manifest") or {}
    maturity = manifest.get("maturity")
    if runnable:
        human = manifest.get("human_review") or "required"
        if bool(manifest.get("production_ready")) and maturity in {
            "production-ready", "production"
        }:
            return f"Production ready / AI-assisted / Human review {human}"
        return f"Launch candidate / AI-assisted / Human review {human}"
    # Defensive fallback for direct engineering projections. Public Hub
    # visibility rejects this card before it reaches a user response.
    return "Unavailable / Not published"


def _workflow_summary(pack: dict[str, Any]) -> str:
    """Human-readable workflow summary. For MedCodER packs, derive from
    pipeline.stages. For others, return a one-line summary."""
    pipeline = pack.get("pipeline")
    if isinstance(pipeline, dict) and pipeline.get("stages"):
        stages = [s.get("name", "?") for s in pipeline.get("stages") if isinstance(s, dict)]
        return f"Pipeline: {' → '.join(stages)}"
    # Medical Coding Agent (Corti 7-step) — hardcoded by agent_ref
    if pack.get("agent_ref") == "icoder/medical-coding-agent@2.0.0":
        return "Corti 7-step: Synthesize → Extract → Search → Assign → Validate → Identify Gaps → Review"
    return pack.get("manifest", {}).get("description", "")


def _agent_id_from_ref(agent_ref: str) -> str:
    """Derive the short agent_id from a full agent_ref.

    ``icoder/medical-coding-agent@2.0.0`` → ``medical-coding-agent``.
    Used in URL paths (clone, chat, A2A) where the slash+@ in agent_ref
    would break routing.
    """
    if not agent_ref:
        return ""
    tail = agent_ref.split("/")[-1]
    return tail.split("@")[0]


def runtime_agent_id_from_ref(agent_ref: str) -> str:
    """Public projection helper shared by Hub-adjacent user surfaces."""

    return _agent_id_from_ref(agent_ref)


def _build_card(pack: dict[str, Any]) -> dict[str, Any]:
    """Project an agent_pack.json into a Corti-style Hub card."""
    manifest = pack.get("manifest") or {}
    normalized = load_pack(pack)
    runnable = _is_runnable(pack, normalized)
    agent_ref = pack.get("agent_ref", "")
    agent_id = _agent_id_from_ref(agent_ref)
    execution = resolve_agent_execution(agent_id, normalized.backend_provider)
    execution_target = execution["execution_target"]
    external_llm_required = execution_target in EXTERNAL_LLM_EXECUTION_TARGETS

    # A2A endpoint — only set for runnable packs that declare one
    a2a = pack.get("a2a") or {}
    # A2A is mounted generically for every executable official pack. Keep the
    # Hub contract aligned with discovery when a pack relies on that canonical
    # route instead of declaring an endpoint explicitly.
    a2a_endpoint = None
    if runnable:
        a2a_endpoint = a2a.get("endpoint") or (
            f"/api/icoder/agents/{agent_id}/v1/message:send"
        )

    # Run endpoint — the compatibility shim. Only for runnable packs.
    run_endpoint = None
    if runnable:
        run_endpoint = f"/api/v1/agents/{agent_id}/run"

    # Phase 3-B2 Loop 1: Corti-style action URLs. clone_url is concrete
    # (POST to clone into the caller's org). chat_url + customize_url are
    # templates — the {project_agent_id} placeholder is replaced by the
    # clone response's concrete value. run_url is the A2A mainline.
    clone_url = f"/api/icoder/agents/{agent_id}/clone" if runnable else None
    chat_url = f"/agents/{{project_agent_id}}/chat" if runnable else None
    customize_url = f"/ai-studio/agents/{{project_agent_id}}" if runnable else None
    run_url = run_endpoint if runnable else None

    # Permissions / red lines
    permissions = pack.get("permissions") or {}
    red_lines = {
        "no_upcoding": permissions.get("no_upcoding", False),
        "no_inference": permissions.get("no_inference", False),
        "evidence_required": permissions.get("evidence_required", False),
        "production_writeback_blocked": permissions.get(
            "production_writeback_blocked", False
        ),
    }

    # Requirements
    requirements = pack.get("requirements") or {}
    llm_caps = pack.get("llm_capabilities") or {}
    required_models = [
        m.get("name") for m in (llm_caps.get("required_models") or [])
        if isinstance(m, dict) and m.get("name")
    ]

    # Output contract
    output_contract = pack.get("output_contract") or {}
    output_summary = {
        "schema_ref": output_contract.get("schema_ref"),
        "required_fields": output_contract.get("required_fields") or [],
        "optional_fields": output_contract.get("optional_fields") or [],
        "field_types": output_contract.get("field_types") or {},
        "field_schemas": output_contract.get("field_schemas") or {},
        "field_relations": output_contract.get("field_relations") or [],
        "evidence_bindings": output_contract.get("evidence_bindings") or [],
        "cross_agent_relations": output_contract.get("cross_agent_relations") or [],
    }

    # Non-goals / constraints
    non_goals = pack.get("non_goals") or []
    human_review_when = pack.get("human_review_required_when") or []

    # Phase 4-D (D-6): Corti-style card metadata (DD-Mon-YYYY · Creator).
    # Source: pack's metadata.created_at / metadata.author (if declared);
    # fallback to file mtime + "iCoDer" default.
    metadata = pack.get("metadata") or {}
    created_at = (
        metadata.get("created_at")
        or pack.get("_pack_mtime_iso")
        or ""
    )
    creator = metadata.get("author") or metadata.get("creator") or "iCoDer"

    # Phase 5 Track D P0 Gate 1 (2026-07-11): Unified display status from
    # ``app.services.agent_display_status``. PDF §B3 invariants — only 5
    # user-visible statuses (preview/available/controlled_use/coming_soon/
    # deprecated), max 2 badges per card. Internal fields preserved in
    # ``display_status_internal`` for engineering dashboards (NOT rendered
    # on user cards).
    display = project_pack_to_display_status(pack).to_dict()

    return {
        "agent_ref": agent_ref,
        "agent_id": agent_id,
        "name": manifest.get("name", ""),
        "display_name": manifest.get("name", ""),
        "category": manifest.get("category", ""),
        "category_display": manifest.get("category_display", ""),
        # Phase 3-B2 Loop 4: top-level use_case (manifest.use_case with
        # fallback to category for pre-Loop 4 packs). Used by /hub?use_case=
        # filter and the frontend use_case dropdown.
        "use_case": manifest.get("use_case") or manifest.get("category", ""),
        "icon": manifest.get("icon", ""),
        "version": manifest.get("version", pack.get("agent_ref", "").split("@")[-1]),
        "description": manifest.get("description", ""),
        "maturity": manifest.get("maturity", ""),
        "production_ready": manifest.get("production_ready", False),
        # Machine-verifiable engineering gate.  Passing this gate only means
        # the pack can enter external validation; it is not a production or
        # regulatory approval claim.
        "pack_status": normalized.status.value,
        "launch_candidate_ready": normalized.launch_candidate_ready,
        "launch_candidate_blockers": list(normalized.launch_candidate_blockers),
        "external_release_gates": list(normalized.external_release_gates),
        "execution_path": execution["execution_path"],
        "execution_target": execution_target,
        "runtime_readiness": {
            "structural_status": (
                "ready" if normalized.launch_candidate_ready else "blocked"
            ),
            "configuration_status": "not_checked",
            "run_action_enabled": False,
            "reason": "runtime_configuration_not_checked",
            "runtime_dependencies": runtime_dependencies_for_target(
                execution_target
            ),
            "external_llm_required": external_llm_required,
            "live_health_verified": False,
            "semantic_validation_status": "not_verified",
            "production_approval_status": (
                "approved"
                if bool(manifest.get("production_ready", False))
                else "not_approved"
            ),
        },
        "human_review": manifest.get("human_review", "required"),
        "hidden_from_hub": manifest.get("hidden_from_hub", False),
        "runnable": runnable,
        "badge": _badge(pack, runnable),
        # Phase 5 Track D P0 Gate 1: user-visible display status (PDF §B3).
        # Frontend MUST render ``display_status`` + ``display_badges`` (≤2)
        # instead of raw maturity/production_ready/human_review.
        "display_status": display["display_status"],
        "display_badges": display["display_badges"],
        "usage_boundaries": display["usage_boundaries"],
        "display_status_internal": display["internal"],
        "tags": manifest.get("tags", []),
        "workflow": _workflow_summary(pack),
        "red_lines": red_lines,
        "requirements": {
            "min_runtime_version": requirements.get("min_runtime_version"),
            "icoder_runtime_modules": requirements.get("icoder_runtime_modules") or [],
            "required_models": required_models,
        },
        "output_contract": output_summary,
        "non_goals": non_goals,
        "human_review_required_when": human_review_when,
        "a2a_endpoint": a2a_endpoint,
        "run_endpoint": run_endpoint,
        # Phase 3-B2 Loop 1: Corti-style action URLs.
        "clone_url": clone_url,
        "chat_url": chat_url,
        "customize_url": customize_url,
        "run_url": run_url,
        # Phase 4-D (D-6): Corti-style card metadata.
        "created_at": created_at,
        "creator": creator,
        # Phase 4-F (2026-07-09): Prebuilt Agent spec fields — drive the
        # Agents list runtime_mode badge + the Agent Detail "Try" demo
        # button + the Settings panel runtime selector. Empty for legacy
        # packs that haven't been upgraded to v1.3 spec yet (F2 will
        # populate them for the 8 iCoDer built agents).
        "default_runtime_mode": pack.get("default_runtime_mode", ""),
        "available_runtime_modes": list(pack.get("available_runtime_modes") or []),
        "example_inputs": list(pack.get("example_inputs") or []),
        "example_outputs": list(pack.get("example_outputs") or []),
        "built_by": pack.get("built_by", ""),
    }


def _attach_public_runtime_readiness(
    cards: list[dict[str, Any]],
) -> None:
    """Public browsing never projects tenant or operator runtime state."""
    for card in cards:
        readiness = dict(card.get("runtime_readiness") or {})
        readiness.update({
            "configuration_status": "not_checked",
            "run_action_enabled": False,
            "reason": "tenant_runtime_readiness_requires_authentication",
            "live_health_verified": False,
        })
        card["runtime_readiness"] = readiness


def _tenant_configuration_reason(selected_model: dict[str, Any] | None) -> str:
    if not selected_model:
        return "tenant_model_deployment_unavailable"
    status_value = str(selected_model.get("status") or "")
    if status_value == "development_only":
        return "mock_provider"
    blockers = {
        str(value) for value in (selected_model.get("blocking_reasons") or [])
    }
    for blocker, public_reason in (
        ("credential_not_configured", "credential_not_configured"),
        ("egress_policy_denied", "external_llm_egress_denied"),
        ("provider_endpoint_mismatch", "provider_endpoint_mismatch"),
        ("tenant_model_deployment_unavailable", "tenant_model_deployment_unavailable"),
        ("unsupported_provider_configuration", "unsupported_provider_configuration"),
    ):
        if blocker in blockers:
            return public_reason
    return "tenant_model_configuration_unavailable"


async def _tenant_readiness_items(
    cards: list[dict[str, Any]],
    *,
    request: Request,
    current_org: Organization,
    db: AsyncSession,
) -> list[AgentHubTenantReadinessItem]:
    policy = getattr(request.app.state, "data_policy", None)
    if not isinstance(policy, RuntimeDataPolicy):
        policy = RuntimeDataPolicy.from_env()
    configured_provider = os.environ.get(
        "LLM_PROVIDER", settings.LLM_PROVIDER or "mock"
    ).strip().lower()
    credential_configured = bool(
        os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
        or settings.LLM_API_KEY
    )
    deployment_map = dict(
        getattr(request.app.state, "model_deployments", {}) or {}
    )
    selection = selection_from_settings(current_org.settings)
    catalog = build_model_catalog(
        configured_provider=configured_provider,
        configured_model=settings.LLM_MODEL,
        configured_base_url=settings.LLM_BASE_URL,
        credential_configured=credential_configured,
        data_policy=policy,
        tenant_selection=selection.to_public_dict(),
        registered_deployments=list(deployment_map.values()),
    )
    deployment_id = str(catalog.get("effective_deployment_id") or "").strip().lower()
    provider_id = str(catalog.get("active_provider") or "").strip().lower()
    selected_model = next(
        (
            dict(item)
            for item in (catalog.get("models") or [])
            if isinstance(item, dict) and item.get("selected") is True
        ),
        None,
    )
    configured = bool(
        selected_model
        and selected_model.get("status") == "configured_not_live_verified"
    )

    probe_cache = dict(getattr(request.app.state, "model_health", {}) or {})
    probe = tenant_cached_probe(
        probe_cache,
        current_org.id,
        deployment_id,
    )
    probe_status = str((probe or {}).get("status") or "not_run")
    probe_blocked = probe_status in {"blocked", "down"}

    canary = await latest_tenant_canary_evidence(
        db,
        organization_id=current_org.id,
        deployment_id=deployment_id,
        ttl_seconds=settings.ICODER_MODEL_LIVE_CANARY_READINESS_TTL_SECONDS,
    )
    # Local-capable Agents have real deployment dependencies too. Resolve and
    # probe their Providers instead of treating "does not require an LLM" as
    # equivalent to healthy. This is especially important for the governed
    # Code Validation baseline, whose pinned external catalog files may be
    # missing, tampered, or forbidden by the deployment profile.
    local_health: dict[str, Any] = {}
    registry = get_default_registry()
    for target in sorted({
        str(card.get("execution_target") or "")
        for card in cards
        if str(card.get("execution_target") or "")
        not in EXTERNAL_LLM_EXECUTION_TARGETS
    }):
        if target:
            local_health[target] = await registry.health(target)
    items: list[AgentHubTenantReadinessItem] = []
    for card in cards:
        target = str(card.get("execution_target") or "")
        llm_required = target in EXTERNAL_LLM_EXECUTION_TARGETS
        structural_status = str(
            (card.get("runtime_readiness") or {}).get("structural_status")
            or "blocked"
        )
        production_status = str(
            (card.get("runtime_readiness") or {}).get(
                "production_approval_status"
            )
            or "not_approved"
        )
        if not llm_required:
            health = local_health.get(target)
            health_state = str(getattr(health, "state", "down") or "down")
            local_ok = health_state == "ok"
            configuration_status = "local_ready" if local_ok else "unavailable"
            run_action_enabled = structural_status == "ready" and local_ok
            reason = (
                "local_runtime_health_verified"
                if local_ok
                else "local_runtime_health_failed"
            )
            connectivity_status = "verified" if local_ok else "failed"
            live_health_verified = local_ok
        elif not configured:
            configuration_status = "unavailable"
            run_action_enabled = False
            reason = _tenant_configuration_reason(selected_model)
            connectivity_status = canary.status
            live_health_verified = False
        elif probe_blocked:
            configuration_status = "unavailable"
            run_action_enabled = False
            reason = "tenant_model_configuration_probe_failed"
            connectivity_status = canary.status
            live_health_verified = False
        else:
            configuration_status = "configured"
            run_action_enabled = structural_status == "ready" and canary.status != "failed"
            reason = (
                "tenant_model_connectivity_failed"
                if canary.status == "failed"
                else "tenant_model_configuration_present"
            )
            connectivity_status = canary.status
            live_health_verified = canary.live_health_verified
        items.append(AgentHubTenantReadinessItem(
            agent_id=str(card.get("agent_id") or ""),
            execution_target=target,
            runtime_readiness=AgentHubTenantRuntimeReadiness(
                structural_status=(
                    "ready" if structural_status == "ready" else "blocked"
                ),
                configuration_status=configuration_status,
                run_action_enabled=run_action_enabled,
                reason=reason,
                runtime_dependencies=runtime_dependencies_for_target(target),
                llm_required=llm_required,
                live_health_verified=live_health_verified,
                connectivity_status=connectivity_status,
                semantic_validation_status="not_verified",
                production_approval_status=(
                    "approved" if production_status == "approved" else "not_approved"
                ),
            ),
            evidence=AgentHubTenantReadinessEvidence(
                scope="tenant_configuration_and_connectivity",
                selection_mode=(
                    "pinned" if selection.mode == "pinned" else "inherit"
                ),
                selection_version=selection.version,
                deployment_id=(deployment_id or None) if llm_required else None,
                provider_id=(provider_id or None) if llm_required else target,
                configuration_probe_status=(
                    probe_status
                    if llm_required
                    else str(getattr(local_health.get(target), "state", "down"))
                ),
                canary_checked_at=canary.checked_at if llm_required else None,
                canary_expires_at=canary.expires_at if llm_required else None,
            ),
        ))
    return items


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/hub", operation_id="icoder_agents_hub_list_v1")
async def list_hub_agents(
    use_case: str | None = Query(
        None,
        description="Filter by manifest.use_case (Phase 3-B2 Loop 4).",
    ),
) -> AgentHubListResponse:
    """Corti-style Agent Hub card list.

    Reads ``official_agents/**/agent_pack.json`` as the canonical source.
    Filters:

    - ``hidden_from_hub=true`` packs excluded.
    - ``agent_type=expert-stub`` packs excluded.
    - ``agent_type=internal_engine`` packs excluded.
    - ``use_case`` query param filters by ``manifest.use_case`` (Phase 3-B2 Loop 4).

    Only executable, Provider-resolvable development launch candidates are
    included. Non-production candidates use
    ``badge="Launch candidate / AI-assisted / Human review required"``.

    No auth — this is a product browsing endpoint. Execution is gated
    separately at the run endpoint.
    """
    cards = [_build_card(pack) for pack in load_visible_launch_candidate_packs()]
    _attach_public_runtime_readiness(cards)
    if use_case:
        cards = [c for c in cards if _card_use_case(c) == use_case]
    # Sort: runnable first, then by category, then by name
    cards.sort(key=lambda c: (not c["runnable"], c["category"], c["name"]))
    return AgentHubListResponse(
        agents=[AgentHubCardResponse.model_validate(card) for card in cards],
        total=len(cards),
        source="official_agents/agent_pack.json",
        schema_version="1.3",
    )


@router.get(
    "/hub/readiness",
    operation_id="icoder_agents_hub_tenant_readiness_v1",
    response_model=AgentHubTenantReadinessResponse,
)
async def get_hub_tenant_readiness(
    request: Request,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> AgentHubTenantReadinessResponse:
    """Return tenant-bound configuration and expiring connectivity evidence."""
    response.headers["Cache-Control"] = "no-store"
    cards = [_build_card(pack) for pack in load_visible_launch_candidate_packs()]
    items = await _tenant_readiness_items(
        cards,
        request=request,
        current_org=current_org,
        db=db,
    )
    items.sort(key=lambda item: item.agent_id)
    return AgentHubTenantReadinessResponse(
        agents=items,
        total=len(items),
        generated_at=datetime.now(UTC).isoformat(),
        schema_version="1.0",
    )


def _card_use_case(card: dict[str, Any]) -> str:
    """Extract use_case from a Hub card (Phase 3-B2 Loop 4 filter).

    Order of precedence:
      1. Top-level ``use_case`` field (set by _build_card from
         ``manifest.use_case``).
      2. Fallback to ``category`` for backward compat (pre-Loop 4 packs
         that haven't yet declared use_case in their manifest).
    """
    return str(card.get("use_case") or card.get("category") or "")


# ---------------------------------------------------------------------------
# Phase 3-B2 Loop 1 — Clone endpoint (Gap 2.3)
# ---------------------------------------------------------------------------


class CloneRequest(BaseModel):
    """Request body for POST /api/icoder/agents/{agent_id}/clone.

    All fields optional — the caller can simply POST {} to clone with
    defaults. ``project_id`` is accepted for Corti API parity but maps
    to the caller's organization (iCoDer is org-scoped, not project-scoped).
    """
    project_id: str | None = Field(
        None, description="Corti-style project_id. Maps to org_id in iCoDer."
    )
    name: str | None = Field(None, description="Override the cloned agent's name.")
    description: str | None = Field(None, description="Override description.")
    open_after_clone: bool = Field(
        True, description="If true, response includes ready-to-navigate URLs."
    )


class CloneResponse(BaseModel):
    """Response body for POST /api/icoder/agents/{agent_id}/clone."""
    project_agent_id: str = Field(..., description="DB UUID of the cloned Agent.")
    runtime_agent_id: str = Field(
        ..., description="Project Agent ID used by Run and A2A transports."
    )
    source_runtime_agent_id: str = Field(
        ..., description="Pinned source implementation ID used only for server-side dispatch."
    )
    source_agent_ref: str = Field(
        ..., description="Original agent_ref (e.g. 'icoder/medical-coding-agent@2.0.0')."
    )
    chat_url: str
    customize_url: str
    run_url: str
    cloned: bool = Field(
        ..., description="True if a new clone was created; False if existing clone returned (idempotent)."
    )


async def _find_prebuilt_by_agent_id(db: AsyncSession, agent_id: str) -> Agent | None:
    """Look up a prebuilt Agent by short agent_id (derived from config.agent_ref)."""
    q = select(Agent).where(Agent.is_prebuilt == True)  # noqa: E712
    result = await db.execute(q)
    for agent in result.scalars().all():
        cfg = agent.config or {}
        ref = cfg.get("agent_ref", "") if isinstance(cfg, dict) else ""
        if _agent_id_from_ref(ref) == agent_id:
            return agent
    return None


def _find_visible_pack_by_agent_id(agent_id: str) -> dict[str, Any] | None:
    """Resolve a clone source from the same Pack boundary published by Hub.

    Hub browsing is Pack-mastered, while the database is a derived projection.
    Requiring a DB seed row here made Clone return 404 whenever startup seeding
    was intentionally disabled even though the exact Agent card was visible.
    """
    for pack in load_visible_launch_candidate_packs():
        if _agent_id_from_ref(str(pack.get("agent_ref") or "")) != agent_id:
            continue
        return pack
    return None


def _clone_config_from_pack(pack: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
    manifest = pack.get("manifest") or {}
    return {
        "agent_ref": str(pack.get("agent_ref") or ""),
        "runtime_agent_id": agent_id,
        "agent_type": pack.get("agent_type", "certified"),
        "format_version": pack.get("format_version", "1.2"),
        "use_case": manifest.get("use_case", ""),
        "maturity": manifest.get("maturity", ""),
        "human_review": manifest.get("human_review", "required"),
        "production_ready": bool(manifest.get("production_ready", False)),
        "hidden_from_hub": bool(manifest.get("hidden_from_hub", False)),
        "non_goals": list(pack.get("non_goals") or []),
        "output_contract": dict(pack.get("output_contract") or {}),
        "permissions": dict(pack.get("permissions") or {}),
        "requirements": dict(pack.get("requirements") or {}),
        "llm_capabilities": dict(pack.get("llm_capabilities") or {}),
        "a2a": dict(pack.get("a2a") or {}),
        "runtime_binding": {
            "internal_engine": dict(pack.get("internal_engine") or {}),
            "code": dict(pack.get("code") or {}),
            "integrity": dict(pack.get("integrity") or {}),
        },
    }


async def _find_existing_clone(
    db: AsyncSession, org_id: str, source_agent_ref: str
) -> Agent | None:
    """Look up an existing clone for (org, source_agent_ref)."""
    q = select(Agent).where(
        Agent.is_prebuilt == False,  # noqa: E712
        Agent.organization_id == org_id,
    )
    result = await db.execute(q)
    for agent in result.scalars().all():
        cfg = agent.config or {}
        if not isinstance(cfg, dict):
            continue
        if cfg.get("source_agent_ref") == source_agent_ref:
            return agent
    return None


def _deterministic_clone_id(org_id: str, source_agent_ref: str) -> str:
    """Make Clone idempotency atomic at the primary-key boundary.

    The previous query-then-random-insert flow could create two clones when
    requests arrived concurrently. A deterministic 48-bit ID matches the
    existing 12-character schema and turns that race into one recoverable
    ``IntegrityError`` on every supported database.
    """

    material = f"icoder-clone-v1\0{org_id}\0{source_agent_ref}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:12]


def _clone_response_payload(
    clone: Agent,
    *,
    source_agent_ref: str,
    source_runtime_agent_id: str,
    cloned: bool,
) -> dict[str, Any]:
    return {
        "project_agent_id": clone.id,
        "runtime_agent_id": clone.id,
        "source_runtime_agent_id": source_runtime_agent_id,
        "source_agent_ref": source_agent_ref,
        "chat_url": f"/agents/{clone.id}/chat",
        "customize_url": f"/ai-studio/agents/{clone.id}",
        "run_url": f"/api/icoder/agents/{clone.id}/v1/message:send",
        "cloned": cloned,
    }


@router.post(
    "/{agent_id}/clone",
    operation_id="icoder_agents_clone_v1",
    response_model=CloneResponse,
)
async def clone_agent(
    agent_id: str,
    response: Response,
    body: CloneRequest | None = None,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clone a prebuilt Agent into the caller's organization.

    Phase 3-B2 Loop 1 (Gap 2.3). The source Agent is identified by
    ``agent_id`` (short form, e.g. ``medical-coding-agent``). The clone
    creates a new ``Agent`` row with ``is_prebuilt=False``,
    ``organization_id=<caller's org>``, ``status=published``, and
    ``config.source_agent_ref=<original agent_ref>``.

    Conflict strategy (idempotent): if a clone already exists for
    ``(org, source_agent_ref)``, return **200 OK** with the existing
    record's URLs (no duplicate created). First clone returns 201 Created.

    Errors:
    - 404: agent_id not found among prebuilt agents.
    - 403: auth failure (no valid token).
    - 400: malformed request body.
    """
    body = body or CloneRequest()

    # 1. Resolve the exact visible Pack. A derived DB prebuilt row is not a
    # prerequisite: startup may intentionally omit development seeding.
    source_pack = _find_visible_pack_by_agent_id(agent_id)
    if source_pack is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "AGENT_NOT_FOUND",
                "message": f"No prebuilt agent with agent_id='{agent_id}'",
                "agent_id": agent_id,
            },
        )
    manifest = source_pack.get("manifest") or {}
    source_agent_ref = str(source_pack.get("agent_ref") or "")
    experts = source_pack.get("experts") or []
    expert_ids = [
        str(item.get("expert_id") or item.get("id") or "").strip()
        for item in experts
        if isinstance(item, dict)
        and str(item.get("expert_id") or item.get("id") or "").strip()
    ]
    source_config = _clone_config_from_pack(source_pack, agent_id=agent_id)

    # 2. Check for existing clone (idempotent).
    existing = await _find_existing_clone(db, org.id, source_agent_ref)
    if existing:
        # Idempotent: 200 OK with existing record's URLs (no duplicate).
        response.status_code = 200
        return _clone_response_payload(
            existing,
            source_agent_ref=source_agent_ref,
            source_runtime_agent_id=agent_id,
            cloned=False,
        )

    # 3. Create the clone.
    cloned = Agent(
        id=_deterministic_clone_id(org.id, source_agent_ref),
        organization_id=org.id,
        name=body.name or f"{manifest.get('name') or agent_id} (Clone)",
        description=body.description or str(manifest.get("description") or ""),
        system_prompt=str(source_pack.get("system_prompt") or ""),
        icon=str(manifest.get("icon") or "Bot"),
        category=str(manifest.get("category") or "general"),
        expert_ids=expert_ids,
        default_expert_id=expert_ids[0] if expert_ids else "",
        a2a_enabled=bool(source_pack.get("a2a")),
        config={
            **source_config,
            "source_agent_ref": source_agent_ref,
            "cloned_from_prebuilt": True,
            "cloned_by": user.id,
            "clone_project_id": body.project_id,
        },
        is_prebuilt=False,
        is_published=True,
        status="published",
        version=str(manifest.get("version") or "1.0.0"),
        created_by=user.id,
        usage_count=0,
    )
    db.add(cloned)
    try:
        await db.flush()
        await log_action(
            db,
            user_id=user.id,
            username=getattr(user, "username", None),
            action="agent.lifecycle.cloned_published",
            resource_type="agent",
            resource_id=cloned.id,
            details={
                "source_agent_ref": source_agent_ref,
                "source_runtime_agent_id": agent_id,
                "status": "published",
                "version": cloned.version,
            },
            organization_id=org.id,
        )
        await db.commit()
        await db.refresh(cloned)
    except IntegrityError:
        # A concurrent request may have inserted the same deterministic clone.
        # Roll back this transaction, then return only a row whose provenance
        # proves it is the same org/source clone (never accept an ID collision).
        await db.rollback()
        existing = await _find_existing_clone(db, org.id, source_agent_ref)
        if existing is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "CLONE_ID_CONFLICT",
                    "message": "The project clone identity conflicted with another Agent.",
                },
            )
        response.status_code = 200
        return _clone_response_payload(
            existing,
            source_agent_ref=source_agent_ref,
            source_runtime_agent_id=agent_id,
            cloned=False,
        )

    # First clone: 201 Created.
    response.status_code = 201
    return _clone_response_payload(
        cloned,
        source_agent_ref=source_agent_ref,
        source_runtime_agent_id=agent_id,
        cloned=True,
    )
