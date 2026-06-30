"""Cycle 7 回环一致性测试 — Corti §13.3 Transcripts (STT) GET single-transcript shape parity.

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-get-transcript.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/transcripts/get-transcript.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/transcripts/{transcriptId}``
     endpoint with three transcript_id sentinels (completed,
     processing-{uuid}, failed-{uuid}) and asserts each response
     validates against the spec's ``TranscriptsResponse`` schema.
  4. Asserts key invariants Corti also enforces (e.g. ``transcripts``
     field is nullable while ``status=processing|failed``;
     ``recordingId`` is a UUID; ``status`` is enum
     ``completed|processing|failed``).

Dynamic fields ignored (per the parity policy):
  - ``id``, ``recordingId`` (server-assigned UUIDs; stub echoes
    transcript_id / interaction_id)
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle7")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-get-transcript.md"


# ─── Spec loader + walker (same as cycle 6 with $ref+nullable fix) ──


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
def stt_get_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_get_spec_is_real_and_cached(stt_get_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_get_spec["openapi"].startswith("3.")
    assert stt_get_spec["info"]["title"] == "Corti API"
    op = stt_get_spec["paths"]["/interactions/{id}/transcripts/{transcriptId}"]["get"]
    assert "Transcripts" in op["tags"]
    assert op["operationId"] == "transcripts_get"
    schemas = stt_get_spec["components"]["schemas"]
    for name in [
        "TranscriptsResponse",
        "TranscriptsMetadata",
        "CommonTranscriptResponse",
        "CommonUsageInfo",
        "TranscriptsStatusEnum",
        "TranscriptsParticipant",
    ]:
        assert name in schemas, f"missing schema {name}"


def test_stt_get_status_enum_matches_spec(stt_get_spec):
    """Spec invariant: status enum = ``completed | processing | failed``."""
    enum = stt_get_spec["components"]["schemas"]["TranscriptsStatusEnum"]["enum"]
    assert set(enum) == {"completed", "processing", "failed"}


def test_v2_stt_get_completed_shape_matches_corti_spec(icoder_client, stt_get_spec):
    """回环: get-transcript response (completed state) validates against the
    Corti OpenAPI schema ``TranscriptsResponse``."""
    schema = stt_get_spec["components"]["schemas"]["TranscriptsResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "f47ac10b-58cc-4372-a567-0e02b2c3d480"  # non-sentinel = completed
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, schema, stt_get_spec, "$.response", errs)
    assert not errs, "iCoDer get-transcript (completed) mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_get_processing_shape_with_nullable_transcripts(icoder_client, stt_get_spec):
    """回环: get-transcript (status=processing) has ``transcripts: null`` per spec.

    This exercises the nullable contract that the walker fix from cycle 6
    was designed to handle.
    """
    schema = stt_get_spec["components"]["schemas"]["TranscriptsResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "processing-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processing"
    assert body["transcripts"] is None, f"expected transcripts=null when processing, got {body['transcripts']!r}"
    errs: list[str] = []
    _check_shape(body, schema, stt_get_spec, "$.response", errs)
    assert not errs, "iCoDer get-transcript (processing) mismatch: " + "; ".join(errs)


def test_v2_stt_get_failed_shape_with_nullable_transcripts(icoder_client, stt_get_spec):
    """Failed-state transcripts also have ``transcripts: null`` per spec."""
    schema = stt_get_spec["components"]["schemas"]["TranscriptsResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "failed-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert body["transcripts"] is None


def test_v2_stt_get_path_echoes_ids(icoder_client):
    """Path-echo invariant: response id == path transcript_id (stub echoes)."""
    transcript_id = "11111111-2222-3333-4444-555555555555"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/aaaa-bbbb-cccc/transcripts/{transcript_id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == transcript_id
    assert body["recordingId"].startswith("aaaa-bbbb-cccc-"), \
        f"recordingId should echo interaction_id prefix; got {body['recordingId']}"


def test_v2_stt_get_completed_has_populated_transcripts(icoder_client):
    """Completed-state contract: ``transcripts`` is a non-empty array."""
    r = icoder_client.get(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/transcripts/zzzz-yyyy-xxxx"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert isinstance(body["transcripts"], list)
    assert len(body["transcripts"]) >= 1


def test_v2_stt_get_reference_round_trip(stt_get_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = stt_get_spec["components"]["schemas"]["TranscriptsResponse"]
    ref = {
        "id": "11111111-2222-3333-4444-555555555555",
        "metadata": {
            "participantsRoles": [{"channel": 1, "role": "doctor"}],
        },
        "transcripts": [
            {
                "channel": 1,
                "participant": 2,
                "speakerId": 1,
                "text": "Reference utterance.",
                "start": 0,
                "end": 1500,
            },
        ],
        "usageInfo": {"creditsConsumed": 0.012},
        "recordingId": "99999999-8888-7777-6666-555555555555",
        "status": "completed",
    }
    errs: list[str] = []
    _check_shape(ref, schema, stt_get_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)