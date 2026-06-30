"""Cycle 12.2 回环一致性测试 — Corti §13.3 Transcripts delete-transcript (DELETE).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/stt-delete-transcript.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/transcripts/delete-transcript.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``DELETE /api/v2/tools/interactions/{id}/transcripts/{transcriptId}``
     endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 204 No Content (empty body).
     - **Family-completeness check**: verifies all 5 transcript endpoints
       coexist (the closing test of the entire STT family).

Closes the **transcripts family** (5 of 5 endpoints) and the **entire
STT family** (9 of 9 endpoints across transcripts + recordings).
Phase 1.3 STT parity complete.
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle12_2")
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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "stt-delete-transcript.md"


# ─── Spec loader (no walker — DELETE has no body) ─────────────────────


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
def stt_delete_transcript_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_stt_delete_transcript_spec_is_real_and_cached(stt_delete_transcript_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert stt_delete_transcript_spec["openapi"].startswith("3.")
    assert stt_delete_transcript_spec["info"]["title"] == "Corti API"
    op = stt_delete_transcript_spec["paths"]["/interactions/{id}/transcripts/{transcriptId}"]["delete"]
    assert "Transcripts" in op["tags"]
    assert op["operationId"] == "transcripts_delete"
    # 204 No Content + 400/401/403/500/504 (NOT 404 — delete-transcript doesn't have 404 in spec).
    assert "204" in op["responses"]
    assert "400" in op["responses"]
    assert "401" in op["responses"]
    assert "403" in op["responses"]
    assert "500" in op["responses"]
    assert "504" in op["responses"]
    # 204 has no body schema.
    assert "content" not in op["responses"]["204"]


def test_v2_stt_delete_transcript_default_returns_204(icoder_client):
    """回环: default delete-transcript returns 204 No Content (no body)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "f47ac10b-58cc-4372-a567-0e02b2c3d480"
    r = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r.status_code == 204, r.text
    # 204 has no body.
    assert r.content == b"", f"expected empty body for 204, got {r.content!r}"


def test_v2_stt_delete_transcript_status_sentinels_still_deletable(icoder_client):
    """processing-/failed- sentinels (cycle-7) are still deletable in cycle 12.2."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    # processing- transcript is deletable
    r_proc = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/processing-deadbeef-cafe"
    )
    assert r_proc.status_code == 204, r_proc.text
    # failed- transcript is deletable
    r_fail = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/failed-deadbeef-cafe"
    )
    assert r_fail.status_code == 204, r_fail.text


def test_v2_stt_delete_transcript_empty_path_rejected(icoder_client):
    """Empty path IDs are rejected."""
    # FastAPI path-matching returns 404 for malformed paths.
    r = icoder_client.delete("/api/v2/tools/interactions//transcripts/")
    assert r.status_code in (400, 404), r.text


def test_v2_stt_delete_transcript_completes_stt_family(icoder_client):
    """Family-completeness check: all 5 transcript endpoints coexist.

    This is the closing test of the **entire STT family** (9 of 9
    endpoints across transcripts + recordings). After this passes,
    Phase 1.3 STT parity is complete.
    """
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    transcript_id = "f47ac10b-58cc-4372-a567-0e02b2c3d480"
    recording_id = "f47ac10b-58cc-4372-a567-0e02b2c3d481"

    # ── Transcripts family (5 of 5) ──
    # 6. LIST
    r_list = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/transcripts/")
    assert r_list.status_code == 200
    # 7. GET single
    r_get = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r_get.status_code == 200
    # 8. CREATE (POST)
    r_create = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/",
        json={"recordingId": recording_id, "primaryLanguage": "en"},
    )
    assert r_create.status_code == 201
    # 12.1. GET STATUS
    r_status = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status"
    )
    assert r_status.status_code == 200
    # 12.2. DELETE  ← this cycle
    r_del = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}"
    )
    assert r_del.status_code == 204

    # ── Recordings family (4 of 4, already complete from cycle 12) ──
    r_rec_list = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/"
    )
    assert r_rec_list.status_code == 200
    r_rec_up = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/",
        content=b"\x00" * 32,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r_rec_up.status_code == 201
    r_rec_get = icoder_client.get(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r_rec_get.status_code == 200
    r_rec_del = icoder_client.delete(
        f"/api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}"
    )
    assert r_rec_del.status_code == 204

    # 9/9 endpoints verified — STT family complete.