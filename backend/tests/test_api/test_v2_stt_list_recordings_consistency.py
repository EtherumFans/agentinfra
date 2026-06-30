"""Cycle 9 回环一致性测试 — Corti §13.3 Recordings LIST shape parity.

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-list-recordings.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/recordings/list-recordings.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/recordings/``
     endpoint with default + sentinel UUIDs and asserts each response
     validates against the spec's ``RecordingsListResponse`` schema.
  4. Asserts key invariants Corti also enforces:
     - ``recordings`` field is a non-nullable array of UUID strings
       (empty array is valid; ``null`` is NOT valid).
     - Path-scoping: each interaction has its own deterministic recordings.

Dynamic fields ignored (per the parity policy):
  - ``requestid`` (server-assigned)
  - The specific UUID strings in recordings[] (stub-derivable; spec
    only requires type=string, format=uuid which is advisory)
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle9")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-list-recordings.md"


# ─── Spec loader + walker (same as cycles 6/7/8) ────────────────────


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
def stt_recordings_list_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_recordings_list_spec_is_real_and_cached(stt_recordings_list_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_recordings_list_spec["openapi"].startswith("3.")
    assert stt_recordings_list_spec["info"]["title"] == "Corti API"
    op = stt_recordings_list_spec["paths"]["/interactions/{id}/recordings/"]["get"]
    assert "Recordings" in op["tags"]
    assert op["operationId"] == "recordings_list"
    schemas = stt_recordings_list_spec["components"]["schemas"]
    assert "RecordingsListResponse" in schemas
    assert "UUID" in schemas


def test_stt_recordings_list_response_required_field(stt_recordings_list_spec):
    """Spec invariant: RecordingsListResponse requires ``recordings`` only."""
    schema = stt_recordings_list_spec["components"]["schemas"]["RecordingsListResponse"]
    assert set(schema["required"]) == {"recordings"}


def test_v2_stt_recordings_list_default_shape_matches_corti_spec(icoder_client, stt_recordings_list_spec):
    """回环: default recordings list response validates against the spec."""
    schema = stt_recordings_list_spec["components"]["schemas"]["RecordingsListResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, schema, stt_recordings_list_spec, "$.response", errs)
    assert not errs, "iCoDer recordings-list (default) mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_recordings_list_empty_sentinel(icoder_client, stt_recordings_list_spec):
    """Empty-sentinel: ``empty-{uuid}`` returns ``{recordings: []}`` (NOT null).

    Unlike cycle-6 transcripts list which used the same sentinel for a
    null envelope, cycle-9 recordings list returns an empty array
    because the spec does NOT declare ``recordings`` as nullable.
    """
    schema = stt_recordings_list_spec["components"]["schemas"]["RecordingsListResponse"]
    interaction_id = "empty-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recordings"] == [], \
        f"expected recordings=[] for empty sentinel, got {body['recordings']!r}"
    errs: list[str] = []
    _check_shape(body, schema, stt_recordings_list_spec, "$.response", errs)
    assert not errs, "iCoDer recordings-list (empty) mismatch: " + "; ".join(errs)


def test_v2_stt_recordings_list_path_echoes_interaction_id(icoder_client):
    """Path-echo invariant: recording UUIDs derive from interaction_id prefix."""
    interaction_id = "1111aaaa-22bb-33cc-44dd-55ee66ff77gg"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["recordings"]) >= 2
    for rec in body["recordings"]:
        # Each recording UUID should echo the interaction_id prefix.
        prefix = interaction_id.replace("-", "")[:8]
        assert rec.startswith(prefix), \
            f"recording {rec!r} should start with interaction_id prefix {prefix!r}"


def test_v2_stt_recordings_list_different_interactions_different_recordings(icoder_client):
    """Path-scoping invariant: different interaction_ids produce different recording UUIDs."""
    r1 = icoder_client.get("/api/v2/tools/interactions/aaaa-1111-2222-3333/transactions"[:-12] + "/recordings/")
    r2 = icoder_client.get("/api/v2/tools/interactions/bbbb-4444-5555-6666/recordings/")
    # Simpler: explicit distinct ids
    r1 = icoder_client.get("/api/v2/tools/interactions/aaaa-1111-2222-3333/recordings/")
    r2 = icoder_client.get("/api/v2/tools/interactions/bbbb-4444-5555-6666/recordings/")
    assert r1.status_code == 200 and r2.status_code == 200
    recs1 = set(r1.json()["recordings"])
    recs2 = set(r2.json()["recordings"])
    assert recs1 != recs2, "different interactions should produce different recording UUIDs"


def test_v2_stt_recordings_list_reference_round_trip(stt_recordings_list_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = stt_recordings_list_spec["components"]["schemas"]["RecordingsListResponse"]
    ref = {
        "recordings": [
            "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "99999999-8888-7777-6666-555555555555",
        ],
    }
    errs: list[str] = []
    _check_shape(ref, schema, stt_recordings_list_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)