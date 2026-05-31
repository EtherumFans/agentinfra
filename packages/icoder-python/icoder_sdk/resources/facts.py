"""Facts extraction resource."""

from ..client import iCoDerClient
from ..types import FactExtractResponse


class FactsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def extract(self, text: str, output_language: str = "zh-CN") -> FactExtractResponse:
        resp = self._client.post("/api/facts/extract", json={
            "text": text,
            "output_language": output_language,
        })
        resp.raise_for_status()
        data = resp.json()
        return FactExtractResponse(
            facts=data.get("facts", {}),
            raw_output=data.get("raw_output", ""),
            credits_consumed=data.get("credits_consumed", 0),
        )
