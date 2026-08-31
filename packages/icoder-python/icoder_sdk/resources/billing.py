"""Billing and usage resources with bounded request controls and pagination."""

from __future__ import annotations

from typing import Optional

from ..client import iCoDerClient
from ..pagination import PageNumberPager
from ..request_options import RequestOptions
from ..types import UsageSummary


def _positive_integer(value: int, name: str, maximum: Optional[int] = None) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or (maximum is not None and value > maximum)
    ):
        suffix = f" at most {maximum}" if maximum is not None else ""
        raise ValueError(f"{name} must be a positive integer{suffix}")
    return value


class BillingResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def balance(self, request_options: Optional[RequestOptions] = None) -> dict:
        resp = self._client.get(
            "/api/billing/balance", request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def transactions(
        self,
        page: int = 1,
        page_size: int = 20,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        _positive_integer(page, "page")
        _positive_integer(page_size, "page_size", 100)
        resp = self._client.get(
            "/api/billing/transactions",
            params={"page": page, "page_size": page_size},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def iterate_transactions(
        self,
        page_size: int = 20,
        request_options: Optional[RequestOptions] = None,
        *,
        initial_page: int = 1,
        max_pages: int = 10000,
    ) -> PageNumberPager[dict, dict]:
        _positive_integer(page_size, "page_size", 100)
        return PageNumberPager(
            lambda page: self.transactions(page, page_size, request_options),
            lambda response: response["transactions"],
            lambda response: response["total"],
            initial_page=initial_page,
            max_pages=max_pages,
        )

    def simulate_debit(
        self,
        amount: float,
        reference: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        """Debit the local development ledger; cloud mode rejects this call."""
        resp = self._client.post(
            "/api/billing/simulation/debit",
            json={"amount": amount, "reference": reference},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def run_settlements(
        self,
        limit: int = 20,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        """List PHI-free local Agent Run preauthorization settlements."""
        _positive_integer(limit, "limit", 100)
        resp = self._client.get(
            "/api/billing/run-settlements", params={"limit": limit},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def run_settlement_page(
        self,
        page: int = 1,
        page_size: int = 20,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        _positive_integer(page, "page")
        _positive_integer(page_size, "page_size", 100)
        resp = self._client.get(
            "/api/billing/run-settlements",
            params={"page": page, "page_size": page_size},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def iterate_run_settlements(
        self,
        page_size: int = 20,
        request_options: Optional[RequestOptions] = None,
        *,
        initial_page: int = 1,
        max_pages: int = 10000,
    ) -> PageNumberPager[dict, dict]:
        _positive_integer(page_size, "page_size", 100)
        return PageNumberPager(
            lambda page: self.run_settlement_page(page, page_size, request_options),
            lambda response: response["items"],
            lambda response: response["total"],
            initial_page=initial_page,
            max_pages=max_pages,
        )

    def retry_run_settlement(
        self,
        run_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        """Retry a failed local settlement after adding credits."""
        from urllib.parse import quote

        resp = self._client.post(
            f"/api/billing/run-settlements/{quote(run_id, safe='')}/retry",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def reconcile_stale_run_settlements(
        self,
        older_than_seconds: int = 3600,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        """Reconcile old crash-orphaned reservations; active runs are skipped."""
        resp = self._client.post(
            "/api/billing/run-settlements/reconcile-stale",
            params={"older_than_seconds": older_than_seconds},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()


class UsageResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def summary(
        self,
        days: int = 30,
        request_options: Optional[RequestOptions] = None,
    ) -> UsageSummary:
        resp = self._client.get(
            "/api/usage/summary",
            params={"days": days},
            request_options=request_options,
        )
        resp.raise_for_status()
        data = resp.json()
        return UsageSummary(
            total_requests=data.get("total_requests", 0),
            credits_used=data.get("credits_used", 0),
            avg_response_time_ms=data.get("avg_response_time_ms", 0),
        )

    def history(
        self,
        days: int = 30,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/usage/history",
            params={"days": days},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()
