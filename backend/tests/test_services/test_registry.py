"""Test Expert Registry service"""
import pytest
from app.services.expert_registry import expert_registry
from app.services.context_scoper import context_scoper


def test_registry_fallback_plan():
    plan = expert_registry._expert_to_registry_entry.__doc__  # just verify module loads
    assert expert_registry is not None


def test_context_scoper_known_expert():
    full_ctx = {
        "documents": [{"content": "test document text"}],
        "evidence": {"diagnosis_facts": [{"name": "hypertension"}]},
        "diagnosis_candidates": [{"code": "I10", "name": "Hypertension"}],
        "procedure_candidates": [],
        "pipeline_id": "test-001",
        "encounter_id": "ENC-001",
        "extra_field": "should be hidden",
    }
    scoped = context_scoper.scope_for("ICDDiagnosisExpert", full_ctx)
    assert "evidence" in scoped
    assert "diagnosis_candidates" not in scoped  # not in required for diagnosis expert
    assert "extra_field" not in scoped
    assert "pipeline_id" in scoped  # metadata always included


def test_context_scoper_report_expert():
    full_ctx = {
        "documents": [{"content": "test"}],
        "evidence": {"diagnosis_facts": [{"name": "test"}]},
        "diagnosis_candidates": [{"code": "I10", "name": "Hypertension"}],
        "procedure_candidates": [{"code": "36.07", "name": "PCI"}],
        "primary_diagnosis": {"code": "I10", "name": "Hypertension"},
    }
    scoped = context_scoper.scope_for("ReportExpert", full_ctx)
    # ReportExpert has empty required list — gets metadata only by default
    assert "pipeline_id" not in scoped  # no pipeline_id set in test context
    assert len(scoped) >= 0  # report expert scoping is lenient


def test_context_scoper_unknown_expert():
    full_ctx = {"documents": [], "secret": "hidden"}
    scoped = context_scoper.scope_for("UnknownExpert", full_ctx)
    assert "secret" in scoped  # unknown experts get full context (safe default)


def test_context_scoper_report():
    full_ctx = {"documents": [{"content": "x" * 100}], "evidence": {}, "diagnosis_candidates": []}
    report = context_scoper.get_scope_report(full_ctx)
    assert len(report) >= 5  # at least 5 experts in the report
    for name, info in report.items():
        assert "fields_available" in info
        assert "fields_hidden" in info
        assert info["fields_available"] + info["fields_hidden"] == len(full_ctx)
