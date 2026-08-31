import json

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


def _client(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.test", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_facts_resource_uses_v2_contract_and_server_usage():
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={
            "facts": [{"group": "diagnosis", "text": "高血压", "value": "高血压"}],
            "outputLanguage": "zh-CN",
            "usageInfo": {"creditsConsumed": 0.011},
        })

    client = _client(handler)
    try:
        result = client.facts.extract("诊断：高血压。")
    finally:
        client.close()

    assert calls == [("/api/v2/tools/extract-facts", {
        "context": [{"type": "text", "text": "诊断：高血压。"}],
        "outputLanguage": "zh-CN",
    })]
    assert result.facts[0].group == "diagnosis"
    assert result.usage_info.credits_consumed == 0.011


def test_textgen_resource_uses_zero_retention_guided_documents():
    calls = []

    def handler(request):
        calls.append((request.url.path, request.headers, json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "document": {"stringDocument": {"出院小结": "生成结果"}},
                "usageInfo": {"creditsConsumed": 0.007},
            },
            headers={"X-Corti-Retention-Policy": "acknowledged"},
        )

    client = _client(handler)
    try:
        result = client.textgen.generate("去标识病历", template="出院小结")
    finally:
        client.close()

    assert calls[0][0] == "/api/v2/tools/guided-documents"
    assert calls[0][1]["x-corti-retention-policy"] == "none"
    assert calls[0][2]["context"] == [{"type": "text", "text": "去标识病历"}]
    assert result == {"output": "生成结果", "credits_consumed": 0.007}
    with pytest.raises(ValueError, match="doc_name.*not supported"):
        client = _client(handler)
        try:
            client.textgen.generate("去标识病历", doc_name="患者姓名")
        finally:
            client.close()


def test_textgen_resource_rejects_missing_retention_acknowledgement():
    def handler(_request):
        return httpx.Response(200, json={
            "document": {"stringDocument": {"note": "must not display"}},
            "usageInfo": {"creditsConsumed": 0},
        })

    client = _client(handler)
    try:
        with pytest.raises(RuntimeError, match="zero-retention"):
            client.textgen.generate("去标识病历")
    finally:
        client.close()
