"""Platform Environments API (Phase 1 cloud-flip 2026-06-27 stub).

Stub endpoints for the iCoDer 托管云 Environment layer (EU/US/CN).
Phase 1 returns 501 Not Implemented + a link to the design intent doc.
Phase 2 will implement real provisioning / region routing logic.

Design contract: docs/cloud/CLOUD_DEPLOYMENT.md §2.1 (Environment)
                  docs/cloud/MULTI_REGION.md §1 (Region Catalog)
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/platform", tags=["platform-environments"])

_NOT_IMPLEMENTED_MSG = (
    "Platform Environments API 是 Phase 1 cloud-flip 设计意图 stub。"
    "当前 ICODER_DEPLOYMENT_MODE=local 不需要此 API。"
    "Phase 2 实装: 见 docs/cloud/CLOUD_DEPLOYMENT.md §7 (Migration Path)。"
)
_DESIGN_DOC_URL = "https://github.com/iCoDer/docs/blob/cloud/CLOUD_DEPLOYMENT.md"


@router.get("/environments", summary="List Environments (Phase 1 stub)")
async def list_environments():
    """列出所有 Environments (EU / US / CN)。

    Phase 1 stub: 返 501 + 设计意图 doc-link。Phase 2 实装按
    `ICODER_DEPLOYMENT_MODE=cloud` 启用。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
        },
    )


@router.post("/environments", summary="Create Environment (Phase 1 stub)")
async def create_environment():
    """创建新 Environment。Phase 2 实装,仅 platform admin 可调用。

    Phase 1 stub: 返 501。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
        },
    )


@router.get("/regions", summary="List Regions (Phase 1 stub)")
async def list_regions():
    """列出所有 region 状态 / SLA / data-residency metadata。

    Phase 1 stub: 返 501。Phase 2 实装读取 deploy/cloud/regions.yaml
    并叠加运行时健康状态。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": "https://github.com/iCoDer/docs/blob/cloud/MULTI_REGION.md",
            "phase": "Phase 2",
        },
    )