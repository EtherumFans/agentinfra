"""A1B-AE-R.2 — Preset Agent materialization tests.

Coverage:

§1  Catalog — 4 stub presets now have delegates_to_pack pointing at a real Pack
§2  claim-check Pack exists at official_agents/claim-check/agent_pack.json
§3  Delegates target Pack dirs actually exist on disk
§4  Legacy orphan Python dirs retain DEPRECATED.md as RETAINED_AS_PYTHON_IMPLEMENTATION
§5  POST /api/v1/agents/quick?from_preset={key} creates a DB Agent seeded from the preset
§6  POST /api/v1/agents/quick without from_preset still works (name-only Corti-style)
§7  POST /api/v1/agents/quick?from_preset=unknown returns 404
§8  Journey 7 clone-preset regrade evidence — preset-backed creation no longer 404s
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_AGENTS_DIR = REPO_ROOT / "official_agents"


# ─────────────────────────────────────────────────────────────────────
# §1 Catalog — delegates_to_pack wiring
# ─────────────────────────────────────────────────────────────────────


def test_cdi_preset_delegates_to_cdi_pack():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-cdi-preset")
    assert p is not None
    assert p.delegates_to_pack == "icoder/clinical-documentation-improvement-agent@1.0.0", (
        f"icoder-cdi-preset.delegates_to_pack must point at the CDI Pack, got {p.delegates_to_pack!r}"
    )


def test_drg_dip_preset_delegates_to_drg_pack():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-drg-dip-preset")
    assert p is not None
    assert p.delegates_to_pack == "icoder/drg-analyzer@1.1.3", (
        f"icoder-drg-dip-preset.delegates_to_pack must point at DRG analyzer Pack, got {p.delegates_to_pack!r}"
    )


def test_claim_check_preset_delegates_to_claim_check_pack():
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-claim-check-preset")
    assert p is not None
    assert p.delegates_to_pack == "icoder/claim-check@1.1.0", (
        f"icoder-claim-check-preset.delegates_to_pack must point at claim-check Pack, got {p.delegates_to_pack!r}"
    )


def test_intake_interview_preset_is_documented_as_deferred():
    """R.2 plan listed 3 presets (cdi/drg-dip/claim-check). Intake-interview
    is deferred to R.4 (Local Expert completion). Its delegates_to_pack may
    remain null until R.4 ships the interviewing Pack."""
    from app.services.preset_agents import get_preset
    p = get_preset("icoder-intake-interview-preset")
    assert p is not None
    # R.2 doesn't break this preset; R.4 will set delegates_to_pack
    assert p.delegates_to_pack is None or "icoder/" in p.delegates_to_pack


# ─────────────────────────────────────────────────────────────────────
# §2 claim-check Pack exists
# ─────────────────────────────────────────────────────────────────────


def test_claim_check_pack_file_exists():
    p = OFFICIAL_AGENTS_DIR / "claim-check" / "agent_pack.json"
    assert p.exists(), f"claim-check agent_pack.json missing at {p}"


def test_claim_check_pack_is_valid_json_with_required_fields():
    p = OFFICIAL_AGENTS_DIR / "claim-check" / "agent_pack.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["format_version"] in {"1.1", "1.2"}
    assert data["agent_ref"] == "icoder/claim-check@1.1.0"
    assert data["agent_type"] == "certified"
    manifest = data["manifest"]
    assert manifest["maturity"] == "runnable"
    assert manifest["production_ready"] is False
    assert manifest["human_review"] == "required"
    # The governed local provider only assembles explicitly labelled claim,
    # chart, and versioned payer-policy facts with exact spans.  It does not
    # adjudicate coding support, coverage, eligibility, or payment.
    assert data["backend_provider"] == "icoder.governed-claim-check.v1"
    assert data["backend_config"]["network_required"] is False
    assert data["backend_config"]["llm_required"] is False
    assert data["tools"] == []
    assert data["llm_capabilities"]["supports_tool_calling"] is False
    assert data["llm_capabilities"]["supports_mcp_tools"] is False
    assert data["permissions"]["evidence_required"] is True
    assert data["permissions"]["production_writeback_blocked"] is True
    assert "missing_policy_items" in data["output_contract"]["required_fields"]
    assert "production_submission_blocked" in data["output_contract"]["required_fields"]
    assert data["human_review_required_when"]


# ─────────────────────────────────────────────────────────────────────
# §3 Delegates target Pack dirs exist on disk
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "preset_key,expected_pack_slug",
    [
        ("icoder-cdi-preset", "clinical-documentation-improvement-agent"),
        ("icoder-drg-dip-preset", "drg-analyzer"),
        ("icoder-claim-check-preset", "claim-check"),
    ],
)
def test_delegates_target_pack_dir_exists(preset_key, expected_pack_slug):
    from app.services.preset_agents import get_preset
    p = get_preset(preset_key)
    assert p is not None
    assert p.delegates_to_pack is not None
    # delegates_to_pack format: "icoder/<slug>@<version>"
    slug = p.delegates_to_pack.split("@")[0].split("/", 1)[1]
    assert slug == expected_pack_slug
    pack_dir = OFFICIAL_AGENTS_DIR / slug
    assert pack_dir.exists(), f"Pack dir missing: {pack_dir}"
    pack_json = pack_dir / "agent_pack.json"
    assert pack_json.exists(), f"agent_pack.json missing in {pack_dir}"


# ─────────────────────────────────────────────────────────────────────
# §4 Legacy orphan Python dirs retain DEPRECATED.md reframed
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "legacy_dir",
    ["code_validation", "compliance_guardrail", "note_completeness"],
)
def test_legacy_underscore_dir_deprecated_md_reframed(legacy_dir):
    """R.2 reframed the 3 underscore dirs as RETAINED_AS_PYTHON_IMPLEMENTATION
    (Python module names cannot contain dashes)."""
    p = OFFICIAL_AGENTS_DIR / legacy_dir / "DEPRECATED.md"
    assert p.exists(), f"DEPRECATED.md missing in {legacy_dir}/"
    content = p.read_text(encoding="utf-8")
    assert "RETAINED_AS_PYTHON_IMPLEMENTATION" in content, (
        f"{legacy_dir}/DEPRECATED.md must be reframed as RETAINED_AS_PYTHON_IMPLEMENTATION per R.2"
    )
    assert "A1B-AE-R.2" in content


# ─────────────────────────────────────────────────────────────────────
# §5 POST /api/v1/agents/quick?from_preset={key} — happy path
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_quick_create_with_from_preset_cdi_seeds_agent(client):
    """POST /api/v1/agents/quick?from_preset=icoder-cdi-preset creates
    a DB Agent seeded with the preset's fields."""
    r = client.post(
        "/api/v1/agents/quick?from_preset=icoder-cdi-preset",
        json={},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["canonical_key"] == "icoder-cdi-preset"
    assert body["agent_type"] == "expert"
    assert body["status"] == "draft"
    assert body["next_step"] == "customize"

    # Verify DB row was created with preset metadata
    from app.database import AsyncSessionLocal
    from sqlalchemy import select
    from app.models.agent import Agent
    import asyncio

    async def _check():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Agent).where(Agent.id == body["id"])
            )
            return result.scalar_one_or_none()

    agent = asyncio.run(_check())
    assert agent is not None
    assert agent.canonical_key == "icoder-cdi-preset"
    assert agent.system_prompt  # seeded from preset
    assert agent.config.get("source_preset") == "icoder-cdi-preset"
    assert agent.config.get("delegates_to_pack") == "icoder/clinical-documentation-improvement-agent@1.0.0"
    # Cleanup
    from sqlalchemy import delete
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == body["id"]))
            await db.commit()
    asyncio.run(_cleanup())


def test_quick_create_with_from_preset_drg_dip(client):
    r = client.post(
        "/api/v1/agents/quick?from_preset=icoder-drg-dip-preset",
        json={},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["canonical_key"] == "icoder-drg-dip-preset"
    from app.database import AsyncSessionLocal
    from sqlalchemy import delete
    from app.models.agent import Agent
    import asyncio
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == body["id"]))
            await db.commit()
    asyncio.run(_cleanup())


def test_quick_create_with_from_preset_claim_check(client):
    r = client.post(
        "/api/v1/agents/quick?from_preset=icoder-claim-check-preset",
        json={},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["canonical_key"] == "icoder-claim-check-preset"
    assert body["agent_type"] == "orchestrator"
    from app.database import AsyncSessionLocal
    from sqlalchemy import delete
    from app.models.agent import Agent
    import asyncio
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == body["id"]))
            await db.commit()
    asyncio.run(_cleanup())


# ─────────────────────────────────────────────────────────────────────
# §6 POST /api/v1/agents/quick without from_preset (Corti name-only)
# ─────────────────────────────────────────────────────────────────────


def test_quick_create_name_only_still_works(client):
    r = client.post(
        "/api/v1/agents/quick",
        json={"name": "R2 Test Agent"},
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["name"] == "R2 Test Agent"
    from app.database import AsyncSessionLocal
    from sqlalchemy import delete
    from app.models.agent import Agent
    import asyncio
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == body["id"]))
            await db.commit()
    asyncio.run(_cleanup())


# ─────────────────────────────────────────────────────────────────────
# §7 POST /api/v1/agents/quick?from_preset=unknown → 404
# ─────────────────────────────────────────────────────────────────────


def test_quick_create_unknown_preset_returns_404(client):
    r = client.post(
        "/api/v1/agents/quick?from_preset=not-a-real-preset",
        json={},
    )
    assert r.status_code == 404, r.text
    assert "Preset not found" in r.text


# ─────────────────────────────────────────────────────────────────────
# §8 Journey 7 regrade — preset-backed creation succeeds
# ─────────────────────────────────────────────────────────────────────


def test_journey_7_regrade_preset_create_no_longer_404(client):
    """Journey 7 originally hit GET /api/v1/agents/resolve/code_validation
    which 404'd because no Agent row existed. R.2 fixes this by adding
    POST /api/v1/agents/quick?from_preset=... that actually creates the row.

    This test verifies that creating from each of the 3 newly-materialized
    presets produces a row that can then be resolved via the alias-aware
    lookup — closing the Journey 7 evidence misjudgment.
    """
    created_ids: list[str] = []
    try:
        for preset_key in (
            "icoder-cdi-preset",
            "icoder-drg-dip-preset",
            "icoder-claim-check-preset",
        ):
            r = client.post(
                f"/api/v1/agents/quick?from_preset={preset_key}",
                json={},
            )
            assert r.status_code in (200, 201), r.text
            created_ids.append(r.json()["id"])

        # Each created Agent should be resolvable by canonical_key
        for i, preset_key in enumerate((
            "icoder-cdi-preset",
            "icoder-drg-dip-preset",
            "icoder-claim-check-preset",
        )):
            r = client.get(f"/api/v1/agents/resolve/{preset_key}")
            assert r.status_code == 200, (
                f"resolve {preset_key} returned {r.status_code}: {r.text}"
            )
            resolved = r.json()
            assert resolved["canonical_key"] == preset_key
    finally:
        from app.database import AsyncSessionLocal
        from sqlalchemy import delete
        from app.models.agent import Agent
        import asyncio
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                for aid in created_ids:
                    await db.execute(delete(Agent).where(Agent.id == aid))
                await db.commit()
        asyncio.run(_cleanup())
