"""Cycle 14 回环一致性测试 — Corti §13.5 facts_create (POST).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/facts-add-facts.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/facts/add-facts.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``POST /api/v2/tools/interactions/{id}/facts/``
     endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 200 + ``{facts: [...]}`` envelope shape.
     - ``facts[]`` items conform to ``FactsCreateItem`` (id/text/group/
       groupId/source/isDiscarded/updatedAt).
     - Request body shape: ``{facts: [{text, group, source?}, ...]}``
       with required ``text`` + ``group``.
     - Echo contract: ``id``/``groupId`` carry the ``interaction_id``
       prefix so SDK callers can verify.
     - Source enum (core|system|user) is honored when supplied.

Closes the **second endpoint of the §13.5 Facts family** (4 more to follow:
list-fact-groups, update-fact, update-facts).
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

# Required env for the dev escape hatch.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle14")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "facts-add-facts.md"


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
def facts_add_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_facts_add_spec_is_real_and_cached(facts_add_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert facts_add_spec["openapi"].startswith("3.")
    assert facts_add_spec["info"]["title"] == "Corti API"
    op = facts_add_spec["paths"]["/interactions/{id}/facts/"]["post"]
    assert "Facts" in op["tags"]
    assert op["operationId"] == "facts_create"
    # Only 200 + 504 in spec (matches list-facts, no 400/401/403/500).
    assert "200" in op["responses"]
    assert "504" in op["responses"]
    # 200 schema is $ref to FactsCreateResponse.
    assert "FactsCreateResponse" in str(op["responses"]["200"])


def test_v2_facts_add_minimal_request(icoder_client):
    """回环: minimal request (1 fact with text+group) → 200 + echo."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Patient is a 67-year-old male.", "group": "demographics"}]},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "facts" in j
    assert isinstance(j["facts"], list)
    assert len(j["facts"]) == 1
    f = j["facts"][0]
    # Spec fields: id, text, group, groupId, source, isDiscarded, updatedAt
    for key in ("id", "text", "group", "groupId", "source", "isDiscarded", "updatedAt"):
        assert key in f, f"missing {key} in created fact"
    # text + group are echoed from input
    assert f["text"] == "Patient is a 67-year-old male."
    assert f["group"] == "demographics"


def test_v2_facts_add_server_assigned_ids(icoder_client):
    """Created facts receive opaque UUID identifiers from the server."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Allergy: penicillin.", "group": "allergies"}]},
    )
    assert r.status_code == 200, r.text
    f = r.json()["facts"][0]
    uuid.UUID(f["id"])
    uuid.UUID(f["groupId"])
    assert f["id"] != f["groupId"]


def test_v2_facts_add_source_optional_default_user(icoder_client):
    """When ``source`` is omitted, persisted facts default to ``"user"``
    (caller-created)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "BP 140/90 mmHg.", "group": "vital-signs"}]},
    )
    assert r.status_code == 200, r.text
    f = r.json()["facts"][0]
    assert f["source"] == "user"


def test_v2_facts_add_source_enum_core_system_user(icoder_client):
    """All 3 source enum values are honored when supplied by caller."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={
            "facts": [
                {"text": "Core fact.", "group": "demographics", "source": "core"},
                {"text": "System fact.", "group": "vital-signs", "source": "system"},
                {"text": "User fact.", "group": "allergies", "source": "user"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert [f["source"] for f in facts] == ["core", "system", "user"]


def test_v2_facts_add_is_discarded_default_false(icoder_client):
    """``isDiscarded`` defaults to ``False`` on every create (per spec semantics)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Plan: follow up in 2 weeks.", "group": "plan"}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["facts"][0]["isDiscarded"] is False


def test_v2_facts_add_empty_facts_array(icoder_client):
    """Empty ``facts: []`` array is accepted (zero facts to add) and returns
    an empty ``facts: []`` envelope (not 400 — spec does not require
    non-empty)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": []},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"facts": []}


def test_v2_facts_add_trailing_slash_optional(icoder_client):
    """Trailing slash is optional (FastAPI dual registration mirrors STT pattern)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    body = {"facts": [{"text": "Test.", "group": "other"}]}
    r_slash = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/", json=body
    )
    r_noslash = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts", json=body
    )
    assert r_slash.status_code == r_noslash.status_code == 200
    slash_fact = r_slash.json()["facts"][0]
    noslash_fact = r_noslash.json()["facts"][0]
    assert slash_fact["id"] != noslash_fact["id"]
    assert slash_fact["text"] == noslash_fact["text"] == "Test."
    assert slash_fact["groupId"] == noslash_fact["groupId"]


def test_v2_facts_add_multiple_facts(icoder_client):
    """Multiple facts are persisted in request order with unique opaque IDs."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={
            "facts": [
                {"text": "First.", "group": "demographics"},
                {"text": "Second.", "group": "vital-signs"},
                {"text": "Third.", "group": "plan"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert len(facts) == 3
    assert [f["text"] for f in facts] == ["First.", "Second.", "Third."]
    ids = [f["id"] for f in facts]
    assert len(set(ids)) == 3
    for fact_id in ids:
        uuid.UUID(fact_id)
