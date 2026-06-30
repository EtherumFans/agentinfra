"""Cycle 10 回环一致性测试 — Corti §13.3 Recordings upload (POST application/octet-stream).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-upload-recording.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/recordings/upload-recording.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``POST /api/v2/tools/interactions/{id}/recordings/``
     endpoint with an ``application/octet-stream`` body and asserts the
     response validates against the spec's ``RecordingsCreateResponse``
     schema.
  4. Asserts key invariants Corti also enforces:
     - Content-Type must be ``application/octet-stream`` (NOT multipart).
     - Empty body is rejected (400).
     - Path-echo: ``recordingId`` echoes ``interaction_id`` prefix.

This is the **first non-JSON content-type** endpoint in iCoDer's v2
surface. The walker doesn't validate format strings (``format: uuid``),
but ``type: string`` is enforced.

Dynamic fields ignored (per the parity policy):
  - ``requestid`` (server-assigned)
  - The specific UUID string in recordingId (stub-derivable)
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle10")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-upload-recording.md"


# ─── Spec loader + walker (same as cycles 6-9) ───────────────────────


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
    if "$ref" in schema:
        parent_overrides = {k: v for k, v in schema.items() if k != "$ref"}
        resolved = _resolve_ref(spec, schema["$ref"])
        schema = {**resolved, **parent_overrides}
    leaf = path.rsplit(".", 1)[-1]
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
def stt_upload_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_upload_spec_is_real_and_cached(stt_upload_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_upload_spec["openapi"].startswith("3.")
    assert stt_upload_spec["info"]["title"] == "Corti API"
    op = stt_upload_spec["paths"]["/interactions/{id}/recordings/"]["post"]
    assert "Recordings" in op["tags"]
    assert op["operationId"] == "recordings_upload"
    # Body content-type is application/octet-stream (binary).
    body_content = op["requestBody"]["content"]
    assert "application/octet-stream" in body_content, \
        f"expected octet-stream body, got {list(body_content.keys())}"
    schemas = stt_upload_spec["components"]["schemas"]
    for name in ["RecordingsCreateResponse", "UUID"]:
        assert name in schemas, f"missing schema {name}"


def test_stt_upload_response_required_field(stt_upload_spec):
    """Spec invariant: RecordingsCreateResponse requires recordingId only."""
    schema = stt_upload_spec["components"]["schemas"]["RecordingsCreateResponse"]
    assert set(schema["required"]) == {"recordingId"}


def test_v2_stt_upload_binary_body_returns_201(icoder_client, stt_upload_spec):
    """回环: upload-recording with binary body validates against the spec."""
    schema = stt_upload_spec["components"]["schemas"]["RecordingsCreateResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    # Simulate a small audio file (1 KB of bytes).
    fake_audio = b"\x00" * 1024
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=fake_audio,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, schema, stt_upload_spec, "$.response", errs)
    assert not errs, "iCoDer upload-recording (binary) mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_upload_empty_body_rejected(icoder_client):
    """Empty body is rejected (400). Per spec, body is required."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 400, r.text


def test_v2_stt_upload_path_echoes_interaction_id(icoder_client):
    """Path-echo invariant: recordingId echoes interaction_id prefix."""
    interaction_id = "abcd1234-5678-90ab-cdef-1234567890ab"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"\x00" * 100,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["recordingId"].startswith(interaction_id), \
        f"recordingId {body['recordingId']!r} should start with {interaction_id!r}"


def test_v2_stt_upload_trailing_slash_alias(icoder_client):
    """Both /recordings/ (Corti spec) and /recordings (REST convention) work."""
    body_bytes = b"\x00" * 50
    headers = {"Content-Type": "application/octet-stream"}
    r1 = icoder_client.post(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/recordings/",
        content=body_bytes,
        headers=headers,
    )
    r2 = icoder_client.post(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/recordings",
        content=body_bytes,
        headers=headers,
    )
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    # Both responses should have a recordingId.
    assert "recordingId" in r1.json()
    assert "recordingId" in r2.json()


def test_v2_stt_upload_reference_round_trip(stt_upload_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = stt_upload_spec["components"]["schemas"]["RecordingsCreateResponse"]
    ref = {
        "recordingId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    }
    errs: list[str] = []
    _check_shape(ref, schema, stt_upload_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)