"""Phase 5 Track D P0 Gate 1 — Hub endpoint surfaces display_status fields.

PDF §B3 invariants enforced at the API contract level:

- Every Hub card MUST include ``display_status`` + ``display_badges`` (≤2)
  + ``usage_boundaries`` + ``display_status_internal``.
- ``display_status`` MUST be one of the 5 PDF §B3 enum values
  (preview/available/controlled_use/coming_soon/deprecated).
- Engineering-internal fields (maturity/production_ready/human_review)
  MUST remain in the payload (PDF §B2: 内部治理字段不能删除) but user
  cards render ``display_*`` instead.
- Hidden_from_hub packs MUST NOT appear in the response.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


_VALID_DISPLAY_STATUSES = {
    "preview",
    "available",
    "controlled_use",
    "coming_soon",
    "deprecated",
}


def test_hub_card_has_display_status_fields(client: TestClient) -> None:
    """Every Hub card includes the 4 new display_status fields."""
    resp = client.get("/api/icoder/agents/hub")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    for card in data["agents"]:
        assert "display_status" in card, (
            f"missing display_status on {card.get('agent_id')!r}"
        )
        assert "display_badges" in card
        assert "usage_boundaries" in card
        assert "display_status_internal" in card
        assert card["display_status"] in _VALID_DISPLAY_STATUSES, (
            f"invalid display_status {card['display_status']!r} "
            f"on {card.get('agent_id')!r}"
        )
        # PDF §B3: max 2 badges per card
        assert len(card["display_badges"]) <= 2, (
            f"card {card.get('agent_id')!r} has {len(card['display_badges'])} "
            f"badges (PDF §B3 max 2)"
        )
        # Each badge must have type + zh + en labels
        for b in card["display_badges"]:
            assert "type" in b
            assert "label_zh" in b
            assert "label_en" in b
            assert b["label_zh"], f"empty label_zh on {b}"
            assert b["label_en"], f"empty label_en on {b}"
        # usage_boundaries must be non-empty
        assert len(card["usage_boundaries"]) >= 1


def test_hub_internal_fields_preserved_for_engineering(client: TestClient) -> None:
    """PDF §B2: 内部治理字段不能删除 — maturity/production_ready/human_review
    stay in the response for engineering dashboards, just not on user cards."""
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    for card in data["agents"]:
        # Legacy engineering fields still present
        assert "maturity" in card
        assert "production_ready" in card
        assert "human_review" in card
        assert card["pack_status"] in {"executable", "metadata_only", "invalid"}
        assert isinstance(card["launch_candidate_ready"], bool)
        assert isinstance(card["launch_candidate_blockers"], list)
        assert isinstance(card["external_release_gates"], list)
        assert card["external_release_gates"], "external production gates must stay explicit"
        # display_status_internal carries the full state for engineering views
        internal = card["display_status_internal"]
        assert "maturity" in internal
        assert "production_ready" in internal
        assert "runtime_mode" in internal
        assert "persistence_ready" in internal


def test_hub_cdi_card_is_preview_with_approval_required(client: TestClient) -> None:
    """CDI agent must show ``preview`` + approval_required secondary badge
    (PDF §B6: CDI stays preview until medical quality validation done)."""
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    cdi = next(
        (
            c for c in data["agents"]
            if "clinical-documentation" in c.get("agent_id", "")
        ),
        None,
    )
    if cdi is None:
        pytest.skip("CDI agent not visible in Hub")
    assert cdi["display_status"] == "preview"
    badge_types = {b["type"] for b in cdi["display_badges"]}
    assert "preview" in badge_types
    assert "approval_required" in badge_types


def test_hub_medical_coding_card_is_preview(client: TestClient) -> None:
    """Medical Coding Agent is also preview (production_ready=false)."""
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    mc = next(
        (
            c for c in data["agents"]
            if c.get("agent_id") == "medical-coding-agent"
        ),
        None,
    )
    if mc is None:
        pytest.skip("medical-coding-agent not visible in Hub")
    assert mc["display_status"] == "preview"
    # Category medical-coding → approval_required secondary badge
    badge_types = {b["type"] for b in mc["display_badges"]}
    assert "approval_required" in badge_types


def test_hub_hidden_packs_excluded(client: TestClient) -> None:
    """Packs with manifest.hidden_from_hub=true MUST NOT appear."""
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    for card in data["agents"]:
        assert card.get("hidden_from_hub") is False or card.get("hidden_from_hub") is None


def test_hub_no_card_renders_raw_engineering_text_in_badges(
    client: TestClient,
) -> None:
    """Raw MVP/production flags must not appear in either badge surface."""
    resp = client.get("/api/icoder/agents/hub")
    data = resp.json()
    for card in data["agents"]:
        assert "mvp" not in card["badge"].lower()
        for b in card["display_badges"]:
            label = b["label_en"].lower()
            # The forbidden engineering strings must never appear
            assert "production_ready=false" not in label
            assert "mvp" not in label
            assert "ai-assisted" not in label
