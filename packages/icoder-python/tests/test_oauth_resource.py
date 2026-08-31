import json

import httpx

from icoder_sdk import iCoDerClient, iCoDerConfig


def test_oauth_resource_uses_public_form_contracts():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={
                "access_token": "partner-token",
                "token_type": "bearer",
                "expires_in": 3600,
            })
        return httpx.Response(201, json={
            "client_id": "client-1",
            "client_secret": "secret-1",
        })

    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.test", access_token="console-token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer console-token"},
        transport=httpx.MockTransport(handler),
    )
    try:
        token = client.oauth.get_token("client/id", "secret+value")
        created = client.oauth.create_client(
            "SDK client",
            "contract",
            "agents:run",
            allowed_agent_ids=["diagnosis-extractor"],
            allowed_purposes=["treatment"],
        )
        client.oauth.update_delegation(
            "client-1",
            allowed_agent_ids=["diagnosis-extractor"],
            allowed_purposes=["treatment"],
        )
    finally:
        client.close()

    assert token["access_token"] == "partner-token"
    assert created["client_id"] == "client-1"
    assert calls[0].headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert calls[0].content.decode() == (
        "client_id=client%2Fid&client_secret=secret%2Bvalue&"
        "grant_type=client_credentials&scope=api%3Aread+api%3Awrite"
    )
    assert calls[1].headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert calls[1].content.decode() == (
        "name=SDK+client&description=contract&scopes=agents%3Arun&"
        "allowed_agent_ids=diagnosis-extractor&allowed_purposes=treatment"
    )
    assert calls[2].url.path == "/api/clients/client-1/delegation"
    assert json.loads(calls[2].content) == {
        "allowed_agent_ids": ["diagnosis-extractor"],
        "allowed_purposes": ["treatment"],
    }
