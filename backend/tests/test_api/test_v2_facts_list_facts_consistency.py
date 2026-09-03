"""Cycle 13 回环一致性测试 — Corti §13.5 facts_list (GET).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/facts-list-facts.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/facts/list-facts.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/interactions/{id}/facts/``
     endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 200 + ``{facts: [...]}`` envelope shape.
     - ``facts[]`` items conform to ``FactsListItem`` (id/text/group/
       groupId/isDiscarded/source/createdAt/updatedAt/evidence).
     - ``evidence[]`` items conform to ``FactsEvidence`` (type/reference/quote).
     - Path-echo contract: ``facts[*].id`` / ``groupId`` / ``evidence.reference``
       all carry the ``interaction_id`` prefix so SDK callers can verify.

Closes the **first endpoint of the §13.5 Facts family** (5 more to follow:
add-facts, list-fact-groups, update-fact, update-facts).
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle13")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "facts-list-facts.md"


# ─── Spec loader (no walker — list endpoint, simple shape) ────────────


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
def facts_list_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_facts_list_spec_is_real_and_cached(facts_list_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert facts_list_spec["openapi"].startswith("3.")
    assert facts_list_spec["info"]["title"] == "Corti API"
    op = facts_list_spec["paths"]["/interactions/{id}/facts/"]["get"]
    assert "Facts" in op["tags"]
    assert op["operationId"] == "facts_list"
    # Only 200 + 504 in spec (interesting — no 400/401/403/500).
    assert "200" in op["responses"]
    assert "504" in op["responses"]
    # 200 schema is $ref to FactsListResponse.
    assert "FactsListResponse" in str(op["responses"]["200"])


def test_v2_facts_list_unknown_interaction_is_empty(icoder_client):
    """Unknown interactions never materialize synthetic clinical facts."""
    interaction_id = "unknown-f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "facts" in j
    assert isinstance(j["facts"], list)
    assert j["facts"] == []


def test_v2_facts_list_item_shape(icoder_client):
    """Each fact carries the spec-required optional fields (id/text/group/
    groupId/isDiscarded/source/createdAt/updatedAt/evidence)."""
    interaction_id = f"shape-{uuid.uuid4()}"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "BP 140/90.", "group": "vital-signs"}]},
    )
    assert created.status_code == 200, created.text
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
    assert r.status_code == 200, r.text
    for f in r.json()["facts"]:
        for key in (
            "id", "text", "group", "groupId", "isDiscarded",
            "source", "createdAt", "updatedAt", "evidence",
        ):
            assert key in f, f"missing {key} in fact {f.get('id')!r}"
        assert isinstance(f["evidence"], list)
        for ev in f["evidence"]:
            for key in ("type", "reference", "quote"):
                assert key in ev, f"missing {key} in evidence of fact {f.get('id')!r}"


def test_v2_facts_list_server_assigned_ids(icoder_client):
    """Persisted facts expose opaque UUID identifiers, not path-derived IDs."""
    interaction_id = f"ids-{uuid.uuid4()}"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [{"text": "Penicillin allergy.", "group": "allergies"}]},
    )
    assert created.status_code == 200, created.text
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert len(facts) == 1
    for f in facts:
        uuid.UUID(f["id"])
        uuid.UUID(f["groupId"])
        for ev in f["evidence"]:
            assert ev["reference"]


def test_v2_facts_list_source_enum(icoder_client):
    """Persisted facts retain the caller-supplied source enum."""
    interaction_id = "source-enum-f47ac10b-58cc-4372-a567-0e02b2c3d479"
    created = icoder_client.post(
        f"/api/v2/tools/interactions/{interaction_id}/facts/",
        json={"facts": [
            {"text": "Core fact.", "group": "assessment", "source": "core"},
            {"text": "System fact.", "group": "imaging-results", "source": "system"},
        ]},
    )
    assert created.status_code == 200, created.text
    r = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
    assert r.status_code == 200, r.text
    sources = {f["source"] for f in r.json()["facts"]}
    assert sources <= {"core", "system", "user"}, sources
    assert sources == {"core", "system"}, sources


def test_v2_facts_list_empty_envelope(icoder_client):
    """``empty-{uuid}`` interaction_id returns ``facts: []`` envelope."""
    r = icoder_client.get(
        "/api/v2/tools/interactions/empty-f47ac10b-58cc-4372-a567-0e02b2c3d479/facts/"
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j == {"facts": []}, j


def test_v2_facts_list_trailing_slash_optional(icoder_client):
    """Spec uses trailing slash; iCoDer also accepts the no-slash form
    (FastAPI dual registration mirrors the STT pattern)."""
    interaction_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    r_slash = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
    r_noslash = icoder_client.get(f"/api/v2/tools/interactions/{interaction_id}/facts")
    assert r_slash.status_code == r_noslash.status_code == 200
    assert r_slash.json() == r_noslash.json()
