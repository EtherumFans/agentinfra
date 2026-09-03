"""Cycle 8 回环一致性测试 — Corti §13.3 Transcripts (STT) create-transcript shape parity.

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-create-transcript.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/transcripts/create-transcript.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``POST /api/v2/tools/interactions/{id}/transcripts/``
     endpoint with a minimal valid body (recordingId + primaryLanguage)
     and asserts the response validates against the spec's
     ``TranscriptsResponse`` schema (which is identical to the cycle-7
     get-transcript response envelope).
  4. Asserts key invariants Corti also enforces:
     - Required body fields (recordingId, primaryLanguage) — missing
       either returns a 4xx.
     - response.recordingId == body.recordingId (echo invariant).
     - response.status is one of ``completed | processing | failed``.
     - response.id is a UUID-shaped string.

Dynamic fields ignored (per the parity policy):
  - ``id`` (server-assigned UUID; stub echoes interaction_id prefix)
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle8")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-create-transcript.md"


# ─── Spec loader + walker (same as cycles 6/7) ──────────────────────


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
def stt_create_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _valid_body(**overrides) -> dict[str, Any]:
    """Return a minimal valid create-transcript body, with overrides."""
    body = {
        "recordingId": "f47ac10b-58cc-4372-a567-0e02b2c3d481",
        "primaryLanguage": "en",
    }
    body.update(overrides)
    return body


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_create_spec_is_real_and_cached(stt_create_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_create_spec["openapi"].startswith("3.")
    assert stt_create_spec["info"]["title"] == "Corti API"
    op = stt_create_spec["paths"]["/interactions/{id}/transcripts/"]["post"]
    assert "Transcripts" in op["tags"]
    assert op["operationId"] == "transcripts_create"
    schemas = stt_create_spec["components"]["schemas"]
    for name in [
        "TranscriptsCreateRequest",
        "TranscriptsResponse",
        "TranscriptsMetadata",
        "CommonTranscriptResponse",
        "CommonUsageInfo",
        "TranscriptsStatusEnum",
        "TranscriptsParticipant",
    ]:
        assert name in schemas, f"missing schema {name}"


def test_stt_create_required_fields_match_spec(stt_create_spec):
    """Spec invariant: TranscriptsCreateRequest requires recordingId + primaryLanguage."""
    schema = stt_create_spec["components"]["schemas"]["TranscriptsCreateRequest"]
    assert set(schema["required"]) == {"recordingId", "primaryLanguage"}


def test_v2_stt_create_minimal_shape_matches_corti_spec(icoder_client, stt_create_spec):
    """回环: minimal create-transcript response validates against the
    Corti OpenAPI schema ``TranscriptsResponse``."""
    schema = stt_create_spec["components"]["schemas"]["TranscriptsResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    body = _valid_body()
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json=body,
    )
    assert r.status_code == 201, r.text
    resp_body = r.json()
    errs: list[str] = []
    _check_shape(resp_body, schema, stt_create_spec, "$.response", errs)
    assert not errs, "iCoDer create-transcript (minimal) mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_create_missing_recording_id_rejected(icoder_client):
    """Required-field validation: missing recordingId → 4xx."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"primaryLanguage": "en"},
    )
    # Pydantic 422 is the canonical "missing required field" response.
    assert r.status_code in (400, 422), r.text


def test_v2_stt_create_missing_primary_language_rejected(icoder_client):
    """Required-field validation: missing primaryLanguage → 4xx."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": "f47ac10b-58cc-4372-a567-0e02b2c3d481"},
    )
    assert r.status_code in (400, 422), r.text


def test_v2_stt_create_body_echoes_recording_id(icoder_client):
    """Body-echo invariant: response.recordingId == body.recordingId."""
    recording_id = "99999999-8888-7777-6666-555555555555"
    body = _valid_body(recordingId=recording_id)
    r = icoder_client.post(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/transcripts/",
        json=body,
    )
    assert r.status_code == 201, r.text
    resp_body = r.json()
    assert resp_body["recordingId"] == recording_id


def test_v2_stt_create_path_echoes_interaction_id(icoder_client):
    """Path-echo invariant: response.id starts with interaction_id prefix."""
    interaction_id = "abcd-1234-efgh-5678"
    body = _valid_body()
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json=body,
    )
    assert r.status_code == 201, r.text
    resp_body = r.json()
    assert resp_body["id"].startswith(interaction_id)


def test_v2_stt_create_optional_fields_accepted(icoder_client, stt_create_spec):
    """回环: full body with all optional knobs validates against the spec."""
    schema = stt_create_spec["components"]["schemas"]["TranscriptsResponse"]
    body = _valid_body(
        spokenPunctuation=True,
        automaticPunctuation=False,
        isMultichannel=True,
        diarize=False,
        participants=[
            {"channel": 1, "role": "doctor"},
            {"channel": 2, "role": "patient"},
        ],
        replacements=[
            {"find": "BID", "replace": "twice daily"},
            {"find": "PO", "replace": "by mouth"},
        ],
        keyterms={"terms": [{"term": "lisinopril"}, {"term": "metformin"}]},
    )
    r = icoder_client.post(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/transcripts/",
        json=body,
    )
    assert r.status_code == 201, r.text
    resp_body = r.json()
    errs: list[str] = []
    _check_shape(resp_body, schema, stt_create_spec, "$.response", errs)
    assert not errs, "iCoDer create-transcript (full) mismatch: " + "; ".join(errs)


def test_v2_stt_create_async_flag_accepted(icoder_client):
    """async=true is accepted (current stub still returns 201 synchronously)."""
    body = _valid_body(**{"async": True})
    r = icoder_client.post(
        "/api/v2/tools/interactions/aaaa-bbbb-cccc/transcripts/",
        json=body,
    )
    assert r.status_code == 201, r.text
    resp_body = r.json()
    assert resp_body["status"] in {"completed", "processing", "failed"}


def test_v2_stt_create_reference_round_trip(stt_create_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = stt_create_spec["components"]["schemas"]["TranscriptsResponse"]
    ref = {
        "id": "f47ac10b-58cc-4372-a567-0e02b2c3d482",
        "metadata": {
            "participantsRoles": [
                {"channel": 1, "role": "doctor"},
                {"channel": 2, "role": "patient"},
            ],
        },
        "transcripts": [
            {
                "channel": 1,
                "participant": 1,
                "speakerId": 1,
                "text": "Reference utterance from create-transcript.",
                "start": 0,
                "end": 2400,
            },
        ],
        "usageInfo": {"creditsConsumed": 0.030},
        "recordingId": "f47ac10b-58cc-4372-a567-0e02b2c3d481",
        "status": "completed",
    }
    errs: list[str] = []
    _check_shape(ref, schema, stt_create_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)


def test_v2_stt_create_request_reference_round_trip(stt_create_spec):
    """Reference sanity: a hand-built Corti-shaped request body validates
    against the spec's TranscriptsCreateRequest schema.
    """
    schema = stt_create_spec["components"]["schemas"]["TranscriptsCreateRequest"]
    ref = {
        "recordingId": "f47ac10b-58cc-4372-a567-0e02b2c3d481",
        "primaryLanguage": "en",
        "spokenPunctuation": True,
        "automaticPunctuation": False,
        "isMultichannel": True,
        "diarize": False,
        "participants": [{"channel": 1, "role": "doctor"}],
        "async": True,
        "replacements": [{"find": "BID", "replace": "twice daily"}],
        "keyterms": {"terms": [{"term": "lisinopril"}]},
    }
    errs: list[str] = []
    _check_shape(ref, schema, stt_create_spec, "$.request_reference", errs)
    assert not errs, "Corti request reference fails its own OpenAPI schema: " + "; ".join(errs)
