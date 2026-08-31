"""Cycle 12.1 回环一致性测试 — Corti §13.3 Transcripts get-transcript-status (GET).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-get-transcript-status.md``
     (fetched 2026-07-01 from
     ``https://docs.corti.ai/api-reference/transcripts/get-transcript-status.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer
     ``GET /api/v2/tools/interactions/{id}/transcripts/{transcriptId}/status``
     endpoint with 4 sentinels (default, processing-, failed-, missing-).
  4. Asserts key invariants Corti also enforces:
     - Response 200 + ``status`` field for valid transcriptId sentinels.
     - Response 404 for ``missing-{uuid}`` sentinel.
     - Status enum matches spec: ``completed | processing | failed``.
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle12_1")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
os.environ.setdefault("ICODER_ENABLE_PROTOCOL_FIXTURES", "1")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-get-transcript-status.md"


# ─── Spec loader + walker (reuses cycle-6/7 walker fix) ──────────────


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
def stt_get_status_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_get_status_spec_is_real_and_cached(stt_get_status_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_get_status_spec["openapi"].startswith("3.")
    assert stt_get_status_spec["info"]["title"] == "Corti API"
    op = stt_get_status_spec["paths"]["/interactions/{id}/transcripts/{transcriptId}/status"]["get"]
    assert "Transcripts" in op["tags"]
    assert op["operationId"] == "transcripts_get_status"
    schemas = stt_get_status_spec["components"]["schemas"]
    for name in ["TranscriptsStatusResponse", "TranscriptsStatusEnum", "UUID"]:
        assert name in schemas, f"missing schema {name}"


def test_stt_get_status_enum_matches_spec(stt_get_status_spec):
    """Spec invariant: status enum = ``completed | processing | failed``."""
    enum = stt_get_status_spec["components"]["schemas"]["TranscriptsStatusEnum"]["enum"]
    assert set(enum) == {"completed", "processing", "failed"}


def test_v2_stt_get_status_default_returns_completed(icoder_client, stt_get_status_spec):
    """回环: default transcript_id returns status=completed."""
    schema = stt_get_status_spec["components"]["schemas"]["TranscriptsStatusResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "f47ac10b-58cc-4372-a567-0e02b2c3d480"  # non-sentinel
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    errs: list[str] = []
    _check_shape(body, schema, stt_get_status_spec, "$.response", errs)
    assert not errs, "iCoDer get-status (default) mismatch: " + "; ".join(errs)


def test_v2_stt_get_status_processing_sentinel(icoder_client, stt_get_status_spec):
    """processing-{uuid} sentinel returns status=processing."""
    schema = stt_get_status_spec["components"]["schemas"]["TranscriptsStatusResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "processing-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processing"
    errs: list[str] = []
    _check_shape(body, schema, stt_get_status_spec, "$.response", errs)
    assert not errs, "iCoDer get-status (processing) mismatch: " + "; ".join(errs)


def test_v2_stt_get_status_failed_sentinel(icoder_client, stt_get_status_spec):
    """failed-{uuid} sentinel returns status=failed."""
    schema = stt_get_status_spec["components"]["schemas"]["TranscriptsStatusResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "failed-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    errs: list[str] = []
    _check_shape(body, schema, stt_get_status_spec, "$.response", errs)
    assert not errs, "iCoDer get-status (failed) mismatch: " + "; ".join(errs)


def test_v2_stt_get_status_missing_sentinel_returns_404(icoder_client):
    """missing-{uuid} sentinel returns 404 (new for cycle 12.1)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "missing-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert r.status_code == 404, r.text
    body = r.json()
    detail = body.get("detail", {})
    assert detail.get("status") == 404
    assert detail.get("type") == "transcript_not_found"


def test_v2_stt_get_status_reference_round_trip(stt_get_status_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = stt_get_status_spec["components"]["schemas"]["TranscriptsStatusResponse"]
    for status_value in ("completed", "processing", "failed"):
        ref = {"status": status_value}
        errs: list[str] = []
        _check_shape(ref, schema, stt_get_status_spec, "$.reference", errs)
        assert not errs, f"Corti reference ({status_value}) fails its own OpenAPI schema: " + "; ".join(errs)
