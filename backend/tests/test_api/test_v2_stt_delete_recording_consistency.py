"""Cycle 12 回环一致性测试 — Corti §13.3 Recordings delete-recording (DELETE).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-delete-recording.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/recordings/delete-recording.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``DELETE /api/v2/tools/interactions/{id}/recordings/{recordingId}``
     endpoint with default + missing-sentinel recordingId.
  4. Asserts key invariants Corti also enforces:
     - Response 204 has no body.
     - 404 for ``missing-{uuid}`` sentinel (mirrors cycle-11).

Closes the **recordings family** (4 of 4 endpoints).
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle12")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-delete-recording.md"


# ─── Spec loader (no walker — DELETE has no body, no JSON envelope) ──


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
def stt_delete_recording_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_delete_recording_spec_is_real_and_cached(stt_delete_recording_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_delete_recording_spec["openapi"].startswith("3.")
    assert stt_delete_recording_spec["info"]["title"] == "Corti API"
    op = stt_delete_recording_spec["paths"]["/interactions/{id}/recordings/{recordingId}"]["delete"]
    assert "Recordings" in op["tags"]
    assert op["operationId"] == "recordings_delete"
    # 204 No Content + 404 (NEW for recordings family).
    assert "204" in op["responses"]
    assert "404" in op["responses"]
    # 204 has no body schema.
    assert "content" not in op["responses"]["204"]


def test_v2_stt_delete_recording_default_returns_204(icoder_client):
    """回环: default delete-recording returns 204 No Content (no body)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    recording_id = "f47ac10b-58cc-4372-a567-0e02b2c3d481"
    r = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r.status_code == 204, r.text
    # 204 has no body.
    assert r.content == b"", f"expected empty body for 204, got {r.content!r}"


def test_v2_stt_delete_recording_missing_sentinel_returns_404(icoder_client):
    """missing-{uuid} sentinel exercises the 404 error code (mirrors cycle-11)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    recording_id = "missing-deadbeef-cafe-1234-5678-90abcdef0000"
    r = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r.status_code == 404, r.text
    body = r.json()
    detail = body.get("detail", {})
    assert detail.get("status") == 404
    assert detail.get("type") == "recording_not_found"


def test_v2_stt_delete_recording_missing_interaction_id_rejected(icoder_client):
    """Empty interaction_id is rejected (FastAPI path-matching ensures this)."""
    # FastAPI will 404 the route since interaction_id is part of the path.
    r = icoder_client.delete("/api/v2/tools/interactions//recordings/aaaa-bbbb")
    assert r.status_code in (400, 404), r.text


def test_v2_stt_delete_recording_completes_recordings_family(icoder_client):
    """Verification: recordings family is complete after cycle 12.

    This test verifies all 4 recording endpoints share the same path
    pattern (interaction-scoped) and respond with their canonical codes.
    """
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    recording_id = "f47ac10b-58cc-4372-a567-0e02b2c3d481"

    # LIST (cycle 9)
    r_list = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert r_list.status_code == 200

    # UPLOAD (cycle 10)
    r_up = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"\x00" * 32,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r_up.status_code == 201

    # GET (cycle 11)
    r_get = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r_get.status_code == 200

    # DELETE (cycle 12)
    r_del = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r_del.status_code == 204
