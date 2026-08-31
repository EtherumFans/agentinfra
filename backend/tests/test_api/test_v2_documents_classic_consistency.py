"""Cycle 5 回环一致性测试 — Corti §13.4 Documents Classic (Planned deprecation) LIST shape parity.

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/documents-classic-list.md``
     (fetched 2026-07-01 from
     ``https://docs.corti.ai/api-reference/documents-classic/list-documents.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/documents/``
     endpoint with a synthetic UUID and asserts the response validates
     against the spec's ``DocumentsListResponse`` schema (which wraps an
     array of ``DocumentsGetResponse`` objects, each containing
     ``sections[]`` of ``DocumentsSection`` rows).
  4. Asserts key invariants Corti also enforces (e.g. path-scoped to a
     single interaction; ``usageInfo.creditsConsumed`` ≥ 0).

Dynamic fields ignored (per the parity policy):
  - ``id`` (server-assigned UUID, stub data echoes the interaction_id
    verbatim which we validate as a contract but don't compare types
    against the literal spec UUID format)
  - ``createdAt``, ``updatedAt`` (timestamps)
  - ``creditsConsumed`` (derived from provider usage; spec requires
    it to be present but not specific value)
"""

from __future__ import annotations

import asyncio
import os
import re
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

# Required env for the dev escape hatch.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle5")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


def _find_repo_root() -> Path:
    """Walk upward from this file until we find the iCoDer repo root
    (identified by the presence of ``docs/corti-reverse-engineered/``)."""
    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        if (cur / "docs" / "corti-reverse-engineered").is_dir():
            return cur
        cur = cur.parent
    raise RuntimeError("could not locate iCoDer repo root from test file")


REPO_ROOT = _find_repo_root()
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "documents-classic-list.md"


# ─── Spec loader ─────────────────────────────────────────────────────


def _extract_openapi_yaml() -> dict[str, Any]:
    """Extract and parse the ``openapi: 3.0.0`` YAML block from the markdown."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    blocks = re.findall(r"````yaml[^\n]*\n(.*?)````", text, flags=re.DOTALL)
    for blk in blocks:
        try:
            parsed = yaml.safe_load(blk)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and parsed.get("openapi"):
            return parsed
    raise AssertionError(f"No openapi 3.0+ YAML block found in {SPEC_PATH}")


# ─── OpenAPI JSON-Schema subset walker ───────────────────────────────


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/"), f"unsupported ref {ref}"
    cur: Any = spec
    for part in ref[2:].split("/"):
        cur = cur[part]
    return cur


def _type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "unknown"


def _check_shape(
    value: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """Recursive OpenAPI shape check. Skips dynamic fields per policy."""
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    leaf = path.rsplit(".", 1)[-1]
    # Dynamic-field skip (per parity policy)
    if leaf in ("requestid", "creditsConsumed", "createdBy"):
        return

    expected_type = schema.get("type")
    nullable = bool(schema.get("nullable", False))
    if value is None:
        if not nullable:
            errors.append(f"{path}: unexpected null (schema does not declare nullable: true)")
        return

    if expected_type and expected_type != "null":
        actual_type = _type_of(value)
        if expected_type == "number" and actual_type == "integer":
            actual_type = "number"
        if actual_type != expected_type:
            errors.append(
                f"{path}: expected type={expected_type}, got type={actual_type} (value={value!r})"
            )
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value {value!r} != const {schema['const']!r}")

    if expected_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for k in required:
            if k not in value:
                errors.append(f"{path}.{k}: required field missing")
        for k, v in value.items():
            if k in properties:
                _check_shape(v, properties[k], spec, f"{path}.{k}", errors)
    elif expected_type == "array" and isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                _check_shape(item, items_schema, spec, f"{path}[{i}]", errors)


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def docs_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client(monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    # Generation cases replace the platform gateway with deterministic local
    # doubles. Satisfy only the route's credential-presence gate for the
    # lifetime of each test; never inherit or call a real provider key.
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle5")
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_documents_classic_spec_is_real_and_cached(docs_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert docs_spec["openapi"].startswith("3.")
    assert docs_spec["info"]["title"] == "Corti API"
    op = docs_spec["paths"]["/interactions/{id}/documents/"]["get"]
    assert "Documents (Classic)" in op["tags"]
    assert op["operationId"] == "documents_list"
    schemas = docs_spec["components"]["schemas"]
    for name in [
        "DocumentsListResponse",
        "DocumentsGetResponse",
        "DocumentsSection",
        "CommonUsageInfo",
        "ErrorResponse",
    ]:
        assert name in schemas, f"missing schema {name}"


def test_v2_documents_classic_list_shape_matches_corti_spec(icoder_client, docs_spec):
    """回环: iCoDer list-documents response validates against the Corti OpenAPI
    schema ``DocumentsListResponse`` (envelope wrapping an array of
    ``DocumentsGetResponse`` objects, each with required sections[])."""
    envelope_schema = docs_spec["components"]["schemas"]["DocumentsListResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/documents/")
    assert r.status_code == 200, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, envelope_schema, docs_spec, "$.response", errs)
    assert not errs, "iCoDer Documents Classic list mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_documents_classic_envelope_has_data_field(icoder_client):
    """Contract invariant: response is an envelope ``{data: [...]}`` not a bare array."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/documents/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "data" in body, f"expected envelope {{data: [...]}}, got keys {list(body.keys())}"
    assert isinstance(body["data"], list)
    assert body["data"] == [], "unknown interactions must not synthesize documents"


def test_v2_documents_classic_path_scoping(icoder_client):
    """Unknown interaction scopes are independently empty, never fabricated."""
    id_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    id_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    r_a = icoder_client.get(f"/api/v2/tools/interactions/{id_a}/documents/")
    r_b = icoder_client.get(f"/api/v2/tools/interactions/{id_b}/documents/")
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    assert r_a.json() == {"data": []}
    assert r_b.json() == {"data": []}


def test_v2_documents_classic_isStream_field_round_trip(icoder_client, docs_spec):
    """An empty real scope remains a valid Corti DocumentsListResponse."""
    item_schema = docs_spec["components"]["schemas"]["DocumentsGetResponse"]
    interaction_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/documents/")
    assert r.status_code == 200, r.text
    docs = r.json()["data"]
    assert docs == []
    # Validate each doc individually against the schema
    errs: list[str] = []
    for i, item in enumerate(docs):
        _check_shape(item, item_schema, docs_spec, f"$.doc[{i}]", errs)
    assert not errs, "iCoDer Documents Classic items mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_documents_classic_reference_round_trip(docs_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schemas. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    envelope_schema = docs_spec["components"]["schemas"]["DocumentsListResponse"]
    item_schema = docs_spec["components"]["schemas"]["DocumentsGetResponse"]
    ref = {
        "data": [
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "name": "Hand-built Reference",
                "templateRef": "tpl-v1",
                "isStream": False,
                "sections": [
                    {
                        "key": "subjective",
                        "name": "Subjective",
                        "text": "Reference text.",
                        "sort": 0,
                        "createdAt": "2026-01-15T08:00:00Z",
                        "updatedAt": "2026-01-15T08:05:00Z",
                    },
                ],
                "createdAt": "2026-01-15T08:00:00Z",
                "updatedAt": "2026-01-15T08:05:00Z",
                "outputLanguage": "en-US",
                "usageInfo": {"creditsConsumed": 0.005},
            },
        ],
    }
    errs: list[str] = []
    _check_shape(ref, envelope_schema, docs_spec, "$.reference_envelope", errs)
    _check_shape(ref["data"][0], item_schema, docs_spec, "$.reference_item", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)


def _create_classic_template(icoder_client, name: str, heading: str) -> str:
    created = icoder_client.post(
        "/api/templates",
        json={
            "name": name,
            "content": json.dumps(
                {
                    "instructions": {"prompt": "Generate only documented content."},
                    "sections": [
                        {
                            "sectionId": f"section-{name}",
                            "heading": heading,
                            "instructions": {"contentPrompt": "Summarize the source."},
                            "outputSchema": {"type": "string"},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "language": "zh-CN",
        },
    )
    assert created.status_code == 201, created.text
    discovered = icoder_client.get("/api/v2/tools/templates/?source=user")
    assert discovered.status_code == 200, discovered.text
    return next(item["id"] for item in discovered.json() if item["name"] == name)


def test_v2_documents_classic_generate_static_persists_and_round_trips(
    icoder_client, docs_spec, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, messages, **kwargs):
            assert "患者主诉胸痛" in messages[-1]["content"]
            assert kwargs["context"]["operation"] == "corti_classic_document"
            return {
                "content": json.dumps({"病史": "患者主诉胸痛。"}, ensure_ascii=False),
                "usage": {"total_tokens": 1000},
            }

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    template_id = _create_classic_template(
        icoder_client, "Classic static generation", "病史"
    )
    interaction_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/documents/",
        json={
            "context": [{"type": "string", "data": "患者主诉胸痛"}],
            "templateKey": template_id,
            "name": "胸痛门诊记录",
            "outputLanguage": "zh-CN",
            "disableGuardrails": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "胸痛门诊记录"
    assert body["templateRef"] == template_id
    assert body["sections"][0]["name"] == "病史"
    assert body["sections"][0]["text"] == "患者主诉胸痛。"
    assert body["usageInfo"]["creditsConsumed"] == 0.011
    errors: list[str] = []
    _check_shape(
        body,
        docs_spec["components"]["schemas"]["DocumentsGetResponse"],
        docs_spec,
        "$.generated",
        errors,
    )
    assert not errors, "; ".join(errors)

    fetched = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/{body['id']}"
    )
    assert fetched.status_code == 200, fetched.text
    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/"
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == body["id"] for item in listed.json()["data"])


def test_v2_documents_classic_generate_ephemeral_acknowledges_without_persisting(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, *args, **kwargs):
            return {"content": json.dumps({"计划": "复诊。"}, ensure_ascii=False)}

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    template_id = _create_classic_template(
        icoder_client, "Classic ephemeral generation", "计划"
    )
    interaction_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "context": [{"type": "facts", "data": [{"text": "四周后复诊", "source": "user"}]}],
            "templateKey": template_id,
            "outputLanguage": "zh-CN",
            "disableGuardrails": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.headers["X-Corti-Retention-Policy"] == "acknowledged"
    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/"
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"data": []}


def test_v2_documents_classic_generate_dynamic_section_override(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, *args, **kwargs):
            operation = kwargs["context"]["operation"]
            if operation == "corti_classic_route_facts":
                return {
                    "content": json.dumps(
                        {"assignments": {"主观资料": [0]}}, ensure_ascii=False
                    )
                }
            assert operation == "corti_classic_generate_section"
            return {"content": json.dumps({"text": "头痛三天。"}, ensure_ascii=False)}

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    interaction_id = "99999999-9999-4999-8999-999999999999"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "context": [
                {
                    "type": "facts",
                    "data": [{"text": "患者头痛三天", "group": "主诉", "source": "core"}],
                }
            ],
            "template": {
                "sections": [
                    {
                        "key": "44444444-aaaa-bbbb-cccc-444444444444",
                        "nameOverride": "主观资料",
                        "contentOverride": "仅总结患者主诉。",
                    }
                ],
                "documentName": "中文主观资料",
            },
            "outputLanguage": "zh-CN",
            "documentationMode": "routed_parallel",
            "disableGuardrails": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "中文主观资料"
    assert created.json()["sections"][0]["key"] == "44444444-aaaa-bbbb-cccc-444444444444"
    assert created.json()["sections"][0]["name"] == "主观资料"


def test_v2_documents_classic_routed_parallel_runs_two_stage_concurrently(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        active = 0
        max_active = 0
        operations: list[str] = []

        async def generate(self, messages, **kwargs):
            operation = kwargs["context"]["operation"]
            self.operations.append(operation)
            if operation == "corti_classic_route_facts":
                return {
                    "content": json.dumps(
                        {
                            "assignments": {
                                "主观资料": [0],
                                "诊疗安排": [1],
                            }
                        },
                        ensure_ascii=False,
                    ),
                    "usage": {"total_tokens": 100},
                }
            assert operation == "corti_classic_generate_section"
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.02)
            try:
                heading = "主观资料" if "主观资料" in messages[0]["content"] else "诊疗安排"
                text = "胸痛两小时。" if heading == "主观资料" else "四周后复诊。"
                return {
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                    "usage": {"total_tokens": 50},
                }
            finally:
                self.active -= 1

    gateway = Gateway()
    monkeypatch.setattr(app.state, "platform_gateway", gateway, raising=False)
    created = icoder_client.post(
        "/api/v2/tools/interactions/55555555-5555-4555-8555-555555555555/documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "context": [
                {
                    "type": "facts",
                    "data": [
                        {"text": "胸痛两小时", "group": "主诉", "source": "core"},
                        {"text": "四周后复诊", "group": "计划", "source": "user"},
                    ],
                }
            ],
            "template": {
                "sections": [
                    {
                        "key": "44444444-aaaa-bbbb-cccc-444444444444",
                        "nameOverride": "主观资料",
                    },
                    {
                        "key": "55555555-aaaa-bbbb-cccc-555555555555",
                        "nameOverride": "诊疗安排",
                    },
                ]
            },
            "outputLanguage": "zh-CN",
            "documentationMode": "routed_parallel",
            "disableGuardrails": True,
        },
    )
    assert created.status_code == 201, created.text
    assert [item["text"] for item in created.json()["sections"]] == [
        "胸痛两小时。",
        "四周后复诊。",
    ]
    assert created.json()["usageInfo"]["creditsConsumed"] == 0.0022
    assert gateway.operations.count("corti_classic_route_facts") == 1
    assert gateway.operations.count("corti_classic_generate_section") == 2
    assert gateway.max_active == 2


def test_v2_documents_classic_routed_parallel_rejects_non_facts(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, *args, **kwargs):
            raise AssertionError("gateway must not run for unsupported routed context")

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    response = icoder_client.post(
        "/api/v2/tools/interactions/44444444-4444-4444-8444-444444444444/documents/",
        json={
            "context": [{"type": "transcript", "data": {"text": "患者胸痛"}}],
            "template": {"sectionKeys": ["44444444-aaaa-bbbb-cccc-444444444444"]},
            "outputLanguage": "zh-CN",
            "documentationMode": "routed_parallel",
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "routed_parallel_requires_facts"


def test_v2_documents_classic_sentence_guardrail_corrects_with_indexed_evidence(
    icoder_client, monkeypatch
):
    from app.database import async_session_factory
    from app.main import app
    from app.models.guided_document import GuidedDocumentRecord
    from app.services.guided_document_repository import guided_document_repository
    from sqlalchemy import select

    class Gateway:
        async def generate(self, messages, **kwargs):
            operation = kwargs["context"]["operation"]
            if operation == "corti_classic_document":
                return {
                    "content": json.dumps(
                        {"摘要": "患者胸痛。患者已确诊肺炎。"}, ensure_ascii=False
                    ),
                    "usage": {"total_tokens": 100},
                }
            assert operation == "corti_classic_guardrail"
            assert "1: 患者已确诊肺炎。" in messages[-1]["content"]
            return {
                "content": json.dumps(
                    {
                        "correctedText": "患者胸痛。",
                        "issues": [
                            {"segmentIndex": 1, "reason": "来源未支持肺炎诊断"}
                        ],
                    },
                    ensure_ascii=False,
                ),
                "usage": {"total_tokens": 50},
            }

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    template_id = _create_classic_template(
        icoder_client, "Classic indexed guardrail", "摘要"
    )
    response = icoder_client.post(
        "/api/v2/tools/interactions/33333333-3333-4333-8333-333333333333/documents/",
        json={
            "context": [{"type": "string", "data": "患者胸痛"}],
            "templateKey": template_id,
            "outputLanguage": "zh-CN",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["sections"][0]["text"] == "患者胸痛。"
    assert response.json()["usageInfo"]["creditsConsumed"] == 0.00165
    document_id = response.json()["id"]

    async def _labels():
        async with async_session_factory() as db:
            row = await db.scalar(select(GuidedDocumentRecord).where(
                GuidedDocumentRecord.document_id == document_id
            ))
            return guided_document_repository.labels(row)

    labels = asyncio.run(_labels())
    assert {item["key"]: item["value"] for item in labels} == {
        "documentation_mode": "global_sequential",
        "guardrails_applied": "true",
        "guardrail_issue_count": "1",
    }


def test_v2_documents_classic_sentence_guardrail_rejects_invalid_index(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, *args, **kwargs):
            operation = kwargs["context"]["operation"]
            if operation == "corti_classic_document":
                return {"content": json.dumps({"摘要": "患者胸痛。"}, ensure_ascii=False)}
            return {
                "content": json.dumps(
                    {
                        "correctedText": "",
                        "issues": [{"segmentIndex": 9, "reason": "越界"}],
                    },
                    ensure_ascii=False,
                )
            }

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    template_id = _create_classic_template(
        icoder_client, "Classic invalid guardrail", "摘要"
    )
    response = icoder_client.post(
        "/api/v2/tools/interactions/22222222-2222-4222-8222-222222222222/documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "context": [{"type": "string", "data": "患者胸痛"}],
            "templateKey": template_id,
            "outputLanguage": "zh-CN",
        },
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["type"] == "invalid_provider_response"


@pytest.mark.parametrize(
    "interaction_id,payload,expected",
    [
        (
            "not-a-uuid",
            {
                "context": [{"type": "string", "data": "x"}],
                "templateKey": "unknown",
                "outputLanguage": "zh-CN",
            },
            400,
        ),
        (
            "77777777-7777-4777-8777-777777777777",
            {
                "context": [
                    {"type": "string", "data": "x"},
                    {"type": "transcript", "data": {"text": "y"}},
                ],
                "templateKey": "unknown",
                "outputLanguage": "zh-CN",
            },
            422,
        ),
        (
            "88888888-8888-4888-8888-888888888888",
            {
                "context": [{"type": "string", "data": "x"}],
                "templateKey": "unknown",
                "outputLanguage": "zh-CN",
            },
            404,
        ),
    ],
)
def test_v2_documents_classic_generate_rejects_invalid_requests(
    icoder_client, interaction_id, payload, expected
):
    response = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/documents/", json=payload
    )
    assert response.status_code == expected, response.text


def test_v2_documents_classic_generate_fails_closed_for_degraded_provider(
    icoder_client, monkeypatch
):
    from app.main import app

    class Gateway:
        async def generate(self, *args, **kwargs):
            return {"content": json.dumps({"摘要": "不应返回"}, ensure_ascii=False), "degraded": True}

    monkeypatch.setattr(app.state, "platform_gateway", Gateway(), raising=False)
    template_id = _create_classic_template(
        icoder_client, "Classic degraded generation", "摘要"
    )
    response = icoder_client.post(
        "/api/v2/tools/interactions/66666666-6666-4666-8666-666666666666/documents/",
        json={
            "context": [{"type": "string", "data": "患者稳定"}],
            "templateKey": template_id,
            "outputLanguage": "zh-CN",
        },
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["type"] == "service_unavailable"
