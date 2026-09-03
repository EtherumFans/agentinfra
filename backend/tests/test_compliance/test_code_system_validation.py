"""Unit tests for code-system validation helpers (Phase 5 Track C Gate 2 §7.2).

Verifies that R002 / R004 split validation works per code-system:
- WHO ICD-10 (international)
- ICD-10-CN 6-digit
- ICD-10 x-placeholder
- ICD-9-CM-3 procedure
- National clinical extension
"""

from __future__ import annotations

import pytest

from compliance_services.medical_coding_rules import (
    classify_code_system,
    normalize_code,
    validate_code_per_system,
    MedicalCodingRuleSet,
)


# ── classify_code_system ────────────────────────────────────────────────


@pytest.mark.parametrize("code,expected", [
    # WHO ICD-10 (international)
    ("A00", "icd10_who"),
    ("I21.9", "icd10_who"),
    ("J15.9", "icd10_who"),
    ("I21.19", "icd10_who"),
    # ICD-10-CN 6-digit (4 digits after dot)
    ("J15.900", "icd10_cn_6digit"),
    ("I21.100", "icd10_cn_6digit"),
    ("S22.000", "icd10_cn_6digit"),
    ("M80.900", "icd10_cn_6digit"),
    # x-placeholder (incomplete)
    ("I21.x00", "icd10_cn_x"),
    ("M80.x", "icd10_cn_x"),
    # ICD-9-CM-3 procedure
    ("81.0100", "icd9_cm3"),
    ("84.5100", "icd9_cm3"),
    # Unknown / invalid
    ("", "unknown"),
    ("123", "unknown"),
    ("XYZ", "unknown"),
    # Bare 3-char (no dot) is valid WHO category-level code
    ("I21", "icd10_who"),
])
def test_classify_code_system(code, expected):
    assert classify_code_system(code) == expected


# ── normalize_code ──────────────────────────────────────────────────────


@pytest.mark.parametrize("code,expected", [
    ("I21.9", "I21.900"),
    ("I21.19", "I21.190"),
    ("J15.900", "J15.900"),  # already 3-digit decimal
    ("S22.000", "S22.000"),
    ("", ""),
])
def test_normalize_code_to_cn_6digit(code, expected):
    assert normalize_code(code, "icd10_cn_6digit") == expected


# ── validate_code_per_system ────────────────────────────────────────────


def test_validate_who_icd10():
    """WHO ICD-10 is format-valid AND assignable."""
    v = validate_code_per_system("I21.9")
    assert v["code_system"] == "icd10_who"
    assert v["format_valid"] is True
    assert v["assignable"] is True
    assert v["normalized_code"] == "I21.900"


def test_validate_cn_6digit():
    """China 6-digit is the canonical assignable form."""
    v = validate_code_per_system("J15.900")
    assert v["code_system"] == "icd10_cn_6digit"
    assert v["format_valid"] is True
    assert v["assignable"] is True


def test_validate_x_placeholder_assignable_false():
    """x-placeholder is format-valid but NOT assignable (incomplete)."""
    v = validate_code_per_system("I21.x00")
    assert v["code_system"] == "icd10_cn_x"
    assert v["format_valid"] is True
    assert v["assignable"] is False  # ← key gate: cannot be final code


def test_validate_icd9_cm3():
    """ICD-9-CM-3 procedure codes validate cleanly."""
    v = validate_code_per_system("81.0100")
    assert v["code_system"] == "icd9_cm3"
    assert v["format_valid"] is True
    assert v["assignable"] is True


def test_validate_unknown_code():
    """Garbage codes return all-False."""
    v = validate_code_per_system("not-a-code")
    assert v["code_system"] == "unknown"
    assert v["format_valid"] is False
    assert v["assignable"] is False


def test_validate_empty_code():
    v = validate_code_per_system("")
    assert v["code_system"] == "unknown"
    assert v["format_valid"] is False
    assert v["assignable"] is False


# ── Integration: MedicalCodingRuleSet R002 ──────────────────────────────


def test_r002_rejects_unknown_format():
    """Unknown format triggers R002 high-severity issue."""
    ruleset = MedicalCodingRuleSet()
    result = ruleset.validate(
        {
            "primary_diagnosis": {"code": "BADCODE"},
            "secondary_diagnoses": [],
            "procedures": [],
        },
        context={},
    )
    r002_issues = [i for i in result.issues if i.rule_id == "R002"]
    assert len(r002_issues) == 1
    assert r002_issues[0].severity == "high"
    assert "无法识别编码体系" in r002_issues[0].message


def test_r002_flags_x_placeholder_as_incomplete():
    """x-placeholder is format-valid but unassignable → medium-severity issue."""
    ruleset = MedicalCodingRuleSet()
    result = ruleset.validate(
        {
            "primary_diagnosis": {"code": "I21.x00"},
            "secondary_diagnoses": [],
            "procedures": [],
        },
        context={},
    )
    r002_issues = [i for i in result.issues if i.rule_id == "R002"]
    assert len(r002_issues) == 1
    assert r002_issues[0].severity == "medium"
    assert "x占位" in r002_issues[0].message


def test_r002_accepts_cn_6digit_clean():
    """China 6-digit code passes R002 without issue."""
    ruleset = MedicalCodingRuleSet()
    result = ruleset.validate(
        {
            "primary_diagnosis": {
                "code": "S22.000",
                "evidence": "T12 fracture",
                "confidence": 0.95,
            },
            "secondary_diagnoses": [],
            "procedures": [],
        },
        context={},
    )
    r002_issues = [i for i in result.issues if i.rule_id == "R002"]
    assert len(r002_issues) == 0


def test_r004_rejects_icd10_as_procedure():
    """ICD-10 code in procedures[] should fail R004 (wrong system)."""
    ruleset = MedicalCodingRuleSet()
    result = ruleset.validate(
        {
            "primary_diagnosis": {"code": "S22.000", "evidence": "x", "confidence": 0.9},
            "secondary_diagnoses": [],
            "procedures": [{"code": "J15.900"}],  # ICD-10 in procedures[]
        },
        context={},
    )
    r004_issues = [i for i in result.issues if i.rule_id == "R004"]
    assert len(r004_issues) == 1
    assert "体系=icd10_cn_6digit" in r004_issues[0].message
