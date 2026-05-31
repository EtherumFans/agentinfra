# Gold Case Importer & Adjudication — tests
import json
import pytest
from app.services.gold_case_importer import (
    import_gold_cases_from_data, import_gold_cases_from_string,
    validate_row, normalize_row, _parse_list_field,
    AdjudicationState, AdjudicationRecord, VALID_TRANSITIONS,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row(**kw):
    r = {"expected_principal_diagnosis": "Z51.102", "encounter_id": "T001", "department": "肿瘤内科",
         "difficulty": "medium"}
    r.update(kw)
    return r


# ── Adjudication State Machine ───────────────────────────────────────────────

class TestAdjudicationStateMachine:
    def test_pending_to_in_review(self):
        rec = AdjudicationRecord("GC-001")
        ok = rec.transition(AdjudicationState.IN_REVIEW)
        assert ok is True
        assert rec.state == AdjudicationState.IN_REVIEW

    def test_illegal_transition(self):
        rec = AdjudicationRecord("GC-002")
        ok = rec.transition(AdjudicationState.FINAL)
        assert ok is False
        assert rec.state == AdjudicationState.PENDING

    def test_full_happy_path(self):
        rec = AdjudicationRecord("GC-003")
        assert rec.transition(AdjudicationState.IN_REVIEW)
        rec.add_review("coder_a", {"expected_principal_diagnosis": "Z51.102"})
        rec.add_review("coder_b", {"expected_principal_diagnosis": "Z51.102"})
        assert rec.check_agreement() is True
        assert rec.transition(AdjudicationState.APPROVED)
        rec.final_codes = {"expected_principal_diagnosis": "Z51.102"}
        assert rec.promote_to_final("1.0") is True
        assert rec.state == AdjudicationState.FINAL

    def test_dispute_path(self):
        rec = AdjudicationRecord("GC-004")
        rec.transition(AdjudicationState.IN_REVIEW)
        rec.add_review("coder_a", {"expected_principal_diagnosis": "Z51.102"})
        rec.add_review("coder_b", {"expected_principal_diagnosis": "C20.x00"})
        assert rec.check_agreement() is False
        rec.transition(AdjudicationState.DISPUTED)
        rec.transition(AdjudicationState.ADJUDICATED)
        rec.final_codes = {"expected_principal_diagnosis": "Z51.102"}
        assert rec.promote_to_final("1.0") is True
        assert rec.final_gold_version == "1.0"

    def test_promote_without_final_codes_fails(self):
        rec = AdjudicationRecord("GC-005")
        rec.transition(AdjudicationState.IN_REVIEW)
        rec.add_review("a", {"expected_principal_diagnosis": "Z51"})
        rec.add_review("b", {"expected_principal_diagnosis": "Z51"})
        rec.transition(AdjudicationState.APPROVED)
        # final_codes not set
        ok = rec.promote_to_final("1.0")
        assert ok is False

    def test_terminal_state_no_transitions(self):
        assert VALID_TRANSITIONS[AdjudicationState.FINAL] == set()


# ── Validation ───────────────────────────────────────────────────────────────

class TestValidateRow:
    def test_valid_row(self):
        r = validate_row({"expected_principal_diagnosis": "Z51.102", "encounter_id": "T"}, 0)
        assert r["status"] == "ok"

    def test_missing_required(self):
        r = validate_row({"encounter_id": "T"}, 0)
        assert r["status"] == "error"

    def test_warning_for_bad_icd(self):
        r = validate_row({"expected_principal_diagnosis": "abc", "encounter_id": "T"}, 0)
        assert r["status"] == "warning"

    def test_warning_for_bad_procedure(self):
        r = validate_row({"expected_principal_diagnosis": "Z51.102", "expected_principal_procedure": "xyz"}, 0)
        assert any("procedure" in w.lower() for w in r["warnings"])

    def test_warning_for_bad_difficulty(self):
        r = validate_row({"expected_principal_diagnosis": "Z51.102", "difficulty": "expert"}, 0)
        assert any("difficulty" in w.lower() for w in r["warnings"])

    def test_secondary_diag_warnings(self):
        r = validate_row({"expected_principal_diagnosis": "Z51.102",
                          "expected_secondary_diagnoses": ["bad_code"]}, 0)
        assert any("secondary" in w.lower() for w in r["warnings"])


class TestParseListField:
    def test_json_string(self):
        assert _parse_list_field('["A", "B"]') == ["A", "B"]

    def test_semicolon_delimited(self):
        assert _parse_list_field("Z51.102; C20.x00") == ["Z51.102", "C20.x00"]

    def test_comma_delimited(self):
        assert _parse_list_field("Z51.102, C20.x00") == ["Z51.102", "C20.x00"]

    def test_already_list(self):
        assert _parse_list_field(["A", "B"]) == ["A", "B"]

    def test_empty(self):
        assert _parse_list_field("") == []

    def test_none(self):
        assert _parse_list_field(None) == []


class TestNormalizeRow:
    def test_basic_normalization(self):
        r = _row()
        n = normalize_row(r)
        assert n["encounter_id"] == "T001"
        assert n["expected_principal_diagnosis"] == "Z51.102"
        assert n["difficulty"] == "medium"

    def test_secondary_codes_parsed(self):
        r = _row(expected_secondary_diagnoses="C20.x00; E11.900")
        n = normalize_row(r)
        assert "C20.x00" in n["expected_secondary_diagnoses"]


# ── Importer ─────────────────────────────────────────────────────────────────

class TestImportGoldCases:
    def test_dry_run_no_imports(self):
        rows = [_row(), _row(encounter_id="T002")]
        result = import_gold_cases_from_data(rows, mode="dry_run")
        assert result["total_rows"] == 2
        assert result["imported"] == 0
        assert len(result["row_results"]) == 2

    def test_import_mode(self):
        rows = [_row(), _row(encounter_id="T002")]
        result = import_gold_cases_from_data(rows, mode="import")
        assert result["imported"] == 2
        assert result["errors"] == 0

    def test_skip_existing(self):
        rows = [_row()]
        result = import_gold_cases_from_data(rows, mode="import", existing_ids={"T001"})
        assert result["skipped"] == 1
        assert result["imported"] == 0

    def test_upsert_existing(self):
        rows = [_row()]
        result = import_gold_cases_from_data(rows, mode="import", upsert=True, existing_ids={"T001"})
        assert result["skipped"] == 0
        assert result["imported"] == 1

    def test_validation_only(self):
        rows = [_row(), {"encounter_id": "BAD"}]  # second row missing required
        result = import_gold_cases_from_data(rows, mode="validation_only")
        assert result["errors"] == 1

    def test_error_rows_counted(self):
        rows = [{"encounter_id": "E1"}, _row()]  # first missing required
        result = import_gold_cases_from_data(rows, mode="import")
        assert result["errors"] >= 1

    def test_adjudication_detected(self):
        rows = [{
            "expected_principal_diagnosis": "Z51.102",
            "encounter_id": "T001",
            "department": "肿瘤内科",
            "reviewer": "coder_a",
            "reviewer2": "coder_b",
            "reviewer2_principal_diagnosis": "C20.x00",
        }]
        result = import_gold_cases_from_data(rows, mode="import")
        assert len(result["adjudication_needed"]) >= 1


class TestImportFromString:
    def test_json_string(self):
        content = json.dumps([_row()])
        result = import_gold_cases_from_string(content, file_format="json", mode="dry_run")
        assert result["total_rows"] == 1

    def test_csv_string(self):
        content = "encounter_id,expected_principal_diagnosis,department\nT001,Z51.102,肿瘤内科\nT002,C20.x00,骨科\n"
        result = import_gold_cases_from_string(content, file_format="csv", mode="dry_run")
        assert result["total_rows"] == 2

    def test_json_object_with_cases_key(self):
        content = json.dumps({"cases": [_row()]})
        result = import_gold_cases_from_string(content, file_format="json", mode="dry_run")
        assert result["total_rows"] == 1

    def test_bad_format_raises(self):
        with pytest.raises(ValueError):
            import_gold_cases_from_string("{}", file_format="xml")
