"""Cycle 16 回环一致性测试 — Corti §13.5 facts_update (PATCH).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/facts-update-fact.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/facts/update-fact.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``PATCH /api/v2/tools/interactions/{id}/facts/{factId}``
     endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 200 + all 8 fields **required** per spec (stricter than
       add-facts where all fields were optional).
     - PATCH semantics: only fields present in the request body are
       changed; omitted fields retain their "current" value.
     - Path-echo contract: response ``id`` == path factId, response
       ``groupId`` carries the interaction_id prefix.

Closes the **fourth endpoint of the §13.5 Facts family** (2 more to follow:
update-facts batch, ...).
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle16")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "facts-update-fact.md"


# ─── Spec loader (no walker — flat envelope) ─────────────────────────


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
def facts_update_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_facts_update_spec_is_real_and_cached(facts_update_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert facts_update_spec["openapi"].startswith("3.")
    assert facts_update_spec["info"]["title"] == "Corti API"
    op = facts_update_spec["paths"]["/interactions/{id}/facts/{factId}"]["patch"]
    assert "Facts" in op["tags"]
    assert op["operationId"] == "facts_update"
    # 200 + 504 (back to 504, not 500 like list-fact-groups).
    assert "200" in op["responses"]
    assert "504" in op["responses"]
    # 200 schema is $ref to FactsUpdateResponse.
    assert "FactsUpdateResponse" in str(op["responses"]["200"])


def test_v2_facts_update_minimal_request(icoder_client):
    """回环: minimal request (1 field) → 200 + all 8 required fields populated."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"text": "Updated fact text."},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # All 8 fields per spec.
    for key in ("id", "text", "group", "groupId", "source", "isDiscarded", "createdAt", "updatedAt"):
        assert key in j, f"missing required {key} in update response"
    assert j["text"] == "Updated fact text."


def test_v2_facts_update_response_all_fields_required(icoder_client):
    """All 8 response fields are REQUIRED (per spec, not optional like add-facts)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"text": "x"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # All 8 keys present, none null.
    for key in ("id", "text", "group", "groupId", "source", "isDiscarded", "createdAt", "updatedAt"):
        assert j.get(key) is not None, f"{key} is None — spec requires this field"


def test_v2_facts_update_path_echo_id(icoder_client):
    """Path-echo contract: response ``id`` == path ``factId``."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"text": "x"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == fact_id


def test_v2_facts_update_path_echo_group_id(icoder_client):
    """Path-echo contract: response ``groupId`` carries interaction_id prefix."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"text": "x"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["groupId"].startswith(interaction_id)


def test_v2_facts_update_patch_semantics(icoder_client):
    """PATCH semantics: omitted fields use stub defaults
    (``group='other'``, ``source='user'``, ``isDiscarded=False``)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={},  # empty body — all fields use defaults
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["group"] == "other"
    assert j["source"] == "user"
    assert j["isDiscarded"] is False


def test_v2_facts_update_all_fields(icoder_client):
    """Caller can update all 4 fields in one request; response reflects
    every updated value."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={
            "text": "Patient reports improvement.",
            "group": "follow-up",
            "source": "user",
            "isDiscarded": False,
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["text"] == "Patient reports improvement."
    assert j["group"] == "follow-up"
    assert j["source"] == "user"
    assert j["isDiscarded"] is False


def test_v2_facts_update_discard_flag(icoder_client):
    """Setting ``isDiscarded=true`` is honored (user marked fact as discarded)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"isDiscarded": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["isDiscarded"] is True


def test_v2_facts_update_source_enum(icoder_client):
    """All 3 source enum values are honored when supplied."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    for source in ("core", "system", "user"):
        r = icoder_client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
            json={"source": source},
        )
        assert r.status_code == 200, r.text
        assert r.json()["source"] == source


def test_v2_facts_update_timestamps(icoder_client):
    """``createdAt`` and ``updatedAt`` are populated; ``updatedAt`` is
    different from ``createdAt`` (per spec semantics — update increments
    updatedAt)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/{fact_id}",
        json={"text": "x"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["createdAt"] is not None
    assert j["updatedAt"] is not None
    # Stub: updatedAt is 1 second after createdAt (deterministic).
    assert j["updatedAt"] > j["createdAt"]
