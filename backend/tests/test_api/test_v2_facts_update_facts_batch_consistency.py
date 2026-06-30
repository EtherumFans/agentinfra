"""Cycle 17 回环一致性测试 — Corti §13.5 facts_batch_update (PATCH).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/facts-update-facts.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/facts/update-facts.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``PATCH /api/v2/tools/interactions/{id}/facts/``
     endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 200 + ``{facts: [...]}`` envelope shape.
     - All 8 response fields per item are **required** (same as cycle 16).
     - PATCH semantics: omitted fields use stub defaults.
     - **NO ``source`` field in request** (per spec — distinct from
       single-resource PATCH).
     - Path-echo: response ``id`` == input ``factId``, response
       ``groupId`` carries the ``interaction_id`` prefix.
     - Batch semantics: multiple facts in one request are echoed back
       in order.

Closes the **fifth endpoint of the §13.5 Facts family** (1 more to follow).
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle17")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "facts-update-facts.md"


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
def facts_batch_update_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_facts_batch_update_spec_is_real_and_cached(facts_batch_update_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert facts_batch_update_spec["openapi"].startswith("3.")
    assert facts_batch_update_spec["info"]["title"] == "Corti API"
    op = facts_batch_update_spec["paths"]["/interactions/{id}/facts/"]["patch"]
    assert "Facts" in op["tags"]
    assert op["operationId"] == "facts_batch_update"
    # 200 + 504 (same as update-fact cycle 16).
    assert "200" in op["responses"]
    assert "504" in op["responses"]
    # 200 schema is $ref to FactsBatchUpdateResponse.
    assert "FactsBatchUpdateResponse" in str(op["responses"]["200"])


def test_facts_batch_update_input_no_source_field(facts_batch_update_spec):
    """Per spec, ``FactsBatchUpdateInput`` does NOT have a ``source`` field
    (distinct from single-resource PATCH cycle 16)."""
    input_schema = facts_batch_update_spec["components"]["schemas"]["FactsBatchUpdateInput"]
    assert "source" not in input_schema.get("properties", {}), (
        "spec invariant violated: FactsBatchUpdateInput must NOT have a source field"
    )


def test_v2_facts_batch_update_minimal_request(icoder_client):
    """回环: minimal request (1 fact with factId only) → 200 + echo."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id}]},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "facts" in j
    assert isinstance(j["facts"], list)
    assert len(j["facts"]) == 1
    f = j["facts"][0]
    # All 8 response fields required.
    for key in ("id", "text", "group", "groupId", "source", "isDiscarded", "createdAt", "updatedAt"):
        assert key in f, f"missing required {key} in batch update response"


def test_v2_facts_batch_update_path_echo_id(icoder_client):
    """Path-echo contract: response ``id`` == input ``factId``."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["facts"][0]["id"] == fact_id


def test_v2_facts_batch_update_path_echo_group_id(icoder_client):
    """Path-echo contract: response ``groupId`` carries interaction_id prefix."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["facts"][0]["groupId"].startswith(interaction_id)


def test_v2_facts_batch_update_patch_semantics(icoder_client):
    """PATCH semantics: omitted fields use stub defaults
    (``group='other'``, ``isDiscarded=False``)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id}]},
    )
    assert r.status_code == 200, r.text
    f = r.json()["facts"][0]
    assert f["group"] == "other"
    assert f["isDiscarded"] is False
    # source is always "user" per stub (not in request per spec)
    assert f["source"] == "user"


def test_v2_facts_batch_update_all_fields(icoder_client):
    """Caller can update all 3 batch-updateable fields (text, group,
    isDiscarded) in one request; response reflects every updated value."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={
            "facts": [{
                "factId": fact_id,
                "text": "Updated.",
                "group": "follow-up",
                "isDiscarded": False,
            }],
        },
    )
    assert r.status_code == 200, r.text
    f = r.json()["facts"][0]
    assert f["text"] == "Updated."
    assert f["group"] == "follow-up"
    assert f["isDiscarded"] is False


def test_v2_facts_batch_update_discard_flag(icoder_client):
    """Setting ``isDiscarded=true`` is honored (user marked fact as discarded)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id, "isDiscarded": True}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["facts"][0]["isDiscarded"] is True


def test_v2_facts_batch_update_multiple_facts(icoder_client):
    """Multiple facts in one request are echoed back in order with
    path-echoed ids."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id_1 = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    fact_id_2 = "4d0e9b23-8055-4c4f-a70f-0382d3ccfb19"
    fact_id_3 = "5e1fac34-9166-4d50-b810-1493e4ddgc20"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={
            "facts": [
                {"factId": fact_id_1, "isDiscarded": True},
                {"factId": fact_id_2, "text": "Second.", "group": "vital-signs"},
                {"factId": fact_id_3, "text": "Third."},
            ],
        },
    )
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert len(facts) == 3
    assert facts[0]["id"] == fact_id_1 and facts[0]["isDiscarded"] is True
    assert facts[1]["id"] == fact_id_2 and facts[1]["text"] == "Second." and facts[1]["group"] == "vital-signs"
    assert facts[2]["id"] == fact_id_3 and facts[2]["text"] == "Third."


def test_v2_facts_batch_update_empty_facts(icoder_client):
    """Empty ``facts: []`` is accepted (no facts to update) and returns
    an empty ``facts: []`` envelope (not 400 — spec does not require
    non-empty)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": []},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"facts": []}


def test_v2_facts_batch_update_trailing_slash_optional(icoder_client):
    """Trailing slash is optional (FastAPI dual registration)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    body = {"facts": [{"factId": fact_id}]}
    r_slash = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/", json=body
    )
    r_noslash = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts", json=body
    )
    assert r_slash.status_code == r_noslash.status_code == 200
    assert r_slash.json() == r_noslash.json()


def test_v2_facts_batch_update_timestamps(icoder_client):
    """``createdAt`` and ``updatedAt`` are populated; ``updatedAt`` is
    different from ``createdAt`` (per spec semantics — update increments
    updatedAt)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    fact_id = "3c9d8a12-7f44-4b3e-9e6f-9271c2bbfa08"
    r = icoder_client.patch(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"factId": fact_id}]},
    )
    assert r.status_code == 200, r.text
    f = r.json()["facts"][0]
    assert f["createdAt"] is not None
    assert f["updatedAt"] is not None
    assert f["updatedAt"] > f["createdAt"]
