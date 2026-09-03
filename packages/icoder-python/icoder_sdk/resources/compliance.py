"""Compliance rule-engine status, catalog, and validation resources."""

from __future__ import annotations

from typing import Any

from ..client import iCoDerClient
from ..request_options import RequestOptions


class ComplianceResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def rule_engine_status(
        self,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            "/api/compliance/rule-engine/status",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def rule_engine_rules(
        self,
        rule_set: str = "medical_coding",
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            "/api/compliance/rule-engine/rules",
            params={"rule_set": rule_set},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def validate(
        self,
        rule_set: str,
        structured_output: dict[str, Any],
        context: dict[str, Any] | None = None,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/api/compliance/rule-engine/validate",
            json={
                "rule_set": rule_set,
                "structured_output": structured_output,
                "context": dict(context or {}),
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()
