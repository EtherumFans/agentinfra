"""Facts extraction resource."""

from typing import Optional

from ..client import iCoDerClient
from ..request_options import RequestOptions
from ..types import FactExtractResponse, FactItem, FactUsageInfo


class FactsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def extract(
        self,
        text: str,
        output_language: str = "zh-CN",
        request_options: Optional[RequestOptions] = None,
    ) -> FactExtractResponse:
        if not text.strip():
            raise ValueError("text must not be empty")
        resp = self._client.post("/api/v2/tools/extract-facts", json={
            "context": [{"type": "text", "text": text}],
            "outputLanguage": output_language,
        }, request_options=request_options)
        resp.raise_for_status()
        data = resp.json()
        return FactExtractResponse(
            facts=[FactItem(
                group=str(item.get("group", "")),
                text=str(item.get("text", "")),
                value=str(item.get("value", "")),
            ) for item in data.get("facts", [])],
            output_language=str(data.get("outputLanguage", output_language)),
            usage_info=FactUsageInfo(
                credits_consumed=float(data.get("usageInfo", {}).get("creditsConsumed", 0)),
            ),
        )
