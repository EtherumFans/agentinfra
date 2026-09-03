"""Evidence-bound local discharge-summary structuring baseline.

The parser recognizes common Chinese and English discharge-summary section
headings, including multi-line sections.  It reorganizes documented text only:
it does not infer diagnoses, assign codes, reconcile medications, invent
instructions, summarize unlabelled narrative, or write to an EHR.  Every
published fact points to an exact ``[start, end)`` span in the redacted input
and remains a clinician-review draft.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/discharge-summary-structuring@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_discharge_summary_structuring"
OUTPUT_CONTRACT_REF = "icoder/DischargeSummaryStructured/v5"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200
MAX_ITEMS_PER_SECTION = 100

SUMMARY_GENERATION_STATUS = "VERBATIM_SECTION_REORGANIZATION_ONLY"
UNRESOLVED_CONFLICT = "UNRESOLVED_CLINICAL_REVIEW_REQUIRED"

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "\nignore previous",
    "ICODER_PROMPT_CANARY_",
)

_LABEL_TO_FIELD = {
    "入院日期": "admission_date",
    "admission date": "admission_date",
    "出院日期": "discharge_date",
    "discharge date": "discharge_date",
    "科室": "department",
    "出院科室": "department",
    "department": "department",
    "出院去向": "discharge_destination",
    "discharge destination": "discharge_destination",
    "入院原因": "admission_reason",
    "入院情况": "admission_reason",
    "主诉": "admission_reason",
    "reason for admission": "admission_reason",
    "chief complaint": "admission_reason",
    "出院诊断": "diagnoses",
    "主要诊断": "primary_diagnoses",
    "其他诊断": "secondary_diagnoses",
    "discharge diagnoses": "diagnoses",
    "discharge diagnosis": "diagnoses",
    "principal diagnosis": "primary_diagnoses",
    "secondary diagnoses": "secondary_diagnoses",
    "手术及操作": "procedures",
    "手术操作": "procedures",
    "主要手术": "procedures",
    "操作/手术": "procedures",
    "procedures": "procedures",
    "procedure": "procedures",
    "诊疗经过": "treatment_course",
    "住院经过": "treatment_course",
    "治疗经过": "treatment_course",
    "hospital course": "treatment_course",
    "treatment course": "treatment_course",
    "检验结果": "laboratory_results",
    "实验室结果": "laboratory_results",
    "laboratory results": "laboratory_results",
    "lab results": "laboratory_results",
    "影像结果": "imaging_results",
    "影像学结果": "imaging_results",
    "imaging results": "imaging_results",
    "出院医嘱": "general_orders",
    "discharge instructions": "general_orders",
    "出院用药": "medication_orders",
    "用药医嘱": "medication_orders",
    "discharge medications": "medication_orders",
    "medication instructions": "medication_orders",
    "活动医嘱": "activity_orders",
    "activity instructions": "activity_orders",
    "饮食医嘱": "diet_orders",
    "diet instructions": "diet_orders",
    "伤口护理": "wound_care_orders",
    "wound care": "wound_care_orders",
    "随访计划": "follow_up",
    "复诊计划": "follow_up",
    "随访": "follow_up",
    "复诊": "follow_up",
    "follow-up plan": "follow_up",
    "follow up plan": "follow_up",
    "follow-up": "follow_up",
    "follow up": "follow_up",
    "出院情况": "discharge_status",
    "出院状态": "discharge_status",
    "转归": "discharge_status",
    "discharge status": "discharge_status",
    "disposition status": "discharge_status",
    "过敏史": "allergies",
    "过敏": "allergies",
    "allergies": "allergies",
    "allergy": "allergies",
    "待回结果": "pending_results",
    "待回报结果": "pending_results",
    "pending results": "pending_results",
    "pending result": "pending_results",
    "并发症": "complications",
    "complications": "complications",
    "complication": "complications",
    "资料冲突": "conflicts",
    "记录冲突": "conflicts",
    "contradictions": "conflicts",
    "contradiction": "conflicts",
    "conflicts": "conflicts",
    "conflict": "conflicts",
}

_LABEL_PATTERN = "|".join(
    re.escape(label)
    for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*"
    rf"(?:[：:][ \t]*(?P<inline>[^\r\n]*)|(?P<line_end>\r?\n|$))"
)
_LEADING_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]*)"
)
_ITEM_SEPARATOR_RE = re.compile(r"[；;]\s*|\r?\n+")
_ITEM_SEPARATOR_WITH_COMMA_RE = re.compile(r"[；;,，]\s*|\r?\n+")

_CORE_SECTION_NAMES = {
    "diagnoses": "出院诊断",
    "treatment_course": "诊疗经过",
    "discharge_orders": "出院医嘱",
    "follow_up_recommendations": "随访/复诊计划",
    "discharge_status": "出院状态/转归",
}

_PUBLIC_FIELDS = (
    "structuring_status",
    "encounter_metadata",
    "admission_reason",
    "diagnoses",
    "procedures",
    "treatment_course",
    "key_results",
    "discharge_orders",
    "follow_up_recommendations",
    "discharge_status",
    "allergies",
    "pending_results",
    "complications",
    "conflicts",
    "missing_sections",
    "source_completeness",
    "evidence_items",
    "limitations",
    "summary_generation_status",
    "icd_codes_assigned",
    "medication_reconciliation_performed",
    "clinical_inference_performed",
    "production_writeback_blocked",
    "manual_review_required",
    "trace_refs",
)


@dataclass(frozen=True)
class Section:
    field: str
    label: str
    value: str
    span: list[int]


def verify_discharge_summary_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "multiline_section_parsing_available": True,
        "unlabelled_narrative_summarized": False,
        "icd_codes_assigned": False,
        "medication_reconciliation_performed": False,
        "clinical_inference_performed": False,
        "production_writeback_blocked": True,
    }


def _bounded_text(value: Any) -> tuple[str, bool]:
    raw = str(value or "")
    source = raw[:MAX_INPUT_CHARS]
    truncated = len(raw) > len(source)
    for marker in _UNTRUSTED_BOUNDARIES:
        index = source.casefold().find(marker.casefold())
        if index >= 0:
            source = source[:index]
            truncated = True
    return source, truncated


def _trim_span(source: str, start: int, end: int) -> tuple[str, list[int]]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and (source[end - 1].isspace() or source[end - 1] in ";；"):
        end -= 1
    return source[start:end], [start, end]


def _sections(source: str) -> list[Section]:
    matches = list(_HEADING_RE.finditer(source))
    sections: list[Section] = []
    for index, match in enumerate(matches):
        field = _LABEL_TO_FIELD[match.group("label").casefold()]
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        if match.group("inline") is not None:
            start = match.start("inline")
        else:
            start = match.end()
        value, span = _trim_span(source, start, next_start)
        if value:
            sections.append(
                Section(
                    field=field,
                    label=match.group("label"),
                    value=value,
                    span=span,
                )
            )
    return sections


def _split_items(
    source: str,
    section: Section,
    *,
    split_commas: bool = False,
) -> list[tuple[str, list[int]]]:
    separator = (
        _ITEM_SEPARATOR_WITH_COMMA_RE if split_commas else _ITEM_SEPARATOR_RE
    )
    parts: list[tuple[str, list[int]]] = []
    cursor = 0
    for match in list(separator.finditer(section.value)) + [None]:
        end = match.start() if match is not None else len(section.value)
        raw_start = cursor
        raw_end = end
        raw = section.value[raw_start:raw_end]
        leading = _LEADING_ITEM_RE.match(raw)
        if leading:
            raw_start += leading.end()
        value, span = _trim_span(
            source,
            section.span[0] + raw_start,
            section.span[0] + raw_end,
        )
        value = value.rstrip("。.").rstrip()
        span[1] = span[0] + len(value)
        if value and len(parts) < MAX_ITEMS_PER_SECTION:
            parts.append((value, span))
        if match is None:
            break
        cursor = match.end()
    return parts


def _add_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"discharge-summary-evidence-{len(evidence_items) + 1}"
    evidence_items.append({
        "evidence_id": evidence_id,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _append_text(current: str, value: str) -> str:
    return f"{current}\n{value}" if current else value


def _normalized_discharge_status(value: str) -> str:
    normalized = value.strip().casefold().rstrip("。.")
    exact = {
        "治愈": "CURED",
        "cured": "CURED",
        "好转": "IMPROVED",
        "improved": "IMPROVED",
        "未愈": "NOT_CURED",
        "not cured": "NOT_CURED",
        "死亡": "DECEASED",
        "deceased": "DECEASED",
        "其他": "OTHER",
        "other": "OTHER",
    }
    return exact.get(normalized, "DOCUMENTED_UNMAPPED")


def _blank_result(trace_id: str) -> dict[str, Any]:
    return {
        "structuring_status": "INPUT_REQUIRED",
        "encounter_metadata": {
            "admission_date": "",
            "discharge_date": "",
            "department": "",
            "discharge_destination": "",
        },
        "admission_reason": "",
        "diagnoses": [],
        "procedures": [],
        "treatment_course": "",
        "key_results": [],
        "discharge_orders": [],
        "follow_up_recommendations": [],
        "discharge_status": {
            "documented_text": "",
            "normalized_status": "NOT_DOCUMENTED",
            "evidence_ref": "",
        },
        "allergies": "",
        "pending_results": [],
        "complications": [],
        "conflicts": [],
        "missing_sections": list(_CORE_SECTION_NAMES.values()),
        "source_completeness": {
            "documented_sections": [],
            "missing_sections": list(_CORE_SECTION_NAMES.values()),
            "input_truncated": False,
            "evidence_item_count": 0,
        },
        "evidence_items": [],
        "limitations": [
            "仅解析明确的中英文出院小结章节标题；未标注自由叙事不会被自动总结。",
            "仅逐字重排已记录内容；未推断诊断、因果、严重程度、预后或治疗意图。",
            "未分配或验证 ICD-10-CN/ICD-9-CM-3 编码。",
            "未执行药物重整、相互作用、禁忌、剂量或过敏匹配。",
            "未补充出院医嘱、复诊计划、返院条件或其他医疗建议。",
            "未连接真实 HIS/EMR、医嘱、MAR/药房、LIS/PACS 或患者门户。",
            "所有结构化内容必须由临床人员对照原始出院记录复核。",
        ],
        "summary_generation_status": SUMMARY_GENERATION_STATUS,
        "icd_codes_assigned": False,
        "medication_reconciliation_performed": False,
        "clinical_inference_performed": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-discharge-summary"],
        },
    }


def build_discharge_summary(
    text: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    trace_id = run_id or f"discharge-summary-{uuid.uuid4().hex}"
    result = _blank_result(trace_id)
    evidence_items: list[dict[str, Any]] = []
    documented_fields: set[str] = set()

    for section in _sections(source):
        if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
            truncated = True
            break
        field = section.field
        documented_fields.add(field)

        if field in {
            "admission_date",
            "discharge_date",
            "department",
            "discharge_destination",
        }:
            evidence_ref = _add_evidence(
                evidence_items,
                field=field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            del evidence_ref
            result["encounter_metadata"][field] = _append_text(
                result["encounter_metadata"][field], section.value
            )
            continue

        if field in {"admission_reason", "treatment_course", "allergies"}:
            _add_evidence(
                evidence_items,
                field=field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            result[field] = _append_text(result[field], section.value)
            continue

        if field in {"diagnoses", "primary_diagnoses", "secondary_diagnoses"}:
            role = {
                "primary_diagnoses": "DOCUMENTED_PRIMARY",
                "secondary_diagnoses": "DOCUMENTED_SECONDARY",
            }.get(field, "DOCUMENTED_UNSPECIFIED")
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field="diagnoses",
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["diagnoses"].append({
                    "text": value,
                    "role": role,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field == "procedures":
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field="procedures",
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["procedures"].append({
                    "text": value,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field in {"laboratory_results", "imaging_results"}:
            category = (
                "LABORATORY_RESULT"
                if field == "laboratory_results"
                else "IMAGING_RESULT"
            )
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field=field,
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["key_results"].append({
                    "category": category,
                    "documented_result": value,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field in {
            "general_orders",
            "medication_orders",
            "activity_orders",
            "diet_orders",
            "wound_care_orders",
        }:
            category = {
                "general_orders": "GENERAL",
                "medication_orders": "MEDICATION",
                "activity_orders": "ACTIVITY",
                "diet_orders": "DIET",
                "wound_care_orders": "WOUND_CARE",
            }[field]
            for value, span in _split_items(
                source,
                section,
                split_commas=field == "general_orders",
            ):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field="discharge_orders",
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["discharge_orders"].append({
                    "category": category,
                    "documented_instruction": value,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field == "follow_up":
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field="follow_up_recommendations",
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["follow_up_recommendations"].append({
                    "documented_instruction": value,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field == "discharge_status":
            evidence_ref = _add_evidence(
                evidence_items,
                field=field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            result["discharge_status"] = {
                "documented_text": section.value,
                "normalized_status": _normalized_discharge_status(section.value),
                "evidence_ref": evidence_ref,
            }
            continue

        if field in {"pending_results", "complications"}:
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field=field,
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result[field].append({
                    "documented_text": value,
                    "evidence_ref": evidence_ref,
                })
            continue

        if field == "conflicts":
            for value, span in _split_items(source, section):
                if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                    truncated = True
                    break
                evidence_ref = _add_evidence(
                    evidence_items,
                    field=field,
                    source_label=section.label,
                    evidence_text=value,
                    char_span=span,
                )
                result["conflicts"].append({
                    "description": value,
                    "resolution": UNRESOLVED_CONFLICT,
                    "evidence_ref": evidence_ref,
                })

    if not evidence_items:
        result["source_completeness"]["input_truncated"] = truncated
        result["_trace"] = {
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "evidence_items_count": 0,
            "valid_spans_count": 0,
            "multiline_sections_count": 0,
            "clinical_inference_performed": False,
        }
        return result

    core_present = {
        "diagnoses": bool(result["diagnoses"]),
        "treatment_course": bool(result["treatment_course"]),
        "discharge_orders": bool(result["discharge_orders"]),
        "follow_up_recommendations": bool(result["follow_up_recommendations"]),
        "discharge_status": bool(result["discharge_status"]["documented_text"]),
    }
    missing_sections = [
        _CORE_SECTION_NAMES[field]
        for field, present in core_present.items()
        if not present
    ]
    result["structuring_status"] = "PARTIAL" if missing_sections else "COMPLETED"
    result["missing_sections"] = missing_sections
    result["evidence_items"] = evidence_items
    result["source_completeness"] = {
        "documented_sections": sorted(documented_fields),
        "missing_sections": missing_sections,
        "input_truncated": truncated,
        "evidence_item_count": len(evidence_items),
    }
    valid_spans = sum(
        1
        for item in evidence_items
        if source[slice(*item["char_span"])] == item["evidence_text"]
    )
    result["_trace"] = {
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "evidence_items_count": len(evidence_items),
        "valid_spans_count": valid_spans,
        "multiline_sections_count": sum("\n" in section.value for section in _sections(source)),
        "clinical_inference_performed": False,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "MAX_EVIDENCE_ITEMS",
    "OUTPUT_CONTRACT_REF",
    "SUMMARY_GENERATION_STATUS",
    "build_discharge_summary",
    "to_pack_output",
    "verify_discharge_summary_health",
]
