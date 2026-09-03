"""Audit the authorized CCL 2026 workbook without emitting case-level data.

The source workbook contains de-identified clinical records governed by a data
use commitment.  This tool is deliberately local-only: it proves source/fixture
equivalence, aggregate label coverage, and current catalog coverage while
writing no chart text, encounter identifiers, or case-level labels.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SCHEMA_VERSION = "icoder.ccl2026-local-dataset-audit/v1"
EXPECTED_HEADERS = (
    "病案标识",
    "主诉",
    "现病史",
    "既往史",
    "个人史",
    "婚姻史",
    "家族史",
    "入院情况",
    "入院诊断",
    "诊疗经过",
    "出院情况",
    "出院医嘱",
    "手术经过",
    "术前诊断",
    "术中诊断",
    "主要疾病（诊断）编码",
    "其他疾病（诊断）编码",
    "主要手术编码",
    "其他手术编码",
)
DX_RE = re.compile(r"^[A-Z]\d{2}(?:\.[\dxX]+)?$")
PROCEDURE_RE = re.compile(r"^\d{2}\.\d{2}[xX]?\d*$")
CELL_COLUMN_RE = re.compile(r"^([A-Z]+)")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _column_index(reference: str) -> int:
    match = CELL_COLUMN_RE.match(reference.upper())
    if not match:
        raise ValueError(f"invalid worksheet cell reference: {reference}")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t"))
            for item in root if item.tag.endswith("}si")]


def _sheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = ""
    for node in workbook.iter():
        if node.tag.endswith("}sheet") and node.attrib.get("name") == sheet_name:
            relationship_id = next(
                (value for key, value in node.attrib.items() if key.endswith("}id")),
                "",
            )
            break
    if not relationship_id:
        raise ValueError(f"worksheet is missing: {sheet_name}")
    relationships = ElementTree.fromstring(
        archive.read("xl/_rels/workbook.xml.rels")
    )
    target = next(
        (
            node.attrib.get("Target", "")
            for node in relationships
            if node.attrib.get("Id") == relationship_id
        ),
        "",
    )
    if not target:
        raise ValueError(f"worksheet relationship is missing: {sheet_name}")
    normalized = target.replace("\\", "/").lstrip("/")
    return normalized if normalized.startswith("xl/") else f"xl/{normalized}"


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.iter() if node.tag.endswith("}t")
        )
    value = next(
        (node.text or "" for node in cell if node.tag.endswith("}v")), ""
    )
    if cell_type == "s" and value:
        try:
            return shared[int(value)]
        except (IndexError, ValueError) as exc:
            raise ValueError("worksheet has an invalid shared-string reference") from exc
    return value


def read_sheet_rows(path: Path, *, sheet_name: str = "Sheet1") -> Iterable[list[str]]:
    """Yield worksheet rows through the XLSX package without office automation."""

    try:
        with zipfile.ZipFile(path) as archive:
            shared = _shared_strings(archive)
            target = _sheet_path(archive, sheet_name)
            with archive.open(target) as source:
                for _event, row in ElementTree.iterparse(source, events=("end",)):
                    if not row.tag.endswith("}row"):
                        continue
                    values = [""] * len(EXPECTED_HEADERS)
                    for cell in row:
                        if not cell.tag.endswith("}c"):
                            continue
                        index = _column_index(cell.attrib.get("r", ""))
                        if index < len(values):
                            values[index] = _cell_value(cell, shared).strip()
                    yield values
                    row.clear()
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError(f"cannot read governed workbook: {exc}") from exc


def _parse_codes(raw: str) -> list[str]:
    return [
        token.strip().strip('"').strip("'")
        for token in re.split(r"[;；\s]+", raw or "")
        if token.strip().strip('"').strip("'")
        and token.strip().casefold() not in {"none", "null", "nan"}
    ]


def _text_blob(row: list[str]) -> str:
    indexes = (1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14)
    return "\n".join(row[index].strip() for index in indexes if row[index].strip())


def load_ccl_cases(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows = iter(read_sheet_rows(path))
    try:
        headers = next(rows)
    except StopIteration:
        return [], []
    cases: list[dict[str, Any]] = []
    for row in rows:
        encounter_id = row[0].strip()
        if not encounter_id or encounter_id == headers[0]:
            continue
        primary_diagnoses = _parse_codes(row[15])
        if len(primary_diagnoses) != 1 or not DX_RE.fullmatch(primary_diagnoses[0]):
            continue
        secondary = [code for code in _parse_codes(row[16]) if DX_RE.fullmatch(code)]
        primary_procedures = _parse_codes(row[17])
        primary_procedure = (
            primary_procedures[0]
            if len(primary_procedures) == 1
            and PROCEDURE_RE.fullmatch(primary_procedures[0])
            else None
        )
        other_procedures = [
            code for code in _parse_codes(row[18]) if PROCEDURE_RE.fullmatch(code)
        ]
        cases.append({
            "encounter_id": encounter_id,
            "department": "",
            "diagnosis_group": "",
            "specialty": "",
            "difficulty": "medium",
            "risk_tags": [],
            "admission_reason": row[1].strip(),
            "expected_principal_diagnosis": primary_diagnoses[0],
            "expected_principal_diag_name": "",
            "expected_principal_procedure": primary_procedure,
            "expected_principal_proc_name": "",
            "expected_secondary_diagnoses": secondary,
            "expected_procedure_codes": other_procedures,
            "expected_drg_group": None,
            "acceptable_alternatives": [],
            "reasoning_expectations": [],
            "evidence_spans": [],
            "text": _text_blob(row),
            "source": "CCL2026",
        })
    return cases, headers


def _catalog_sets() -> tuple[set[str], set[str], dict[str, Any]]:
    from data.code_dicts.icd_data import load_catalogs

    diagnoses, procedures, status = load_catalogs()
    return (
        {str(code).strip().upper() for code, _name, _chapter in diagnoses},
        {str(code).strip().upper() for code, _name, _drg in procedures},
        status,
    )


def build_report(
    *,
    workbook_path: Path,
    fixture_path: Path,
    authorized_root: Path,
    authorization_acknowledged: bool,
    expected_case_count: int = 1800,
    diagnosis_catalog: set[str] | None = None,
    procedure_catalog: set[str] | None = None,
    catalog_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    workbook = workbook_path.resolve()
    fixture = fixture_path.resolve()
    root = authorized_root.resolve()
    try:
        workbook.relative_to(root)
    except ValueError:
        errors.append("source workbook escapes the explicitly authorized root")
    if not authorization_acknowledged:
        errors.append("explicit user authorization acknowledgement is absent")
    if not workbook.is_file():
        errors.append("source workbook is missing")
    if not fixture.is_file():
        errors.append("bound repository fixture is missing")

    source_cases: list[dict[str, Any]] = []
    headers: list[str] = []
    fixture_cases: list[dict[str, Any]] = []
    if not errors:
        try:
            source_cases, headers = load_ccl_cases(workbook)
            loaded_fixture = json.loads(fixture.read_text(encoding="utf-8"))
            if not isinstance(loaded_fixture, list):
                raise ValueError("bound repository fixture is not a list")
            fixture_cases = [item for item in loaded_fixture if isinstance(item, dict)]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(str(exc))

    if diagnosis_catalog is None or procedure_catalog is None:
        try:
            diagnosis_catalog, procedure_catalog, loaded_status = _catalog_sets()
            catalog_status = loaded_status
        except Exception as exc:  # fail closed on the governed catalog boundary
            errors.append(f"trusted code catalog is unavailable: {type(exc).__name__}")
            diagnosis_catalog, procedure_catalog = set(), set()
    diagnosis_catalog = {value.upper() for value in diagnosis_catalog}
    procedure_catalog = {value.upper() for value in procedure_catalog}
    catalog_status = dict(catalog_status or {})

    source_digests = [_canonical_sha256(case) for case in source_cases]
    fixture_digests = [_canonical_sha256(case) for case in fixture_cases]
    encounter_counts = Counter(
        str(case.get("encounter_id") or "") for case in source_cases
    )
    diagnosis_assignments = [
        code.upper()
        for case in source_cases
        for code in (
            [str(case.get("expected_principal_diagnosis") or "")]
            + [str(value) for value in case.get("expected_secondary_diagnoses") or []]
        )
        if code
    ]
    procedure_assignments = [
        code.upper()
        for case in source_cases
        for code in (
            [str(case.get("expected_principal_procedure") or "")]
            + [str(value) for value in case.get("expected_procedure_codes") or []]
        )
        if code
    ]
    exact_match = source_digests == fixture_digests
    header_match = tuple(headers) == EXPECTED_HEADERS
    duplicates = sum(count - 1 for count in encounter_counts.values() if count > 1)
    diagnosis_unmatched = sum(
        code not in diagnosis_catalog for code in diagnosis_assignments
    )
    procedure_unmatched = sum(
        code not in procedure_catalog for code in procedure_assignments
    )
    source_only = len(Counter(source_digests) - Counter(fixture_digests))
    fixture_only = len(Counter(fixture_digests) - Counter(source_digests))
    ready = bool(
        not errors
        and authorization_acknowledged
        and header_match
        and len(source_cases) == expected_case_count
        and len(fixture_cases) == expected_case_count
        and exact_match
        and duplicates == 0
        and diagnosis_unmatched == 0
        and procedure_unmatched == 0
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_local_isolated_benchmark" if ready else "blocked",
        "source_workbook": {
            "path": str(workbook),
            "sha256": _sha256_file(workbook) if workbook.is_file() else "",
            "size_bytes": workbook.stat().st_size if workbook.is_file() else 0,
            "sheet_name": "Sheet1",
            "column_count": len(headers),
            "schema_match": header_match,
            "parsed_case_count": len(source_cases),
        },
        "bound_repository_fixture": {
            "path": str(fixture),
            "sha256": _sha256_file(fixture) if fixture.is_file() else "",
            "size_bytes": fixture.stat().st_size if fixture.is_file() else 0,
            "case_count": len(fixture_cases),
        },
        "equivalence": {
            "exact_ordered_canonical_match": exact_match,
            "source_only_case_digest_count": source_only,
            "fixture_only_case_digest_count": fixture_only,
            "duplicate_encounter_identifier_count": duplicates,
        },
        "aggregate_label_coverage": {
            "diagnosis_assignment_count": len(diagnosis_assignments),
            "unique_diagnosis_code_count": len(set(diagnosis_assignments)),
            "diagnosis_catalog_unmatched_assignment_count": diagnosis_unmatched,
            "procedure_assignment_count": len(procedure_assignments),
            "unique_procedure_code_count": len(set(procedure_assignments)),
            "procedure_catalog_unmatched_assignment_count": procedure_unmatched,
        },
        "catalog_snapshot": {
            "schema_version": catalog_status.get("schema_version", ""),
            "catalog_release": catalog_status.get("catalog_release", ""),
            "integrity_verified": catalog_status.get("integrity_verified") is True,
            "diagnosis_count": int(catalog_status.get("diagnosis_count") or 0),
            "procedure_count": int(catalog_status.get("procedure_count") or 0),
        },
        "governance": {
            "user_authorization_acknowledged": authorization_acknowledged,
            "aggregate_only_report": True,
            "raw_clinical_text_emitted": False,
            "encounter_identifiers_emitted": False,
            "case_level_labels_emitted": False,
            "external_provider_egress_allowed": False,
            "source_workbook_copy_allowed": False,
            "redistribution_rights_proven": False,
            "independent_clinical_gold_proven": False,
            "production_accuracy_claim_allowed": False,
            "local_isolated_benchmark_allowed": ready,
        },
        "errors": sorted(set(errors)),
    }
    digest_payload = copy.deepcopy(report)
    report["report_sha256"] = _canonical_sha256(digest_payload)
    return report


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported report schema_version")
    supplied = str(report.get("report_sha256") or "")
    payload = copy.deepcopy(report)
    payload.pop("report_sha256", None)
    if supplied != _canonical_sha256(payload):
        errors.append("canonical report digest mismatch")
    governance = report.get("governance")
    governance = governance if isinstance(governance, dict) else {}
    required_false = {
        "raw_clinical_text_emitted",
        "encounter_identifiers_emitted",
        "case_level_labels_emitted",
        "external_provider_egress_allowed",
        "source_workbook_copy_allowed",
        "redistribution_rights_proven",
        "independent_clinical_gold_proven",
        "production_accuracy_claim_allowed",
    }
    for field in required_false:
        if governance.get(field) is not False:
            errors.append(f"governance boundary must remain false: {field}")
    if governance.get("aggregate_only_report") is not True:
        errors.append("report must remain aggregate-only")
    if report.get("status") == "ready_for_local_isolated_benchmark":
        if report.get("errors"):
            errors.append("ready report contains audit errors")
        if governance.get("local_isolated_benchmark_allowed") is not True:
            errors.append("ready report does not allow the local isolated benchmark")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--authorized-root", type=Path, required=True)
    parser.add_argument("--acknowledge-user-authorization", action="store_true")
    parser.add_argument("--expected-case-count", type=int, default=1800)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assert-ready", action="store_true")
    args = parser.parse_args()
    report = build_report(
        workbook_path=args.workbook,
        fixture_path=args.fixture,
        authorized_root=args.authorized_root,
        authorization_acknowledged=args.acknowledge_user_authorization,
        expected_case_count=args.expected_case_count,
    )
    validation_errors = validate_report(report)
    if validation_errors:
        report["status"] = "invalid"
        report["errors"] = sorted(set(report["errors"] + validation_errors))
        report.pop("report_sha256", None)
        report["report_sha256"] = _canonical_sha256(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "parsed_case_count": report["source_workbook"]["parsed_case_count"],
        "exact_fixture_match": report["equivalence"]["exact_ordered_canonical_match"],
        "diagnosis_catalog_unmatched": report["aggregate_label_coverage"]["diagnosis_catalog_unmatched_assignment_count"],
        "procedure_catalog_unmatched": report["aggregate_label_coverage"]["procedure_catalog_unmatched_assignment_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 1 if validation_errors or (args.assert_ready and report["status"] != "ready_for_local_isolated_benchmark") else 0


if __name__ == "__main__":
    raise SystemExit(main())
