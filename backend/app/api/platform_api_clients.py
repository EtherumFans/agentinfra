"""Platform API Clients API (Phase 1 cloud-flip 2026-06-27 stub).

Stub endpoints for the iCoDer 托管云 API Client layer
(backend-service vs ROPC embedded). Phase 1 returns 501 + design-doc link.
Phase 2 will implement client credential issuance, scope management,
and OAuth 2.1 token endpoints.

Design contract: docs/cloud/API_CLIENT_MODEL.md
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/clients", tags=["platform-api-clients"])

_NOT_IMPLEMENTED_MSG = (
    "Platform API Clients API 是 Phase 1 cloud-flip 设计意图 stub。"
    "当前 ICODER_DEPLOYMENT_MODE=local 仍使用单一 JWT (HS256)。"
    "Phase 2 实装 OAuth 2.1 (client_credentials + ROPC + PKCE) + scope 系统。"
)
_DESIGN_DOC_URL = "https://github.com/iCoDer/docs/blob/cloud/API_CLIENT_MODEL.md"


@router.get("", summary="List API Clients (Phase 1 stub)")
async def list_clients():
    """列出当前 Tenant 的所有 API Clients。

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


@router.post("", summary="Create API Client (Phase 1 stub)")
async def create_client():
    """创建新 API Client (backend-service 或 ROPC embedded)。

    Phase 1 stub: 返 501。Phase 2 实装会生成 client_secret
    (一次性显示,需 Tenant admin 立即存入 secret manager)。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
        },
    )


@router.get("/{client_id}/scopes", summary="Get Client Scopes (Phase 1 stub)")
async def get_client_scopes(client_id: str):
    """查指定 Client 的 scope 集合。

    Phase 1 stub: 返 501。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
            "client_id": client_id,
        },
    )


@router.patch("/{client_id}/scopes", summary="Update Client Scopes (Phase 1 stub)")
async def update_client_scopes(client_id: str):
    """更新 Client 的 scope 集合 (最小权限原则)。

    Phase 1 stub: 返 501。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
            "client_id": client_id,
        },
    )


@router.delete("/{client_id}", summary="Revoke API Client (Phase 1 stub)")
async def revoke_client(client_id: str):
    """撤销 Client (立即吊销所有 active token)。

    Phase 1 stub: 返 501。
    """
    raise HTTPException(
        status_code=501,
        detail={
            "message": _NOT_IMPLEMENTED_MSG,
            "design_doc": _DESIGN_DOC_URL,
            "phase": "Phase 2",
            "client_id": client_id,
        },
    )