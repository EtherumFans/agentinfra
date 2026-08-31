"""Evidence-bound local prior-authorization packet assembly.

The baseline copies only explicitly headed Chinese or English fields into a
fixed review-only packet.  It does not infer payer criteria, medical
necessity, diagnoses, codes, clinical scores, missing clinical tests, or
treatment recommendations.  Every copied fact is bound to an exact span in
the redacted input.  Submission and health-record writeback are always
blocked.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/prior-auth@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_prior_authorization"
OUTPUT_CONTRACT_REF = "icoder/PriorAuthorizationOutput/v5"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200
MAX_ITEMS_PER_SECTION = 60
DRAFT_GENERATION_STATUS = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
MEDICAL_NECESSITY_STATUS = "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"

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
    "参保人编号": "member_id",
    "参保编号": "member_id",
    "医保编号": "member_id",
    "保险会员号": "member_id",
    "member id": "member_id",
    "insurance member id": "member_id",
    "申请医师": "provider_name",
    "经治医师": "provider_name",
    "provider name": "provider_name",
    "申请医师资质": "provider_credentials",
    "医师资质": "provider_credentials",
    "provider credentials": "provider_credentials",
    "医师执业编号": "provider_identifier",
    "医师编号": "provider_identifier",
    "npi": "provider_identifier",
    "provider identifier": "provider_identifier",
    "申请机构": "provider_facility",
    "医疗机构": "provider_facility",
    "provider facility": "provider_facility",
    "申请方联系方式": "provider_contact",
    "医师联系方式": "provider_contact",
    "provider contact": "provider_contact",
    "支付方": "payer_name",
    "保险公司": "payer_name",
    "医保经办机构": "payer_name",
    "payer": "payer_name",
    "insurance company": "payer_name",
    "保险计划": "plan_name",
    "医保计划": "plan_name",
    "plan name": "plan_name",
    "统筹区": "payer_region",
    "参保地": "payer_region",
    "payer region": "payer_region",
    "申请类型": "request_type",
    "预授权类型": "request_type",
    "request type": "request_type",
    "申请药品": "requested_item_name",
    "申请项目": "requested_item_name",
    "申请服务": "requested_item_name",
    "requested medication": "requested_item_name",
    "requested item": "requested_item_name",
    "剂量": "dose",
    "dose": "dose",
    "给药途径": "route",
    "route": "route",
    "用药频次": "frequency",
    "频次": "frequency",
    "frequency": "frequency",
    "疗程": "duration",
    "申请时长": "duration",
    "duration": "duration",
    "申请编码": "requested_code",
    "药品编码": "requested_code",
    "procedure code": "requested_code",
    "requested code": "requested_code",
    "已记录诊断": "diagnosis_context",
    "诊断依据": "diagnosis_context",
    "诊断": "diagnosis_context",
    "diagnosis": "diagnosis_context",
    "诊断编码": "diagnosis_code",
    "icd-10": "diagnosis_code",
    "diagnosis code": "diagnosis_code",
    "申请原因": "request_reason",
    "申请目的": "request_reason",
    "request reason": "request_reason",
    "临床文书摘录": "clinical_documentation",
    "相关病历记录": "clinical_documentation",
    "clinical documentation": "clinical_documentation",
    "客观证据": "objective_evidence",
    "检查结果": "objective_evidence",
    "objective evidence": "objective_evidence",
    "既往治疗": "prior_treatments",
    "既往用药": "prior_treatments",
    "prior treatment": "prior_treatments",
    "prior medication trials": "prior_treatments",
    "禁忌或不耐受": "contraindications_intolerances",
    "禁忌证": "contraindications_intolerances",
    "不耐受": "contraindications_intolerances",
    "contraindications or intolerances": "contraindications_intolerances",
    "支付方要求": "payer_requirements",
    "预授权标准": "payer_requirements",
    "payer requirements": "payer_requirements",
    "支付政策编号": "policy_identifier",
    "政策编号": "policy_identifier",
    "policy identifier": "policy_identifier",
    "支付政策版本": "policy_version",
    "政策版本": "policy_version",
    "policy version": "policy_version",
    "政策生效日期": "policy_effective_date",
    "policy effective date": "policy_effective_date",
    "政策来源": "policy_source",
    "payer policy source": "policy_source",
    "policy source": "policy_source",
    "已记录医疗必要性说明": "documented_medical_necessity",
    "医师医疗必要性说明": "documented_medical_necessity",
    "documented medical necessity": "documented_medical_necessity",
    "既往拒绝原因": "denial_reason",
    "拒绝原因": "denial_reason",
    "prior denial reason": "denial_reason",
}

_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*"
    rf"(?:[：:][ \t]*(?P<inline>[^\r\n]*)|(?P<line_end>\r?\n|$))"
)
_ITEM_SEPARATOR_RE = re.compile(r"[；;]\s*|\r?\n+")
_LEADING_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]*)"
)

_CORE_FIELDS = {
    "patient_name": "患者姓名",
    "date_of_birth": "出生日期",
    "member_id": "参保人编号/保险会员号",
    "provider_name": "申请医师",
    "provider_credentials": "申请医师资质",
    "provider_identifier": "医师执业编号/NPI",
    "payer_name": "支付方/保险公司",
    "request_type": "申请类型",
    "requested_item_name": "申请药品/项目",
    "diagnosis_context": "已记录诊断",
    "request_reason": "申请原因",
    "clinical_documentation": "临床文书摘录",
}
_MEDICATION_CORE_FIELDS = {
    "dose": "剂量",
    "route": "给药途径",
    "frequency": "用药频次",
}
_SUPPORTING_FIELDS = {
    "duration": "疗程/申请时长",
    "objective_evidence": "客观证据",
    "prior_treatments": "既往治疗/用药",
    "contraindications_intolerances": "禁忌或不耐受",
    "documented_medical_necessity": "已记录医疗必要性说明",
}
_POLICY_FIELDS = {
    "payer_requirements": "支付方要求",
    "policy_identifier": "支付政策编号",
    "policy_version": "支付政策版本",
    "policy_effective_date": "政策生效日期",
    "policy_source": "政策来源",
}
_MEDICATION_TERMS = ("药品", "药物", "用药", "medication", "drug", "pharmacy")

_PUBLIC_FIELDS = (
    "authorization_status",
    "request_type",
    "patient_information",
    "provider_information",
    "payer_information",
    "requested_item",
    "diagnosis_context",
    "request_reason",
    "clinical_documentation",
    "objective_evidence",
    "prior_treatments",
    "contraindications_intolerances",
    "payer_policy",
    "documented_medical_necessity",
    "denial_reason",
    "missing_required_fields",
    "missing_supporting_items",
    "missing_policy_items",
    "authorization_packet_draft",
    "policy_evaluation_status",
    "medical_necessity_assessment_status",
    "evidence_items",
    "limitations",
    "draft_generation_status",
    "clinical_inference_performed",
    "new_diagnosis_generated",
    "new_treatment_recommended",
    "external_knowledge_used",
    "medical_calculator_used",
    "medical_coding_validation_performed",
    "production_submission_blocked",
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


def verify_prior_authorization_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "payer_policy_lookup_performed": False,
        "medical_necessity_assessed": False,
        "clinical_inference_performed": False,
        "medical_calculator_used": False,
        "medical_coding_validation_performed": False,
        "production_submission_blocked": True,
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
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        start = match.start("inline") if match.group("inline") is not None else match.end()
        value, span = _trim_span(source, start, end)
        if value:
            sections.append(Section(
                field=_LABEL_TO_FIELD[match.group("label").casefold()],
                label=match.group("label"),
                value=value,
                span=span,
            ))
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


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _add_evidence(
    items: list[dict[str, Any]],
    *,
    field: str,
    source_label: str,
    evidence_text: str,
    char_span: list[int],
) -> str:
    evidence_id = f"prior-auth-evidence-{len(items) + 1}"
    items.append({
        "evidence_id": evidence_id,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _blank_result(trace_id: str) -> dict[str, Any]:
    return {
        "authorization_status": "INPUT_REQUIRED",
        "request_type": _fact(),
        "patient_information": {
            "name": _fact(),
            "date_of_birth": _fact(),
            "member_id": _fact(),
        },
        "provider_information": {
            "name": _fact(),
            "credentials": _fact(),
            "provider_identifier": _fact(),
            "facility": _fact(),
            "contact": _fact(),
        },
        "payer_information": {
            "payer_name": _fact(),
            "plan_name": _fact(),
            "region": _fact(),
        },
        "requested_item": {
            "name": _fact(),
            "dose": _fact(),
            "route": _fact(),
            "frequency": _fact(),
            "duration": _fact(),
            "documented_code": _fact(),
        },
        "diagnosis_context": [],
        "request_reason": _fact(),
        "clinical_documentation": [],
        "objective_evidence": [],
        "prior_treatments": [],
        "contraindications_intolerances": [],
        "payer_policy": {
            "requirements": [],
            "policy_identifier": _fact(),
            "version": _fact(),
            "effective_date": _fact(),
            "source": _fact(),
        },
        "documented_medical_necessity": _fact(),
        "denial_reason": _fact(),
        "missing_required_fields": list(_CORE_FIELDS.values()),
        "missing_supporting_items": list(_SUPPORTING_FIELDS.values()),
        "missing_policy_items": list(_POLICY_FIELDS.values()),
        "authorization_packet_draft": "",
        "policy_evaluation_status": "POLICY_NOT_PROVIDED",
        "medical_necessity_assessment_status": MEDICAL_NECESSITY_STATUS,
        "evidence_items": [],
        "limitations": [
            "仅解析明确的中英文预授权字段标题；未标注自由叙事不会被自动总结。",
            "仅逐字装配已记录事实；未评估、确认或推断医疗必要性、适应证、严重程度或支付资格。",
            "未调用支付方网站、医保目录、商保规则、PubMed、指南、药品库或其他外部知识。",
            "未计算风险或严重程度评分，未校验 ICD、药品、项目或耗材编码。",
            "未新增诊断、既往治疗失败、禁忌、不耐受、检查结果、政策条款或缺失临床项目。",
            "未连接真实 HIS/EMR、医保/商保平台、表单、传真或提交接口。",
            "证据包禁止自动提交或写回，必须由临床人员和医保/商保专员逐项复核。",
        ],
        "draft_generation_status": DRAFT_GENERATION_STATUS,
        "clinical_inference_performed": False,
        "new_diagnosis_generated": False,
        "new_treatment_recommended": False,
        "external_knowledge_used": False,
        "medical_calculator_used": False,
        "medical_coding_validation_performed": False,
        "production_submission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-prior-authorization"],
        },
    }


_SCALAR_TARGETS = {
    "request_type": ("request_type",),
    "patient_name": ("patient_information", "name"),
    "date_of_birth": ("patient_information", "date_of_birth"),
    "member_id": ("patient_information", "member_id"),
    "provider_name": ("provider_information", "name"),
    "provider_credentials": ("provider_information", "credentials"),
    "provider_identifier": ("provider_information", "provider_identifier"),
    "provider_facility": ("provider_information", "facility"),
    "provider_contact": ("provider_information", "contact"),
    "payer_name": ("payer_information", "payer_name"),
    "plan_name": ("payer_information", "plan_name"),
    "payer_region": ("payer_information", "region"),
    "requested_item_name": ("requested_item", "name"),
    "dose": ("requested_item", "dose"),
    "route": ("requested_item", "route"),
    "frequency": ("requested_item", "frequency"),
    "duration": ("requested_item", "duration"),
    "requested_code": ("requested_item", "documented_code"),
    "request_reason": ("request_reason",),
    "policy_identifier": ("payer_policy", "policy_identifier"),
    "policy_version": ("payer_policy", "version"),
    "policy_effective_date": ("payer_policy", "effective_date"),
    "policy_source": ("payer_policy", "source"),
    "documented_medical_necessity": ("documented_medical_necessity",),
    "denial_reason": ("denial_reason",),
}
_LIST_TARGETS = {
    "diagnosis_context": "diagnosis_context",
    "diagnosis_code": "diagnosis_context",
    "clinical_documentation": "clinical_documentation",
    "objective_evidence": "objective_evidence",
    "prior_treatments": "prior_treatments",
    "contraindications_intolerances": "contraindications_intolerances",
    "payer_requirements": "payer_policy.requirements",
}


def _set_fact(
    result: dict[str, Any], target: tuple[str, ...], value: str, evidence_ref: str
) -> None:
    container: dict[str, Any] = result
    for key in target[:-1]:
        container = container[key]
    fact = container[target[-1]]
    fact["documented_text"] = (
        f"{fact['documented_text']}\n{value}" if fact["documented_text"] else value
    )
    fact["evidence_ref"] = evidence_ref


def _get_target(result: dict[str, Any], target: tuple[str, ...]) -> Any:
    value: Any = result
    for key in target:
        value = value[key]
    return value


def _documented(result: dict[str, Any], field: str) -> bool:
    if field in _SCALAR_TARGETS:
        return bool(_get_target(result, _SCALAR_TARGETS[field])["documented_text"])
    if field in {"diagnosis_context", "diagnosis_code"}:
        return bool(result["diagnosis_context"])
    if field in _LIST_TARGETS:
        target = _LIST_TARGETS[field]
        if target == "payer_policy.requirements":
            return bool(result["payer_policy"]["requirements"])
        return bool(result[target])
    return False


def _is_medication_request(result: dict[str, Any]) -> bool:
    value = result["request_type"]["documented_text"].casefold()
    return any(term in value for term in _MEDICATION_TERMS)


def _draft(result: dict[str, Any]) -> str:
    def text(fact: dict[str, str]) -> str:
        return fact["documented_text"] or "未记录"

    def joined(items: list[dict[str, str]]) -> str:
        return "；".join(item["documented_text"] for item in items) or "未记录"

    policy = result["payer_policy"]
    requested = result["requested_item"]
    return "\n".join([
        "## 预授权证据包草案",
        f"患者姓名：{text(result['patient_information']['name'])}",
        f"出生日期：{text(result['patient_information']['date_of_birth'])}",
        f"参保人编号：{text(result['patient_information']['member_id'])}",
        f"申请医师：{text(result['provider_information']['name'])}",
        f"医师资质：{text(result['provider_information']['credentials'])}",
        f"医师执业编号/NPI：{text(result['provider_information']['provider_identifier'])}",
        f"申请机构：{text(result['provider_information']['facility'])}",
        f"申请方联系方式：{text(result['provider_information']['contact'])}",
        f"支付方：{text(result['payer_information']['payer_name'])}",
        f"保险/医保计划：{text(result['payer_information']['plan_name'])}",
        f"统筹区/参保地：{text(result['payer_information']['region'])}",
        f"申请类型：{text(result['request_type'])}",
        f"申请药品/项目：{text(requested['name'])}",
        f"剂量/途径/频次/疗程：{text(requested['dose'])} / {text(requested['route'])} / {text(requested['frequency'])} / {text(requested['duration'])}",
        f"已记录编码：{text(requested['documented_code'])}",
        f"已记录诊断及编码：{joined(result['diagnosis_context'])}",
        f"申请原因：{text(result['request_reason'])}",
        f"临床文书摘录：{joined(result['clinical_documentation'])}",
        f"客观证据：{joined(result['objective_evidence'])}",
        f"既往治疗/用药：{joined(result['prior_treatments'])}",
        f"禁忌或不耐受：{joined(result['contraindications_intolerances'])}",
        f"支付方要求：{joined(policy['requirements'])}",
        f"政策编号/版本/生效日期：{text(policy['policy_identifier'])} / {text(policy['version'])} / {text(policy['effective_date'])}",
        f"政策来源：{text(policy['source'])}",
        f"医师已记录的医疗必要性说明：{text(result['documented_medical_necessity'])}",
        f"既往拒绝原因：{text(result['denial_reason'])}",
        f"政策评估状态：{result['policy_evaluation_status']}",
        f"医疗必要性评估状态：{MEDICAL_NECESSITY_STATUS}",
        "声明：本草案仅逐字装配已提供材料，不构成支付政策符合性或医疗必要性结论；禁止自动提交或写回。",
    ])


def build_prior_authorization(
    text: str, *, run_id: str | None = None
) -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    trace_id = run_id or f"prior-auth-{uuid.uuid4().hex}"
    result = _blank_result(trace_id)
    evidence_items: list[dict[str, Any]] = []

    for section in _sections(source):
        if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
            truncated = True
            break
        if section.field in _SCALAR_TARGETS:
            evidence_ref = _add_evidence(
                evidence_items,
                field=section.field,
                source_label=section.label,
                evidence_text=section.value,
                char_span=section.span,
            )
            _set_fact(
                result,
                _SCALAR_TARGETS[section.field],
                section.value,
                evidence_ref,
            )
            continue
        target = _LIST_TARGETS.get(section.field)
        if not target:
            continue
        destination = (
            result["payer_policy"]["requirements"]
            if target == "payer_policy.requirements"
            else result[target]
        )
        for value, span in _split_items(source, section):
            if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                truncated = True
                break
            evidence_ref = _add_evidence(
                evidence_items,
                field=section.field,
                source_label=section.label,
                evidence_text=value,
                char_span=span,
            )
            destination.append(_fact(value, evidence_ref))

    required = dict(_CORE_FIELDS)
    if _is_medication_request(result):
        required.update(_MEDICATION_CORE_FIELDS)
    result["missing_required_fields"] = [
        label for field, label in required.items() if not _documented(result, field)
    ]
    result["missing_supporting_items"] = [
        label
        for field, label in _SUPPORTING_FIELDS.items()
        if not _documented(result, field)
    ]
    result["missing_policy_items"] = [
        label for field, label in _POLICY_FIELDS.items() if not _documented(result, field)
    ]

    provided_policy_fields = len(_POLICY_FIELDS) - len(result["missing_policy_items"])
    if provided_policy_fields == 0:
        result["policy_evaluation_status"] = "POLICY_NOT_PROVIDED"
    elif result["missing_policy_items"]:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_INCOMPLETE"
    else:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_ONLY"

    if result["missing_required_fields"]:
        result["authorization_status"] = "INPUT_REQUIRED"
    elif result["missing_policy_items"]:
        result["authorization_status"] = "POLICY_REQUIRED"
        result["authorization_packet_draft"] = _draft(result)
    else:
        result["authorization_status"] = "READY_FOR_REVIEW"
        result["authorization_packet_draft"] = _draft(result)

    result["evidence_items"] = evidence_items
    if truncated:
        result["limitations"].append(
            "输入或证据超过本地安全上限，或检测到不可信指令边界；超出部分未处理。"
        )
    valid_spans = sum(
        source[slice(*item["char_span"])] == item["evidence_text"]
        for item in evidence_items
    )
    result["_trace"] = {
        "agent_ref": AGENT_REF,
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "output_contract": OUTPUT_CONTRACT_REF,
        "input_chars": len(source),
        "input_truncated": truncated,
        "evidence_items_count": len(evidence_items),
        "valid_spans_count": valid_spans,
        "external_calls": 0,
        "llm_calls": 0,
        "medical_calculator_calls": 0,
        "medical_coding_calls": 0,
        "submission_calls": 0,
        "writeback_calls": 0,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_prior_authorization",
    "to_pack_output",
    "verify_prior_authorization_health",
]
