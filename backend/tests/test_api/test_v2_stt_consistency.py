"""Cycle 6 回环一致性测试 — Corti §13.3 Transcripts (STT) LIST shape parity.

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-list-transcripts.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/transcripts/list-transcripts.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/transcripts/``
     endpoint with and without ``?full=true`` and asserts the response
     validates against the spec's ``TranscriptsListResponse`` schema.
  4. Asserts the spec's nullable envelope field
     (``transcripts: T[] | null``) round-trips correctly when the
     interaction_id sentinel is used.

Dynamic fields ignored (per the parity policy):
  - ``id`` (server-assigned UUID, stub echoes interaction_id into id)
  - ``createdAt``, ``updatedAt`` (timestamps; not in this schema)
  - ``creditsConsumed`` (not in this schema)
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle6")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-list-transcripts.md"


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
    """Recursive OpenAPI shape check. Skips dynamic fields per policy.

    When ``schema`` contains both ``$ref`` and parent-level fields
    (``type``, ``nullable``, ``enum``), the parent fields are merged
    onto the resolved schema so that OpenAPI properties like
    ``transcript: {$ref: ..., type: object, nullable: true}`` honor
    their parent metadata.
    """
    if "$ref" in schema:
        parent_overrides = {k: v for k, v in schema.items() if k != "$ref"}
        resolved = _resolve_ref(spec, schema["$ref"])
        # Merge: parent overrides win over resolved-schema defaults.
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
def stt_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_spec_is_real_and_cached(stt_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_spec["openapi"].startswith("3.")
    assert stt_spec["info"]["title"] == "Corti API"
    op = stt_spec["paths"]["/interactions/{id}/transcripts/"]["get"]
    assert "Transcripts" in op["tags"]
    assert op["operationId"] == "transcripts_list"
    schemas = stt_spec["components"]["schemas"]
    for name in [
        "TranscriptsListResponse",
        "TranscriptsListItem",
        "TranscriptsData",
        "CommonTranscriptResponse",
        "ErrorResponse",
    ]:
        assert name in schemas, f"missing schema {name}"


def test_stt_envelope_field_is_nullable_in_spec(stt_spec):
    """Contract invariant: spec declares ``transcripts: nullable: true`` on the
    envelope. Walker must honor this; if it didn't, empty-interaction tests
    would fail with 'unexpected null' errors."""
    field = stt_spec["components"]["schemas"]["TranscriptsListResponse"]["properties"]["transcripts"]
    assert field.get("nullable") is True, (
        "spec should declare transcripts nullable; if this fails the spec "
        "drifted from docs.corti.ai and the walker must be reviewed"
    )


def test_v2_stt_list_shape_matches_corti_spec(icoder_client, stt_spec):
    """回环: iCoDer list-transcripts response validates against the Corti OpenAPI
    schema ``TranscriptsListResponse`` (envelope with optional transcripts array)."""
    envelope_schema = stt_spec["components"]["schemas"]["TranscriptsListResponse"]
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/transcripts/")
    assert r.status_code == 200, r.text
    body = r.json()
    errs: list[str] = []
    _check_shape(body, envelope_schema, stt_spec, "$.response", errs)
    assert not errs, "iCoDer STT list mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_list_full_true_includes_transcript_data(icoder_client, stt_spec):
    """?full=true round-trip: each item carries the full transcript payload
    (channel/participant/text/start/end rows)."""
    item_schema = stt_spec["components"]["schemas"]["TranscriptsListItem"]
    interaction_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/transcripts/?full=true")
    assert r.status_code == 200, r.text
    items = r.json()["transcripts"]
    assert items is not None and len(items) >= 1
    # Every item with full=true must include the transcript payload
    for item in items:
        assert item.get("transcript") is not None, (
            "expected transcript payload when ?full=true; got None for "
            f"id={item.get('id')}"
        )
    errs: list[str] = []
    for i, item in enumerate(items):
        _check_shape(item, item_schema, stt_spec, f"$.item[{i}]", errs)
    assert not errs, "iCoDer STT full=true item mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_stt_list_full_false_omits_transcript(icoder_client, stt_spec):
    """?full=false (default): transcript field is omitted (None), not populated."""
    interaction_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/transcripts/")
    assert r.status_code == 200, r.text
    items = r.json()["transcripts"]
    assert items is not None and len(items) >= 1
    for item in items:
        # Either absent (omitted) or explicit null (both acceptable per spec).
        assert item.get("transcript") in (None, ), (
            f"expected transcript=null when ?full omitted, got {item.get('transcript')!r}"
        )


def test_v2_stt_envelope_nullable_round_trip(icoder_client, stt_spec):
    """Spec declares ``transcripts: nullable: true``. Stub returns null when
    interaction_id starts with ``empty-``. Walker must accept this."""
    envelope_schema = stt_spec["components"]["schemas"]["TranscriptsListResponse"]
    interaction_id = "empty-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/transcripts/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("transcripts") is None, (
        f"expected transcripts=null for sentinel id, got {body.get('transcripts')!r}"
    )
    # Walker should also accept this without errors (null is permitted by nullable: true)
    errs: list[str] = []
    _check_shape(body, envelope_schema, stt_spec, "$.response", errs)
    assert not errs, "iCoDer STT nullable envelope mismatch: " + "; ".join(errs)


def test_v2_stt_path_scoping(icoder_client):
    """Path-scoping invariant: different interaction_ids yield different
    transcript ids (stub echoes UUID into id)."""
    id_a = "12345678-aaaa-aaaa-aaaa-123456789012"
    id_b = "12345678-bbbb-bbbb-bbbb-123456789012"
    r_a = icoder_client.get(f"/api/v2/tools/interactions/{id_a}/transcripts/")
    r_b = icoder_client.get(f"/api/v2/tools/interactions/{id_b}/transcripts/")
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    ids_a = {t["id"] for t in r_a.json()["transcripts"]}
    ids_b = {t["id"] for t in r_b.json()["transcripts"]}
    assert ids_a != ids_b, "expected path-scoping: different ids should yield different transcript ids"


def test_v2_stt_reference_round_trip(stt_spec):
    """Reference sanity: a hand-built Corti-shaped response validates against
    its own OpenAPI schemas. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    envelope_schema = stt_spec["components"]["schemas"]["TranscriptsListResponse"]
    ref = {
        "transcripts": [
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "transcriptSample": "Reference sample text.",
                "transcript": {
                    "metadata": {"participantsRoles": [{"channel": 1, "role": "patient"}]},
                    "transcripts": [
                        {
                            "channel": 1,
                            "participant": 1,
                            "speakerId": 1,
                            "text": "Reference utterance.",
                            "start": 0,
                            "end": 1500,
                        },
                    ],
                },
            },
        ],
    }
    errs: list[str] = []
    _check_shape(ref, envelope_schema, stt_spec, "$.reference", errs)
    assert not errs, "Corti reference fails its own OpenAPI schema: " + "; ".join(errs)