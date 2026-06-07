"""Tests for MedCodERRetrievalRuleSet."""
from __future__ import annotations

import os
import sys

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from compliance_services.medcoder_retrieval_rules import MedCodERRetrievalRuleSet  # noqa: E402


@pytest.fixture
def rs():
    return MedCodERRetrievalRuleSet()


def _dx(disease, retrieved):
    return {"disease_text": disease, "retrieved_codes": retrieved}


def _cand(code, score=0.7, chapter="循环系统疾病"):
    return {"code": code, "name": f"测试{code}", "score": score, "chapter": chapter, "source": "retrieve"}


# ── Mode gating ──


class TestModeGating:
    def test_non_medcoder_mode_is_noop(self, rs):
        # Even with bad output, non-medcoder mode should not flag
        out = {"mode": "hybrid", "extracted_diagnoses": [
            _dx("X", [_cand("ZZZ.999", score=0.1, chapter="")]),
        ]}
        result = rs.validate(out, {})
        assert result.passed
        assert result.issues == []
        assert result.rules_fired == []


# ── MR-001: catalog membership ──


class TestMR001:
    def test_all_known_codes_passes(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900"), _cand("I50.100", score=0.6)]),
        ]}
        ctx = {"catalog_has": lambda c: c.startswith("I50")}
        result = rs.validate(out, ctx)
        assert "MR-001" not in result.rules_fired
        assert result.passed

    def test_unknown_code_fails(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900"), _cand("ZZZ.999")]),
        ]}
        ctx = {"catalog_has": lambda c: c.startswith("I50")}
        result = rs.validate(out, ctx)
        assert "MR-001" in result.rules_fired
        assert not result.passed
        # Issue names the offending code
        assert any("ZZZ.999" in i.message for i in result.issues)

    def test_without_catalog_has_skips_check(self, rs):
        """If context has no catalog_has fn, MR-001 cannot fire."""
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("ZZZ.999")]),
        ]}
        result = rs.validate(out, {})  # no catalog_has
        assert "MR-001" not in result.rules_fired


# ── MR-002: high-similarity threshold ──


class TestMR002:
    def test_high_similarity_passes(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", score=0.85), _cand("I50.100", score=0.6)]),
        ]}
        result = rs.validate(out, {})
        assert "MR-002" not in result.rules_fired
        assert not result.manual_review_required

    def test_low_similarity_triggers_manual_review(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", score=0.4), _cand("I50.100", score=0.3)]),
        ]}
        result = rs.validate(out, {})
        assert "MR-002" in result.rules_fired
        assert result.manual_review_required is True

    def test_empty_retrieved_does_not_trigger(self, rs):
        # MR-002 only fires if retrieved list is non-empty
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", []),
        ]}
        result = rs.validate(out, {})
        assert "MR-002" not in result.rules_fired


# ── MR-003: top-1 chapter metadata ──


class TestMR003:
    def test_non_empty_chapter_passes(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", chapter="循环系统疾病")]),
        ]}
        result = rs.validate(out, {})
        assert "MR-003" not in result.rules_fired

    def test_empty_chapter_fires(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", chapter="")]),
        ]}
        result = rs.validate(out, {})
        assert "MR-003" in result.rules_fired

    def test_empty_chapter_whitespace_fires(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", chapter="   ")]),
        ]}
        result = rs.validate(out, {})
        assert "MR-003" in result.rules_fired


# ── Multiple diagnoses ──


class TestMultipleDiagnoses:
    def test_independent_validation(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": [
            _dx("心衰", [_cand("I50.900", score=0.85, chapter="循环")]),  # good
            _dx("Ghost", [_cand("ZZZ.999", score=0.3, chapter="")]),  # bad
        ]}
        result = rs.validate(out, {"catalog_has": lambda c: c.startswith("I50")})
        assert "MR-001" in result.rules_fired
        assert "MR-002" in result.rules_fired
        assert "MR-003" in result.rules_fired
        assert not result.passed

    def test_empty_extractions_fails(self, rs):
        out = {"mode": "medcoder", "extracted_diagnoses": []}
        result = rs.validate(out, {})
        assert not result.passed
        assert any("MR-000" in i.rule_id for i in result.issues)


# ── Registration helper ──


class TestRegistration:
    def test_register_with_engine(self):
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.medcoder_retrieval_rules import register_with
        engine = RuleEngine()
        assert "medcoder_retrieval" not in engine.available_rule_sets
        register_with(engine)
        assert "medcoder_retrieval" in engine.available_rule_sets
        assert "medcoder_retrieval" in engine.SUPPORTED_RULE_SETS
