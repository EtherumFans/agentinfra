"""Platform Tenants API (Phase 1 cloud-flip 2026-06-27 stub).

Stub endpoints for the iCoDer 托管云 Tenant layer (hospital / ISV).
Phase 1 returns 501 + design-doc link.
Phase 2 will implement tenant provisioning, environment assignment,
and per-tenant credential vault.

Note: existing `app.api.organizations` (11 endpoints) is the
in-development multi-tenant primitive; Phase 2 will rename to `tenants`
or layer Tenants above Organizations.

Design contract: docs/cloud/CLOUD_DEPLOYMENT.md §2.2 (Tenant)
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/tenants", tags=["platform-tenants"])

_NOT_IMPLEMENTED_MSG = (
    "Platform Tenants API 是 Phase 1 cloud-flip 设计意图 stub。"
    "当前 ICODER_DEPLOYMENT_MODE=local 使用 app.api.organizations 的 "
    "Organization schema 即可,无需 Platform Tenants。"
    "Phase 2 实装: docs/cloud/CLOUD_DEPLOYMENT.md §7 (Migration Path)。"
)
_DESIGN_DOC_URL = "https://github.com/iCoDer/docs/blob/cloud/CLOUD_DEPLOYMENT.md"


@router.get("/current", summary="Get current Tenant (Phase 1 stub)")
async def get_current_tenant():
    """查当前请求上下文的 Tenant。

    Phase 1 stub: 返 501。Phase 2 实装从 JWT claims 提取 tenant_id
    并查 tenant metadata。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
        },
    )


@router.post("", summary="Create Tenant (Phase 1 stub)")
async def create_tenant():
    """创建新 Tenant (仅 platform admin 可调用,通过 onboarding intake)。

    Phase 1 stub: 返 501。Phase 2 实装配合 CLOUD_INTAKE_TEMPLATE.md
    走合规审批流。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": "https://github.com/iCoDer/docs/blob/cloud/CLOUD_INTAKE_TEMPLATE.md",
            "phase": "Phase 2",
        },
    )


@router.get("/{tenant_id}/environments", summary="Get Tenant Environments (Phase 1 stub)")
async def get_tenant_environments(tenant_id: str):
    """查指定 Tenant 可用的 Environment 列表 (用于跨 region failover 选择)。

    Phase 1 stub: 返 501。Phase 2 实装读 tenant.environment_assignment 表。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
            "tenant_id": tenant_id,
        },
    )