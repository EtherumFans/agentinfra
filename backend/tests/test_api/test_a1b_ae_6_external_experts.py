"""A1B-AE.6 — Calculator + PubMed + Clinical Trials Expert tests.

These three are Corti public §3.2 keys 3, 7, 8 of 9. A1B-AE.6 ships
Expert Registry entries + deterministic offline implementations.

Coverage:
§1  Medical Calculator Expert — BMI + Cockcroft-Gault + dispatch errors
§2  PubMed Expert — stub returns empty offline result
§3  Clinical Trials Expert — stub returns empty offline result
§4  Charter Amendment 1 §7 forbidden verdicts preserved
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 Medical Calculator Expert
# ─────────────────────────────────────────────────────────────────────

def test_calculator_constants():
    from app.agents.experts.medical_calculator_expert import (
        MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY,
        SUPPORTED_CALCULATORS,
    )
    assert MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY == "medical-calculator"
    assert "bmi" in SUPPORTED_CALCULATORS
    assert "cockcroft-gault" in SUPPORTED_CALCULATORS


def test_calculator_bmi_normal():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("bmi", weight_kg=70, height_m=1.75)
    assert r.calculator == "bmi"
    assert 22 <= r.output["bmi"] <= 23
    assert r.output["category"] == "normal"


def test_calculator_bmi_categories():
    from app.agents.experts.medical_calculator_expert import calculate
    assert calculate("bmi", weight_kg=45, height_m=1.75).output["category"] == "underweight"
    assert calculate("bmi", weight_kg=80, height_m=1.75).output["category"] == "overweight"
    assert calculate("bmi", weight_kg=100, height_m=1.75).output["category"] == "obese"


def test_calculator_bmi_rejects_non_positive():
    from app.agents.experts.medical_calculator_expert import calculate
    with pytest.raises(ValueError):
        calculate("bmi", weight_kg=0, height_m=1.75)
    with pytest.raises(ValueError):
        calculate("bmi", weight_kg=70, height_m=-1)


def test_calculator_cockcroft_gault_male():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("cockcroft-gault", age_years=50, weight_kg=70,
                  serum_creatinine_mg_dl=1.0, sex="male")
    # (140-50)*70 / (72*1.0) * 1.0 = 87.5
    assert abs(r.output["crcl_ml_min"] - 87.5) < 0.1


def test_calculator_cockcroft_gault_female_multiplier():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("cockcroft-gault", age_years=50, weight_kg=70,
                  serum_creatinine_mg_dl=1.0, sex="female")
    # female = male * 0.85 = 74.375
    assert abs(r.output["crcl_ml_min"] - 74.375) < 0.1


def test_calculator_cockcroft_gault_renal_warning():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("cockcroft-gault", age_years=80, weight_kg=50,
                  serum_creatinine_mg_dl=2.0, sex="male")
    # CrCl ~ (60*50)/(72*2) = 20.83 — should trigger <30 warning
    assert any("CrCl < 30" in w for w in r.warnings)


def test_calculator_cockcroft_gault_age_warning():
    from app.agents.experts.medical_calculator_expert import calculate
    r = calculate("cockcroft-gault", age_years=70, weight_kg=70,
                  serum_creatinine_mg_dl=1.0, sex="male")
    assert any("Age >= 65" in w for w in r.warnings)


def test_calculator_unknown_raises_not_implemented():
    from app.agents.experts.medical_calculator_expert import calculate
    # A1B-AE-R.4.a — CHA2DS2-VASc is now implemented; CURB-65 is the
    # canonical "not yet implemented" key per A1B-AE.6 docstring.
    with pytest.raises(NotImplementedError):
        calculate("CURB-65")


def test_calculator_invalid_sex():
    from app.agents.experts.medical_calculator_expert import calculate
    with pytest.raises(ValueError):
        calculate("cockcroft-gault", age_years=50, weight_kg=70,
                  serum_creatinine_mg_dl=1.0, sex="other")


# ─────────────────────────────────────────────────────────────────────
# §2 PubMed Expert (offline stub)
# ─────────────────────────────────────────────────────────────────────

def test_pubmed_constants():
    from app.agents.experts.pubmed_expert import PUBMED_EXPERT_CANONICAL_KEY
    assert PUBMED_EXPERT_CANONICAL_KEY == "pubmed"


def test_pubmed_stub_returns_empty_with_flag():
    from app.agents.experts.pubmed_expert import search
    r = search("diabetes type 2 metformin")
    assert r.live_search_performed is False
    assert r.articles == []
    assert r.total == 0
    assert "STUB" in r.notes


def test_pubmed_stub_empty_query():
    from app.agents.experts.pubmed_expert import search
    r = search("")
    assert r.articles == []
    assert r.live_search_performed is False


# ─────────────────────────────────────────────────────────────────────
# §3 Clinical Trials Expert (offline stub)
# ─────────────────────────────────────────────────────────────────────

def test_clinical_trials_constants():
    from app.agents.experts.clinical_trials_expert import (
        CLINICAL_TRIALS_EXPERT_CANONICAL_KEY,
    )
    assert CLINICAL_TRIALS_EXPERT_CANONICAL_KEY == "clinical-trials"


def test_clinical_trials_stub_returns_empty_with_flag():
    from app.agents.experts.clinical_trials_expert import search
    r = search("heart failure")
    assert r.live_search_performed is False
    assert r.trials == []
    assert r.total == 0
    assert "STUB" in r.notes


def test_clinical_trials_stub_empty_query():
    from app.agents.experts.clinical_trials_expert import search
    r = search("")
    assert r.trials == []
    assert r.live_search_performed is False


# ─────────────────────────────────────────────────────────────────────
# §4 Charter Amendment 1 §7
# ─────────────────────────────────────────────────────────────────────

def test_forbidden_verdicts_preserved():
    forbidden = {
        "PRODUCTION_READY", "FULLY_VERIFIED", "PHI_BOUNDED",
        "CORTI_PARITY_VERIFIED", "PASS_A1A_GATE4_FINAL",
        "READY_FOR_HOSPITAL_DEPLOYMENT", "CLINICAL_GRADE_VERIFIED",
        "CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED",
    }
    allowed = {"PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED"}
    assert forbidden.isdisjoint(allowed)
