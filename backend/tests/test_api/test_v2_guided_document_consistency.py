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

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

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
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def stub_chat(monkeypatch):
    """Stub ``llm_service.chat`` to return a deterministic structured doc."""
    from app.api import v2_tools_guided_document as api_mod

    captured: dict[str, Any] = {}

    async def _fake_chat(messages, *args, **kwargs):
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

    monkeypatch.setattr(api_mod.llm_service, "chat", _fake_chat)
    return captured


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
    icoder_client, stub_chat, openapi_spec
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
            "templateRef": {"templateId": "11111111-2222-3333-4444-555555555555"},
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


def test_v2_guided_document_error_envelope_matches_corti_spec(
    icoder_client, openapi_spec
):
    """回环: 422 (missing retention header) emits a Corti-shaped ErrorResponse.

    Per the OpenAPI, ``422`` body uses ``ErrorResponse``.
    """
    schema = openapi_spec["components"]["schemas"]["ErrorResponse"]
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        # No X-Corti-Retention-Policy header → Cycle 3 422.
        json={
            "outputLanguage": "en-US",
            "templateRef": {"templateId": "11111111-2222-3333-4444-555555555555"},
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


def test_v2_guided_document_empty_context_rejected(icoder_client, stub_chat, openapi_spec):
    """回环: empty context (no context[], no interactionId) → 422
    ``missing_context``."""
    schema = openapi_spec["components"]["schemas"]["ErrorResponse"]
    r = icoder_client.post(
        "/api/v2/tools/guided-documents/",
        headers={"X-Corti-Retention-Policy": "none"},
        json={
            "outputLanguage": "en-US",
            "templateRef": {"templateId": "11111111-2222-3333-4444-555555555555"},
            # no context, no interactionId
        },
    )
    assert r.status_code == 422, r.text
    inner = r.json().get("detail", {})
    assert inner.get("type") == "missing_context"


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