"""Phase 3-B0 Section E — Agent visibility contract tests.

Verifies that the honesty rules from Section A.5 are enforced at the data
layer. These tests catch the most material Section C findings:

- A.5.1: metadata-only agents must not declare status=EXECUTABLE
- A.5.2: stub agents must not be labeled maturity=mvp
- A.5.4: hidden agents must not appear in user-facing listings
- A.5.5: production_ready=false must be surfaced (pack must declare it)

These are data-only tests (no live API calls) so they're fast and hermetic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from icoder_runtime.core.agent_pack_loader import load_pack
from icoder_runtime.core.agent_pack_schema import PackStatus

REPO_ROOT = Path(__file__).resolve().parents[4]
OFFICIAL_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"


def _load_packs() -> list[tuple[Path, dict]]:
    out = []
    for p in OFFICIAL_AGENTS_DIR.rglob("agent_pack.json"):
        with p.open("r", encoding="utf-8") as f:
            out.append((p, json.load(f)))
    return out


def _manifest(pack: dict) -> dict:
    return pack.get("manifest") or {}


# --- A.5.1: metadata-only ≠ runnable ---

def test_a51_metadata_only_packs_must_not_have_runnable_signals():
    """Canonical metadata-only packs must not claim runnable maturity.

    Prompt agents can be executable through a backend provider and tools even
    when ``experts`` is empty, so the canonical loader is the source of truth.
    """
    packs = _load_packs()
    for path, pack in packs:
        if pack.get("agent_type") == "expert-stub":
            continue  # expert-stubs are stage-level experts, separate test
        m = _manifest(pack)
        normalized = load_pack(pack, source_path=str(path))
        if normalized.status == PackStatus.METADATA_ONLY:
            # No experts → no implementation → must NOT be labeled runnable/mvp/production-ready
            maturity = m.get("maturity")
            assert maturity not in ("mvp", "runnable", "production-ready"), (
                f"Pack {pack.get('agent_ref')} has no experts[] but maturity={maturity} "
                f"(A.5.1 violation: metadata-only ≠ runnable). "
                f"Set maturity=metadata-only in {path}."
            )


# --- A.5.2: stub ≠ MVP ---

def test_a52_stubs_must_not_be_labeled_mvp():
    """Canonical metadata-only packs must not declare maturity=mvp."""
    packs = _load_packs()
    for path, pack in packs:
        if pack.get("agent_type") == "expert-stub":
            continue
        normalized = load_pack(pack, source_path=str(path))
        if normalized.status == PackStatus.METADATA_ONLY:
            m = _manifest(pack)
            maturity = m.get("maturity")
            assert maturity != "mvp", (
                f"Pack {pack.get('agent_ref')} has no experts but maturity=mvp "
                f"(A.5.2 violation: stub ≠ MVP). "
                f"Set maturity=metadata-only in {path}."
            )


# --- A.5.4: legacy/hidden ≠ visible ---

def test_a54_expert_stubs_must_be_hidden_from_hub():
    """Expert-stub packs (Stage 1/2/4/5 of MedCodER) are internal pipeline
    stages, not user-facing Agents. They MUST set manifest.hidden_from_hub=true.
    """
    packs = _load_packs()
    for path, pack in packs:
        if pack.get("agent_type") == "expert-stub":
            m = _manifest(pack)
            assert m.get("hidden_from_hub") is True, (
                f"Expert-stub {pack.get('agent_ref')} must be manifest.hidden_from_hub=true "
                f"(A.5.4 violation: internal pipeline stage exposed as user-facing Agent) "
                f"in {path}"
            )


def test_a54_internal_engine_must_be_hidden_from_hub():
    """Internal engine packs (medcoder-coding-review) must be hidden_from_hub=true."""
    packs = _load_packs()
    for path, pack in packs:
        if pack.get("agent_type") == "internal_engine":
            m = _manifest(pack)
            assert m.get("hidden_from_hub") is True, (
                f"Internal engine {pack.get('agent_ref')} must be manifest.hidden_from_hub=true "
                f"in {path}"
            )


def test_all_user_facing_packs_are_executable_launch_candidates():
    """No visible, non-deprecated Agent may regress to metadata-only/stub."""

    packs = _load_packs()
    visible_count = 0
    for path, pack in packs:
        manifest = _manifest(pack)
        if manifest.get("hidden_from_hub") is True or pack.get("deprecated"):
            continue
        visible_count += 1
        normalized = load_pack(pack, source_path=str(path))
        assert normalized.status == PackStatus.EXECUTABLE, (
            f"User-facing pack {pack.get('agent_ref')} is "
            f"{normalized.status.value}: {normalized.validation_errors}"
        )
        assert normalized.launch_candidate_ready is True, (
            f"User-facing pack {pack.get('agent_ref')} is not an engineering "
            f"launch candidate: {normalized.launch_candidate_blockers}"
        )
        assert manifest.get("maturity") == "runnable", (
            f"User-facing pack {pack.get('agent_ref')} must declare "
            "maturity=runnable"
        )
        assert manifest.get("production_ready") is False, (
            "Engineering launch-candidate status must not bypass external "
            f"production gates for {pack.get('agent_ref')}"
        )

    assert visible_count == 26


def test_every_non_executable_pack_is_hidden_and_explicitly_classified():
    """Non-executable packs are only aliases or internal pipeline stages."""

    packs = _load_packs()
    classifications: dict[str, str] = {}
    for path, pack in packs:
        normalized = load_pack(pack, source_path=str(path))
        if normalized.status == PackStatus.EXECUTABLE:
            continue
        manifest = _manifest(pack)
        assert manifest.get("hidden_from_hub") is True
        if pack.get("deprecated"):
            assert pack.get("deprecated_replacement")
            classifications[pack["agent_ref"]] = "deprecated_alias"
        else:
            assert pack.get("agent_type") == "expert-stub"
            classifications[pack["agent_ref"]] = "internal_pipeline_stage"

    assert classifications == {
        "icoder/cdi-review@1.0.0": "deprecated_alias",
        "icoder/documentation-gap@1.0.0": "deprecated_alias",
        "icoder/index-navigator@1.0.0": "internal_pipeline_stage",
        "icoder/code-reconciler@1.0.0": "internal_pipeline_stage",
        "icoder/tabular-validator@1.0.0": "internal_pipeline_stage",
    }


# --- A.5.5: production_ready must be declared ---

def test_a55_packs_must_declare_production_ready():
    """Every pack must explicitly declare manifest.production_ready (true or false).
    Missing the field is a violation — users can't be told "MVP" if the field
    doesn't exist.
    """
    packs = _load_packs()
    for path, pack in packs:
        m = _manifest(pack)
        assert "production_ready" in m, (
            f"Pack {pack.get('agent_ref')} must declare manifest.production_ready (true/false) "
            f"in {path}"
        )


def test_a55_metadata_only_packs_must_be_production_ready_false():
    """Packs with maturity=metadata-only or stub must have production_ready=false.
    A stub claiming production_ready=true would mislead users.
    """
    packs = _load_packs()
    for path, pack in packs:
        m = _manifest(pack)
        maturity = m.get("maturity")
        if maturity in ("metadata-only", "stub", None):
            # Allow None maturity for internal engine (different convention)
            if pack.get("agent_type") == "internal_engine":
                continue
            pr = m.get("production_ready")
            assert pr is False, (
                f"Pack {pack.get('agent_ref')} has maturity={maturity} "
                f"but production_ready={pr} (A.5.5 violation). "
                f"Set production_ready=false in {path}."
            )


# --- No overclaim: visible packs must not claim 100% accuracy / F1 ---

OVERCLAIM_PATTERNS = [
    "100% accuracy",
    "F1 > 0.9",
    "outperforms",
    "state-of-the-art",
    "AI-powered",
    "fully automated",
]


def test_no_overclaim_in_visible_pack_descriptions():
    """Visible packs must not use overclaim language in description."""
    packs = _load_packs()
    for path, pack in packs:
        m = _manifest(pack)
        if m.get("hidden_from_hub") is True:
            continue
        desc = m.get("description", "") or ""
        for pattern in OVERCLAIM_PATTERNS:
            assert pattern.lower() not in desc.lower(), (
                f"Pack {pack.get('agent_ref')} description contains overclaim {pattern!r} "
                f"in {path}"
            )


# --- Maturity taxonomy ---

LEGAL_MATURITIES = {
    "metadata-only",
    "stub",
    "mvp",
    "runnable",
    "production-ready",
    "internal",  # used by internal_engine packs
}


def test_packs_use_legal_maturity_values():
    """maturity field must use one of the canonical values (or 'internal' for internal_engine)."""
    packs = _load_packs()
    for path, pack in packs:
        m = _manifest(pack)
        maturity = m.get("maturity")
        if maturity is None:
            continue  # separate test enforces presence for non-internal packs
        assert maturity in LEGAL_MATURITIES, (
            f"Pack {pack.get('agent_ref')} has illegal maturity {maturity!r} "
            f"in {path}. Legal values: {LEGAL_MATURITIES}"
        )
