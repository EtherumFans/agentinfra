"""MockCodingAdapter — deterministic mock for testing and development."""

from __future__ import annotations

from typing import Any
from icoder_runtime.core.coding_schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema,
)


class MockCodingAdapter(CodingEngineAdapter):
    """Returns MedicalCodingOutputSchema.mock_result(). Always marked is_mock=True."""

    name = "mock_coding_adapter"

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        return MedicalCodingOutputSchema.mock_result()

    def health_check(self) -> dict:
        return {"engine": self.name, "status": "healthy", "mode": "mock"}
