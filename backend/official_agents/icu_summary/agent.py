"""Evidence-bound local ICU admission summary baseline.

Only explicitly labelled ICU admission facts are reorganized.  The runtime
does not calculate APACHE/SOFA/GCS, apply vital/laboratory thresholds, screen
medications, infer diagnoses or clinical trajectory, generate treatment
recommendations, or write to an EHR.  Every extracted fact is bound to an
exact ``[start, end)`` span and all output remains a clinician-review draft.
"""

from __future__ import annotations

import re
import uuid
from typing import Any


AGENT_REF = "icoder/icu-summary@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_icu_admission_summary"
OUTPUT_CONTRACT_REF = "icoder/IcuSummaryOutput/v3"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_FIELD_RE = re.compile(
    r"(?im)^[ \t]*(?P<label>"
    r"患者信息|patient information|"
    r"入ICU原因|入重症原因|入院原因|reason for icu admission|"
    r"入院诊断|诊断|admission diagnoses?|"
    r"现病史|既往史|病史|medical history|"
    r"手术史|surgical history|"
    r"过敏史|过敏|allergies?|"
    r"社会史|social history|"
    r"活动问题|当前问题|active problems?|"
    r"用药|当前用药|medications?|"
    r"生命体征|vital signs?|"
    r"检验结果|实验室结果|检验|labs?|laboratory results?|"
    r"操作/手术|操作|手术|procedures?|"
    r"器官支持|organ support|"
    r"时间线|事件|timeline|"
    r"趋势|key trends?|"
    r"待办|待处理|pending items?|"
    r"风险|已记录风险|risks?|"
    r"矛盾/缺口|记录矛盾|记录缺口|conflicts?/gaps?"
    r")\s*[：:]\s*(?P<value>[^\r\n]*)"
)

_LABEL_TO_FIELD = {
    "患者信息": "patient_information",
    "patient information": "patient_information",
    "入icu原因": "admission_reason",
    "入重症原因": "admission_reason",
    "入院原因": "admission_reason",
    "reason for icu admission": "admission_reason",
    "入院诊断": "admission_diagnoses",
    "诊断": "admission_diagnoses",
    "admission diagnosis": "admission_diagnoses",
    "admission diagnoses": "admission_diagnoses",
    "现病史": "medical_history",
    "既往史": "medical_history",
    "病史": "medical_history",
    "medical history": "medical_history",
    "手术史": "surgical_history",
    "surgical history": "surgical_history",
    "过敏史": "allergies",
    "过敏": "allergies",
    "allergy": "allergies",
    "allergies": "allergies",
    "社会史": "social_history",
    "social history": "social_history",
    "活动问题": "active_problems",
    "当前问题": "active_problems",
    "active problem": "active_problems",
    "active problems": "active_problems",
    "用药": "medications",
    "当前用药": "medications",
    "medication": "medications",
    "medications": "medications",
    "生命体征": "vital_signs",
    "vital sign": "vital_signs",
    "vital signs": "vital_signs",
    "检验结果": "laboratory_results",
    "实验室结果": "laboratory_results",
    "检验": "laboratory_results",
    "lab": "laboratory_results",
    "labs": "laboratory_results",
    "laboratory result": "laboratory_results",
    "laboratory results": "laboratory_results",
    "操作/手术": "procedures",
    "操作": "procedures",
    "手术": "procedures",
    "procedure": "procedures",
    "procedures": "procedures",
    "器官支持": "organ_support",
    "organ support": "organ_support",
    "时间线": "timeline",
    "事件": "timeline",
    "timeline": "timeline",
    "趋势": "key_trends",
    "key trend": "key_trends",
    "key trends": "key_trends",
    "待办": "pending_items",
    "待处理": "pending_items",
    "pending item": "pending_items",
    "pending items": "pending_items",
    "风险": "risks",
    "已记录风险": "risks",
    "risk": "risks",
    "risks": "risks",
    "矛盾/缺口": "conflicts",
    "记录矛盾": "conflicts",
    "记录缺口": "conflicts",
    "conflict/gap": "conflicts",
    "conflicts/gaps": "conflicts",
}

_COMPLETENESS_FIELDS = (
    "patient_information",
    "admission_reason",
    "admission_diagnoses",
    "medical_history",
    "allergies",
    "active_problems",
    "medications",
    "vital_signs",
    "laboratory_results",
    "organ_support",
    "pending_items",
)
_DISPLAY_NAMES = {
    "patient_information": "患者信息",
    "admission_reason": "入ICU原因",
    "admission_diagnoses": "入院诊断",
    "medical_history": "病史",
    "allergies": "过敏史",
    "active_problems": "活动问题",
    "medications": "用药",
    "vital_signs": "生命体征",
    "laboratory_results": "检验结果",
    "organ_support": "器官支持",
    "pending_items": "待办",
}
_PUBLIC_FIELDS = (
    "summary_status",
    "patient_background",
    "admission_reason",
    "admission_diagnoses",
    "timeline",
    "active_problems",
    "organ_support",
    "medications",
    "vital_signs",
    "laboratory_results",
    "procedures",
    "key_trends",
    "pending_items",
    "risks",
    "conflicts",
    "source_completeness",
    "evidence_items",
    "limitations",
    "clinical_scores_status",
    "medication_screening_status",
    "clinical_recommendations_generated",
    "production_writeback_blocked",
    "manual_review_required",
    "trace_refs",
)


def verify_icu_summary_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "explicit_label_extraction_available": True,
        "clinical_scores_calculated": False,
        "medication_screening_performed": False,
        "clinical_recommendations_generated": False,
        "production_writeback_blocked": True,
    }


def _bounded_text(value: Any) -> str:
    text = str(value or "")
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:MAX_INPUT_CHARS]


def _trimmed_group_span(
    text: str,
    match: re.Match[str],
    group: str,
) -> tuple[str, list[int]]:
    start, end = match.span(group)
    value = text[start:end]
    left = len(value) - len(value.lstrip())
    right = len(value.rstrip())
    start += left
    end = start + max(right - left, 0)
    return text[start:end], [start, end]


def _add_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"icu-evidence-{len(evidence_items) + 1}"
    evidence_items.append({
        "evidence_id": evidence_id,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _blank_values() -> dict[str, Any]:
    return {
        "patient_information": "",
        "admission_reason": "",
        "admission_diagnoses": [],
        "medical_history": "",
        "surgical_history": "",
        "allergies": "",
        "social_history": "",
        "timeline": [],
        "active_problems": [],
        "organ_support": [],
        "medications": [],
        "vital_signs": [],
        "laboratory_results": [],
        "procedures": [],
        "key_trends": [],
        "pending_items": [],
        "risks": [],
        "conflicts": [],
    }


def _append_field(
    values: dict[str, Any],
    field: str,
    value: str,
    evidence_ref: str,
) -> None:
    if field in {
        "patient_information",
        "admission_reason",
        "medical_history",
        "surgical_history",
        "allergies",
        "social_history",
    }:
        values[field] = f"{values[field]}；{value}" if values[field] else value
    elif field == "admission_diagnoses":
        values[field].append({
            "diagnosis": value,
            "assertion": "DOCUMENTED",
            "evidence_ref": evidence_ref,
        })
    elif field == "timeline":
        values[field].append({"time": "", "event": value, "evidence_ref": evidence_ref})
    elif field == "active_problems":
        values[field].append({
            "problem": value,
            "status": "DOCUMENTED",
            "evidence_ref": evidence_ref,
        })
    elif field == "organ_support":
        values[field].append({
            "type": "DOCUMENTED_ORGAN_SUPPORT",
            "detail": value,
            "route": "",
            "evidence_ref": evidence_ref,
        })
    elif field == "medications":
        values[field].append({
            "documented_text": value,
            "dose": "",
            "route": "",
            "evidence_ref": evidence_ref,
        })
    elif field == "key_trends":
        values[field].append({
            "indicator": "原记录趋势",
            "trend": value,
            "interpretation": "未解释；仅保留原文记录。",
            "evidence_ref": evidence_ref,
        })
    elif field == "pending_items":
        values[field].append({
            "item": value,
            "status": "DOCUMENTED_PENDING",
            "evidence_ref": evidence_ref,
        })
    elif field == "risks":
        values[field].append({
            "risk": value,
            "basis": "原记录明确标注",
            "evidence_ref": evidence_ref,
        })
    elif field == "conflicts":
        values[field].append({
            "description": value,
            "evidence": value,
            "field": "记录",
            "evidence_ref": evidence_ref,
        })
    else:
        values[field].append({"text": value, "evidence_ref": evidence_ref})


def build_icu_summary(text: str, *, run_id: str | None = None) -> dict[str, Any]:
    source = _bounded_text(text)
    values = _blank_values()
    evidence_items: list[dict[str, Any]] = []
    truncated = len(str(text or "")) > len(source)

    for match in _FIELD_RE.finditer(source):
        if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
            truncated = True
            break
        label = match.group("label")
        field = _LABEL_TO_FIELD.get(label.casefold())
        if not field:
            continue
        value, span = _trimmed_group_span(source, match, "value")
        if not value:
            continue
        evidence_ref = _add_evidence(
            evidence_items,
            field=field,
            source_label=label,
            evidence_text=value,
            char_span=span,
        )
        _append_field(values, field, value, evidence_ref)

    missing_sections = [
        _DISPLAY_NAMES[field]
        for field in _COMPLETENESS_FIELDS
        if not values[field]
    ]
    if not evidence_items:
        status = "INPUT_REQUIRED"
    elif missing_sections:
        status = "PARTIAL"
    else:
        status = "COMPLETED"

    if status == "INPUT_REQUIRED":
        values = _blank_values()
        evidence_items = []
    valid_spans = sum(
        1
        for item in evidence_items
        if source[slice(*item["char_span"])] == item["evidence_text"]
    )
    trace_id = run_id or f"icu-summary-{uuid.uuid4().hex}"
    result = {
        "summary_status": status,
        "patient_background": {
            "patient_information": values["patient_information"],
            "medical_history": values["medical_history"],
            "surgical_history": values["surgical_history"],
            "allergies": values["allergies"],
            "social_history": values["social_history"],
        },
        "admission_reason": values["admission_reason"],
        "admission_diagnoses": values["admission_diagnoses"],
        "timeline": values["timeline"],
        "active_problems": values["active_problems"],
        "organ_support": values["organ_support"],
        "medications": values["medications"],
        "vital_signs": values["vital_signs"],
        "laboratory_results": values["laboratory_results"],
        "procedures": values["procedures"],
        "key_trends": values["key_trends"],
        "pending_items": values["pending_items"],
        "risks": values["risks"],
        "conflicts": values["conflicts"],
        "source_completeness": {
            "missing_sections": missing_sections if status != "INPUT_REQUIRED" else list(_DISPLAY_NAMES.values()),
            "input_truncated": truncated,
            "evidence_item_count": len(evidence_items),
        },
        "evidence_items": evidence_items,
        "limitations": [
            "仅解析明确字段标签；未标注自由文本不会被重写为 ICU 临床事实。",
            "未计算 APACHE II、SOFA、GCS、死亡风险或其他临床评分。",
            "未应用生命体征/检验参考范围，未执行药物相互作用、剂量或肝肾调整审查。",
            "未调用 PubMed、DrugBank、Medical Calculator 或真实 EHR/MAR/LIS/监护设备。",
            "未生成诊疗建议；所有字段须 ICU 医师对照原始记录复核。",
        ],
        "clinical_scores_status": "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED",
        "medication_screening_status": "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED",
        "clinical_recommendations_generated": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-icu-summary"],
        },
        "_trace": {
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "evidence_items_count": len(evidence_items),
            "valid_spans_count": valid_spans,
            "clinical_scores_calculated": False,
            "medication_screening_performed": False,
            "clinical_recommendations_generated": False,
        },
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_icu_summary",
    "to_pack_output",
    "verify_icu_summary_health",
]
