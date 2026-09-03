"""Development-verifiable platform Environment and Region catalog APIs.

The catalog is mastered by ``deploy/cloud/regions.yaml``.  This module never
claims that declared regions are provisioned: creation produces a dry-run
deployment plan only.  Real cloud changes remain an external operations gate.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.models.user import User


router = APIRouter(prefix="/api/platform", tags=["platform-environments"])
CATALOG_PATH = Path(__file__).resolve().parents[3] / "deploy" / "cloud" / "regions.yaml"


class EnvironmentPlanRequest(BaseModel):
    environment_code: str = Field(..., pattern="^(eu|us|cn)$")
    region_code: str
    tenant_id: str | None = None
    dry_run: bool = True


def _catalog() -> dict[str, Any]:
    try:
        catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Region catalog unavailable: {type(exc).__name__}",
        ) from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("environments"), list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Region catalog is invalid",
        )
    return catalog


def _environment_view(environment: dict[str, Any]) -> dict[str, Any]:
    regions = environment.get("regions") or []
    return {
        **environment,
        "provisioned": any(bool(region.get("enabled")) for region in regions),
        "runtime_state": (
            "provisioned" if any(bool(region.get("enabled")) for region in regions)
            else "declared_not_provisioned"
        ),
    }


@router.get("/environments", summary="List declared platform Environments")
async def list_environments(
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    catalog = _catalog()
    return {
        "deployment_mode": os.getenv("ICODER_DEPLOYMENT_MODE", "local"),
        "source": "deploy/cloud/regions.yaml",
        "environments": [_environment_view(item) for item in catalog["environments"]],
    }


@router.post("/environments", summary="Build an Environment deployment plan")
async def create_environment_plan(
    data: EnvironmentPlanRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if getattr(current_user.role, "value", current_user.role) != "admin":
        raise HTTPException(status_code=403, detail="Platform admin role required")
    if not data.dry_run:
        raise HTTPException(
            status_code=409,
            detail=(
                "Direct cloud provisioning is disabled. Run with dry_run=true, "
                "then obtain production infrastructure approval."
            ),
        )

    catalog = _catalog()
    environment = next(
        (item for item in catalog["environments"] if item.get("code") == data.environment_code),
        None,
    )
    region = next(
        (item for item in (environment or {}).get("regions", []) if item.get("code") == data.region_code),
        None,
    )
    if environment is None or region is None:
        raise HTTPException(status_code=404, detail="Environment or region not found in catalog")

    return {
        "kind": "environment_deployment_plan",
        "dry_run": True,
        "environment_code": data.environment_code,
        "region_code": data.region_code,
        "tenant_id": data.tenant_id,
        "cloud_provider": region.get("cloud_provider"),
        "data_residency_required": environment.get("data_residency_required", True),
        "cross_environment_replication": environment.get("cross_environment_replication"),
        "steps": [
            "validate_tenant_data_residency",
            "provision_network_and_secrets",
            "provision_database_and_object_storage",
            "deploy_runtime_and_region_assets",
            "run_security_privacy_and_disaster_recovery_gates",
            "obtain_production_operations_approval",
        ],
        "external_approval_required": True,
        "provisioned": False,
    }


@router.get("/regions", summary="List declared Regions and readiness")
async def list_regions(
    _current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    catalog = _catalog()
    regions = []
    for environment in catalog["environments"]:
        for region in environment.get("regions") or []:
            regions.append({
                **region,
                "environment_code": environment.get("code"),
                "compliance": list(environment.get("compliance") or []),
                "data_residency_required": environment.get("data_residency_required", True),
                "runtime_state": (
                    "provisioned" if region.get("enabled") else "declared_not_provisioned"
                ),
            })
    return {"source": "deploy/cloud/regions.yaml", "regions": regions}
