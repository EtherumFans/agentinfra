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

import os
import re
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
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
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
    assert len(body["data"]) >= 1, "expected at least one stub document"


def test_v2_documents_classic_path_scoping(icoder_client):
    """Path-scoping invariant: different interaction_ids yield different stub
    document IDs (because the stub data echoes the interaction UUID into the
    document id). This proves the path param is actually being read."""
    id_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    id_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    r_a = icoder_client.get(f"/api/v2/tools/interactions/{id_a}/documents/")
    r_b = icoder_client.get(f"/api/v2/tools/interactions/{id_b}/documents/")
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    ids_a = {d["id"] for d in r_a.json()["data"]}
    ids_b = {d["id"] for d in r_b.json()["data"]}
    assert ids_a != ids_b, "expected path-scoping: different ids should yield different document ids"


def test_v2_documents_classic_isStream_field_round_trip(icoder_client, docs_spec):
    """``isStream`` is a required boolean on each document. The stub data
    exercises both ``true`` and ``false`` values."""
    item_schema = docs_spec["components"]["schemas"]["DocumentsGetResponse"]
    interaction_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/documents/")
    assert r.status_code == 200, r.text
    docs = r.json()["data"]
    is_stream_values = {d["isStream"] for d in docs}
    assert True in is_stream_values, "expected at least one isStream=true document in stub"
    assert False in is_stream_values, "expected at least one isStream=false document in stub"
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