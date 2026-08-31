"""Declarative Environments/Regions and Tenant compatibility resources."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


class PlatformResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list_environments(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            "/api/platform/environments", request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def list_regions(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            "/api/platform/regions", request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def plan_environment(
        self,
        environment_code: str,
        region_code: str,
        *,
        tenant_id: str | None = None,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/api/platform/environments",
            json={
                "environment_code": environment_code,
                "region_code": region_code,
                "tenant_id": tenant_id,
                "dry_run": True,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def current_tenant(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            "/api/tenants/current", request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def tenant_environments(
        self,
        tenant_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/tenants/{quote(tenant_id, safe='')}/environments",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()
