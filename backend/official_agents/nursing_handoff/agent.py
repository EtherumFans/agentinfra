"""Evidence-bound local nursing shift handoff baseline.

The local runtime accepts at most ten explicitly delimited patient sections and
extracts only labelled handoff fields.  It can reorder documented facts into a
stable SBAR-shaped contract, but it does not infer acuity, clinical priority,
new nursing actions, medication state, device condition, or escalation
thresholds.  Every extracted field is bound to an exact ``[start, end)`` span
in the submitted text and every output requires receiving-nurse review.
"""

from __future__ import annotations

import re
import uuid
from typing import Any


AGENT_REF = "icoder/nursing-handoff@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_nursing_handoff"
OUTPUT_CONTRACT_REF = "icoder/NursingHandoffOutput/v4"
MAX_INPUT_CHARS = 30_000
MAX_PATIENTS = 10
MAX_EVIDENCE_ITEMS = 200

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_PATIENT_RE = re.compile(
    r"(?im)^[ \t]*(?:患者|patient)\s*[：:]\s*(?P<value>[^\r\n]{1,160})"
)
_FIELD_RE = re.compile(
    r"(?im)^[ \t]*(?P<label>"
    r"床位|房间/床位|房间/床|room/bed|"
    r"主要问题|入院诊断|主要诊断|primary issue|"
    r"当前状态|现状|current status|"
    r"背景|既往史|background|"
    r"本班事件|近期事件|班次事件|recent events?|"
    r"管路/设备|<REDACTED:NAME>/设备|管路|导管|LDA|lines/devices|"
    r"用药/MAR|用药|药物|MAR|medications?|"
    r"检验/检查|实验室/检查|检验检查|待回结果|labs?/diagnostics?|"
    r"待办|未完成任务|随访事项|任务|pending tasks?|"
    r"安全/预防|<REDACTED:NAME>/预防|安全风险|护理风险|注意事项|safety/precautions|"
    r"升级触发|报告条件|上报条件|escalation triggers?|"
    r"矛盾/缺口|记录缺口|矛盾|gaps?/contradictions?"
    r")\s*[：:]\s*(?P<value>[^\r\n]*)"
)

_LABEL_TO_FIELD = {
    "床位": "room_bed",
    "房间/床位": "room_bed",
    "房间/床": "room_bed",
    "room/bed": "room_bed",
    "主要问题": "primary_issue",
    "入院诊断": "primary_issue",
    "主要诊断": "primary_issue",
    "primary issue": "primary_issue",
    "当前状态": "current_status",
    "现状": "current_status",
    "current status": "current_status",
    "背景": "background",
    "既往史": "background",
    "background": "background",
    "本班事件": "recent_events",
    "近期事件": "recent_events",
    "班次事件": "recent_events",
    "recent event": "recent_events",
    "recent events": "recent_events",
    "管路/设备": "lines_devices",
    "<redacted:name>/设备": "lines_devices",
    "管路": "lines_devices",
    "导管": "lines_devices",
    "lda": "lines_devices",
    "lines/devices": "lines_devices",
    "用药/mar": "medications",
    "用药": "medications",
    "药物": "medications",
    "mar": "medications",
    "medication": "medications",
    "medications": "medications",
    "检验/检查": "labs_diagnostics",
    "实验室/检查": "labs_diagnostics",
    "检验检查": "labs_diagnostics",
    "待回结果": "labs_diagnostics",
    "lab/diagnostics": "labs_diagnostics",
    "labs/diagnostics": "labs_diagnostics",
    "待办": "pending_tasks",
    "未完成任务": "pending_tasks",
    "随访事项": "pending_tasks",
    "任务": "pending_tasks",
    "pending task": "pending_tasks",
    "pending tasks": "pending_tasks",
    "安全/预防": "safety_precautions",
    "<redacted:name>/预防": "safety_precautions",
    "安全风险": "safety_precautions",
    "护理风险": "safety_precautions",
    "注意事项": "safety_precautions",
    "safety/precautions": "safety_precautions",
    "升级触发": "documented_escalation_triggers",
    "报告条件": "documented_escalation_triggers",
    "上报条件": "documented_escalation_triggers",
    "escalation trigger": "documented_escalation_triggers",
    "escalation triggers": "documented_escalation_triggers",
    "矛盾/缺口": "gaps_conflicts",
    "记录缺口": "gaps_conflicts",
    "矛盾": "gaps_conflicts",
    "gap/contradictions": "gaps_conflicts",
    "gaps/contradictions": "gaps_conflicts",
}

_LIST_FIELDS = {
    "recent_events",
    "lines_devices",
    "medications",
    "labs_diagnostics",
    "pending_tasks",
    "safety_precautions",
    "documented_escalation_triggers",
    "gaps_conflicts",
}
_COMPLETENESS_FIELDS = (
    "room_bed",
    "primary_issue",
    "current_status",
    "lines_devices",
    "medications",
    "labs_diagnostics",
    "pending_tasks",
    "safety_precautions",
)
_DISPLAY_NAMES = {
    "room_bed": "床位",
    "primary_issue": "主要问题",
    "current_status": "当前状态",
    "lines_devices": "管路/设备",
    "medications": "用药/MAR",
    "labs_diagnostics": "检验/检查",
    "pending_tasks": "待办",
    "safety_precautions": "安全/预防",
}
_PENDING_MARKERS = ("待结果", "待回报", "未出", "pending")
_PUBLIC_FIELDS = (
    "handoff_status",
    "assignment_summary",
    "patient_handoffs",
    "situation",
    "background",
    "assessment",
    "recommendations",
    "safety_risks",
    "lines_devices",
    "pending_tasks",
    "escalation_triggers",
    "source_completeness",
    "evidence_items",
    "limitations",
    "clinical_priority_assessed",
    "medical_calculator_used",
    "production_writeback_blocked",
    "manual_review_required",
    "trace_refs",
)


def verify_nursing_handoff_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "medical_calculator_used": False,
        "clinical_priority_assessed": False,
        "explicit_label_extraction_available": True,
        "multi_patient_limit": MAX_PATIENTS,
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


def _empty_patient(identifier: str) -> dict[str, Any]:
    return {
        "patient_identifier": identifier,
        "room_bed": "",
        "primary_issue": "",
        "current_status": "",
        "background": "",
        "recent_events": [],
        "lines_devices": [],
        "medications": [],
        "labs_diagnostics": [],
        "pending_tasks": [],
        "safety_precautions": [],
        "documented_escalation_triggers": [],
        "gaps_conflicts": [],
        "key_considerations": [],
        "evidence_refs": [],
        "missing_sections": [],
    }


def _add_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    patient_index: int,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"handoff-evidence-{len(evidence_items) + 1}"
    evidence_items.append({
        "evidence_id": evidence_id,
        "patient_index": patient_index,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _extract_patients(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    all_patient_matches = list(_PATIENT_RE.finditer(text))
    truncated = len(all_patient_matches) > MAX_PATIENTS
    patient_matches = all_patient_matches[:MAX_PATIENTS]
    patients: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []

    for patient_index, match in enumerate(patient_matches):
        identifier, identifier_span = _trimmed_group_span(text, match, "value")
        if not identifier:
            continue
        patient = _empty_patient(identifier)
        patient["evidence_refs"].append(_add_evidence(
            evidence_items,
            patient_index=patient_index,
            field="patient_identifier",
            source_label="患者",
            evidence_text=identifier,
            char_span=identifier_span,
        ))
        section_start = match.end()
        section_end = (
            all_patient_matches[patient_index + 1].start()
            if patient_index + 1 < len(all_patient_matches)
            else len(text)
        )
        section = text[section_start:section_end]
        for field_match in _FIELD_RE.finditer(section):
            if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                truncated = True
                break
            label = field_match.group("label")
            field = _LABEL_TO_FIELD.get(label.casefold())
            if not field:
                continue
            local_value, local_span = _trimmed_group_span(section, field_match, "value")
            if not local_value:
                continue
            span = [section_start + local_span[0], section_start + local_span[1]]
            evidence_id = _add_evidence(
                evidence_items,
                patient_index=patient_index,
                field=field,
                source_label=label,
                evidence_text=local_value,
                char_span=span,
            )
            patient["evidence_refs"].append(evidence_id)
            if field in _LIST_FIELDS:
                patient[field].append(local_value)
            elif patient[field]:
                patient[field] = f"{patient[field]}；{local_value}"
            else:
                patient[field] = local_value

        patient["missing_sections"] = [
            _DISPLAY_NAMES[field]
            for field in _COMPLETENESS_FIELDS
            if not patient[field]
        ]
        pending_labs = [
            item
            for item in patient["labs_diagnostics"]
            if any(marker.casefold() in item.casefold() for marker in _PENDING_MARKERS)
        ]
        patient["key_considerations"] = list(dict.fromkeys(
            patient["pending_tasks"]
            + pending_labs
            + patient["gaps_conflicts"]
            + patient["safety_precautions"]
        ))
        patients.append(patient)

    return patients, evidence_items, truncated


def _join_patient_values(
    patients: list[dict[str, Any]],
    fields: tuple[str, ...],
    *,
    empty: str,
) -> str:
    rows: list[str] = []
    for patient in patients:
        values: list[str] = []
        for field in fields:
            value = patient.get(field)
            if isinstance(value, list):
                values.extend(str(item) for item in value if str(item).strip())
            elif str(value or "").strip():
                values.append(str(value))
        if values:
            rows.append(f"{patient['patient_identifier']}：{'；'.join(values)}")
    return " | ".join(rows) if rows else empty


def build_nursing_handoff(text: str, *, run_id: str | None = None) -> dict[str, Any]:
    source = _bounded_text(text)
    patients, evidence_items, truncated = _extract_patients(source)
    domain_evidence_count = sum(
        1 for item in evidence_items if item["field"] != "patient_identifier"
    )
    if not patients or domain_evidence_count == 0:
        status = "INPUT_REQUIRED"
    elif any(patient["missing_sections"] for patient in patients):
        status = "PARTIAL"
    else:
        status = "COMPLETED"

    assignment_summary = [
        {
            "patient_identifier": patient["patient_identifier"],
            "room_bed": patient["room_bed"],
            "primary_issue": patient["primary_issue"],
            "current_status": patient["current_status"],
            "open_items": patient["key_considerations"],
            "evidence_refs": patient["evidence_refs"],
        }
        for patient in patients
    ] if status != "INPUT_REQUIRED" else []
    public_patients = patients if status != "INPUT_REQUIRED" else []
    safety_risks = [
        item for patient in public_patients for item in patient["safety_precautions"]
    ]
    lines_devices = [
        item for patient in public_patients for item in patient["lines_devices"]
    ]
    pending_tasks = list(dict.fromkeys(
        item
        for patient in public_patients
        for item in (
            patient["pending_tasks"]
            + [
                lab for lab in patient["labs_diagnostics"]
                if any(marker.casefold() in lab.casefold() for marker in _PENDING_MARKERS)
            ]
        )
    ))
    documented_escalation = [
        item
        for patient in public_patients
        for item in patient["documented_escalation_triggers"]
    ]
    all_missing = sorted({
        item for patient in public_patients for item in patient["missing_sections"]
    })
    valid_spans = sum(
        1
        for item in evidence_items
        if source[slice(*item["char_span"])] == item["evidence_text"]
    )
    trace_id = run_id or f"nursing-handoff-{uuid.uuid4().hex}"

    result = {
        "handoff_status": status,
        "assignment_summary": assignment_summary,
        "patient_handoffs": public_patients,
        "situation": _join_patient_values(
            public_patients,
            ("primary_issue", "current_status", "recent_events"),
            empty="未获得明确标注的患者交班内容。",
        ),
        "background": _join_patient_values(
            public_patients,
            ("background",),
            empty="未记录；本地基线不补写背景信息。",
        ),
        "assessment": _join_patient_values(
            public_patients,
            ("current_status", "labs_diagnostics", "safety_precautions"),
            empty="未记录；本地基线不生成临床评估。",
        ),
        "recommendations": _join_patient_values(
            public_patients,
            ("pending_tasks",),
            empty="未记录；本地基线不生成护理建议或新医嘱。",
        ),
        "safety_risks": safety_risks,
        "lines_devices": lines_devices,
        "pending_tasks": pending_tasks,
        "escalation_triggers": (
            "；".join(documented_escalation)
            if documented_escalation
            else "未记录；本地基线不生成临床升级阈值。"
        ),
        "source_completeness": {
            "patient_count": len(public_patients),
            "max_patients": MAX_PATIENTS,
            "missing_sections": all_missing,
            "input_truncated": truncated or len(str(text or "")) > len(source),
        },
        "evidence_items": evidence_items if status != "INPUT_REQUIRED" else [],
        "limitations": [
            "仅解析明确的患者分区与字段标签；未标注自由文本不会被重写为护理事实。",
            "未评估患者病情轻重、护理优先级、生命体征阈值或治疗方案。",
            "未连接真实护理系统、MAR、检验系统、设备状态或 Medical Calculator。",
            "所有待办、风险、管路状态和升级条件均须接班护士对照原始记录核验。",
        ] + ([f"输入超过本地上限，仅处理前 {MAX_PATIENTS} 个患者或前 {MAX_INPUT_CHARS} 个字符。"] if truncated else []),
        "clinical_priority_assessed": False,
        "medical_calculator_used": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-nursing-handoff"],
        },
        "_trace": {
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "evidence_items_count": len(evidence_items) if status != "INPUT_REQUIRED" else 0,
            "valid_spans_count": valid_spans if status != "INPUT_REQUIRED" else 0,
            "patient_count": len(public_patients),
            "clinical_priority_assessed": False,
            "medical_calculator_used": False,
        },
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_nursing_handoff",
    "to_pack_output",
    "verify_nursing_handoff_health",
]
