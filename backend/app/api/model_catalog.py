"""Authenticated, secret-free model catalog for the iCoDer Console."""

from __future__ import annotations

import os
import logging
import asyncio
import math
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import (
    get_current_organization,
    get_current_user,
    require_org_membership,
    require_org_role,
)
from app.models.organization import Organization, OrganizationMember
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.model_catalog import build_model_catalog
from app.services.model_readiness import (
    tenant_cached_probe,
    tenant_deployment_cache_key,
)
from app.services.tenant_model_routing import (
    selection_from_settings,
    update_selection_settings,
)
from icoder_runtime.core.data_policy import RuntimeDataPolicy


router = APIRouter(prefix="/api/v1/model-catalog", tags=["model-catalog"])
logger = logging.getLogger(__name__)


class ModelCatalogItemResponse(BaseModel):
    id: str
    display_name: str
    default_model: str
    model: str
    deployment_kind: str
    selected: bool
    credential_required: bool
    credential_configured: bool | None
    adapter_capabilities: list[str]
    china_scenario: str
    provider_region: Literal["cn", "eu", "us"]
    tenant_region: Literal["cn", "eu", "us"]
    egress_decision: Literal["allow", "deny"]
    status: Literal[
        "available_to_configure",
        "configured_not_live_verified",
        "development_only",
        "blocked",
    ]
    blocking_reasons: list[str]
    health_status: str = "unknown"
    health_checked_at: str | None = None
    canary_status: str = "not_run"
    canary_checked_at: str | None = None
    canary_scope: Literal["connectivity_only_no_patient_data"] = (
        "connectivity_only_no_patient_data"
    )


class ModelCatalogResponse(BaseModel):
    active_provider: str
    active_model: str
    operator_default_provider: str
    operator_default_model: str
    effective_deployment_id: str
    tenant_selection: "TenantModelSelectionResponse"
    registered_deployments: list["ModelDeploymentResponse"]
    selection_editable: bool = False
    live_canary_available: bool = False
    live_canary_policy: "ModelLiveCanaryPolicy"
    tenant_region: Literal["cn", "eu", "us"]
    egress_policy: Literal["strict", "best_effort", "off"]
    external_llm_allowed: bool
    models: list[ModelCatalogItemResponse]
    readiness_scope: Literal["configuration_and_policy_only"]
    live_health_verified: Literal[False]
    disclaimer: str


class ModelDeploymentResponse(BaseModel):
    id: str
    provider_id: str
    model: str
    is_default: bool
    tenant_selectable: bool
    credential_configured: bool
    canary_status: str = "not_run"
    canary_checked_at: str | None = None


class TenantModelSelectionResponse(BaseModel):
    mode: Literal["inherit", "pinned"]
    deployment_id: str | None = None
    version: int


class TenantModelSelectionUpdate(BaseModel):
    mode: Literal["inherit", "pinned"]
    deployment_id: str | None = Field(default=None, max_length=64)
    expected_version: int = Field(ge=0)


class ModelHealthProbeRequest(BaseModel):
    """Request a no-network configuration health probe for one deployment.

    A configuration probe deliberately never calls an external model and
    therefore cannot create provider usage or billing.  Live model quality
    remains a separate, explicitly controlled external gate.
    """

    deployment_id: str = Field(min_length=1, max_length=64)


class ModelHealthProbeResponse(BaseModel):
    deployment_id: str
    provider_id: str
    model: str
    status: str
    probe_mode: Literal["configuration"] = "configuration"
    egress_decision: Literal["allow", "deny"]
    credential_configured: bool
    circuit_open: bool
    checked_at: str


class ModelLiveCanaryRequest(BaseModel):
    """Explicit authorization for one fixed, non-clinical provider request."""

    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1, max_length=64)
    acknowledge_external_call: Literal[True]
    purpose: Literal["connectivity_only_no_patient_data"]
    max_cost_cny: float = Field(gt=0, le=1.0)


class ModelLiveCanaryCost(BaseModel):
    amount: float = Field(ge=0)
    currency: Literal["CNY"] = "CNY"
    billing_authoritative: Literal[False] = False
    source: Literal["provider_usage_pricing_estimate"] = (
        "provider_usage_pricing_estimate"
    )


class ModelLiveCanaryUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ModelLiveCanaryResponse(BaseModel):
    deployment_id: str
    provider_id: str
    model: str
    status: Literal[
        "reachable",
        "provider_unavailable",
        "unexpected_response",
        "budget_exceeded",
    ]
    reason_code: Literal[
        "ok",
        "provider_degraded",
        "provider_timeout",
        "provider_exception",
        "unexpected_response",
        "reported_cost_exceeded_cap",
    ]
    probe_mode: Literal["external_connectivity_canary"] = (
        "external_connectivity_canary"
    )
    egress_decision: Literal["allow"] = "allow"
    synthetic_payload: Literal[True] = True
    patient_data_sent: Literal[False] = False
    expected_token_matched: bool
    latency_ms: int = Field(ge=0)
    usage: ModelLiveCanaryUsage
    cost: ModelLiveCanaryCost
    request_cost_cap_cny: float
    estimated_max_cost_cny: float
    checked_at: str


class ModelLiveCanaryPolicy(BaseModel):
    purpose: Literal["connectivity_only_no_patient_data"] = (
        "connectivity_only_no_patient_data"
    )
    fixed_synthetic_payload: Literal[True] = True
    patient_data_allowed: Literal[False] = False
    requires_owner_admin: Literal[True] = True
    requires_explicit_acknowledgement: Literal[True] = True
    max_cost_cny: float
    max_output_tokens: int
    timeout_seconds: float
    cooldown_seconds: int


@router.get(
    "",
    summary="List configured and supported LLM provider options",
    response_model=ModelCatalogResponse,
)
async def get_model_catalog(
    request: Request,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    member: OrganizationMember = Depends(require_org_membership),
) -> ModelCatalogResponse:
    response.headers["Cache-Control"] = "no-store"
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
    deployment_map = dict(getattr(request.app.state, "model_deployments", {}) or {})
    catalog = build_model_catalog(
            configured_provider=configured_provider,
            configured_model=settings.LLM_MODEL,
            configured_base_url=settings.LLM_BASE_URL,
            credential_configured=credential_configured,
            data_policy=policy,
            tenant_selection=selection_from_settings(current_org.settings).to_public_dict(),
            registered_deployments=list(deployment_map.values()),
    )
    # Health probes are intentionally process-local and configuration-only.
    # They are not used to claim live model availability; the public catalog
    # remains ``live_health_verified=false`` unless a future external gate
    # supplies independent evidence.
    health_cache = dict(getattr(request.app.state, "model_health", {}) or {})
    canary_cache = dict(getattr(request.app.state, "model_live_canary", {}) or {})
    for item in catalog.get("models", []):
        if item.get("selected"):
            probe = tenant_cached_probe(
                health_cache,
                current_org.id,
                str(catalog.get("effective_deployment_id") or ""),
            )
            if isinstance(probe, dict):
                item["health_status"] = str(probe.get("status") or "unknown")
                item["health_checked_at"] = probe.get("checked_at")
        deployment_id = str(item.get("id") or "").strip().lower()
        canary = tenant_cached_probe(canary_cache, current_org.id, deployment_id)
        if isinstance(canary, dict):
            item["canary_status"] = str(canary.get("status") or "not_run")
            item["canary_checked_at"] = canary.get("checked_at")
    for deployment in catalog.get("registered_deployments", []):
        deployment_id = str(deployment.get("id") or "").strip().lower()
        canary = tenant_cached_probe(canary_cache, current_org.id, deployment_id)
        if isinstance(canary, dict):
            deployment["canary_status"] = str(canary.get("status") or "not_run")
            deployment["canary_checked_at"] = canary.get("checked_at")
    catalog["selection_editable"] = member.role.value in {"owner", "admin"}
    effective_metadata = deployment_map.get(
        str(catalog.get("effective_deployment_id") or "").strip().lower()
    ) or {}
    effective_provider_id = str(
        effective_metadata.get("provider_id") or ""
    ).strip().lower()
    catalog["live_canary_available"] = bool(
        settings.ICODER_MODEL_LIVE_CANARY_ENABLED
        and catalog["selection_editable"]
        and policy.allow_external_llm
        and float(settings.ICODER_MODEL_LIVE_CANARY_MAX_COST_CNY) > 0
        and effective_provider_id in _LIVE_CANARY_PROVIDER_IDS
        and bool(effective_metadata.get("credential_configured"))
    )
    catalog["live_canary_policy"] = ModelLiveCanaryPolicy(
        max_cost_cny=max(
            0.0, min(float(settings.ICODER_MODEL_LIVE_CANARY_MAX_COST_CNY), 1.0)
        ),
        max_output_tokens=max(
            1, min(int(settings.ICODER_MODEL_LIVE_CANARY_MAX_OUTPUT_TOKENS), 32)
        ),
        timeout_seconds=max(
            1.0, min(float(settings.ICODER_MODEL_LIVE_CANARY_TIMEOUT_SECONDS), 30.0)
        ),
        cooldown_seconds=max(
            60, min(int(settings.ICODER_MODEL_LIVE_CANARY_COOLDOWN_SECONDS), 86400)
        ),
    ).model_dump()
    return ModelCatalogResponse.model_validate(catalog)


@router.post(
    "/health-probe",
    summary="Run a tenant-audited, no-network deployment configuration probe",
    response_model=ModelHealthProbeResponse,
)
async def probe_model_health(
    body: ModelHealthProbeRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ModelHealthProbeResponse:
    """Inspect one registered deployment without making an LLM request.

    This endpoint intentionally calls only the provider's local
    ``health_check`` method.  It never sends prompt text, never exposes a
    credential or endpoint, and never silently changes tenant routing.  The
    returned status is configuration health, not clinical or live-provider
    quality; callers must use the separate external validation gate for that.
    """

    response.headers["Cache-Control"] = "no-store"
    deployment_id = body.deployment_id.strip().lower()
    deployments = dict(getattr(request.app.state, "model_deployments", {}) or {})
    metadata = deployments.get(deployment_id)
    gateway = getattr(request.app.state, "platform_gateway", None)
    if not metadata or gateway is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MODEL_DEPLOYMENT_NOT_FOUND"},
        )

    provider_id = str(metadata.get("provider_id") or deployment_id).strip().lower()
    policy = getattr(request.app.state, "data_policy", None)
    if not isinstance(policy, RuntimeDataPolicy):
        policy = RuntimeDataPolicy.from_env()
    decision = policy.egress_decision(provider_id)
    circuit_open = False
    try:
        from icoder_runtime.circuit_breaker import llm_circuit_breaker

        circuit_open = bool(llm_circuit_breaker.is_open)
    except Exception:
        # A missing breaker must not make a configuration probe fail.
        circuit_open = False

    if decision.get("decision") != "allow":
        health: dict[str, object] = {"status": "blocked"}
    else:
        try:
            provider = gateway.get_exact(deployment_id)
        except Exception:
            health = {"status": "down"}
        else:
            try:
                raw_health = provider.health_check()
                health = dict(raw_health) if isinstance(raw_health, dict) else {"status": "unknown"}
            except Exception as exc:
                # Keep the error type out of the public response; the probe
                # remains actionable without reflecting provider internals.
                logger.warning(
                    "model health probe failed deployment=%s error_type=%s",
                    deployment_id,
                    type(exc).__name__,
                )
                health = {"status": "down"}

    checked_at = datetime.now(UTC).isoformat()
    result = ModelHealthProbeResponse(
        deployment_id=deployment_id,
        provider_id=provider_id,
        model=str(metadata.get("model") or ""),
        status=str(health.get("status") or "unknown"),
        egress_decision="allow" if decision.get("decision") == "allow" else "deny",
        credential_configured=bool(metadata.get("credential_configured", False)),
        circuit_open=circuit_open,
        checked_at=checked_at,
    )

    cache = getattr(request.app.state, "model_health", None)
    if not isinstance(cache, dict):
        cache = {}
        request.app.state.model_health = cache
    cache[tenant_deployment_cache_key(current_org.id, deployment_id)] = (
        result.model_dump()
    )
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "model.health.probe",
        "model_deployment",
        deployment_id,
        details={
            "deployment_id": deployment_id,
            "provider_id": provider_id,
            "status": result.status,
            "probe_mode": "configuration",
            "egress_decision": result.egress_decision,
            "circuit_open": result.circuit_open,
            "credential_configured": result.credential_configured,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    return result


_LIVE_CANARY_MESSAGES = [
    {
        "role": "system",
        "content": (
            "This is a synthetic connectivity canary with no patient data. "
            "Reply with exactly ICODER_CANARY_OK and nothing else."
        ),
    },
    {"role": "user", "content": "ICODER_SYNTHETIC_CONNECTIVITY_CANARY"},
]
_LIVE_CANARY_EXPECTED = "ICODER_CANARY_OK"
_LIVE_CANARY_INPUT_TOKEN_BOUND = 1024
_LIVE_CANARY_PROVIDER_IDS = {"deepseek", "qwen", "openai_compat"}


def _live_canary_estimated_max_cost(max_output_tokens: int) -> float:
    return round(
        (
            _LIVE_CANARY_INPUT_TOKEN_BOUND
            * max(float(settings.LLM_PRICE_INPUT_PER_1M), 0.0)
            + max_output_tokens
            * max(float(settings.LLM_PRICE_OUTPUT_PER_1M), 0.0)
        )
        / 1_000_000.0,
        6,
    )


def _bounded_usage_count(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(parsed, 1_000_000))


@router.post(
    "/live-canary",
    summary="Run one budgeted fixed-payload external model connectivity canary",
    response_model=ModelLiveCanaryResponse,
)
async def run_model_live_canary(
    body: ModelLiveCanaryRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ModelLiveCanaryResponse:
    """Send one fixed synthetic request; never accept or return prompt text."""

    response.headers["Cache-Control"] = "no-store"
    if not settings.ICODER_MODEL_LIVE_CANARY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MODEL_LIVE_CANARY_DISABLED"},
        )

    deployment_id = body.deployment_id.strip().lower()
    deployments = dict(getattr(request.app.state, "model_deployments", {}) or {})
    metadata = deployments.get(deployment_id)
    gateway = getattr(request.app.state, "platform_gateway", None)
    if not metadata or gateway is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MODEL_DEPLOYMENT_NOT_FOUND"},
        )

    provider_id = str(metadata.get("provider_id") or "").strip().lower()
    if provider_id not in _LIVE_CANARY_PROVIDER_IDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MODEL_LIVE_CANARY_EXTERNAL_PROVIDER_REQUIRED"},
        )
    if not bool(metadata.get("credential_configured")):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MODEL_LIVE_CANARY_CREDENTIAL_NOT_CONFIGURED"},
        )

    policy = getattr(request.app.state, "data_policy", None)
    if not isinstance(policy, RuntimeDataPolicy):
        policy = RuntimeDataPolicy.from_env()
    decision = policy.egress_decision(provider_id)
    if decision.get("decision") != "allow":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "MODEL_LIVE_CANARY_EGRESS_DENIED"},
        )
    try:
        provider = gateway.get_exact(deployment_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "MODEL_DEPLOYMENT_NOT_REGISTERED"},
        ) from exc

    server_cost_cap = max(
        0.0, min(float(settings.ICODER_MODEL_LIVE_CANARY_MAX_COST_CNY), 1.0)
    )
    max_output_tokens = max(
        1, min(int(settings.ICODER_MODEL_LIVE_CANARY_MAX_OUTPUT_TOKENS), 32)
    )
    timeout_seconds = max(
        1.0, min(float(settings.ICODER_MODEL_LIVE_CANARY_TIMEOUT_SECONDS), 30.0)
    )
    cooldown_seconds = max(
        60, min(int(settings.ICODER_MODEL_LIVE_CANARY_COOLDOWN_SECONDS), 86400)
    )
    estimated_max_cost = _live_canary_estimated_max_cost(max_output_tokens)
    if body.max_cost_cny > server_cost_cap:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MODEL_LIVE_CANARY_CAP_EXCEEDS_SERVER_LIMIT"},
        )
    if estimated_max_cost > body.max_cost_cny:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "MODEL_LIVE_CANARY_CAP_BELOW_ESTIMATE"},
        )

    # Persist the reservation before network I/O. The organization row lock
    # serializes concurrent requests; a crashed canary still consumes cooldown.
    await db.execute(
        select(Organization)
        .where(Organization.id == current_org.id)
        .with_for_update()
    )
    threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        seconds=cooldown_seconds
    )
    recent = (
        await db.execute(
            select(AuditLog)
            .where(
                AuditLog.organization_id == current_org.id,
                AuditLog.action == "model.live_canary.started",
                AuditLog.resource_id == deployment_id,
                AuditLog.created_at >= threshold,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if recent is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "MODEL_LIVE_CANARY_COOLDOWN"},
            headers={"Retry-After": str(cooldown_seconds)},
        )
    common_audit = {
        "deployment_id": deployment_id,
        "provider_id": provider_id,
        "probe_mode": "external_connectivity_canary",
        "egress_decision": "allow",
        "max_cost": body.max_cost_cny,
        "estimated_max_cost": estimated_max_cost,
        "max_output_tokens": max_output_tokens,
        "timeout_seconds": timeout_seconds,
        "cooldown_seconds": cooldown_seconds,
        "synthetic_payload": True,
        "patient_data_sent": False,
        "acknowledged": True,
    }
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "model.live_canary.started",
        "model_deployment",
        deployment_id,
        details=common_audit,
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    started = time.perf_counter()
    provider_result: dict[str, object] = {}
    reason_code = "provider_exception"
    canary_status = "provider_unavailable"
    matched = False
    try:
        raw_result = await asyncio.wait_for(
            provider.generate(
                messages=[dict(item) for item in _LIVE_CANARY_MESSAGES],
                context={
                    "max_tokens": max_output_tokens,
                    "temperature": 0.0,
                    "timeout_seconds": timeout_seconds,
                    "max_attempts": 1,
                },
            ),
            timeout=timeout_seconds + 0.5,
        )
        provider_result = raw_result if isinstance(raw_result, dict) else {}
        if provider_result.get("degraded") is True:
            reason_code = "provider_degraded"
        else:
            matched = str(provider_result.get("content") or "").strip() == (
                _LIVE_CANARY_EXPECTED
            )
            if matched:
                canary_status = "reachable"
                reason_code = "ok"
            else:
                canary_status = "unexpected_response"
                reason_code = "unexpected_response"
    except TimeoutError:
        reason_code = "provider_timeout"
    except Exception as exc:
        logger.warning(
            "model live canary failed deployment=%s error_type=%s",
            deployment_id,
            type(exc).__name__,
        )
        reason_code = "provider_exception"

    latency_ms = max(0, int((time.perf_counter() - started) * 1000))
    raw_usage = provider_result.get("usage")
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = _bounded_usage_count(usage.get("input_tokens"))
    output_tokens = _bounded_usage_count(usage.get("output_tokens"))
    try:
        reported_cost = max(float(provider_result.get("cost_usd") or 0.0), 0.0)
        if not math.isfinite(reported_cost):
            reported_cost = 0.0
    except (TypeError, ValueError, OverflowError):
        reported_cost = 0.0
    if reported_cost > body.max_cost_cny:
        canary_status = "budget_exceeded"
        reason_code = "reported_cost_exceeded_cap"
        matched = False

    checked_at = datetime.now(UTC).isoformat()
    result = ModelLiveCanaryResponse(
        deployment_id=deployment_id,
        provider_id=provider_id,
        model=str(metadata.get("model") or ""),
        status=canary_status,
        reason_code=reason_code,
        expected_token_matched=matched,
        latency_ms=latency_ms,
        usage=ModelLiveCanaryUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
        cost=ModelLiveCanaryCost(amount=reported_cost),
        request_cost_cap_cny=body.max_cost_cny,
        estimated_max_cost_cny=estimated_max_cost,
        checked_at=checked_at,
    )
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "model.live_canary.completed",
        "model_deployment",
        deployment_id,
        details={
            **common_audit,
            "status": result.status,
            "reason_code": result.reason_code,
            "expected_token_matched": result.expected_token_matched,
            "latency_ms": result.latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": reported_cost,
            "currency": "CNY",
            "billing_authoritative": False,
        },
        tokens_used=input_tokens + output_tokens,
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    cache = getattr(request.app.state, "model_live_canary", None)
    if not isinstance(cache, dict):
        cache = {}
        request.app.state.model_live_canary = cache
    cache[tenant_deployment_cache_key(current_org.id, deployment_id)] = {
        "status": result.status,
        "checked_at": result.checked_at,
    }
    return result


@router.put(
    "/selection",
    summary="Pin or inherit the current tenant's approved model deployment",
    response_model=TenantModelSelectionResponse,
)
async def update_model_selection(
    body: TenantModelSelectionUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> TenantModelSelectionResponse:
    response.headers["Cache-Control"] = "no-store"
    locked_org = (
        await db.execute(
            select(Organization)
            .where(Organization.id == current_org.id)
            .with_for_update()
        )
    ).scalar_one()
    current = selection_from_settings(locked_org.settings)
    if body.expected_version != current.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "MODEL_SELECTION_VERSION_CONFLICT",
                "current_version": current.version,
            },
        )

    deployment_id = str(body.deployment_id or "").strip().lower()
    if body.mode == "pinned":
        deployments = dict(
            getattr(request.app.state, "model_deployments", {}) or {}
        )
        deployment = deployments.get(deployment_id)
        gateway = getattr(request.app.state, "platform_gateway", None)
        registered = set(getattr(gateway, "registered_deployments", ()) or ())
        if (
            not deployment
            or not deployment.get("tenant_selectable")
            or deployment_id not in registered
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "MODEL_DEPLOYMENT_NOT_SELECTABLE",
                },
            )
        policy = getattr(request.app.state, "data_policy", None)
        if not isinstance(policy, RuntimeDataPolicy):
            policy = RuntimeDataPolicy.from_env()
        provider_id = str(deployment.get("provider_id") or deployment_id)
        decision = policy.egress_decision(provider_id)
        if decision["decision"] != "allow":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "MODEL_DEPLOYMENT_EGRESS_DENIED",
                },
            )
    else:
        deployment_id = ""

    next_version = current.version + 1
    locked_org.settings = update_selection_settings(
        locked_org.settings,
        mode=body.mode,
        deployment_id=deployment_id,
        version=next_version,
    )
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "model.selection.update",
        "organization_model_selection",
        current_org.id,
        details={
            "previous_selection_mode": current.mode,
            "previous_model_deployment_id": current.deployment_id or None,
            "selection_mode": body.mode,
            "model_deployment_id": deployment_id or None,
            "version": next_version,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return TenantModelSelectionResponse(
        mode=body.mode,
        deployment_id=deployment_id or None,
        version=next_version,
    )
