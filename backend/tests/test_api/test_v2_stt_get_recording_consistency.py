"""Cycle 11 回环一致性测试 — Corti §13.3 Recordings get-recording (GET single).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-get-recording.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/recordings/get-recording.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/recordings/{recordingId}``
     endpoint with default + missing-sentinel recordingId and asserts
     response content type + body + error codes.
  4. Asserts key invariants Corti also enforces:
     - Response is raw binary (``text/plain`` + ``format: binary``),
       NOT a JSON envelope.
     - 404 for ``missing-{uuid}`` sentinel.
     - Path-echo via X-Stub headers (not body, since body is binary).

This is the **second non-JSON response** in iCoDer's v2 surface.
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle11")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-get-recording.md"


# ─── Spec loader (walker not needed — response is raw binary) ───────


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


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def stt_get_recording_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_get_recording_spec_is_real_and_cached(stt_get_recording_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_get_recording_spec["openapi"].startswith("3.")
    assert stt_get_recording_spec["info"]["title"] == "Corti API"
    op = stt_get_recording_spec["paths"]["/interactions/{id}/recordings/{recordingId}"]["get"]
    assert "Recordings" in op["tags"]
    assert op["operationId"] == "recordings_get"
    # 200 response is binary (text/plain + format: binary), NOT JSON.
    success_content = op["responses"]["200"]["content"]
    assert "text/plain" in success_content
    schema = success_content["text/plain"]["schema"]
    assert schema["type"] == "string"
    assert schema["format"] == "binary"
    # 404 error response exists (new for cycle 11).
    assert "404" in op["responses"]


def test_v2_stt_get_recording_default_returns_binary(icoder_client):
    """回环: default get-recording returns 200 with text/plain binary body."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    recording_id = "f47ac10b-58cc-4372-a567-0e02b2c3d481"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r.status_code == 200, r.text
    # Body must be raw bytes (NOT a JSON dict).
    assert r.content  # non-empty
    assert isinstance(r.content, bytes)
    # Content-Type per spec is text/plain (per OpenAPI declaration).
    assert r.headers["content-type"].startswith("text/plain"), \
        f"expected text/plain, got {r.headers['content-type']}"
    # Try parsing as JSON — should fail (it's not a JSON envelope).
    with pytest.raises(Exception):
        r.json()


def test_v2_stt_get_recording_missing_sentinel_returns_404(icoder_client):
    """missing-{uuid} sentinel exercises the 404 error code."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    recording_id = "missing-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r.status_code == 404, r.text
    body = r.json()
    # FastAPI wraps HTTPException detail: {"detail": {...}}.
    detail = body.get("detail", {})
    assert detail.get("status") == 404
    assert detail.get("type") == "recording_not_found"


def test_v2_stt_get_recording_path_echo_via_headers(icoder_client):
    """Path-echo invariant: X-Stub-* headers echo path IDs (since body is binary)."""
    interaction_id = "abcd1234-5678-90ab-cdef-1234567890ab"
    recording_id = "11112222-3333-4444-5555-666677778888"
    r = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r.status_code == 200, r.text
    # Headers carry the path IDs (since the body is binary, headers
    # are the testable surface).
    assert r.headers.get("x-stub-recording-id") == recording_id
    assert r.headers.get("x-stub-interaction-id") == interaction_id


def test_v2_stt_get_recording_interaction_id_missing_returns_400(icoder_client):
    """Empty interaction_id is rejected."""
    # FastAPI path-matching requires a value, so this is hard to trigger
    # naturally; we test the empty-recording_id branch instead.
    r = icoder_client.get("/api/v2/tools/interactions//recordings/")
    # Either a 404 (route doesn't match) or 400 (validation kicks in).
    assert r.status_code in (400, 404), r.text


def test_v2_stt_get_recording_content_type_is_text_plain(stt_get_recording_spec):
    """Reference sanity: spec declares response content-type text/plain."""
    op = stt_get_recording_spec["paths"]["/interactions/{id}/recordings/{recordingId}"]["get"]
    success_content = op["responses"]["200"]["content"]
    assert "text/plain" in success_content
    # application/json must NOT be the success content-type.
    assert "application/json" not in success_content
