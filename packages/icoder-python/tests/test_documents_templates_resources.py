import json

import httpx
import pytest

from icoder_sdk import iCoDerClient, iCoDerConfig


def _client(handler):
    client = iCoDerClient(
        iCoDerConfig(base_url="https://api.cn.icoder.cloud", access_token="token")
    )
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        headers={"Authorization": "Bearer token"},
        transport=httpx.MockTransport(handler),
    )
    return client


def test_documents_resource_zero_retention_and_lifecycle_paths():
    calls = []
    document = {
        "id": "doc-1",
        "name": "note",
        "templateRef": "template-1",
        "isStream": False,
        "sections": [],
        "createdAt": "2026-08-14T00:00:00Z",
        "updatedAt": "2026-08-14T00:00:00Z",
        "outputLanguage": "zh-CN",
        "usageInfo": {"creditsConsumed": 0.0},
    }

    def handler(request):
        body = json.loads(request.content) if request.content else None
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        calls.append((request.method, raw_path, request.headers, body))
        if request.method == "POST":
            return httpx.Response(
                201,
                json=document,
                headers={"X-Corti-Retention-Policy": "acknowledged"},
            )
        if request.method == "GET" and request.url.path.endswith("/documents/"):
            return httpx.Response(200, json={"data": [document]})
        if request.method in {"GET", "PATCH"}:
            return httpx.Response(200, json=document)
        return httpx.Response(204)

    client = _client(handler)
    request = {
        "context": [{"type": "string", "data": "去标识样例"}],
        "templateKey": "template-1",
        "outputLanguage": "zh-CN",
    }
    try:
        created = client.documents.create(
            "interaction/encoded", request, retention_policy="none"
        )
        preview = client.documents.preview("interaction/encoded", request)
        listed = client.documents.list("interaction/encoded")
        fetched = client.documents.get("interaction/encoded", "doc/1")
        updated = client.documents.update(
            "interaction/encoded", "doc/1", {"name": "updated"}
        )
        client.documents.delete("interaction/encoded", "doc/1")
    finally:
        client.close()

    assert created["status_code"] == 201
    assert created["retention_acknowledged"] is True
    assert preview == document
    assert listed == [document]
    assert fetched == document
    assert updated == document
    assert [call[:2] for call in calls] == [
        ("POST", "/api/v2/tools/interactions/interaction%2Fencoded/documents/"),
        ("POST", "/api/v2/tools/interactions/interaction%2Fencoded/documents/"),
        ("GET", "/api/v2/tools/interactions/interaction%2Fencoded/documents/"),
        ("GET", "/api/v2/tools/interactions/interaction%2Fencoded/documents/doc%2F1"),
        ("PATCH", "/api/v2/tools/interactions/interaction%2Fencoded/documents/doc%2F1"),
        ("DELETE", "/api/v2/tools/interactions/interaction%2Fencoded/documents/doc%2F1"),
    ]
    assert calls[0][2]["x-corti-retention-policy"] == "none"


def test_documents_preview_fails_when_zero_retention_is_not_acknowledged():
    def handler(_request):
        return httpx.Response(201, json={})

    client = _client(handler)
    try:
        with pytest.raises(RuntimeError, match="zero-retention"):
            client.documents.preview(
                "interaction",
                {
                    "context": [{"type": "string", "data": "sample"}],
                    "templateKey": "template",
                    "outputLanguage": "zh-CN",
                },
            )
    finally:
        client.close()


def test_templates_resource_filters_and_section_lifecycle_paths():
    calls = []

    def handler(request):
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        calls.append((request.method, raw_path, list(request.url.params.multi_items())))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200 if request.method != "POST" else 201, json=[] if request.url.path.endswith("/") else {})

    client = _client(handler)
    try:
        client.templates.list(
            lang=["zh-CN", "en-US"], region=["CHN"], source="project"
        )
        client.templates.get("template/1")
        client.templates.publish("template/1")
        client.templates.list_sections(
            lang=["zh-CN"], label=["regulatory_basis:CN-medical-record-standard"]
        )
        client.templates.get_section("section/1")
        client.templates.create_section({"name": "主诉"})
        client.templates.update_section("section/1", {"description": "更新"})
        client.templates.delete_section("section/1")
    finally:
        client.close()

    assert [call[:2] for call in calls] == [
        ("GET", "/api/v2/tools/templates/"),
        ("GET", "/api/v2/tools/templates/template%2F1"),
        ("POST", "/api/v2/tools/templates/template%2F1/publish"),
        ("GET", "/api/v2/tools/sections/"),
        ("GET", "/api/v2/tools/sections/section%2F1"),
        ("POST", "/api/v2/tools/sections/"),
        ("PATCH", "/api/v2/tools/sections/section%2F1"),
        ("DELETE", "/api/v2/tools/sections/section%2F1"),
    ]
    assert calls[0][2] == [
        ("lang", "zh-CN"),
        ("lang", "en-US"),
        ("region", "CHN"),
        ("source", "project"),
    ]
