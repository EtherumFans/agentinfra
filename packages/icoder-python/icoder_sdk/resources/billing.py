"""Billing & Usage resources."""

from ..client import iCoDerClient
from ..types import UsageSummary


class BillingResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def balance(self) -> dict:
        resp = self._client.get("/api/billing/balance")
        resp.raise_for_status()
        return resp.json()

    def transactions(self, page: int = 1, page_size: int = 20) -> dict:
        resp = self._client.get("/api/billing/transactions", params={"page": page, "page_size": page_size})
        resp.raise_for_status()
        return resp.json()


class UsageResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def summary(self, days: int = 30) -> UsageSummary:
        resp = self._client.get("/api/usage/summary", params={"days": days})
        resp.raise_for_status()
        data = resp.json()
        return UsageSummary(
            total_requests=data.get("total_requests", 0),
            credits_used=data.get("credits_used", 0),
            avg_response_time_ms=data.get("avg_response_time_ms", 0),
        )

    def history(self, days: int = 30) -> dict:
        resp = self._client.get("/api/usage/history", params={"days": days})
        resp.raise_for_status()
        return resp.json()
