"""Phase D3 (2026-06-26) — homepage_coding_review shim is GONE.

Locks down the deletion of the deprecated
``official_agents.homepage_coding_review`` module + the
``official_agents.homepage-coding-review`` package. Future
attempts to resurrect them should fail this test.
"""

from __future__ import annotations

import importlib
import sys
import pytest


def test_homepage_coding_review_module_gone():
    """The shim module ``official_agents.homepage_coding_review`` must not exist."""
    # Drop any cached import from earlier in the test session
    for cached in [k for k in list(sys.modules) if "homepage_coding_review" in k]:
        sys.modules.pop(cached, None)
    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module("official_agents.homepage_coding_review")


def test_homepage_coding_review_package_gone():
    """The hyphen-named package ``official_agents.homepage-coding-review`` must not exist."""
    for cached in [k for k in list(sys.modules) if "homepage-coding-review" in k]:
        sys.modules.pop(cached, None)
    with pytest.raises((ImportError, ModuleNotFoundError)):
        importlib.import_module("official_agents.homepage-coding-review")


def test_a2a_agent_card_module_no_longer_exports_homepage_factory():
    """``app.icoder.agent_runtime.a2a.agent_card`` must not re-export
    ``homepage_coding_review_card``."""
    from app.icoder.agent_runtime.a2a.agent_card import __all__ as card_all
    assert "homepage_coding_review_card" not in card_all, (
        f"homepage_coding_review_card leaked into agent_card.__all__: {card_all}"
    )
    # Also check the a2a package level re-export
    from app.icoder.agent_runtime.a2a import __all__ as a2a_all
    assert "homepage_coding_review_card" not in a2a_all, (
        f"homepage_coding_review_card leaked into a2a.__all__: {a2a_all}"
    )


def test_main_orchestrator_stub_uses_medcoder_agent_id():
    """The Phase 1 Orchestrator stub in app.main must register the
    MedCodER agent id, not the legacy homepage id."""
    import inspect
    import app.main
    src = inspect.getsource(app.main)
    assert "id=\"medcoder-coding-review\"" in src, (
        "app.main Orchestrator stub still uses the legacy homepage id"
    )
    # Also verify the legacy id is gone from the orchestrator stub
    # (some other parts of the file may still reference it for comments
    #  only — assert the operative AgentDefinition call uses medcoder).
    assert "id=\"homepage-coding-review\"" not in src, (
        "app.main Orchestrator stub still constructs an AgentDefinition "
        "with the legacy id='homepage-coding-review'"
    )


def test_canonical_constants_importable_from_singleton():
    """The 7 canonical constants must be importable from the SSOT module."""
    from icoder_runtime.constants.coding_review_constants import (
        AGENT_REF,
        AGENT_CATEGORY,
        PIPELINE_STAGES,
        PRIORITY_HIGH_RISK_CODES,
        ALLOWED_HUMAN_DECISIONS,
        ALLOWED_HUMAN_ACTIONS,
        PIPELINE_VALIDATION_DISCLAIMER,
    )
    # The values must be the MedCodER values, not the legacy 14-stage values
    assert AGENT_REF == "icoder/medcoder-coding-review-agent@1.0.0"
    assert len(PIPELINE_STAGES) == 5
    assert len(PRIORITY_HIGH_RISK_CODES) == 5


def test_report_renders_medcoder_subcategory():
    """The HTML report's §1 section must show medcoder-coding-review subcategory,
    not the legacy homepage-coding-review."""
    from icoder_runtime.reports.coding_review_report import render_report
    html = render_report(
        run_id="test-run-001",
        trace_id="test-trace-001",
        input_source="manual",
        prediction_mode="link_validation",
        model_version="test",
        code_dict_version="test",
        rule_version="test",
        primary_diagnosis=None,
        secondary_diagnoses=[],
        procedures=[],
        high_risk_coding_points=[],
        evidence_chain=[],
        human_review_records=[],
        risk_route={"level": "unknown"},
        safety_gate={"rule_count": 0},
        drg_route=None,
        audit_log=[],
        pipeline_stages_observed=[
            "extraction", "retrieval", "merge", "rerank", "calibration",
        ],
    )
    assert "medcoder-coding-review" in html
    assert "homepage-coding-review" not in html
    assert "official_reference_agent" not in html
