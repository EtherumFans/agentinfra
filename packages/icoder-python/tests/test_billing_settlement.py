import httpx

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_billing_resource_exposes_run_settlement_contract():
    calls = []

    def handler(request):
        calls.append((
            request.method,
            request.url.path,
            request.url.params.get("limit") or request.url.params.get("older_than_seconds"),
        ))
        if request.url.path == "/api/billing/balance":
            return httpx.Response(200, json={
                "balance": 1.0, "reserved": 0.05, "available": 0.95,
                "currency": "CNY",
            })
        if request.url.path == "/api/billing/run-settlements":
            return httpx.Response(200, json={
                "items": [{
                    "run_id": "run/id", "status": "SETTLEMENT_FAILED",
                    "reserved_amount": 0.05, "settled_amount": 2.0,
                    "currency": "CNY",
                }],
                "total": 1,
                "simulation": True,
            })
        if request.url.path == "/api/billing/run-settlements/reconcile-stale":
            return httpx.Response(200, json={
                "simulation": True, "released": 1, "marked_retryable": 1,
                "skipped_active": 1, "inspected": 3, "older_than_seconds": 3600,
            })
        return httpx.Response(200, json={
            "status": "SETTLED", "settled_amount": 2.0, "currency": "CNY",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        balance = client.billing.balance()
        settlements = client.billing.run_settlements(limit=7)
        retried = client.billing.retry_run_settlement("run/id")
        reconciled = client.billing.reconcile_stale_run_settlements(3600)
    finally:
        client.close()

    assert balance["available"] == 0.95
    assert settlements["items"][0]["status"] == "SETTLEMENT_FAILED"
    assert retried["status"] == "SETTLED"
    assert reconciled["released"] == 1
    assert calls == [
        ("GET", "/api/billing/balance", None),
        ("GET", "/api/billing/run-settlements", "7"),
        ("POST", "/api/billing/run-settlements/run/id/retry", None),
        ("POST", "/api/billing/run-settlements/reconcile-stale", "3600"),
    ]
