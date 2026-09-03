"""Evidence-bound local patient discharge education baseline.

Only explicitly labelled discharge facts are reorganized.  The runtime does
not interpret results, reconcile medications, add return precautions or
follow-up steps, translate clinical meaning from model memory, generate new
medical advice, or publish/write to a patient record.  Every documented fact
is bound to an exact ``[start, end)`` span and remains a clinician-review
draft.
"""

from __future__ import annotations

import re
import uuid
from typing import Any


AGENT_REF = "icoder/discharge-edu@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_discharge_education"
OUTPUT_CONTRACT_REF = "icoder/DischargeEducationOutput/v3"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200
MAX_QUESTIONS = 30

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_FIELD_RE = re.compile(
    r"(?im)^[ \t]*(?P<label>"
    r"出院诊断|discharge diagnoses?|"
    r"就诊原因|主诉|reason for visit|chief complaint|"
    r"诊疗经过|住院经过|treatment course|what happened|"
    r"出院去向|discharge destination|"
    r"检验结果|lab results?|laboratory results?|"
    r"影像结果|imaging results?|"
    r"操作/手术|操作|手术|procedures?|"
    r"出院用药|用药医嘱|medication instructions?|discharge medications?|"
    r"复诊计划|随访计划|复诊|随访|follow[- ]?up(?: plan)?|"
    r"警示症状|返院提示|就医提示|return precautions?|warning signs?|"
    r"生活方式|活动医嘱|饮食医嘱|伤口护理|家庭护理|"
    r"lifestyle|activity instructions?|diet instructions?|wound care|home care|"
    r"待回结果|待办|pending results?|pending items?|"
    r"资料冲突|记录冲突|contradictions?|conflicts?"
    r")\s*[：:]\s*(?P<value>[^\r\n]*)"
)

_LABEL_TO_FIELD = {
    "出院诊断": "diagnosis_summary",
    "discharge diagnosis": "diagnosis_summary",
    "discharge diagnoses": "diagnosis_summary",
    "就诊原因": "reason_for_visit",
    "主诉": "reason_for_visit",
    "reason for visit": "reason_for_visit",
    "chief complaint": "reason_for_visit",
    "诊疗经过": "treatment_course",
    "住院经过": "treatment_course",
    "treatment course": "treatment_course",
    "what happened": "treatment_course",
    "出院去向": "discharge_destination",
    "discharge destination": "discharge_destination",
    "检验结果": "laboratory_result",
    "lab result": "laboratory_result",
    "lab results": "laboratory_result",
    "laboratory result": "laboratory_result",
    "laboratory results": "laboratory_result",
    "影像结果": "imaging_result",
    "imaging result": "imaging_result",
    "imaging results": "imaging_result",
    "操作/手术": "procedure",
    "操作": "procedure",
    "手术": "procedure",
    "procedure": "procedure",
    "procedures": "procedure",
    "出院用药": "medication_instructions",
    "用药医嘱": "medication_instructions",
    "medication instruction": "medication_instructions",
    "medication instructions": "medication_instructions",
    "discharge medication": "medication_instructions",
    "discharge medications": "medication_instructions",
    "复诊计划": "follow_up",
    "随访计划": "follow_up",
    "复诊": "follow_up",
    "随访": "follow_up",
    "follow-up": "follow_up",
    "follow up": "follow_up",
    "follow-up plan": "follow_up",
    "follow up plan": "follow_up",
    "警示症状": "warning_signs",
    "返院提示": "warning_signs",
    "就医提示": "warning_signs",
    "return precaution": "warning_signs",
    "return precautions": "warning_signs",
    "warning sign": "warning_signs",
    "warning signs": "warning_signs",
    "生活方式": "lifestyle",
    "活动医嘱": "lifestyle",
    "饮食医嘱": "lifestyle",
    "伤口护理": "lifestyle",
    "家庭护理": "lifestyle",
    "lifestyle": "lifestyle",
    "activity instruction": "lifestyle",
    "activity instructions": "lifestyle",
    "diet instruction": "lifestyle",
    "diet instructions": "lifestyle",
    "wound care": "lifestyle",
    "home care": "lifestyle",
    "待回结果": "pending_results",
    "待办": "pending_results",
    "pending result": "pending_results",
    "pending results": "pending_results",
    "pending item": "pending_results",
    "pending items": "pending_results",
    "资料冲突": "contradiction",
    "记录冲突": "contradiction",
    "contradiction": "contradiction",
    "contradictions": "contradiction",
    "conflict": "contradiction",
    "conflicts": "contradiction",
}

_CORE_FIELDS = (
    "diagnosis_summary",
    "medication_instructions",
    "follow_up",
    "warning_signs",
    "lifestyle",
)
_DISPLAY_NAMES = {
    "diagnosis_summary": "出院诊断",
    "medication_instructions": "出院用药",
    "follow_up": "复诊/随访计划",
    "warning_signs": "警示症状/返院提示",
    "lifestyle": "生活方式/家庭护理",
}
_QUESTION_BY_FIELD = {
    "diagnosis_summary": "请用自己的话复述病历中记录的出院诊断。",
    "medication_instructions": "请对照出院医嘱复述用药名称、剂量、途径和频次。",
    "follow_up": "请复述已经记录的复诊或随访安排。",
    "warning_signs": "请复述出院记录中写明的警示症状和返院提示。",
    "lifestyle": "请复述出院记录中写明的生活方式或家庭护理事项。",
    "pending_results": "请说明记录中哪些结果仍待回报，以及应向谁确认。",
}
_PUBLIC_FIELDS = (
    "education_status",
    "diagnosis_summary",
    "encounter_summary",
    "key_results",
    "medication_instructions",
    "medication_reconciliation_status",
    "follow_up",
    "warning_signs",
    "lifestyle",
    "pending_results",
    "teach_back_questions",
    "clarification_questions",
    "contradictions",
    "missing_items",
    "source_completeness",
    "evidence_items",
    "limitations",
    "translation_status",
    "external_knowledge_used",
    "clinical_interpretation_performed",
    "clinical_recommendations_generated",
    "production_writeback_blocked",
    "manual_review_required",
    "trace_refs",
)


def verify_discharge_education_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "explicit_label_extraction_available": True,
        "plain_language_translation_performed": False,
        "external_knowledge_used": False,
        "clinical_interpretation_performed": False,
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


def _append_text(current: str, value: str) -> str:
    return f"{current}；{value}" if current else value


def _add_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"discharge-edu-evidence-{len(evidence_items) + 1}"
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
        "diagnosis_summary": "",
        "reason_for_visit": "",
        "treatment_course": "",
        "discharge_destination": "",
        "key_results": [],
        "medication_instructions": "",
        "follow_up": "",
        "warning_signs": "",
        "lifestyle": "",
        "pending_results": "",
        "contradictions": [],
    }


def _append_field(
    values: dict[str, Any],
    *,
    field: str,
    value: str,
    evidence_ref: str,
) -> None:
    if field in {
        "diagnosis_summary",
        "reason_for_visit",
        "treatment_course",
        "discharge_destination",
        "medication_instructions",
        "follow_up",
        "warning_signs",
        "lifestyle",
        "pending_results",
    }:
        values[field] = _append_text(values[field], value)
        return
    if field in {"laboratory_result", "imaging_result", "procedure"}:
        category = {
            "laboratory_result": "LABORATORY_RESULT",
            "imaging_result": "IMAGING_RESULT",
            "procedure": "PROCEDURE",
        }[field]
        values["key_results"].append({
            "category": category,
            "documented_result": value,
            "interpretation": "未解释；仅保留原文记录。",
            "evidence_ref": evidence_ref,
        })
        return
    if field == "contradiction":
        values["contradictions"].append({
            "description": value,
            "resolution": "UNRESOLVED_CLINICAL_REVIEW_REQUIRED",
            "evidence_ref": evidence_ref,
        })


def build_discharge_education(
    text: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    source = _bounded_text(text)
    values = _blank_values()
    evidence_items: list[dict[str, Any]] = []
    documented_fields: set[str] = set()
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
        _append_field(
            values,
            field=field,
            value=value,
            evidence_ref=evidence_ref,
        )
        documented_fields.add(field)

    missing_items = [
        _DISPLAY_NAMES[field]
        for field in _CORE_FIELDS
        if not values[field]
    ]
    if not evidence_items:
        status = "INPUT_REQUIRED"
    elif missing_items:
        status = "PARTIAL"
    else:
        status = "COMPLETED"

    if status == "INPUT_REQUIRED":
        values = _blank_values()
        evidence_items = []
        documented_fields = set()
        missing_items = list(_DISPLAY_NAMES.values())

    teach_back_questions = [
        question
        for field, question in _QUESTION_BY_FIELD.items()
        if values.get(field)
    ][:MAX_QUESTIONS]
    clarification_questions = [
        f"请向临床团队确认：{item}。"
        for item in missing_items
    ]
    if values["contradictions"]:
        clarification_questions.append("请临床团队核对并澄清已记录的资料冲突。")
    clarification_questions = clarification_questions[:MAX_QUESTIONS]

    valid_spans = sum(
        1
        for item in evidence_items
        if source[slice(*item["char_span"])] == item["evidence_text"]
    )
    trace_id = run_id or f"discharge-edu-{uuid.uuid4().hex}"
    result = {
        "education_status": status,
        "diagnosis_summary": values["diagnosis_summary"],
        "encounter_summary": {
            "reason_for_visit": values["reason_for_visit"],
            "treatment_course": values["treatment_course"],
            "discharge_destination": values["discharge_destination"],
        },
        "key_results": values["key_results"],
        "medication_instructions": values["medication_instructions"],
        "medication_reconciliation_status": (
            "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED"
        ),
        "follow_up": values["follow_up"],
        "warning_signs": values["warning_signs"],
        "lifestyle": values["lifestyle"],
        "pending_results": values["pending_results"],
        "teach_back_questions": teach_back_questions,
        "clarification_questions": clarification_questions,
        "contradictions": values["contradictions"],
        "missing_items": missing_items,
        "source_completeness": {
            "documented_sections": sorted(documented_fields),
            "missing_sections": missing_items,
            "input_truncated": truncated,
            "evidence_item_count": len(evidence_items),
        },
        "evidence_items": evidence_items,
        "limitations": [
            "仅解析明确字段标签；未标注自由文本不会被重写为患者宣教事实。",
            "仅逐字重排已记录内容；未执行通俗化医学释义、阅读等级改写或多语言翻译。",
            "未解释检验/影像意义，未补充诊断、预后、警示症状、返院条件或随访步骤。",
            "未执行药物重整、相互作用、剂量、禁忌、过敏或肝肾功能审查。",
            "未调用 PubMed、Web Search、Medical Calculator、患者门户或真实 EHR/MAR/LIS/PACS。",
            "所有患者可见内容必须由临床人员对照原始出院记录复核后发布。",
        ],
        "translation_status": "VERBATIM_DOCUMENTED_CONTENT_ONLY",
        "external_knowledge_used": False,
        "clinical_interpretation_performed": False,
        "clinical_recommendations_generated": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-discharge-education"],
        },
        "_trace": {
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "evidence_items_count": len(evidence_items),
            "valid_spans_count": valid_spans,
            "plain_language_translation_performed": False,
            "external_knowledge_used": False,
            "clinical_interpretation_performed": False,
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
    "build_discharge_education",
    "to_pack_output",
    "verify_discharge_education_health",
]
