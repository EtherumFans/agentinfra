"""Phase 4-D (D-6) — Corti-style card metadata on Prebuilt Hub cards.

Verifies the /api/icoder/agents/hub endpoint returns created_at + creator
fields per card, matching Corti's "DD-Mon-YYYY · Creator" list card layout.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p11")
os.environ.setdefault("ICODER_PHASE1_STUB_LLM", "0")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_hub_cards_have_created_at_and_creator(client):
    """Every Hub card should carry created_at (DD-Mon-YYYY) + creator (str)."""
    r = client.get("/api/icoder/agents/hub")
    assert r.status_code == 200
    body = r.json()
    cards = body.get("agents") or []
    assert cards, "no hub cards returned"
    for card in cards:
        assert "created_at" in card, f"card {card.get('agent_ref')} missing created_at"
        assert "creator" in card, f"card {card.get('agent_ref')} missing creator"
        # created_at format: DD-Mon-YYYY (e.g. 08-Jul-2026) or empty string
        ca = card["created_at"]
        assert ca == "" or len(ca) >= 8, f"card {card.get('agent_ref')} created_at looks wrong: {ca!r}"
        # creator: non-empty string (default "iCoDer")
        cr = card["creator"]
        assert isinstance(cr, str) and cr, f"card {card.get('agent_ref')} creator empty"


def test_hub_card_created_at_format_matches_corti(client):
    """At least one card's created_at should parse as DD-Mon-YYYY."""
    import datetime as _dt
    r = client.get("/api/icoder/agents/hub")
    cards = r.json().get("agents") or []
    parsed_one = False
    for c in cards:
        ca = c.get("created_at") or ""
        if not ca:
            continue
        try:
            _dt.datetime.strptime(ca, "%d-%b-%Y")
            parsed_one = True
            break
        except ValueError:
            continue
    assert parsed_one, "no card had a DD-Mon-YYYY created_at; all parses failed"
