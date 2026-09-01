"""Tenant-scoped model deployment selection.

The selected deployment is stored inside the organization's JSON settings so
it follows the existing tenant lifecycle without introducing a secret store.
Only deployment identifiers and version metadata are persisted; credentials
and endpoint URLs remain operator-owned environment configuration.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select


MODEL_ROUTING_SETTINGS_KEY = "_model_routing"
_request_tenant_id: ContextVar[str] = ContextVar(
    "icoder_model_routing_tenant_id",
    default="",
)


@dataclass(frozen=True)
class TenantModelSelection:
    mode: str = "inherit"
    deployment_id: str = ""
    version: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "deployment_id": self.deployment_id or None,
            "version": self.version,
        }


def bind_request_tenant(tenant_id: str | None) -> Token[str]:
    return _request_tenant_id.set(str(tenant_id or ""))


def reset_request_tenant(token: Token[str]) -> None:
    _request_tenant_id.reset(token)


def current_request_tenant() -> str:
    return _request_tenant_id.get()


def selection_from_settings(settings: Any) -> TenantModelSelection:
    if not isinstance(settings, dict):
        return TenantModelSelection()
    raw = settings.get(MODEL_ROUTING_SETTINGS_KEY)
    if not isinstance(raw, dict):
        return TenantModelSelection()
    mode = str(raw.get("mode") or "inherit").strip().lower()
    deployment_id = str(raw.get("deployment_id") or "").strip().lower()
    try:
        version = max(0, int(raw.get("version") or 0))
    except (TypeError, ValueError):
        version = 0
    if mode != "pinned" or not deployment_id:
        return TenantModelSelection(mode="inherit", version=version)
    return TenantModelSelection(
        mode="pinned",
        deployment_id=deployment_id,
        version=version,
    )


def update_selection_settings(
    settings: Any,
    *,
    mode: str,
    deployment_id: str,
    version: int,
) -> dict[str, Any]:
    updated = dict(settings) if isinstance(settings, dict) else {}
    updated[MODEL_ROUTING_SETTINGS_KEY] = {
        "mode": mode,
        "deployment_id": deployment_id if mode == "pinned" else "",
        "version": version,
    }
    return updated


async def resolve_tenant_model_route(
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the current tenant's non-secret routing selection from DB."""

    tenant_id = ""
    if isinstance(context, dict):
        tenant_id = str(
            context.get("organization_id")
            or context.get("tenant_id")
            or ""
        ).strip()
    tenant_id = tenant_id or current_request_tenant()
    if not tenant_id:
        return None

    # Imports stay local so the reusable runtime core never depends on the
    # FastAPI application's SQLAlchemy model graph.
    from app.database import AsyncSessionLocal
    from app.models.organization import Organization
    from app.services.database_tenancy import bind_tenant_to_transaction

    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, tenant_id)
        row = (
            await db.execute(
                select(Organization.settings).where(
                    Organization.id == tenant_id,
                    Organization.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise LookupError("tenant_model_policy_not_found")
    selection = selection_from_settings(row)
    return selection.to_public_dict()
