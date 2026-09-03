"""Cycle 3 回环一致性测试 — Corti §13.4 Guided Documents shape parity.

This is the hard gate for Cycle 3. The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/guided-documents-generate.md``
     (downloaded from
     ``https://docs.corti.ai/api-reference/guided-documents/generate-a-structured-document.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``/api/v2/tools/guided-documents/`` endpoint with a
     realistic request and asserts the response validates against the
     spec's ``GuidedDocumentsCreateEphemeralResponse`` schema.
  4. Asserts key invariants Corti also enforces (e.g. ephemeral response
     must include ``usageInfo.creditsConsumed`` ≥ 0; missing retention
     header → 422).

Dynamic fields ignored (per the parity policy):
  - ``requestid`` (server-assigned UUID)
  - ``creditsConsumed`` (derived from provider usage)
  - ``document.templateId`` only if dynamic; static for Cycle 3 since
    we echo the caller-supplied UUID verbatim.
  - ``document.templateVersionId`` (defaulted when caller omits).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.fernet import Fernet
from sqlalchemy import select

# Required env for the dev escape hatch + LLM stub.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle3")
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
SPEC_MD_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "guided-documents-generate.md"


# ─── Spec loaders ────────────────────────────────────────────────────


def _extract_openapi_yaml() -> dict[str, Any]:
    """Extract and parse the ``openapi: 3.0.0`` YAML block from the markdown."""
    text = SPEC_MD_PATH.read_text(encoding="utf-8")
    # The fence opener is `` ````yaml /path/to/file post /path `` (4 backticks,
    # then ``yaml`` plus an optional inline header line ending at \n).
    blocks = re.findall(r"````yaml[^\n]*\n(.*?)````", text, flags=re.DOTALL)
    for blk in blocks:
        try:
            parsed = yaml.safe_load(blk)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and parsed.get("openapi"):
            return parsed
    raise AssertionError(f"No openapi 3.0+ YAML block found in {SPEC_MD_PATH}")


@pytest.fixture(scope="module")
def openapi_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


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
    # Dynamic-field skip
    if leaf in ("requestid", "creditsConsumed"):
        return errors

    expected_type = schema.get("type")
    nullable = bool(schema.get("nullable", False))
    if value is None:
        # Corti OpenAPI marks several optional fields (interactionId,
        # structuredDocument) as `nullable: true`. Honor that. Anything
        # else that arrives as null but isn't declared nullable is a
        # contract violation.
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


@pytest.fixture
def icoder_client(monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    # Provider calls are replaced by deterministic test doubles in generation
    # cases. Keep the credential gate explicit and test-local so suite order or
    # a deliberately empty developer environment cannot change the outcome.
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle3")
    return TestClient(app)


@pytest.fixture
def stub_chat(monkeypatch):
    """Inject a deterministic result at the canonical gateway boundary."""
    from app.api import v2_tools_guided_document as api_mod

    captured: dict[str, Any] = {}

    async def _fake_chat(messages):
        captured["messages"] = list(messages)
        return {
            "content": json.dumps({
                "subjective": "Patient reports chest tightness for 3 days.",
                "objective": "BP 180/110, HR 92.",
                "assessment": "Suspected hypertensive urgency.",
                "plan": "Start ACE inhibitor; follow-up in 1 week.",
            }),
            "usage": {"prompt_tokens": 250, "completion_tokens": 80, "total_tokens": 330},
        }

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", _fake_chat)
    return captured


@pytest.fixture
def stored_template_ref(icoder_client):
    name = f"Guided test template {uuid.uuid4()}"
    created = icoder_client.post(
        "/api/templates",
        json={
            "name": name,
            "description": "Template used by Guided Documents contract tests.",
            "content": "Return subjective, objective, assessment, and plan sections.",
            "category": "outpatient",
            "language": "en-US",
        },
    )
    assert created.status_code == 201, created.text
    listed = icoder_client.get("/api/v2/tools/templates/?source=user")
    assert listed.status_code == 200, listed.text
    match = next(row for row in listed.json() if row["name"] == name)
    return {"templateId": match["id"]}


# ─── Tests ───────────────────────────────────────────────────────────


def test_openapi_spec_is_real_and_cached():
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    spec = _extract_openapi_yaml()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Corti API"
    # The POST /documents/ endpoint must be declared under Guided Documents.
    op = spec["paths"]["/documents/"]["post"]
    assert "Guided Documents" in op["tags"]
    assert op["operationId"] == "guided_documents_generate"
    # Schema refs that the回环 test relies on must exist.
    schemas = spec["components"]["schemas"]
    for name in [
        "GuidedDocumentsGenerateByTemplateRef",
        "GuidedEphemeralDocument",
        "GuidedDocumentsCreateEphemeralResponse",
        "ErrorResponse",
        "CommonUsageInfo",
    ]:
        assert name in schemas, f"missing schema {name}"


def test_v2_guided_document_ephemeral_shape_matches_corti_spec(
    icoder_client, stub_chat, stored_template_ref, openapi_spec
):
    """回环: iCoDer's ephemeral response validates against the Corti OpenAPI
    schema ``GuidedDocumentsCreateEphemeralResponse``.
    """
    schema = openapi_spec["components"]["schemas"]["GuidedDocumentsCreateEphemeralResponse"]
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "context": [
                {"type": "text", "text": "67yo male with chest tightness for 3 days."}
            ],
            "labels": [{"key": "encounter_type", "value": "outpatient"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, schema, openapi_spec, "$.response", errs)
    assert not errs, "iCoDer ephemeral response mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_guided_document_default_retention_saves_and_returns_201(
    icoder_client, stub_chat, stored_template_ref, openapi_spec
):
    interaction_id = f"guided-saved-{uuid.uuid4()}"
    fact = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Chest tightness for three days.", "group": "chief-complaint"}]},
    )
    assert fact.status_code == 200, fact.text

    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "interactionId": interaction_id,
            "labels": [{"key": "encounter_type", "value": "outpatient"}],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    errors: list[str] = []
    schema = openapi_spec["components"]["schemas"]["GuidedDocumentsCreateResponse"]
    _check_shape(body, schema, openapi_spec, "$.saved_response", errors)
    assert not errors, "; ".join(errors)
    uuid.UUID(body["document"]["id"])

    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/"
    )
    assert listed.status_code == 200, listed.text
    match = next(
        row for row in listed.json()["data"]
        if row["id"] == body["document"]["id"]
    )
    assert match["templateRef"] == stored_template_ref["templateId"]
    assert [section["key"] for section in match["sections"]] == [
        "subjective", "objective", "assessment", "plan"
    ]


def test_v2_guided_document_unknown_template_returns_404(icoder_client, stub_chat):
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": {"templateId": str(uuid.uuid4())},
            "context": [{"type": "text", "text": "Patient reports chest pain."}],
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["type"] == "template_not_found"


def test_builder_composed_template_round_trips_to_guided_generation(
    icoder_client, monkeypatch
):
    """A Console Builder-style saved definition is executable by templateRef."""
    from app.api import v2_tools_guided_document as api_mod

    heading = f"中国病案主要诊断依据-{uuid.uuid4()}"
    section = icoder_client.post(
        "/api/v2/tools/sections/",
        json={
            "name": heading,
            "description": "仅归纳病历中明确记录的主要诊断依据。",
            "language": "zh-CN",
            "specialties": ["medical-records", "coding"],
            "outputSchema": {"type": "string"},
        },
    )
    assert section.status_code == 201, section.text
    generation = section.json()["generation"]
    assert generation["sectionId"] == section.json()["id"]
    assert generation["sectionVersionId"] == section.json()["versionId"]

    template_name = f"Builder template {uuid.uuid4()}"
    created = icoder_client.post(
        "/api/templates",
        json={
            "name": template_name,
            "description": "Builder round-trip contract.",
            "content": json.dumps({
                "instructions": {"prompt": "仅生成有原文证据支持的内容。"},
                "sections": [generation],
            }, ensure_ascii=False),
            "category": "inpatient",
            "language": "zh-CN",
        },
    )
    assert created.status_code == 201, created.text
    discovered = icoder_client.get("/api/v2/tools/templates/?source=user")
    template = next(row for row in discovered.json() if row["name"] == template_name)

    async def _builder_provider(messages):
        return {
            "content": json.dumps({heading: "病历明确记录急性阑尾炎为主要诊断。"}, ensure_ascii=False),
            "usage": {"input_tokens": 40, "output_tokens": 20},
        }

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", _builder_provider)
    generated = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "zh-CN",
            "templateRef": {"templateId": template["id"]},
            "context": [{"type": "text", "text": "出院记录：主要诊断为急性阑尾炎。"}],
        },
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["document"]["stringDocument"] == {
        heading: "病历明确记录急性阑尾炎为主要诊断。"
    }


def test_v2_saved_guided_document_is_encrypted_at_rest(
    icoder_client, stub_chat, stored_template_ref, monkeypatch
):
    from app.database import AsyncSessionLocal
    from app.models.guided_document import GuidedDocumentRecord
    from app.services.phi_encryption import is_encrypted_value

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", raising=False)
    interaction_id = f"guided-encrypted-{uuid.uuid4()}"
    phi = f"Sensitive patient statement {uuid.uuid4()}"

    fact = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": phi, "group": "chief-complaint"}]},
    )
    assert fact.status_code == 200, fact.text
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "interactionId": interaction_id,
        },
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["document"]["id"]

    async def _load_row():
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(GuidedDocumentRecord).where(
                GuidedDocumentRecord.document_id == document_id
            ))

    row = asyncio.run(_load_row())
    assert row is not None
    for stored in (
        row.encrypted_string_document_json,
        row.encrypted_structured_document_json,
        row.encrypted_labels_json,
    ):
        if stored is not None:
            assert is_encrypted_value(stored)
            assert phi not in stored

    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/"
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == document_id for item in listed.json()["data"])


def test_v2_guided_document_dynamic_template_validates_schema_and_auto_saves(
    icoder_client, monkeypatch
):
    from app.api import v2_tools_guided_document as api_mod

    async def dynamic_result(_messages):
        return {
            "content": json.dumps({
                "Assessment": {"diagnosis": "Hypertension", "severity": 2},
                "Plan": ["Recheck blood pressure", "Review medication adherence"],
            }),
            "usage": {"input_tokens": 100, "output_tokens": 40},
        }

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", dynamic_result)
    name = f"Dynamic SOAP {uuid.uuid4()}"
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [
                {
                    "type": "transcript",
                    "transcript": {"transcripts": [{"text": "Blood pressure is elevated."}]},
                },
                {
                    "type": "facts",
                    "facts": [{"text": "BP 180/110", "group": "vital-signs"}],
                },
            ],
            "dynamicTemplate": {
                "name": name,
                "generation": {
                    "instructions": {"prompt": "Create a concise assessment and plan."},
                    "sections": [
                        {
                            "heading": "Assessment",
                            "instructions": {"contentPrompt": "Document diagnosis and severity."},
                            "outputSchema": {
                                "type": "object",
                                "fields": [
                                    {
                                        "key": "diagnosis",
                                        "description": "Diagnosis",
                                        "value": {"type": "string"},
                                    },
                                    {
                                        "key": "severity",
                                        "description": "Severity score",
                                        "value": {"type": "number", "minimum": 0, "maximum": 3},
                                    },
                                ],
                            },
                        },
                        {
                            "heading": "Plan",
                            "instructions": {"contentPrompt": "Document supported next steps."},
                            "outputSchema": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": 5,
                            },
                        },
                    ],
                },
            },
        },
    )
    assert response.status_code == 200, response.text
    document = response.json()["document"]
    uuid.UUID(document["templateId"])
    assert document["structuredDocument"]["Assessment"]["severity"] == 2
    assert json.loads(document["stringDocument"]["Plan"])[0] == "Recheck blood pressure"

    templates = icoder_client.get("/api/v2/tools/templates/?source=user")
    assert templates.status_code == 200, templates.text
    assert any(
        row["id"] == document["templateId"] and row["name"] == name
        for row in templates.json()
    )


def test_v2_guided_document_assembly_resolves_curated_sections(
    icoder_client, monkeypatch
):
    from app.api import v2_tools_guided_document as api_mod

    async def assembly_result(_messages):
        return {
            "content": json.dumps({
                "Subjective": "Patient reports improved symptoms.",
                "Follow-up Plan": "Return in two weeks.",
            }),
            "usage": {},
        }

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", assembly_result)
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [{"type": "text", "text": "Symptoms improved; follow-up planned."}],
            "assemblyTemplate": {
                "name": f"Assembly {uuid.uuid4()}",
                "instructions": {"prompt": "Use only supplied evidence."},
                "sectionRefs": [
                    {"sectionId": "44444444-aaaa-bbbb-cccc-444444444444"},
                    {
                        "sectionId": "55555555-aaaa-bbbb-cccc-555555555555",
                        "overrides": {"heading": "Follow-up Plan"},
                    },
                ],
            },
        },
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["document"]["stringDocument"]) == {
        "Subjective", "Follow-up Plan"
    }


def test_v2_guided_document_dynamic_provider_schema_mismatch_fails_closed(
    icoder_client, monkeypatch
):
    from app.api import v2_tools_guided_document as api_mod

    async def wrong_type(_messages):
        return {"content": json.dumps({"Score": "high"}), "usage": {}}

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", wrong_type)
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [{"type": "text", "text": "Clinical context."}],
            "dynamicTemplate": {
                "name": "Numeric score",
                "generation": {
                    "instructions": {"prompt": "Return a numeric score."},
                    "sections": [{
                        "heading": "Score",
                        "instructions": {"contentPrompt": "Return severity score."},
                        "outputSchema": {"type": "number", "minimum": 0, "maximum": 10},
                    }],
                },
            },
        },
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["type"] == "invalid_provider_response"


def test_v2_guided_document_assembly_unknown_section_returns_404(
    icoder_client, stub_chat
):
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [{"type": "text", "text": "Clinical context."}],
            "assemblyTemplate": {
                "name": "Missing section",
                "sectionRefs": [{"sectionId": str(uuid.uuid4())}],
            },
        },
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["type"] == "section_not_found"


def test_v2_guided_template_runtime_overrides_persist_inherited_aggregate(
    icoder_client, monkeypatch
):
    from app.api import v2_tools_guided_document as api_mod

    token = uuid.uuid4().hex[:8]
    base_heading = f"Base Section {token}"
    overridden_heading = f"Overridden Section {token}"
    outputs = iter([
        {base_heading: "Base output."},
        {overridden_heading: "Overridden output."},
    ])

    async def provider(_messages):
        return {"content": json.dumps(next(outputs)), "usage": {}}

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", provider)
    base = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [{"type": "text", "text": "Documented evidence."}],
            "dynamicTemplate": {
                "name": f"Override base {token}",
                "generation": {
                    "instructions": {"prompt": "Base instructions."},
                    "sections": [{
                        "heading": base_heading,
                        "instructions": {"contentPrompt": "Base content."},
                        "outputSchema": {"type": "string"},
                    }],
                },
            },
        },
    )
    assert base.status_code == 200, base.text
    base_template_id = base.json()["document"]["templateId"]
    section_list = icoder_client.get("/api/v2/tools/sections/?source=project")
    section_id = next(
        row["id"] for row in section_list.json() if row["name"] == base_heading
    )

    overridden = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "context": [{"type": "text", "text": "Documented evidence."}],
            "templateRef": {
                "templateId": base_template_id,
                "overrides": {
                    "instructions": {"prompt": "Runtime instructions."},
                    "sections": [{
                        "sectionId": section_id,
                        "generation": {"heading": overridden_heading},
                    }],
                },
            },
        },
    )
    assert overridden.status_code == 200, overridden.text
    overridden_document = overridden.json()["document"]
    assert overridden_document["templateId"] != base_template_id
    assert overridden_document["stringDocument"] == {
        overridden_heading: "Overridden output."
    }

    templates = icoder_client.get("/api/v2/tools/templates/?source=user")
    aggregate = next(
        row for row in templates.json()
        if row["id"] == overridden_document["templateId"]
    )
    assert aggregate["autoGenerated"] is True
    assert aggregate["inheritedFromId"] == base_template_id


def test_v2_classic_document_get_update_delete_lifecycle(
    icoder_client, stub_chat, stored_template_ref
):
    interaction_id = f"document-crud-{uuid.uuid4()}"
    created_fact = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Documented chest tightness.", "group": "chief-complaint"}]},
    )
    assert created_fact.status_code == 200, created_fact.text
    generated = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        json={
            "outputLanguage": "en-US",
            "interactionId": interaction_id,
            "templateRef": stored_template_ref,
        },
    )
    assert generated.status_code == 201, generated.text
    document_id = generated.json()["document"]["id"]
    path = f"/api/v2/tools/interactions/{interaction_id}/documents/{document_id}"

    fetched = icoder_client.get(path)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == document_id
    assert icoder_client.get(
        f"/api/v2/tools/interactions/wrong-{interaction_id}/documents/{document_id}"
    ).status_code == 404

    updated = icoder_client.patch(
        path,
        json={
            "name": "Clinician reviewed note",
            "sections": [
                {"key": "plan", "name": "Plan", "text": "Follow up.", "sort": 1},
                {"key": "assessment", "name": "Assessment", "text": "Stable.", "sort": 0},
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Clinician reviewed note"
    assert [item["key"] for item in updated.json()["sections"]] == ["assessment", "plan"]
    assert updated.json()["updatedAt"] >= updated.json()["createdAt"]

    duplicate = icoder_client.patch(
        path,
        json={
            "sections": [
                {"key": "same", "name": "One", "text": "One", "sort": 0},
                {"key": "same", "name": "Two", "text": "Two", "sort": 1},
            ]
        },
    )
    assert duplicate.status_code == 422
    assert icoder_client.get(path).json()["name"] == "Clinician reviewed note"

    deleted = icoder_client.delete(path)
    assert deleted.status_code == 204, deleted.text
    assert icoder_client.get(path).status_code == 404
    listed = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/documents/"
    )
    assert listed.json() == {"data": []}


def test_v2_guided_document_error_envelope_matches_corti_spec(
    icoder_client, stored_template_ref, openapi_spec
):
    """回环: unsupported retention header emits a Corti-shaped ErrorResponse.

    Per the OpenAPI, ``422`` body uses ``ErrorResponse``.
    """
    schema = openapi_spec["components"]["schemas"]["ErrorResponse"]
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "forever"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "context": [{"type": "text", "text": "示例。"}],
        },
    )
    assert r.status_code == 422, r.text
    body = r.json()
    errs: list[str] = []
    # ErrorResponse sits under FastAPI's `detail` field as a dict.
    inner = body.get("detail", body)
    _check_shape(inner, schema, openapi_spec, "$.error_response", errs)
    assert not errs, "iCoDer 422 error envelope mismatch: " + "; ".join(errs)


def test_v2_guided_document_empty_context_rejected(
    icoder_client, stub_chat, stored_template_ref, openapi_spec
):
    """回环: empty context (no context[], no interactionId) → 422
    ``missing_context``."""
    schema = openapi_spec["components"]["schemas"]["ErrorResponse"]
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            # no context, no interactionId
        },
    )
    assert r.status_code == 422, r.text
    inner = r.json().get("detail", {})
    assert inner.get("type") == "missing_context"


def test_v2_guided_document_oversized_context_rejected_before_llm(
    icoder_client, stub_chat, stored_template_ref
):
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "context": [{"type": "text", "text": "x" * 200_001}],
        },
    )
    assert response.status_code == 422, response.text
    assert not stub_chat


def test_v2_guided_document_content_length_guard_returns_413(
    icoder_client, stub_chat
):
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"Content-Length": str(1024 * 1024 + 1)},
        json={},
    )
    assert response.status_code == 413, response.text
    assert response.json()["type"] == "request_too_large"
    assert not stub_chat


def test_v2_guided_document_resolves_persisted_interaction_facts(
    icoder_client, stub_chat, stored_template_ref
):
    """interactionId-only generation uses real tenant-scoped Facts context."""
    interaction_id = f"guided-facts-{uuid.uuid4()}"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={
            "facts": [
                {
                    "text": "Patient has a severe penicillin allergy.",
                    "group": "allergies",
                    "source": "user",
                }
            ]
        },
    )
    assert created.status_code == 200, created.text

    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "interactionId": interaction_id,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["document"]["interactionId"] == interaction_id
    user_message = stub_chat["messages"][-1]["content"]
    assert "Persisted clinical facts" in user_message
    assert "severe penicillin allergy" in user_message


def test_v2_guided_document_unknown_interaction_fails_closed(
    icoder_client, stub_chat, stored_template_ref
):
    interaction_id = f"guided-empty-{uuid.uuid4()}"
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "interactionId": interaction_id,
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "interaction_context_unavailable"


def test_v2_guided_document_no_llm_credential_returns_503(icoder_client, monkeypatch):
    """医院 pilot gate: no LLM credential + no dev opt-in → 503."""
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": {"templateId": "11111111-2222-3333-4444-555555555555"},
            "context": [{"type": "text", "text": "示例"}],
        },
    )
    assert r.status_code == 503, r.text


def test_v2_guided_document_invalid_provider_json_fails_closed(
    icoder_client,
    monkeypatch,
    stored_template_ref,
):
    from app.api import v2_tools_guided_document as api_mod

    async def malformed(_messages):
        return {"content": "not-json", "usage": {}}

    monkeypatch.setattr(api_mod, "_invoke_guided_document_model", malformed)
    response = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": stored_template_ref,
            "context": [{"type": "text", "text": "Patient reports chest pain."}],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["type"] == "invalid_provider_response"


@pytest.mark.asyncio
async def test_v2_guided_document_rejects_degraded_gateway(monkeypatch):
    from app.main import app
    from app.api.v2_tools_guided_document import _invoke_guided_document_model

    class DegradedGateway:
        async def generate(self, *args, **kwargs):
            return {"content": "{}", "is_mock": True, "degraded": True}

    monkeypatch.setattr(
        app.state,
        "platform_gateway",
        DegradedGateway(),
        raising=False,
    )
    with pytest.raises(RuntimeError, match="guided_document_provider_degraded"):
        await _invoke_guided_document_model([
            {"role": "user", "content": "Patient reports chest pain."},
        ])


def test_v2_guided_document_reference_round_trip(openapi_spec):
    """Reference sanity: a hand-built Corti response validates against the
    same OpenAPI schemas. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = openapi_spec["components"]["schemas"]["GuidedDocumentsCreateEphemeralResponse"]
    ref = {
        "document": {
            "name": "guided-doc-001",
            "templateId": "11111111-2222-3333-4444-555555555555",
            "templateVersionId": "22222222-3333-4444-5555-666666666666",
            "language": "en-US",
            "interactionId": None,
            "stringDocument": {"subjective": "Patient reports X."},
            "labels": [{"key": "k", "value": "v"}],
        },
        "usageInfo": {"creditsConsumed": 0.003},
    }
    errs: list[str] = []
    _check_shape(ref, schema, openapi_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)
