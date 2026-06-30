"""Cycle 15 回环一致性测试 — Corti §13.5 facts_fact_groups_list (GET).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/facts-list-fact-groups.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/facts/list-fact-groups.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/factgroups/`` endpoint.
  4. Asserts key invariants Corti also enforces:
     - **GLOBAL endpoint**, NOT path-scoped to an interaction (path is
       ``/factgroups/`` not ``/interactions/{id}/fact-groups/``).
     - Response 200 + ``{data: [...]}`` envelope shape.
     - ``data[]`` items conform to ``FactsFactGroupsItem`` (id/key/translations).
     - ``translations[]`` items conform to ``FactsFactGroupsItemTranslation``
       (id/languages_id/name).
     - **Deterministic catalog**: every call returns the same 17 group
       rows (matches ``CORTI_FACT_GROUPS`` frozenset) with stable UUID5
       ids so SDK callers can cache the response.

Closes the **third endpoint of the §13.5 Facts family** (3 more to follow:
update-fact, update-facts, ...).
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
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle15")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "facts-list-fact-groups.md"


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
def facts_fact_groups_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_facts_fact_groups_spec_is_real_and_cached(facts_fact_groups_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert facts_fact_groups_spec["openapi"].startswith("3.")
    assert facts_fact_groups_spec["info"]["title"] == "Corti API"
    op = facts_fact_groups_spec["paths"]["/factgroups/"]["get"]
    assert "Facts" in op["tags"]
    assert op["operationId"] == "facts_fact_groups_list"
    # 200 + 500 (note: 500, NOT 504 like list-facts/add-facts).
    assert "200" in op["responses"]
    assert "500" in op["responses"]
    # 200 schema is $ref to FactsFactGroupsListResponse.
    assert "FactsFactGroupsListResponse" in str(op["responses"]["200"])


def test_v2_facts_fact_groups_global_path(icoder_client):
    """GLOBAL endpoint, NOT path-scoped: path is /api/v2/tools/factgroups/,
    not /api/v2/tools/interactions/{id}/fact-groups/."""
    # No interaction_id — direct global path.
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "data" in j
    assert isinstance(j["data"], list)
    assert len(j["data"]) >= 1


def test_v2_facts_fact_groups_envelope_shape(icoder_client):
    """Each item has id/key/translations per spec (all fields optional in spec)."""
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    for item in r.json()["data"]:
        for key in ("id", "key", "translations"):
            assert key in item, f"missing {key} in item {item.get('id')!r}"
        assert isinstance(item["translations"], list)
        assert len(item["translations"]) >= 1
        for tr in item["translations"]:
            for key in ("id", "languages_id", "name"):
                assert key in tr, f"missing {key} in translation of {item.get('key')!r}"


def test_v2_facts_fact_groups_keys_match_canonical(icoder_client):
    """iCoDer exposes the same canonical 17 keys defined in
    ``CORTI_FACT_GROUPS`` (alphabetically sorted)."""
    from app.schemas.v2_tools_facts import CORTI_FACT_GROUPS
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    keys = [item["key"] for item in r.json()["data"]]
    assert keys == sorted(CORTI_FACT_GROUPS)
    assert set(keys) == set(CORTI_FACT_GROUPS)


def test_v2_facts_fact_groups_uuids_stable(icoder_client):
    """UUID5 ids are stable across calls (fixed namespace + key) so SDK
    callers can cache them."""
    r1 = icoder_client.get("/api/v2/tools/factgroups/")
    r2 = icoder_client.get("/api/v2/tools/factgroups/")
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json(), "catalog must be deterministic"


def test_v2_facts_fact_groups_uuids_are_valid(icoder_client):
    """All group ids are valid UUIDs."""
    import uuid as _uuid
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    for item in r.json()["data"]:
        # Should not raise.
        _uuid.UUID(item["id"])


def test_v2_facts_fact_groups_uuids_unique(icoder_client):
    """Each group has a unique UUID (no collisions in the catalog)."""
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()["data"]]
    assert len(ids) == len(set(ids)), f"duplicate UUIDs in catalog: {ids}"


def test_v2_facts_fact_groups_translation_default(icoder_client):
    """Default stub gives each group exactly 1 en-US translation row."""
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    for item in r.json()["data"]:
        assert len(item["translations"]) == 1
        tr = item["translations"][0]
        assert tr["languages_id"] == "en-US"
        # name defaults to the key itself (canonical form).
        assert tr["name"] == item["key"]


def test_v2_facts_fact_groups_trailing_slash_optional(icoder_client):
    """Trailing slash is optional (FastAPI dual registration)."""
    r_slash = icoder_client.get("/api/v2/tools/factgroups/")
    r_noslash = icoder_client.get("/api/v2/tools/factgroups")
    assert r_slash.status_code == r_noslash.status_code == 200
    assert r_slash.json() == r_noslash.json()


def test_v2_facts_fact_groups_canonical_sample(icoder_client):
    """A few canonical Corti groups are present (demographics, vital-signs,
    plan) — these are the same groups iCoDer's extract-facts prompt
    advertises."""
    r = icoder_client.get("/api/v2/tools/factgroups/")
    assert r.status_code == 200, r.text
    keys = {item["key"] for item in r.json()["data"]}
    for expected in ("demographics", "chief-complaint", "vital-signs", "plan"):
        assert expected in keys, f"missing canonical group {expected!r} in {keys}"
