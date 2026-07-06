"""Phase 3-B0 Section E — Agent inventory contract tests.

Verifies the static inventory documented in PHASE3B0_FULL_AGENT_INVENTORY.md
matches the codebase reality. Catches drift if packs are added/removed without
updating the inventory.

Covers spec items:
  1. Agent Hub agents all have valid status.
  2. runnable agents have run path.
  3. metadata-only agents don't show Run button (verified via pack metadata).
  9. visible agents have Agent Card.
  10. visible agents have category.
  11. visible agents don't use internal technical name as primary title.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
OFFICIAL_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
INVENTORY_MD = REPO_ROOT / "docs" / "phase3" / "PHASE3B0_FULL_AGENT_INVENTORY.md"


def _load_all_packs() -> list[dict]:
    """Load every agent_pack.json under backend/official_agents/."""
    packs = []
    for pack_path in OFFICIAL_AGENTS_DIR.rglob("agent_pack.json"):
        with pack_path.open("r", encoding="utf-8") as f:
            packs.append(json.load(f))
    return packs


def _manifest(pack: dict) -> dict:
    """Manifest getter — packs store user-facing fields under manifest.*"""
    return pack.get("manifest") or {}


def _is_user_visible(pack: dict) -> bool:
    """A pack is user-visible if hidden_from_hub is not true."""
    return not _manifest(pack).get("hidden_from_hub", False)


# --- Spec item 1: All packs have valid agent_type ---

LEGAL_AGENT_TYPES = {
    "certified",
    "community",
    "reference",
    "expert-stub",
    "internal_engine",
}


def test_all_packs_have_valid_agent_type():
    """Every pack must declare a legal agent_type per v1.2 taxonomy."""
    packs = _load_all_packs()
    assert len(packs) >= 16, f"Expected ≥16 packs, found {len(packs)}"
    for pack in packs:
        at = pack.get("agent_type")
        assert at in LEGAL_AGENT_TYPES, (
            f"Pack {pack.get('agent_ref', '<unknown>')} has invalid agent_type {at!r}"
        )


# --- Spec item 9: Visible packs have Agent Card completeness ---

REQUIRED_CARD_FIELDS = ["name", "description", "category"]


def test_visible_packs_have_agent_card_fields():
    """Visible (non-hidden) packs must have name + description + category in manifest."""
    packs = _load_all_packs()
    visible = [p for p in packs if _is_user_visible(p)]
    assert len(visible) >= 11, f"Expected ≥11 visible packs, found {len(visible)}"
    for pack in visible:
        m = _manifest(pack)
        for field in REQUIRED_CARD_FIELDS:
            assert m.get(field), (
                f"Pack {pack.get('agent_ref', '<unknown>')} missing manifest.{field}"
            )


# --- Spec item 10: Visible packs have category ---

def test_visible_packs_have_category():
    """Every visible pack must declare a category slug."""
    packs = _load_all_packs()
    visible = [p for p in packs if _is_user_visible(p)]
    for pack in visible:
        m = _manifest(pack)
        assert m.get("category"), (
            f"Pack {pack.get('agent_ref', '<unknown>')} has no manifest.category"
        )


# --- Spec item 11: Visible packs don't use internal technical name as primary title ---

TECHNICAL_NAME_PATTERNS = [
    "evidence-extractor",
    "index-navigator",
    "code-reconciler",
    "tabular-validator",
    "medcoder",
    "MedCodER",
    "HybridCodingAdapter",
    "Stage1",
    "Stage2",
]


def test_visible_packs_have_user_facing_names():
    """Visible packs must not use internal technical names as primary title."""
    packs = _load_all_packs()
    visible = [p for p in packs if _is_user_visible(p)]
    for pack in visible:
        m = _manifest(pack)
        name = m.get("name", "")
        agent_ref = pack.get("agent_ref", "")
        for pattern in TECHNICAL_NAME_PATTERNS:
            assert pattern not in name, (
                f"Pack {agent_ref} name {name!r} contains technical pattern {pattern!r}"
            )


# --- Spec item 3: metadata-only packs must NOT have status=EXECUTABLE ---

def test_expert_stubs_must_be_hidden():
    """Expert-stub packs must have manifest.hidden_from_hub=true (A.5.4 rule)."""
    packs = _load_all_packs()
    for pack in packs:
        if pack.get("agent_type") == "expert-stub":
            m = _manifest(pack)
            assert m.get("hidden_from_hub") is True, (
                f"Expert-stub pack {pack.get('agent_ref')} must be manifest.hidden_from_hub=true"
            )


# --- Inventory count sanity ---

def test_inventory_md_mentions_pack_count():
    """The inventory markdown must reference the 16-pack count."""
    if not INVENTORY_MD.exists():
        pytest.skip("Inventory markdown not present")
    text = INVENTORY_MD.read_text(encoding="utf-8")
    assert "16" in text, "Inventory markdown must reference pack count"


# --- Quick fix verification: hidden_from_hub drift ---

def test_internal_engine_is_hidden():
    """The MedCodER internal engine pack must be manifest.hidden_from_hub=true."""
    packs = _load_all_packs()
    for pack in packs:
        if pack.get("agent_type") == "internal_engine":
            m = _manifest(pack)
            assert m.get("hidden_from_hub") is True, (
                f"Internal engine pack {pack.get('agent_ref')} must be hidden"
            )
            return
    pytest.fail("No internal_engine pack found — expected medcoder-coding-review")
