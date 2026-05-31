# Gold Case Importer & Adjudication
import json
import csv
import io
import re
from enum import Enum
from typing import Optional


# ── Adjudication State Machine ───────────────────────────────────────────────

class AdjudicationState(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    DISPUTED = "disputed"
    ADJUDICATED = "adjudicated"
    RESOLVED = "resolved"
    FINAL = "final"


VALID_TRANSITIONS: dict[AdjudicationState, set[AdjudicationState]] = {
    AdjudicationState.PENDING: {AdjudicationState.IN_REVIEW},
    AdjudicationState.IN_REVIEW: {AdjudicationState.APPROVED, AdjudicationState.DISPUTED},
    AdjudicationState.APPROVED: {AdjudicationState.FINAL, AdjudicationState.DISPUTED},
    AdjudicationState.DISPUTED: {AdjudicationState.ADJUDICATED, AdjudicationState.IN_REVIEW},
    AdjudicationState.ADJUDICATED: {AdjudicationState.RESOLVED, AdjudicationState.FINAL},
    AdjudicationState.RESOLVED: {AdjudicationState.FINAL},
    AdjudicationState.FINAL: set(),  # terminal
}


class AdjudicationRecord:
    """Tracks adjudication state for a single gold case."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.state = AdjudicationState.PENDING
        self.reviewers: list[str] = []
        self.reviewer_decisions: dict[str, dict] = {}  # reviewer_id -> {principal_diag: ..., notes: ...}
        self.adjudicator: Optional[str] = None
        self.final_codes: Optional[dict] = None
        self.final_gold_version: Optional[str] = None
        self.history: list[dict] = []

    def transition(self, to_state: AdjudicationState, actor: str = "system", reason: str = "") -> bool:
        if to_state not in VALID_TRANSITIONS.get(self.state, set()):
            return False
        self.state = to_state
        self.history.append({"from": self.state.value, "to": to_state.value, "actor": actor, "reason": reason})
        return True

    def add_review(self, reviewer_id: str, decision: dict) -> None:
        self.reviewers.append(reviewer_id)
        self.reviewer_decisions[reviewer_id] = decision

    def check_agreement(self) -> bool:
        """True if all reviewers agree on principal diagnosis."""
        if len(self.reviewer_decisions) < 2:
            return False
        codes = {d.get("expected_principal_diagnosis", "") for d in self.reviewer_decisions.values()}
        return len(codes) == 1

    def promote_to_final(self, version: str) -> bool:
        if self.state not in (AdjudicationState.APPROVED, AdjudicationState.ADJUDICATED, AdjudicationState.RESOLVED):
            return False
        if not self.final_codes:
            return False
        ok = self.transition(AdjudicationState.FINAL, actor="system", reason=f"Promoted to final gold v{version}")
        if ok:
            self.final_gold_version = version
        return ok


# ── Importer ─────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = ["expected_principal_diagnosis"]
OPTIONAL_FIELDS = [
    "encounter_id", "department", "specialty", "difficulty", "diagnosis_group",
    "expected_principal_diag_name", "expected_principal_procedure", "expected_principal_proc_name",
    "expected_secondary_diagnoses", "expected_procedure_codes", "expected_drg_group",
    "acceptable_alternatives", "reasoning_expectations", "evidence_spans",
    "discharge_diagnoses", "admission_reason", "risk_tags",
]
ICD10_RE = re.compile(r"^[A-Z]\d{2}(\.(\d+[xX]?\d*|[xX]\d+))?$")
ICD9_RE = re.compile(r"^\d{2}\.(\d+[xX]?\d*|[xX]\d+)$")


def _parse_icd10_code(code: str) -> Optional[str]:
    code = code.strip().strip('"').strip("'")
    if not code:
        return None
    if ICD10_RE.match(code):
        return code
    return None


def _parse_list_field(val) -> list:
    """Parse a field that might be a JSON string or semicolon-delimited string."""
    if val is None or val == "":
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("["):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                pass
        # Semicolon or comma separated
        parts = re.split(r"[;；,，]", val)
        return [p.strip().strip('"').strip("'") for p in parts if p.strip()]
    return []


def validate_row(row: dict, row_index: int) -> dict:
    """Validate a single row. Returns {row_index, encounter_id, status, errors, warnings}."""
    errors = []
    warnings = []
    eid = row.get("encounter_id", f"ROW-{row_index}")

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in row or not str(row[field]).strip():
            errors.append(f"Missing required field: {field}")

    pd = str(row.get("expected_principal_diagnosis", "")).strip()
    if pd and not _parse_icd10_code(pd):
        warnings.append(f"expected_principal_diagnosis '{pd}' invalid ICD-10 format")

    pp = str(row.get("expected_principal_procedure", "")).strip()
    if pp and pp.lower() not in ("", "none", "null"):
        if not ICD9_RE.match(pp):
            warnings.append(f"expected_principal_procedure '{pp}' invalid ICD-9-CM-3 format")

    # Secondary diagnoses
    sd_raw = row.get("expected_secondary_diagnoses", [])
    sd_list = _parse_list_field(sd_raw) if not isinstance(sd_raw, list) else sd_raw
    for i, code in enumerate(sd_list):
        code = str(code).strip().strip('"').strip("'")
        if code and not _parse_icd10_code(code):
            warnings.append(f"expected_secondary_diagnoses[{i}] '{code}' invalid ICD-10 format")

    # Procedure codes
    pc_raw = row.get("expected_procedure_codes", [])
    pc_list = _parse_list_field(pc_raw) if not isinstance(pc_raw, list) else pc_raw
    for i, code in enumerate(pc_list):
        code = str(code).strip().strip('"').strip("'")
        if code and not ICD9_RE.match(code):
            warnings.append(f"expected_procedure_codes[{i}] '{code}' invalid ICD-9-CM-3 format")

    # Difficulty
    diff = str(row.get("difficulty", "medium")).strip().lower()
    if diff not in ("easy", "medium", "hard"):
        warnings.append(f"difficulty '{diff}' not in [easy, medium, hard]")

    # Determine status
    if errors:
        status = "error"
    elif warnings:
        status = "warning"
    else:
        status = "ok"

    return {
        "row_index": row_index,
        "encounter_id": eid,
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


def normalize_row(row: dict) -> dict:
    """Normalize a row to Python types suitable for GoldCaseCreate."""
    return {
        "encounter_id": str(row.get("encounter_id", "")).strip(),
        "department": str(row.get("department", "")).strip(),
        "diagnosis_group": str(row.get("diagnosis_group", "")).strip(),
        "specialty": str(row.get("specialty", "")).strip(),
        "difficulty": str(row.get("difficulty", "medium")).strip(),
        "risk_tags": _parse_list_field(row.get("risk_tags", [])),
        "admission_reason": str(row.get("admission_reason", "")).strip(),
        "expected_principal_diagnosis": str(row.get("expected_principal_diagnosis", "")).strip(),
        "expected_principal_diag_name": str(row.get("expected_principal_diag_name", "")).strip(),
        "expected_principal_procedure": str(row.get("expected_principal_procedure", "")).strip() or None,
        "expected_principal_proc_name": str(row.get("expected_principal_proc_name", "")).strip(),
        "expected_secondary_diagnoses": _parse_list_field(row.get("expected_secondary_diagnoses", [])),
        "expected_procedure_codes": _parse_list_field(row.get("expected_procedure_codes", [])),
        "expected_drg_group": str(row.get("expected_drg_group", "")).strip() or None,
        "acceptable_alternatives": _parse_list_field(row.get("acceptable_alternatives", [])),
        "reasoning_expectations": _parse_list_field(row.get("reasoning_expectations", [])),
        "evidence_spans": row.get("evidence_spans", []),
    }


def import_gold_cases_from_data(
    rows: list[dict],
    mode: str = "import",
    upsert: bool = False,
    existing_ids: set[str] | None = None,
) -> dict:
    """Import gold cases from a list of row dicts.

    Args:
        rows: list of dicts, each representing one gold case
        mode: "dry_run" | "validation_only" | "import"
        upsert: if True, update existing; if False, skip existing
        existing_ids: set of already-imported encounter_ids

    Returns import summary dict.
    """
    existing = existing_ids or set()
    row_results = []
    imported = 0
    skipped = 0
    error_count = 0
    warning_count = 0
    adjudication_needed = []

    for i, row in enumerate(rows):
        # Validate
        validation = validate_row(row, i)
        row_results.append(validation)

        if validation["status"] == "error":
            error_count += 1
            if mode != "validation_only":
                continue

        if validation["status"] == "warning":
            warning_count += 1

        if mode in ("dry_run", "validation_only"):
            continue

        # Import
        eid = validation["encounter_id"]
        if eid in existing and not upsert:
            validation["status"] = "skipped"
            skipped += 1
            continue

        normalized = normalize_row(row)
        # Check if reviewers disagree (adjudication trigger)
        reviewer = row.get("reviewer", "")
        reviewer2 = row.get("reviewer2", "")
        if reviewer and reviewer2:
            pd1 = str(row.get("expected_principal_diagnosis", "")).strip()
            pd2 = str(row.get("reviewer2_principal_diagnosis", "")).strip()
            if pd1 and pd2 and pd1 != pd2:
                adjudication_needed.append({
                    "encounter_id": eid,
                    "reviewer1": reviewer,
                    "reviewer1_code": pd1,
                    "reviewer2": reviewer2,
                    "reviewer2_code": pd2,
                })

        imported += 1

    total = len(rows)
    return {
        "total_rows": total,
        "imported": imported if mode == "import" else 0,
        "skipped": skipped,
        "errors": error_count,
        "warnings": warning_count,
        "row_results": row_results,
        "adjudication_needed": adjudication_needed,
        "mode": mode,
    }


def import_gold_cases_from_file(
    file_path: str,
    file_format: str = "json",
    mode: str = "import",
    upsert: bool = False,
    existing_ids: set[str] | None = None,
) -> dict:
    """Import gold cases from a file (JSON or CSV).

    Args:
        file_path: path to the input file
        file_format: "json" or "csv"
        mode: "dry_run" | "validation_only" | "import"
        upsert: whether to update existing records
        existing_ids: set of already-imported encounter_ids

    Returns import summary dict.
    """
    if file_format == "json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("cases", data.get("gold_cases", []))
    elif file_format == "csv":
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    else:
        raise ValueError(f"Unsupported format: {file_format}. Use 'json' or 'csv'.")

    return import_gold_cases_from_data(rows, mode=mode, upsert=upsert, existing_ids=existing_ids)


def import_gold_cases_from_string(
    content: str,
    file_format: str = "json",
    mode: str = "import",
    upsert: bool = False,
    existing_ids: set[str] | None = None,
) -> dict:
    """Import gold cases from a string (JSON or CSV)."""
    if file_format == "json":
        data = json.loads(content)
        rows = data if isinstance(data, list) else data.get("cases", data.get("gold_cases", []))
    elif file_format == "csv":
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
    else:
        raise ValueError(f"Unsupported format: {file_format}. Use 'json' or 'csv'.")
    return import_gold_cases_from_data(rows, mode=mode, upsert=upsert, existing_ids=existing_ids)
