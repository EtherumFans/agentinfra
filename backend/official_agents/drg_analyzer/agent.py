"""Governed deterministic DRG/DIP risk review for explicitly coded cases.

The Agent never extracts or assigns medical codes.  It accepts only labelled,
coder-supplied ICD-10-CN / ICD-9-CM-3 data with exact source evidence, then
invokes the repository's hash-pinned development risk heuristics.  Candidate
group labels are deliberately non-authoritative and never include weight,
score, payment, settlement, submission, or writeback values.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
from uuid import uuid4


AGENT_REF = "icoder/drg-analyzer@1.1.3"
OUTPUT_CONTRACT_REF = "icoder/DRGDIPRiskReview/v8"
LOCAL_RUNTIME_MODE = "governed_local_explicit_coded_case_risk_review"
REVIEW_METHOD = "EXPLICIT_CODED_CASE_DETERMINISTIC_UNVERIFIED_RISK_REVIEW"
MAX_INPUT_CHARS = 60_000
MAX_ITEMS = 100

_SCALAR_LABELS = {
    "审核目的": "review_purpose",
    "review purpose": "review_purpose",
    "诊断编码标准": "diagnosis_coding_system",
    "diagnosis coding system": "diagnosis_coding_system",
    "诊断编码版本": "diagnosis_coding_version",
    "diagnosis coding version": "diagnosis_coding_version",
    "手术编码标准": "procedure_coding_system",
    "procedure coding system": "procedure_coding_system",
    "手术编码版本": "procedure_coding_version",
    "procedure coding version": "procedure_coding_version",
    "患者性别": "patient_gender",
    "patient gender": "patient_gender",
    "患者年龄": "patient_age",
    "patient age": "patient_age",
    "主诊断编码": "primary_diagnosis",
    "primary diagnosis code": "primary_diagnosis",
}
_SECTION_LABELS = {
    "次诊断编码": "secondary_diagnoses",
    "secondary diagnosis codes": "secondary_diagnoses",
    "手术操作编码": "procedures",
    "procedure codes": "procedures",
}
_UNTRUSTED_PATTERN = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?(?:system|developer)\s+prompt|"
    r"system\s+prompt|developer\s+message|"
    r"忽略.{0,12}(?:指令|提示)|(?:系统|开发者)提示词)",
    re.IGNORECASE,
)
_DIAGNOSIS_CODE = re.compile(r"^[A-Z][0-9][A-Z0-9](?:\.[A-Z0-9]{1,4})?$")
_PROCEDURE_CODE = re.compile(r"^[0-9]{2}(?:\.[0-9A-Z]{1,4})?$")


@dataclass(frozen=True)
class Line:
    text: str
    start: int
    end: int


def verify_drg_dip_risk_review_health() -> dict[str, Any]:
    from app.services.clinical_asset_governance import get_drg_risk_governance
    from app.config import settings

    governance = get_drg_risk_governance(
        deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
    )
    return {
        "agent_ref": AGENT_REF,
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "output_contract": OUTPUT_CONTRACT_REF,
        "review_method": REVIEW_METHOD,
        "network_required": False,
        "llm_required": False,
        "deterministic": True,
        "governance": governance,
    }


def _bounded_text(value: Any) -> tuple[str, bool]:
    text = str(value or "").replace("\x00", "").strip()
    truncated = len(text) > MAX_INPUT_CHARS
    return text[:MAX_INPUT_CHARS], truncated


def _lines(source: str) -> list[Line]:
    rows: list[Line] = []
    for match in re.finditer(r"[^\r\n]+", source):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        offset = len(raw) - len(raw.lstrip())
        rows.append(Line(stripped, match.start() + offset, match.start() + offset + len(stripped)))
    return rows


def _split_label(text: str) -> tuple[str, str] | None:
    match = re.match(r"^([^:：]{1,80})[:：]\s*(.*)$", text)
    if not match:
        return None
    return match.group(1).strip().lower(), match.group(2).strip()


def _value_span(line: Line, value: str) -> list[int]:
    if not value:
        return [line.end, line.end]
    relative = line.text.rfind(value)
    if relative < 0:
        return [line.start, line.end]
    return [line.start + relative, line.start + relative + len(value)]


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _blank_code_item() -> dict[str, Any]:
    return {
        "code": "",
        "display": "",
        "source_document": "",
        "evidence_text": "",
        "char_span": [0, 0],
        "evidence_ref": "",
        "evidence_status": "NOT_PROVIDED",
    }


def _blank_candidate_group() -> dict[str, Any]:
    return {
        "candidate_drg": "",
        "candidate_name": "",
        "mdc": "",
        "mdc_name": "",
        "adrg": "",
        "cc_level": "",
        "grouping_method": "",
        "coverage": False,
        "result_status": "NOT_ASSESSED",
    }


def _blank_result(run_id: str) -> dict[str, Any]:
    return {
        "review_status": "INPUT_REQUIRED",
        "review_conclusion": "NOT_ASSESSABLE",
        "review_method": REVIEW_METHOD,
        "coded_case": {
            "review_purpose": _fact(),
            "diagnosis_coding_standard": {"system": _fact(), "version": _fact()},
            "procedure_coding_standard": {"system": _fact(), "version": _fact()},
            "patient_gender": _fact(),
            "patient_age": _fact(),
            "primary_diagnosis": _blank_code_item(),
            "secondary_diagnoses": [],
            "procedures": [],
        },
        "development_candidate_group": _blank_candidate_group(),
        "dip_review": {
            "status": "NOT_ASSESSED",
            "note": "未运行开发期 DIP 风险复核。",
        },
        "risk_findings": [],
        "review_actions": [],
        "quality_flags": {
            "candidate_coverage": False,
            "candidate_only": True,
            "rule_pack_integrity_verified": False,
        },
        "governance": {
            "rule_pack_id": "cn.drg_dip.risk_heuristics",
            "rule_pack_version": "1.0.0-development",
            "jurisdiction": "CN_GENERIC_DEVELOPMENT",
            "authority_status": "experimental_unverified",
            "license_status": "external_review_required",
            "use_restriction": "development_risk_review_only_not_for_grouping_payment_or_settlement",
        },
        "evidence_items": [],
        "missing_required_fields": [],
        "input_conflicts": [],
        "limitations": [
            "仅处理编码员明确提供的结构化诊断/手术编码及逐字证据，不从自由文本提取或新增编码。",
            "内置规则和术语映射未经官方来源、许可、地区版本或医院版本独立验证，仅供开发期风险复核。",
            "候选 DRG 不是官方分组，不计算或输出权重、CMI、DIP 分值、支付或结算金额。",
            "不判断诊断成立、编码正确性、临床合理性、医疗必要性或医保支付资格。",
            "READY_FOR_CODER_REVIEW 只表示本地启发式运行完成，不表示可用于编码、报送、支付或结算。",
            "结果必须由获授权的地区/医院分组器和人工编码员独立复核，禁止自动提交和写回。",
        ],
        "code_extraction_performed": False,
        "code_assignment_performed": False,
        "code_validation_performed": False,
        "clinical_inference_performed": False,
        "local_development_rules_used": False,
        "official_grouping_performed": False,
        "official_dip_scoring_performed": False,
        "payment_calculation_performed": False,
        "billing_authoritative": False,
        "production_submission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id,
            "provider_trace_refs": [f"{run_id}:governed-drg-dip-risk-review"],
        },
        "_trace": {
            "input_truncated": False,
            "prompt_canary_detected": False,
            "evidence_items_count": 0,
            "valid_spans_count": 0,
            "diagnosis_count": 0,
            "procedure_count": 0,
            "risk_count": 0,
            "candidate_coverage": False,
        },
    }


def _normalize_system(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _parse_code_item(line: Line, *, kind: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.text.split("|", 3)]
    if len(parts) != 4 or not all(parts):
        return None
    code, display, source_document, evidence_text = parts
    normalized_code = code.upper()
    pattern = _DIAGNOSIS_CODE if kind == "diagnosis" else _PROCEDURE_CODE
    if not pattern.fullmatch(normalized_code):
        return None
    return {
        "code": normalized_code,
        "display": display,
        "source_document": source_document,
        "evidence_text": evidence_text,
        "char_span": _value_span(line, evidence_text),
    }


def _risk_evidence_refs(rule_id: str, coded_case: dict[str, Any]) -> list[str]:
    primary = coded_case["primary_diagnosis"].get("evidence_ref", "")
    secondary = [item.get("evidence_ref", "") for item in coded_case["secondary_diagnoses"]]
    procedures = [item.get("evidence_ref", "") for item in coded_case["procedures"]]
    gender = coded_case["patient_gender"].get("evidence_ref", "")
    mapping = {
        "DRG001": [primary],
        "DRG002": [primary, *procedures[:1]],
        "DRG003": [primary, *secondary],
        "DRG004": [primary, gender],
        "DIP001": [primary, *secondary],
        "DIP002": procedures,
        "DIP003": [primary, *procedures[:1]],
    }
    return list(dict.fromkeys(ref for ref in mapping.get(rule_id, []) if ref))


async def build_drg_dip_risk_review(
    text: Any,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or f"run-{uuid4()}"
    result = _blank_result(run_id)
    source, truncated = _bounded_text(text)
    result["_trace"]["input_truncated"] = truncated
    if not source:
        result["missing_required_fields"] = ["input_text"]
        return result
    if _UNTRUSTED_PATTERN.search(source):
        result["missing_required_fields"] = ["safe_labelled_input"]
        result["_trace"]["prompt_canary_detected"] = True
        return result

    scalar_values: dict[str, tuple[str, Line, str]] = {}
    primary_raw: dict[str, Any] | None = None
    secondary_raw: list[dict[str, Any]] = []
    procedures_raw: list[dict[str, Any]] = []
    invalid_primary = False
    invalid_secondary: list[str] = []
    invalid_procedures: list[str] = []
    current_section = ""

    for line in _lines(source):
        labelled = _split_label(line.text)
        if labelled:
            label, value = labelled
            if label in _SCALAR_LABELS:
                field = _SCALAR_LABELS[label]
                if field == "primary_diagnosis":
                    if value:
                        span = _value_span(line, value)
                        primary_raw = _parse_code_item(
                            Line(value, span[0], span[1]), kind="diagnosis"
                        )
                        invalid_primary = primary_raw is None
                    else:
                        primary_raw = None
                    current_section = ""
                else:
                    scalar_values[field] = (value, line, label)
                    current_section = ""
                continue
            if label in _SECTION_LABELS:
                current_section = _SECTION_LABELS[label]
                if value:
                    span = _value_span(line, value)
                    synthetic = Line(value, span[0], span[1])
                    parsed = _parse_code_item(
                        synthetic,
                        kind="diagnosis" if current_section == "secondary_diagnoses" else "procedure",
                    )
                    if parsed:
                        (secondary_raw if current_section == "secondary_diagnoses" else procedures_raw).append(parsed)
                    elif current_section == "secondary_diagnoses":
                        invalid_secondary.append(value)
                    else:
                        invalid_procedures.append(value)
                continue
        if current_section:
            parsed = _parse_code_item(
                line,
                kind="diagnosis" if current_section == "secondary_diagnoses" else "procedure",
            )
            if parsed:
                (secondary_raw if current_section == "secondary_diagnoses" else procedures_raw).append(parsed)
            elif current_section == "secondary_diagnoses":
                invalid_secondary.append(line.text)
            else:
                invalid_procedures.append(line.text)

    evidence_items: list[dict[str, Any]] = []

    def add_evidence(field: str, label: str, value: str, span: list[int]) -> str:
        evidence_id = f"drg-evidence-{len(evidence_items) + 1}"
        evidence_items.append({
            "evidence_id": evidence_id,
            "field": field,
            "label": label,
            "text": value,
            "char_span": span,
        })
        return evidence_id

    for field, target in (
        ("review_purpose", ("review_purpose",)),
        ("diagnosis_coding_system", ("diagnosis_coding_standard", "system")),
        ("diagnosis_coding_version", ("diagnosis_coding_standard", "version")),
        ("procedure_coding_system", ("procedure_coding_standard", "system")),
        ("procedure_coding_version", ("procedure_coding_standard", "version")),
        ("patient_gender", ("patient_gender",)),
        ("patient_age", ("patient_age",)),
    ):
        value, line, label = scalar_values.get(field, ("", Line("", 0, 0), field))
        ref = add_evidence(field, label, value, _value_span(line, value)) if value else ""
        fact = _fact(value, ref)
        if len(target) == 1:
            result["coded_case"][target[0]] = fact
        else:
            result["coded_case"][target[0]][target[1]] = fact

    def finalize_code_item(raw: dict[str, Any], field: str) -> dict[str, Any]:
        ref = add_evidence(field, field, raw["evidence_text"], raw["char_span"])
        return {
            **raw,
            "evidence_ref": ref,
            "evidence_status": "EXACT_INPUT_SPAN",
        }

    if primary_raw:
        result["coded_case"]["primary_diagnosis"] = finalize_code_item(
            primary_raw, "primary_diagnosis"
        )
    result["coded_case"]["secondary_diagnoses"] = [
        finalize_code_item(item, "secondary_diagnosis")
        for item in secondary_raw[:MAX_ITEMS]
    ]
    result["coded_case"]["procedures"] = [
        finalize_code_item(item, "procedure")
        for item in procedures_raw[:MAX_ITEMS]
    ]

    missing: list[str] = []
    for field in ("review_purpose", "diagnosis_coding_system", "diagnosis_coding_version"):
        if not scalar_values.get(field, ("", None, None))[0]:
            missing.append(field)
    diagnosis_system = scalar_values.get("diagnosis_coding_system", ("", None, None))[0]
    if diagnosis_system and _normalize_system(diagnosis_system) != "ICD10CN":
        missing.append("supported_diagnosis_coding_system_ICD_10_CN")
    if not primary_raw:
        missing.append("valid_primary_diagnosis")
    if invalid_primary:
        missing.append("valid_primary_diagnosis_format")
    if invalid_secondary:
        missing.append("valid_secondary_diagnosis_lines")
    if invalid_procedures:
        missing.append("valid_procedure_lines")
    if len(secondary_raw) > MAX_ITEMS:
        missing.append("secondary_diagnosis_limit_exceeded")
    if len(procedures_raw) > MAX_ITEMS:
        missing.append("procedure_limit_exceeded")
    if procedures_raw:
        procedure_system = scalar_values.get("procedure_coding_system", ("", None, None))[0]
        procedure_version = scalar_values.get("procedure_coding_version", ("", None, None))[0]
        if not procedure_system:
            missing.append("procedure_coding_system")
        elif _normalize_system(procedure_system) != "ICD9CM3":
            missing.append("supported_procedure_coding_system_ICD_9_CM_3")
        if not procedure_version:
            missing.append("procedure_coding_version")
    gender = scalar_values.get("patient_gender", ("", None, None))[0].upper()
    if gender and gender not in {"M", "F"}:
        missing.append("valid_patient_gender_M_or_F")
    age_text = scalar_values.get("patient_age", ("", None, None))[0]
    age_value: int | None = None
    if age_text:
        try:
            age_value = int(age_text)
        except ValueError:
            missing.append("valid_patient_age")
        else:
            if age_value < 0 or age_value > 150:
                missing.append("valid_patient_age")
                age_value = None
    if truncated:
        missing.append("complete_untruncated_input")

    conflicts: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in result["coded_case"]["secondary_diagnoses"]:
        grouped[item["code"]].append(item)
    for code, items in grouped.items():
        if len(items) > 1:
            conflicts.append({
                "field": "secondary_diagnoses.code",
                "documented_value": code,
                "reason": "同一次诊断编码被重复提供。",
                "evidence_refs": [item["evidence_ref"] for item in items],
            })
    primary_code = result["coded_case"]["primary_diagnosis"]["code"]
    duplicate_primary = [
        item for item in result["coded_case"]["secondary_diagnoses"]
        if item["code"] == primary_code and primary_code
    ]
    if duplicate_primary:
        conflicts.append({
            "field": "primary_diagnosis.code",
            "documented_value": primary_code,
            "reason": "主诊断编码同时出现在次诊断集合中。",
            "evidence_refs": [
                result["coded_case"]["primary_diagnosis"]["evidence_ref"],
                *[item["evidence_ref"] for item in duplicate_primary],
            ],
        })
    procedure_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in result["coded_case"]["procedures"]:
        procedure_groups[item["code"]].append(item)
    for code, items in procedure_groups.items():
        if len(items) > 1:
            conflicts.append({
                "field": "procedures.code",
                "documented_value": code,
                "reason": "同一手术操作编码被重复提供。",
                "evidence_refs": [item["evidence_ref"] for item in items],
            })

    result["evidence_items"] = evidence_items
    result["missing_required_fields"] = sorted(set(missing))
    result["input_conflicts"] = conflicts
    if missing:
        result["review_status"] = "INPUT_REQUIRED"
        result["_trace"].update({
            "evidence_items_count": len(evidence_items),
            "valid_spans_count": sum(
                1 for item in evidence_items
                if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
            ),
        })
        return result
    if conflicts:
        result["review_status"] = "EVIDENCE_REVIEW_REQUIRED"
        result["_trace"].update({
            "evidence_items_count": len(evidence_items),
            "valid_spans_count": sum(
                1 for item in evidence_items
                if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
            ),
        })
        return result

    from app.services.drg_analyzer_service import DRGAnalysisAdapter

    service_result = await DRGAnalysisAdapter().analyze_async(
        primary_diagnosis={
            "code": primary_raw["code"],
            "name": primary_raw["display"],
            "description": primary_raw["display"],
            "confidence": 1.0,
        },
        secondary_diagnoses=[
            {
                "code": item["code"],
                "name": item["display"],
                "description": item["display"],
                "confidence": 1.0,
            }
            for item in result["coded_case"]["secondary_diagnoses"]
        ],
        procedures=[
            {
                "code": item["code"],
                "name": item["display"],
                "description": item["display"],
                "confidence": 1.0,
            }
            for item in result["coded_case"]["procedures"]
        ],
        context={"patient_gender": gender, "patient_age": age_value},
    )
    payload = service_result.to_dict()
    if payload.get("error"):
        result["review_status"] = "RUNTIME_FAILED"
        result["review_conclusion"] = "FAIL"
        result["risk_findings"] = [{
            "rule_id": "DRG_RUNTIME_FAILURE",
            "severity": "critical",
            "category": "runtime",
            "message": "DRG/DIP 开发期风险复核未完成，结果不可使用。",
            "review_action": "检查受治理规则资产和本地运行时后重新执行，并由人工复核。",
            "input_evidence_refs": [],
        }]
        result["_trace"]["runtime_failure_reason"] = str(payload.get("error_reason") or "unknown")
    else:
        impact = payload.get("drg_impact") or {}
        result["review_status"] = "READY_FOR_CODER_REVIEW"
        result["review_conclusion"] = str(payload.get("review_conclusion") or "WARNING")
        result["development_candidate_group"] = {
            "candidate_drg": str(impact.get("predicted_drg") or ""),
            "candidate_name": str(impact.get("drg_name") or ""),
            "mdc": str(impact.get("mdc") or ""),
            "mdc_name": str(impact.get("mdc_name") or ""),
            "adrg": str(impact.get("adrg") or ""),
            "cc_level": str(impact.get("cc_level") or ""),
            "grouping_method": str(impact.get("grouping_method") or ""),
            "coverage": bool(impact.get("coverage")),
            "result_status": "EXPERIMENTAL_UNVERIFIED_CANDIDATE",
        }
        dip = payload.get("dip_impact") or {}
        result["dip_review"] = {
            "status": "NO_AUTHORIZED_REGIONAL_DIP_PACK",
            "note": str(dip.get("note") or "未安装经授权的地区 DIP 目录。"),
        }
        result["risk_findings"] = [
            {
                "rule_id": str(item.get("rule_id") or ""),
                "severity": str(item.get("severity") or "info"),
                "category": str(item.get("risk_type") or "grouping"),
                "message": str(item.get("message") or ""),
                "review_action": str(item.get("suggestion") or ""),
                "input_evidence_refs": _risk_evidence_refs(
                    str(item.get("rule_id") or ""), result["coded_case"]
                ),
            }
            for item in list(payload.get("risks") or [])[:MAX_ITEMS]
            if isinstance(item, dict)
        ]
        result["review_actions"] = list(dict.fromkeys(
            finding["review_action"]
            for finding in result["risk_findings"]
            if finding["review_action"]
        ))
        governance = payload.get("governance") or {}
        result["governance"] = {
            "rule_pack_id": str(governance.get("asset_id") or ""),
            "rule_pack_version": str(governance.get("version") or ""),
            "jurisdiction": str(governance.get("jurisdiction") or ""),
            "authority_status": str(governance.get("authority_status") or ""),
            "license_status": str(governance.get("license_status") or ""),
            "use_restriction": str(governance.get("use_restriction") or ""),
        }
        result["quality_flags"] = {
            "candidate_coverage": bool(impact.get("coverage")),
            "candidate_only": True,
            "rule_pack_integrity_verified": True,
        }
        result["local_development_rules_used"] = True

    valid_spans = sum(
        1 for item in evidence_items
        if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
    )
    result["_trace"].update({
        "evidence_items_count": len(evidence_items),
        "valid_spans_count": valid_spans,
        "diagnosis_count": 1 + len(result["coded_case"]["secondary_diagnoses"]),
        "procedure_count": len(result["coded_case"]["procedures"]),
        "risk_count": len(result["risk_findings"]),
        "candidate_coverage": result["development_candidate_group"]["coverage"],
    })
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    public = deepcopy(result)
    public.pop("_trace", None)
    return public


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "REVIEW_METHOD",
    "build_drg_dip_risk_review",
    "to_pack_output",
    "verify_drg_dip_risk_review_health",
]
