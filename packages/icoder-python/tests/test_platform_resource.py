import json

import httpx

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_platform_resource_paths_and_dry_run_contract():
    calls = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        return httpx.Response(200, json={"ok": True})

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
        client.platform.list_environments()
        client.platform.list_regions()
        client.platform.plan_environment("cn", "cn-hangzhou", tenant_id="tenant-1")
        client.platform.current_tenant()
        client.platform.tenant_environments("tenant-1")
    finally:
        client.close()

    assert [call[:2] for call in calls] == [
        ("GET", "/api/platform/environments"),
        ("GET", "/api/platform/regions"),
        ("POST", "/api/platform/environments"),
        ("GET", "/api/tenants/current"),
        ("GET", "/api/tenants/tenant-1/environments"),
    ]
    assert calls[2][2]["dry_run"] is True
