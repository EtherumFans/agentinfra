"""Unified, PHI-minimizing offline evaluation for all Hub-visible Agents."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from icoder_runtime.backends.output_contract_validation import (
    validate_declared_field_schemas,
    validate_evidence_bindings,
    validate_required_field_types,
)


SUITE_SCHEMA = "icoder.offline-evaluation-suite/v1"
PACKET_SCHEMA = "icoder.offline-evaluation-predictions/v1"
REPORT_SCHEMA = "icoder.offline-evaluation-report/v1"
DEFAULT_PACKS = Path(__file__).resolve().parents[2] / "official_agents"
DEFAULT_SUITE = (
    Path(__file__).resolve().parents[2] / "evaluations" / "agent_hub_26_v1.json"
)
_SECRET = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{16,}|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b|"
    r"api[_-]?key\s*[:=]\s*[^\s\"']+)"
)


class OfflineEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OfflineCase:
    agent_id: str
    case_id: str
    input_text: str
    expected_output: dict[str, Any]
    output_contract: dict[str, Any]
    pack_sha256: str
    input_sha256: str
    expected_output_sha256: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha(value: object) -> str:
    content = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(content).hexdigest()


def _agent_id(pack: dict[str, Any]) -> str:
    return str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]


def _declared_source_documents(
    output: dict[str, Any], contract: dict[str, Any], input_text: str,
) -> list[dict[str, str]]:
    """Map Pack-declared document IDs to the one synthetic example input.

    Some Packs use document-aware evidence bindings even though their compact
    example fixture stores one ``input_text`` instead of a documents array.
    This adapter preserves the declared IDs while binding every span to the
    exact same immutable example string.
    """

    def resolve(base: Any, path: str) -> Any:
        current = base
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    documents: dict[tuple[str, str], dict[str, str]] = {}
    for binding in contract.get("evidence_bindings") or []:
        if not isinstance(binding, dict):
            continue
        collection = resolve(output, str(binding.get("for_each") or ""))
        document_path = binding.get("document_id_path")
        version_path = binding.get("document_version_path")
        if not isinstance(collection, list) or not isinstance(document_path, str):
            continue
        for item in collection:
            document_id = resolve(item, document_path)
            version = resolve(item, version_path) if isinstance(version_path, str) else ""
            if isinstance(document_id, str) and document_id:
                normalized_version = version if isinstance(version, str) else ""
                documents[(document_id, normalized_version)] = {
                    "document_id": document_id,
                    "document_version": normalized_version,
                    "normalization": "none",
                    "text": input_text,
                }
    return list(documents.values())


def load_offline_cases(
    *, packs_dir: Path = DEFAULT_PACKS, suite_path: Path = DEFAULT_SUITE,
) -> tuple[dict[str, Any], list[OfflineCase], str]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if (
        not isinstance(suite, dict)
        or suite.get("schema_version") != SUITE_SCHEMA
        or suite.get("patient_data_included") is not False
        or suite.get("clinical_accuracy_claimed") is not False
    ):
        raise OfflineEvaluationError("OFFLINE_SUITE_INVALID")
    expected_ids = suite.get("expected_agent_ids")
    if (
        not isinstance(expected_ids, list)
        or len(expected_ids) != 26
        or len(set(expected_ids)) != 26
        or expected_ids != sorted(expected_ids)
    ):
        raise OfflineEvaluationError("OFFLINE_SUITE_AGENT_SCOPE_INVALID")
    cases: list[OfflineCase] = []
    discovered: set[str] = set()
    for path in sorted(packs_dir.glob("*/agent_pack.json")):
        raw = path.read_bytes()
        pack = json.loads(raw)
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        agent_id = _agent_id(pack)
        if not agent_id or agent_id in discovered:
            raise OfflineEvaluationError("OFFLINE_PACK_AGENT_ID_INVALID")
        discovered.add(agent_id)
        inputs = pack.get("example_inputs")
        outputs = pack.get("example_outputs")
        contract = pack.get("output_contract")
        if (
            not isinstance(inputs, list) or not inputs or not isinstance(inputs[0], dict)
            or not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], dict)
            or not isinstance(contract, dict)
        ):
            raise OfflineEvaluationError(f"OFFLINE_PACK_EXAMPLE_INVALID:{agent_id}")
        input_text = str(inputs[0].get("input_text") or inputs[0].get("text") or "")
        if not input_text or len(input_text) > 100_000:
            raise OfflineEvaluationError(f"OFFLINE_PACK_INPUT_INVALID:{agent_id}")
        case_id = hashlib.sha256(
            f"{suite['suite_id']}:{agent_id}:0".encode("utf-8")
        ).hexdigest()[:24]
        cases.append(OfflineCase(
            agent_id=agent_id,
            case_id=case_id,
            input_text=input_text,
            expected_output=outputs[0],
            output_contract=contract,
            pack_sha256=hashlib.sha256(raw).hexdigest(),
            input_sha256=hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
            expected_output_sha256=_sha(outputs[0]),
        ))
    if discovered != set(expected_ids) or len(cases) != 26:
        raise OfflineEvaluationError("OFFLINE_VISIBLE_AGENT_SCOPE_DRIFT")
    snapshot = {
        "suite_sha256": hashlib.sha256(suite_path.read_bytes()).hexdigest(),
        "cases": [
            {
                "agent_id": case.agent_id, "case_id": case.case_id,
                "pack_sha256": case.pack_sha256,
                "input_sha256": case.input_sha256,
                "expected_output_sha256": case.expected_output_sha256,
                "contract": case.output_contract.get("schema_ref"),
            }
            for case in cases
        ],
    }
    return suite, cases, _sha(snapshot)


def build_reference_prediction_packet(
    *, packs_dir: Path = DEFAULT_PACKS, suite_path: Path = DEFAULT_SUITE,
) -> dict[str, Any]:
    suite, cases, dataset_sha256 = load_offline_cases(
        packs_dir=packs_dir, suite_path=suite_path,
    )
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA,
        "suite_id": suite["suite_id"],
        "dataset_sha256": dataset_sha256,
        "source": "official_agent_pack_reference_outputs",
        "items": [
            {
                "agent_id": case.agent_id,
                "case_id": case.case_id,
                "output": case.expected_output,
            }
            for case in cases
        ],
    }
    packet["packet_sha256"] = _sha(packet)
    return packet


def evaluate_prediction_packet(
    packet: dict[str, Any], *, packs_dir: Path = DEFAULT_PACKS,
    suite_path: Path = DEFAULT_SUITE,
) -> dict[str, Any]:
    suite, cases, dataset_sha256 = load_offline_cases(
        packs_dir=packs_dir, suite_path=suite_path,
    )
    if not isinstance(packet, dict):
        raise OfflineEvaluationError("OFFLINE_PACKET_INVALID")
    unsigned_packet = dict(packet)
    packet_digest = unsigned_packet.pop("packet_sha256", None)
    if (
        packet.get("schema_version") != PACKET_SCHEMA
        or packet.get("suite_id") != suite["suite_id"]
        or packet.get("dataset_sha256") != dataset_sha256
        or packet_digest != _sha(unsigned_packet)
        or not isinstance(packet.get("items"), list)
        or len(packet["items"]) > 2600
    ):
        raise OfflineEvaluationError("OFFLINE_PACKET_INVALID")
    predictions: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_count = 0
    malformed_count = 0
    for item in packet["items"]:
        if (
            not isinstance(item, dict) or set(item) != {"agent_id", "case_id", "output"}
            or not isinstance(item.get("agent_id"), str)
            or not isinstance(item.get("case_id"), str)
            or not isinstance(item.get("output"), dict)
        ):
            malformed_count += 1
            continue
        key = (item["agent_id"], item["case_id"])
        if key in predictions:
            duplicate_count += 1
        else:
            predictions[key] = item["output"]

    rows: list[dict[str, Any]] = []
    for case in cases:
        output = predictions.get((case.agent_id, case.case_id))
        required = list(case.output_contract.get("required_fields") or [])
        optional = list(case.output_contract.get("optional_fields") or [])
        allowed = set(required + optional)
        present = isinstance(output, dict)
        missing = [field for field in required if not present or field not in output]
        undeclared_count = (
            len(set(output) - allowed) if isinstance(output, dict) else 0
        )
        type_violations = (
            validate_required_field_types(output, case.output_contract)
            if isinstance(output, dict) else []
        )
        schema_violations = (
            validate_declared_field_schemas(output, case.output_contract)
            if isinstance(output, dict) else []
        )
        evidence_violations = (
            validate_evidence_bindings(
                output, case.output_contract, source_text=case.input_text,
                source_documents=_declared_source_documents(
                    output, case.output_contract, case.input_text,
                ),
            )
            if isinstance(output, dict) else []
        )
        secret_findings = bool(
            isinstance(output, dict)
            and _SECRET.search(json.dumps(output, ensure_ascii=False, default=str))
        )
        contract_passed = bool(
            present and not missing and not undeclared_count
            and not type_violations and not schema_violations
        )
        passed = contract_passed and not evidence_violations and not secret_findings
        rows.append({
            "agent_id": case.agent_id,
            "case_id": case.case_id,
            "present": present,
            "passed": passed,
            "contract_passed": contract_passed,
            "evidence_bindings_passed": not evidence_violations,
            "secret_leakage_detected": secret_findings,
            "exact_reference_match": (
                _sha(output) == case.expected_output_sha256
                if isinstance(output, dict) else False
            ),
            "missing_required_count": len(missing),
            "undeclared_field_count": undeclared_count,
            "field_type_violation_count": len(type_violations),
            "field_schema_relation_violation_count": len(schema_violations),
            "evidence_binding_violation_count": len(evidence_violations),
        })
    expected_keys = {(case.agent_id, case.case_id) for case in cases}
    unexpected_count = len(set(predictions) - expected_keys)
    passed_count = sum(1 for row in rows if row["passed"])
    exact_count = sum(1 for row in rows if row["exact_reference_match"])
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "suite_id": suite["suite_id"],
        "dataset_sha256": dataset_sha256,
        "prediction_packet_sha256": packet_digest,
        "passed": (
            passed_count == len(cases) and duplicate_count == 0
            and malformed_count == 0 and unexpected_count == 0
        ),
        "agent_count": len({case.agent_id for case in cases}),
        "case_count": len(cases),
        "passed_case_count": passed_count,
        "failed_case_count": len(cases) - passed_count,
        "exact_reference_match_count": exact_count,
        "contract_pass_rate": round(passed_count / len(cases), 6),
        "exact_reference_match_rate": round(exact_count / len(cases), 6),
        "duplicate_prediction_count": duplicate_count,
        "malformed_prediction_count": malformed_count,
        "unexpected_prediction_count": unexpected_count,
        "agents": rows,
        "aggregate_only": True,
        "case_text_emitted": False,
        "patient_data_used": False,
        "clinical_accuracy_proven": False,
        "limitations": [
            "Reference examples prove evaluator integration and contract conformance, not clinical accuracy.",
            "Independent de-identified clinical gold sets and blinded specialist review remain external gates.",
        ],
    }
    report["report_sha256"] = _sha(report)
    return report


def validate_offline_report(report: dict[str, Any]) -> None:
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256", None)
    if (
        report.get("schema_version") != REPORT_SCHEMA
        or digest != _sha(unsigned)
        or report.get("agent_count") != 26
        or report.get("case_count") != 26
        or report.get("aggregate_only") is not True
        or report.get("case_text_emitted") is not False
        or report.get("patient_data_used") is not False
        or report.get("clinical_accuracy_proven") is not False
    ):
        raise OfflineEvaluationError("OFFLINE_REPORT_INVALID")


__all__ = [
    "DEFAULT_PACKS", "DEFAULT_SUITE", "OfflineCase", "OfflineEvaluationError",
    "build_reference_prediction_packet", "evaluate_prediction_packet",
    "load_offline_cases", "validate_offline_report",
]
