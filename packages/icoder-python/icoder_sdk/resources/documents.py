"""Corti-compatible Classic Documents generation and lifecycle."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


class DocumentsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    @staticmethod
    def _base(interaction_id: str) -> str:
        return f"/api/v2/tools/interactions/{quote(interaction_id, safe='')}/documents"

    def create(
        self,
        interaction_id: str,
        request: dict[str, Any],
        *,
        retention_policy: str | None = None,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        if retention_policy not in {None, "none"}:
            raise ValueError("retention_policy supports only None or 'none'")
        headers = (
            {"X-Corti-Retention-Policy": "none"}
            if retention_policy == "none"
            else None
        )
        response = self._client.post(
            f"{self._base(interaction_id)}/",
            json=request,
            headers=headers,
            request_options=request_options,
        )
        response.raise_for_status()
        return {
            "document": response.json(),
            "status_code": response.status_code,
            "retention_acknowledged": (
                response.headers.get("X-Corti-Retention-Policy") == "acknowledged"
            ),
        }

    def preview(
        self,
        interaction_id: str,
        request: dict[str, Any],
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        result = self.create(
            interaction_id,
            request,
            retention_policy="none",
            request_options=request_options,
        )
        if not result["retention_acknowledged"]:
            raise RuntimeError("server did not acknowledge the zero-retention policy")
        return result["document"]

    def list(
        self, interaction_id: str, request_options: RequestOptions | None = None,
    ) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{self._base(interaction_id)}/", request_options=request_options,
        )
        response.raise_for_status()
        return response.json()["data"]

    def get(
        self,
        interaction_id: str,
        document_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"{self._base(interaction_id)}/{quote(document_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def update(
        self,
        interaction_id: str,
        document_id: str,
        request: dict[str, Any],
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.patch(
            f"{self._base(interaction_id)}/{quote(document_id, safe='')}",
            json=request,
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def delete(
        self,
        interaction_id: str,
        document_id: str,
        request_options: RequestOptions | None = None,
    ) -> None:
        response = self._client.delete(
            f"{self._base(interaction_id)}/{quote(document_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
