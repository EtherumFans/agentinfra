"""Phase 5 Track D P0 Gate 1 — Agent Display Status Mapper unit tests.

PDF §B3 invariants enforced:

    preview         可体验，但尚未完成生产质量验证
    available       功能可稳定运行
    controlled_use  可进入真实业务流程，但关键动作需审批
    coming_soon     当前不可运行
    deprecated      不再推荐使用

Also enforces PDF §B5 invariants:

    - runtime_mode=stub/mock → never "available"
    - production_ready=false → never "available"
    - quality_validated=false → never hide the validation state
    - persistence_ready=false workflow agent → never "controlled_use"
    - deprecated → "deprecated"
    - no runnable path + no real provider → "coming_soon"
"""
from __future__ import annotations

from app.services.agent_display_status import (
    AgentStateInput,
    derive_agent_display_status,
    project_pack_to_display_status,
)


# ---------------------------------------------------------------------------
# Rule 1 — deprecated always wins
# ---------------------------------------------------------------------------


def test_deprecated_pack_returns_deprecated_status():
    state = AgentStateInput(
        maturity="deprecated",
        production_ready=True,
        quality_validated=True,
        runtime_mode="real",
        persistence_ready=True,
        integration_ready=True,
        runnable=True,
        has_backend_provider=True,
        deprecated=True,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "deprecated"
    assert any(b.type == "deprecated" for b in result.display_badges)


def test_maturity_deprecated_treated_as_deprecated_even_without_flag():
    state = AgentStateInput(
        maturity="deprecated",
        production_ready=True,
        quality_validated=True,
        runtime_mode="real",
        persistence_ready=True,
        integration_ready=True,
        runnable=True,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "deprecated"


# ---------------------------------------------------------------------------
# Rule 2 — expert-stub / maturity=stub → coming_soon
# ---------------------------------------------------------------------------


def test_expert_stub_pack_returns_coming_soon():
    state = AgentStateInput(
        maturity="stub",
        agent_type="expert-stub",
        runnable=False,
        has_backend_provider=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "coming_soon"
    assert any(b.type == "coming_soon" for b in result.display_badges)


# ---------------------------------------------------------------------------
# Rule 3 — internal_engine → deprecated internal-only
# ---------------------------------------------------------------------------


def test_internal_engine_returns_internal_only():
    state = AgentStateInput(
        maturity="internal",
        agent_type="internal_engine",
        runnable=True,
        has_backend_provider=True,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "deprecated"
    assert any(b.type == "internal_only" for b in result.display_badges)


# ---------------------------------------------------------------------------
# Rule 4 — not runnable + no backend provider → coming_soon
# ---------------------------------------------------------------------------


def test_not_runnable_no_provider_returns_coming_soon():
    state = AgentStateInput(
        maturity="mvp",
        runnable=False,
        has_backend_provider=False,
        production_ready=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "coming_soon"


# ---------------------------------------------------------------------------
# Rule 5 — runnable but runtime_mode=stub/mock/unavailable → coming_soon
# ---------------------------------------------------------------------------


def test_runnable_with_stub_runtime_returns_coming_soon():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="stub",
        production_ready=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "coming_soon"


def test_runnable_with_mock_runtime_returns_coming_soon():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="mock",
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "coming_soon"


# ---------------------------------------------------------------------------
# Rule 6 — production_ready=false OR quality_validated=false → preview
# ---------------------------------------------------------------------------


def test_unvalidated_runnable_pack_returns_preview():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=False,
        quality_validated=False,
        category="cdi",
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "preview"
    badge_types = {b.type for b in result.display_badges}
    assert "preview" in badge_types
    # CDI category gets approval_required secondary badge
    assert "approval_required" in badge_types


def test_quality_validated_false_returns_preview_even_if_production_ready():
    state = AgentStateInput(
        maturity="production",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=True,
        quality_validated=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "preview"


def test_medical_coding_category_gets_approval_required_secondary():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=False,
        quality_validated=False,
        category="medical-coding",
    )
    result = derive_agent_display_status(state)
    badge_types = {b.type for b in result.display_badges}
    assert "approval_required" in badge_types


def test_evidence_extraction_category_gets_clinical_decision_badge():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=False,
        quality_validated=False,
        category="evidence-extraction",
    )
    result = derive_agent_display_status(state)
    badge_types = {b.type for b in result.display_badges}
    assert "clinical_decision_confirmation_required" in badge_types


def test_code_validation_category_gets_anomaly_badge():
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=False,
        quality_validated=False,
        category="code-validation",
    )
    result = derive_agent_display_status(state)
    badge_types = {b.type for b in result.display_badges}
    assert "anomaly_confirmation_required" in badge_types


# ---------------------------------------------------------------------------
# Rule 7 — production_ready + quality_validated + no persistence → preview
#           + persistence_ready + no integration → controlled_use
# ---------------------------------------------------------------------------


def test_validated_but_no_persistence_returns_preview():
    state = AgentStateInput(
        maturity="production",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=True,
        quality_validated=True,
        persistence_ready=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "preview"


def test_validated_no_integration_returns_controlled_use():
    state = AgentStateInput(
        maturity="production",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=True,
        quality_validated=True,
        persistence_ready=True,
        integration_ready=False,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "controlled_use"
    badge_types = {b.type for b in result.display_badges}
    assert "controlled_use" in badge_types
    assert "approval_required" in badge_types


# ---------------------------------------------------------------------------
# Rule 8 — fully validated + integrated → available
# ---------------------------------------------------------------------------


def test_fully_validated_pack_returns_available():
    state = AgentStateInput(
        maturity="production",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=True,
        quality_validated=True,
        persistence_ready=True,
        integration_ready=True,
    )
    result = derive_agent_display_status(state)
    assert result.display_status == "available"
    assert any(b.type == "available" for b in result.display_badges)


# ---------------------------------------------------------------------------
# PDF §B3 — max 2 badges per card
# ---------------------------------------------------------------------------


def test_badge_count_never_exceeds_two():
    """PDF §B3: 每张卡片最多显示两个主要 Badge."""
    # CDI preview would otherwise get 3 badges (preview + approval_required +
    # extra); ensure we cap at 2.
    state = AgentStateInput(
        maturity="mvp",
        runnable=True,
        has_backend_provider=True,
        runtime_mode="real",
        production_ready=False,
        quality_validated=False,
        category="cdi",
    )
    result = derive_agent_display_status(state)
    assert len(result.display_badges) <= 2


# ---------------------------------------------------------------------------
# Internal fields preservation
# ---------------------------------------------------------------------------


def test_internal_fields_preserved_for_engineering_views():
    """PDF §B2: 内部治理字段不能删除 — 只是不在用户卡片渲染."""
    state = AgentStateInput(
        maturity="mvp",
        production_ready=False,
        quality_validated=False,
        runtime_mode="real",
        persistence_ready=False,
        integration_ready=False,
        human_review_policy="required",
        availability="preview",
        deprecated=False,
        hidden_from_hub=False,
        runnable=True,
        has_backend_provider=True,
        agent_type="certified",
        category="cdi",
    )
    result = derive_agent_display_status(state)
    internal = result.internal
    assert internal["maturity"] == "mvp"
    assert internal["production_ready"] is False
    assert internal["runtime_mode"] == "real"
    assert internal["persistence_ready"] is False
    assert internal["runnable"] is True


# ---------------------------------------------------------------------------
# project_pack_to_display_status convenience wrapper
# ---------------------------------------------------------------------------


def test_project_pack_stub_returns_coming_soon():
    pack = {
        "agent_ref": "icoder/code-reconciler@1.0.0",
        "agent_type": "expert-stub",
        "manifest": {"maturity": "stub", "name": "Code Reconciler"},
    }
    result = project_pack_to_display_status(pack)
    assert result.display_status == "coming_soon"


def test_project_pack_deprecated_returns_deprecated():
    pack = {
        "agent_ref": "icoder/cdi-review@1.0.0",
        "deprecated": True,
        "manifest": {"maturity": "deprecated", "name": "CDI Review (legacy)"},
    }
    result = project_pack_to_display_status(pack)
    assert result.display_status == "deprecated"


def test_project_pack_cdi_mvp_returns_preview_with_approval_badge():
    pack = {
        "agent_ref": "icoder/clinical-documentation-improvement-agent@1.0.0",
        "agent_type": "certified",
        "manifest": {
            "maturity": "mvp",
            "name": "Clinical Documentation Improvement",
            "category": "cdi",
            "production_ready": False,
            "human_review": "required",
        },
        "a2a": {"endpoint": "/a2a/cdi-agent"},
    }
    result = project_pack_to_display_status(pack)
    assert result.display_status == "preview"
    badge_types = {b.type for b in result.display_badges}
    assert "preview" in badge_types
    assert "approval_required" in badge_types


def test_project_pack_medical_coding_mvp_returns_preview():
    pack = {
        "agent_ref": "icoder/medical-coding-agent@2.0.0",
        "agent_type": "certified",
        "manifest": {
            "maturity": "mvp",
            "name": "Medical Coding Agent",
            "category": "medical-coding",
            "production_ready": False,
            "human_review": "required",
        },
        "a2a": {"endpoint": "/a2a/medical-coding-agent"},
    }
    result = project_pack_to_display_status(pack)
    assert result.display_status == "preview"


def test_project_pack_metadata_only_returns_coming_soon():
    pack = {
        "agent_ref": "icoder/drg-analyzer@1.0.0",
        "agent_type": "certified",
        "manifest": {
            "maturity": "metadata-only",
            "name": "DRG Analyzer",
            "category": "drg",
        },
        # No a2a.endpoint, no backend_provider
    }
    result = project_pack_to_display_status(pack)
    assert result.display_status == "coming_soon"


def test_project_pack_with_real_runtime_mode_hint_respects_hint():
    """runtime_mode_hint overrides maturity-based inference."""
    pack = {
        "agent_ref": "icoder/note-completeness@1.0.0",
        "agent_type": "certified",
        "manifest": {"maturity": "mvp", "name": "Note Completeness"},
        "a2a": {"endpoint": "/a2a/note-completeness"},
    }
    # Caller passes real runtime_mode_hint
    result = project_pack_to_display_status(pack, runtime_mode_hint="real")
    # Still preview because production_ready=false default + quality_validated=false
    assert result.display_status == "preview"


def test_label_catalog_has_zh_and_en_for_all_badge_types():
    """Every BadgeType must have a (zh, en) pair in the catalog."""
    from app.services.agent_display_status import _LABELS, BadgeType
    import typing

    literal = typing.get_args(BadgeType)
    for bt in literal:
        assert bt in _LABELS, f"Missing label for badge type: {bt}"
        zh, en = _LABELS[bt]
        assert zh, f"Empty zh label for {bt}"
        assert en, f"Empty en label for {bt}"


def test_usage_boundaries_always_non_empty():
    """Every status must produce at least one usage boundary string."""
    for state in [
        AgentStateInput(maturity="deprecated", deprecated=True),
        AgentStateInput(maturity="stub", agent_type="expert-stub"),
        AgentStateInput(maturity="internal", agent_type="internal_engine"),
        AgentStateInput(maturity="mvp", runnable=False, has_backend_provider=False),
        AgentStateInput(maturity="mvp", runnable=True, has_backend_provider=True, runtime_mode="stub"),
        AgentStateInput(maturity="mvp", runnable=True, has_backend_provider=True, runtime_mode="real",
                        production_ready=False, quality_validated=False, category="cdi"),
        AgentStateInput(maturity="production", runnable=True, has_backend_provider=True, runtime_mode="real",
                        production_ready=True, quality_validated=True, persistence_ready=False),
        AgentStateInput(maturity="production", runnable=True, has_backend_provider=True, runtime_mode="real",
                        production_ready=True, quality_validated=True, persistence_ready=True,
                        integration_ready=False),
        AgentStateInput(maturity="production", runnable=True, has_backend_provider=True, runtime_mode="real",
                        production_ready=True, quality_validated=True, persistence_ready=True,
                        integration_ready=True),
    ]:
        result = derive_agent_display_status(state)
        assert len(result.usage_boundaries) >= 1, (
            f"Status {result.display_status} produced no usage_boundaries"
        )
