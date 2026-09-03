"""Evidence-bound local referral-letter drafting baseline.

Only explicitly headed Chinese or English fields are copied into a fixed
clinician-to-clinician referral template.  The module never infers urgency,
specialty, diagnoses, requested actions, missing tests, or treatment advice.
Every clinical fact points to an exact ``[start, end)`` span in the redacted
input.  The result is always a review-only draft and is never transmitted.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/referral-gen@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_referral_drafting"
OUTPUT_CONTRACT_REF = "icoder/ReferralOutput/v3"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 160
MAX_ITEMS_PER_SECTION = 50
DRAFT_GENERATION_STATUS = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "\nignore previous",
    "ICODER_PROMPT_CANARY_",
)

_LABEL_TO_FIELD = {
    "患者姓名": "patient_name",
    "姓名": "patient_name",
    "patient name": "patient_name",
    "出生日期": "date_of_birth",
    "出生年月": "date_of_birth",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "病历号": "medical_record_number",
    "住院号": "medical_record_number",
    "门诊号": "medical_record_number",
    "mrn": "medical_record_number",
    "medical record number": "medical_record_number",
    "转出医师": "referring_clinician",
    "转诊医师": "referring_clinician",
    "referring clinician": "referring_clinician",
    "referring provider": "referring_clinician",
    "转出机构": "referring_facility",
    "转出医院": "referring_facility",
    "referring facility": "referring_facility",
    "转出科室": "referring_department",
    "referring department": "referring_department",
    "转出方联系方式": "referring_contact",
    "转出医师联系方式": "referring_contact",
    "referring contact": "referring_contact",
    "接诊医师": "receiving_clinician",
    "接收医师": "receiving_clinician",
    "receiving clinician": "receiving_clinician",
    "receiving provider": "receiving_clinician",
    "目标专科": "receiving_specialty",
    "接收专科": "receiving_specialty",
    "转诊科室": "receiving_specialty",
    "receiving specialty": "receiving_specialty",
    "接收机构": "receiving_facility",
    "接收医院": "receiving_facility",
    "receiving facility": "receiving_facility",
    "转诊方向": "referral_direction",
    "referral direction": "referral_direction",
    "转诊原因": "referral_reason",
    "reason for referral": "referral_reason",
    "referral reason": "referral_reason",
    "紧急程度": "urgency",
    "转诊紧急程度": "urgency",
    "urgency": "urgency",
    "期望时间": "timeframe",
    "预约时限": "timeframe",
    "转诊时限": "timeframe",
    "desired timeframe": "timeframe",
    "timeframe": "timeframe",
    "主诉": "chief_concern",
    "主要问题": "chief_concern",
    "chief concern": "chief_concern",
    "chief complaint": "chief_concern",
    "相关病史": "relevant_history",
    "既往史": "relevant_history",
    "relevant history": "relevant_history",
    "当前情况": "current_presentation",
    "现病情况": "current_presentation",
    "current presentation": "current_presentation",
    "工作诊断": "working_assessment",
    "临床印象": "working_assessment",
    "已记录诊断": "working_assessment",
    "working assessment": "working_assessment",
    "检查结果": "diagnostic_results",
    "检验影像": "diagnostic_results",
    "diagnostic results": "diagnostic_results",
    "当前用药": "medications",
    "用药清单": "medications",
    "current medications": "medications",
    "medications": "medications",
    "过敏史": "allergies",
    "过敏": "allergies",
    "allergies": "allergies",
    "请求事项": "requested_action",
    "会诊问题": "requested_action",
    "转诊请求": "requested_action",
    "requested action": "requested_action",
    "接收方需完成": "requested_action",
}

_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*"
    rf"(?:[：:][ \t]*(?P<inline>[^\r\n]*)|(?P<line_end>\r?\n|$))"
)
_REDACTED_MRN_LINE_RE = re.compile(
    r"(?m)^[ \t]*(?P<value><REDACTED:MEDICAL_RECORD_NO>"
    r"(?:<REDACTED:PHONE>)?)[ \t]*(?:\r?\n|$)"
)
_REDACTED_HISTORY_LINE_RE = re.compile(
    r"(?m)^[ \t]*(?P<label><REDACTED:NAME>史)[ \t]*[：:]"
    r"[ \t]*(?P<value>[^\r\n]*)"
)
_ITEM_SEPARATOR_RE = re.compile(r"[；;]\s*|\r?\n+")
_LEADING_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]*)"
)

_CORE_FIELDS = {
    "patient_name": "患者姓名",
    "date_of_birth": "出生日期",
    "medical_record_number": "病历号/住院号/门诊号",
    "referring_clinician": "转出医师",
    "receiving_specialty": "目标专科",
    "referral_reason": "转诊原因",
    "urgency": "紧急程度",
    "timeframe": "期望时间",
    "requested_action": "请求事项",
}
_SUPPORTING_FIELDS = {
    "chief_concern": "主诉/主要问题",
    "medications": "当前用药",
    "allergies": "过敏史",
    "diagnostic_results": "检查结果",
}

_PUBLIC_FIELDS = (
    "referral_status",
    "referral_direction",
    "patient_identifiers",
    "referring_party",
    "receiving_party",
    "referral_reason",
    "urgency",
    "clinical_summary",
    "diagnostic_results",
    "medications",
    "allergies",
    "requested_action",
    "referral_letter_draft",
    "missing_required_fields",
    "missing_supporting_items",
    "evidence_items",
    "limitations",
    "draft_generation_status",
    "clinical_inference_performed",
    "new_diagnosis_generated",
    "new_treatment_recommended",
    "external_knowledge_used",
    "production_transmission_blocked",
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


def verify_referral_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "multiline_section_parsing_available": True,
        "unlabelled_narrative_summarized": False,
        "clinical_inference_performed": False,
        "new_diagnosis_generated": False,
        "new_treatment_recommended": False,
        "production_transmission_blocked": True,
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
    redacted_mrn_matches = list(_REDACTED_MRN_LINE_RE.finditer(source))
    redacted_history_matches = list(_REDACTED_HISTORY_LINE_RE.finditer(source))
    boundaries = sorted(
        [match.start() for match in matches]
        + [match.start() for match in redacted_mrn_matches]
        + [match.start() for match in redacted_history_matches]
    )
    sections: list[Section] = []
    for match in matches:
        next_start = next(
            (boundary for boundary in boundaries if boundary > match.start()),
            len(source),
        )
        start = match.start("inline") if match.group("inline") is not None else match.end()
        value, span = _trim_span(source, start, next_start)
        if value:
            sections.append(Section(
                field=_LABEL_TO_FIELD[match.group("label").casefold()],
                label=match.group("label"),
                value=value,
                span=span,
            ))
    for match in redacted_mrn_matches:
        value, span = _trim_span(source, match.start("value"), match.end("value"))
        sections.append(Section(
            field="medical_record_number",
            label="<REDACTED:MEDICAL_RECORD_NO>",
            value=value,
            span=span,
        ))
    for match in redacted_history_matches:
        value, span = _trim_span(source, match.start("value"), match.end("value"))
        if value:
            sections.append(Section(
                field="relevant_history",
                label=match.group("label"),
                value=value,
                span=span,
            ))
    sections.sort(key=lambda section: section.span[0])
    return sections


def _split_items(source: str, section: Section) -> list[tuple[str, list[int]]]:
    parts: list[tuple[str, list[int]]] = []
    cursor = 0
    for match in list(_ITEM_SEPARATOR_RE.finditer(section.value)) + [None]:
        raw_end = match.start() if match is not None else len(section.value)
        raw_start = cursor
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
    items: list[dict[str, Any]],
    *,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"referral-evidence-{len(items) + 1}"
    items.append({
        "evidence_id": evidence_id,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _blank_result(trace_id: str) -> dict[str, Any]:
    return {
        "referral_status": "INPUT_REQUIRED",
        "referral_direction": _fact(),
        "patient_identifiers": {
            "name": _fact(),
            "date_of_birth": _fact(),
            "medical_record_number": _fact(),
        },
        "referring_party": {
            "clinician": _fact(),
            "facility": _fact(),
            "department": _fact(),
            "contact": _fact(),
        },
        "receiving_party": {
            "clinician": _fact(),
            "specialty": _fact(),
            "facility": _fact(),
        },
        "referral_reason": _fact(),
        "urgency": {"documented_level": "", "documented_timeframe": "", "evidence_refs": []},
        "clinical_summary": {
            "chief_concern": _fact(),
            "relevant_history": _fact(),
            "current_presentation": _fact(),
            "working_assessment": _fact(),
        },
        "diagnostic_results": [],
        "medications": [],
        "allergies": [],
        "requested_action": _fact(),
        "referral_letter_draft": "",
        "missing_required_fields": list(_CORE_FIELDS.values()),
        "missing_supporting_items": list(_SUPPORTING_FIELDS.values()),
        "evidence_items": [],
        "limitations": [
            "仅解析明确的中英文转诊字段标题；未标注自由叙事不会被自动总结。",
            "仅将逐字记录的内容装配进固定模板；未推断转诊原因、目标专科、紧急程度或时限。",
            "未新增诊断、鉴别诊断、治疗建议、检查建议、用药变更或待补材料。",
            "未调用指南、药品、医保、区域转诊目录或其他外部知识。",
            "未连接真实 HIS/EMR、区域转诊平台、预约系统、短信或传真服务。",
            "草案禁止自动发送或写回，必须由转出医师逐项复核。",
        ],
        "draft_generation_status": DRAFT_GENERATION_STATUS,
        "clinical_inference_performed": False,
        "new_diagnosis_generated": False,
        "new_treatment_recommended": False,
        "external_knowledge_used": False,
        "production_transmission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-referral"],
        },
    }


_SCALAR_TARGETS = {
    "patient_name": ("patient_identifiers", "name"),
    "date_of_birth": ("patient_identifiers", "date_of_birth"),
    "medical_record_number": ("patient_identifiers", "medical_record_number"),
    "referring_clinician": ("referring_party", "clinician"),
    "referring_facility": ("referring_party", "facility"),
    "referring_department": ("referring_party", "department"),
    "referring_contact": ("referring_party", "contact"),
    "receiving_clinician": ("receiving_party", "clinician"),
    "receiving_specialty": ("receiving_party", "specialty"),
    "receiving_facility": ("receiving_party", "facility"),
    "referral_direction": ("referral_direction",),
    "referral_reason": ("referral_reason",),
    "chief_concern": ("clinical_summary", "chief_concern"),
    "relevant_history": ("clinical_summary", "relevant_history"),
    "current_presentation": ("clinical_summary", "current_presentation"),
    "working_assessment": ("clinical_summary", "working_assessment"),
    "requested_action": ("requested_action",),
}


def _set_fact(result: dict[str, Any], target: tuple[str, ...], value: str, evidence_ref: str) -> None:
    container: dict[str, Any] = result
    for key in target[:-1]:
        container = container[key]
    key = target[-1]
    current = container[key]
    if current["documented_text"]:
        current["documented_text"] += "\n" + value
    else:
        current["documented_text"] = value
    current["evidence_ref"] = evidence_ref


def _documented_field(result: dict[str, Any], field: str) -> bool:
    if field in _SCALAR_TARGETS:
        container: Any = result
        for key in _SCALAR_TARGETS[field]:
            container = container[key]
        return bool(container.get("documented_text"))
    if field == "urgency":
        return bool(result["urgency"]["documented_level"])
    if field == "timeframe":
        return bool(result["urgency"]["documented_timeframe"])
    return bool(result.get(field))


def _draft(result: dict[str, Any]) -> str:
    def text(fact: dict[str, str]) -> str:
        return fact["documented_text"] or "未记录"

    diagnostics = "；".join(item["documented_text"] for item in result["diagnostic_results"]) or "未记录"
    medications = "；".join(item["documented_text"] for item in result["medications"]) or "未记录"
    allergies = "；".join(item["documented_text"] for item in result["allergies"]) or "未记录"
    return "\n".join([
        "## 转诊信草案",
        f"患者：{text(result['patient_identifiers']['name'])}",
        f"出生日期：{text(result['patient_identifiers']['date_of_birth'])}",
        f"病历号：{text(result['patient_identifiers']['medical_record_number'])}",
        f"转出医师：{text(result['referring_party']['clinician'])}",
        f"转出机构/科室：{text(result['referring_party']['facility'])} / {text(result['referring_party']['department'])}",
        f"接收医师/专科：{text(result['receiving_party']['clinician'])} / {text(result['receiving_party']['specialty'])}",
        f"接收机构：{text(result['receiving_party']['facility'])}",
        f"紧急程度：{result['urgency']['documented_level'] or '未记录'}",
        f"期望时间：{result['urgency']['documented_timeframe'] or '未记录'}",
        f"转诊原因：{text(result['referral_reason'])}",
        f"主诉/主要问题：{text(result['clinical_summary']['chief_concern'])}",
        f"相关病史：{text(result['clinical_summary']['relevant_history'])}",
        f"当前情况：{text(result['clinical_summary']['current_presentation'])}",
        f"已记录诊断/临床印象：{text(result['clinical_summary']['working_assessment'])}",
        f"检查结果：{diagnostics}",
        f"当前用药：{medications}",
        f"过敏史：{allergies}",
        f"请求事项：{text(result['requested_action'])}",
        f"转出方联系方式：{text(result['referring_party']['contact'])}",
        "状态：仅供转出医师复核，禁止自动发送或写回。",
    ])


def build_referral(text: str, *, run_id: str | None = None) -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    trace_id = run_id or f"referral-{uuid.uuid4().hex}"
    result = _blank_result(trace_id)
    evidence_items: list[dict[str, Any]] = []

    for section in _sections(source):
        if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
            truncated = True
            break
        field = section.field
        if field in _SCALAR_TARGETS:
            evidence_ref = _add_evidence(
                evidence_items,
                field=field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            _set_fact(result, _SCALAR_TARGETS[field], section.value, evidence_ref)
            continue
        if field in {"urgency", "timeframe"}:
            evidence_ref = _add_evidence(
                evidence_items,
                field=field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            target = "documented_level" if field == "urgency" else "documented_timeframe"
            result["urgency"][target] = section.value
            result["urgency"]["evidence_refs"].append(evidence_ref)
            continue
        if field in {"diagnostic_results", "medications", "allergies"}:
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
                result[field].append(_fact(value, evidence_ref))

    missing_required = [
        label for field, label in _CORE_FIELDS.items()
        if not _documented_field(result, field)
    ]
    missing_supporting = [
        label for field, label in _SUPPORTING_FIELDS.items()
        if not _documented_field(result, field)
    ]
    result["missing_required_fields"] = missing_required
    result["missing_supporting_items"] = missing_supporting
    result["evidence_items"] = evidence_items

    if missing_required:
        result["referral_status"] = "INPUT_REQUIRED"
    elif missing_supporting:
        result["referral_status"] = "PARTIAL"
        result["referral_letter_draft"] = _draft(result)
    else:
        result["referral_status"] = "READY_FOR_REVIEW"
        result["referral_letter_draft"] = _draft(result)

    valid_spans = sum(
        1 for item in evidence_items
        if source[slice(*item["char_span"])] == item["evidence_text"]
    )
    result["_trace"] = {
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "evidence_items_count": len(evidence_items),
        "valid_spans_count": valid_spans,
        "input_truncated": truncated,
        "clinical_inference_performed": False,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "DRAFT_GENERATION_STATUS",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_referral",
    "to_pack_output",
    "verify_referral_health",
]
