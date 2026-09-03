"""Corti-compatible Guided Template and Section resources."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


def _discovery_params(filters: dict[str, Any]) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    for key in ("lang", "region", "specialty", "label"):
        for value in filters.get(key, []) or []:
            params.append((key, str(value)))
    if filters.get("published") is not None:
        params.append(("published", str(bool(filters["published"])).lower()))
    if filters.get("source"):
        params.append(("source", str(filters["source"])))
    return params


class TemplatesResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(
        self,
        *,
        request_options: RequestOptions | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        response = self._client.get(
            "/api/v2/tools/templates/",
            params=_discovery_params(filters),
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def get(
        self,
        template_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/templates/{quote(template_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def publish(
        self,
        template_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        """Publish the current draft behind an opaque public template ID."""
        response = self._client.post(
            f"/api/v2/tools/templates/{quote(template_id, safe='')}/publish",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def list_sections(
        self,
        *,
        request_options: RequestOptions | None = None,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        response = self._client.get(
            "/api/v2/tools/sections/",
            params=_discovery_params(filters),
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def get_section(
        self,
        section_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/tools/sections/{quote(section_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def create_section(
        self,
        request: dict[str, Any],
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/api/v2/tools/sections/",
            json=request,
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def update_section(
        self,
        section_id: str,
        request: dict[str, Any],
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.patch(
            f"/api/v2/tools/sections/{quote(section_id, safe='')}",
            json=request,
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def delete_section(
        self,
        section_id: str,
        request_options: RequestOptions | None = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v2/tools/sections/{quote(section_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
