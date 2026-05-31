# Gold Case Template — unit tests
import pytest
from app.services.gold_case_template import (
    generate_gold_case_template, validate_gold_case, import_gold_case,
    _validate_icd10, _validate_icd9,
)


class TestTemplateGeneration:
    def test_json_template_has_sections(self):
        t = generate_gold_case_template()
        for key in ("_instructions", "case_metadata", "original_codes", "gold_codes",
                     "acceptable_alternatives", "reasoning_expectations"):
            assert key in t

    def test_json_with_department(self):
        t = generate_gold_case_template(department="肿瘤内科")
        assert t["case_metadata"]["department"] == "肿瘤内科"

    def test_markdown_template(self):
        md = generate_gold_case_template(department="骨科", output_format="markdown")
        assert isinstance(md, str)
        assert "Gold Case Template" in md
        assert "骨科" in md

    def test_template_contains_placeholder_hints(self):
        t = generate_gold_case_template()
        assert t["case_metadata"]["department"].startswith("<")
        assert t["gold_codes"]["expected_principal_diagnosis"].startswith("<")


class TestICDValidation:
    def test_valid_icd10(self):
        assert _validate_icd10("Z51.102") is True
        assert _validate_icd10("C20.x00") is True
        assert _validate_icd10("M80.900") is True
        assert _validate_icd10("E11.900") is True

    def test_invalid_icd10(self):
        assert _validate_icd10("") is False
        assert _validate_icd10("abc") is False
        assert _validate_icd10("12345") is False

    def test_valid_icd9(self):
        assert _validate_icd9("99.2503") is True
        assert _validate_icd9("81.6600x001") is True

    def test_invalid_icd9(self):
        assert _validate_icd9("") is False
        assert _validate_icd9("abc") is False


class TestGoldCaseValidation:
    def test_valid_case_passes(self):
        data = {
            "case_metadata": {"department": "肿瘤内科"},
            "gold_codes": {"expected_principal_diagnosis": "Z51.102"},
        }
        r = validate_gold_case(data)
        assert r["valid"] is True
        assert len(r["errors"]) == 0

    def test_missing_department(self):
        data = {
            "case_metadata": {},
            "gold_codes": {"expected_principal_diagnosis": "Z51.102"},
        }
        r = validate_gold_case(data)
        assert r["valid"] is False

    def test_missing_principal_diagnosis(self):
        data = {
            "case_metadata": {"department": "骨科"},
            "gold_codes": {},
        }
        r = validate_gold_case(data)
        assert r["valid"] is False

    def test_warning_for_nonstandard_icd(self):
        data = {
            "case_metadata": {"department": "骨科"},
            "gold_codes": {"expected_principal_diagnosis": "123"},
        }
        r = validate_gold_case(data)
        assert len(r["warnings"]) >= 1

    def test_warning_for_invalid_procedure(self):
        data = {
            "case_metadata": {"department": "骨科"},
            "gold_codes": {
                "expected_principal_diagnosis": "M80.900",
                "expected_principal_procedure": "abcde",
            },
        }
        r = validate_gold_case(data)
        assert len(r["warnings"]) >= 1

    def test_warning_for_invalid_difficulty(self):
        data = {
            "case_metadata": {"department": "骨科", "difficulty": "impossible"},
            "gold_codes": {"expected_principal_diagnosis": "M80.900"},
        }
        r = validate_gold_case(data)
        assert any("difficulty" in w.lower() for w in r["warnings"])

    def test_warning_for_duplicate_codes(self):
        data = {
            "case_metadata": {"department": "骨科"},
            "gold_codes": {
                "expected_principal_diagnosis": "M80.900",
                "expected_secondary_diagnoses": ["M80.900"],
            },
        }
        r = validate_gold_case(data)
        assert any("duplicate" in w.lower() or "Duplicate" in w for w in r["warnings"])

    def test_full_valid_case(self):
        data = {
            "case_metadata": {
                "department": "肿瘤内科",
                "diagnosis_group": "化疗",
                "difficulty": "medium",
                "specialty": "肿瘤内科",
                "admission_reason": "术后化疗",
            },
            "original_codes": {
                "original_primary_diagnosis": "Z51.102",
            },
            "gold_codes": {
                "expected_principal_diagnosis": "Z51.102",
                "expected_principal_diag_name": "恶性肿瘤化学治疗",
                "expected_principal_procedure": "99.2503",
                "expected_secondary_diagnoses": ["C20.x00"],
                "expected_procedure_codes": ["99.2503"],
            },
            "acceptable_alternatives": ["Z51.101"],
            "reasoning_expectations": ["should cite R013"],
        }
        r = validate_gold_case(data)
        assert r["valid"] is True


class TestGoldCaseImport:
    def test_valid_import(self):
        data = {
            "case_metadata": {"department": "肿瘤内科"},
            "gold_codes": {"expected_principal_diagnosis": "Z51.102"},
        }
        result = import_gold_case(data)
        assert result is not None
        assert result["expected_principal_diagnosis"] == "Z51.102"

    def test_invalid_import_returns_none(self):
        data = {
            "case_metadata": {},
            "gold_codes": {},
        }
        result = import_gold_case(data)
        assert result is None
