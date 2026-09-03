"""Evidence-bound local claim review packet assembly.

Only explicitly labelled claim, chart, and payer-policy fields are copied.
The implementation never infers coding support, coverage, eligibility,
medical necessity, DRG/DIP grouping, or denial probability.  Every copied
fact is bound to an exact span in the redacted request.  Claim submission
and source-system writeback are always blocked.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/claim-check@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_claim_review"
OUTPUT_CONTRACT_REF = "icoder/ClaimCheckOutput/v4"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200
MAX_ITEMS_PER_SECTION = 80

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "\nignore previous",
    "ICODER_PROMPT_CANARY_",
)

_LABEL_TO_FIELD = {
    "结算单号": "claim_id",
    "理赔单号": "claim_id",
    "claim id": "claim_id",
    "就诊编号": "encounter_id",
    "住院号": "encounter_id",
    "encounter id": "encounter_id",
    "结算类型": "claim_type",
    "理赔类型": "claim_type",
    "claim type": "claim_type",
    "服务日期": "service_date",
    "就诊日期": "service_date",
    "service date": "service_date",
    "患者姓名": "patient_name",
    "姓名": "patient_name",
    "patient name": "patient_name",
    "参保人编号": "member_id",
    "医保编号": "member_id",
    "member id": "member_id",
    "医疗机构": "facility",
    "结算机构": "facility",
    "facility": "facility",
    "申请医师": "provider_name",
    "经治医师": "provider_name",
    "provider name": "provider_name",
    "医师执业编号": "provider_identifier",
    "医师编号": "provider_identifier",
    "provider identifier": "provider_identifier",
    "支付方": "payer_name",
    "医保经办机构": "payer_name",
    "保险公司": "payer_name",
    "payer": "payer_name",
    "保险计划": "plan_name",
    "医保计划": "plan_name",
    "plan name": "plan_name",
    "统筹区": "payer_region",
    "参保地": "payer_region",
    "payer region": "payer_region",
    "拟报诊断": "billed_diagnoses",
    "申报诊断": "billed_diagnoses",
    "billed diagnoses": "billed_diagnoses",
    "拟报手术": "billed_procedures",
    "申报手术": "billed_procedures",
    "billed procedures": "billed_procedures",
    "拟报项目": "billed_items",
    "费用明细": "billed_items",
    "billed items": "billed_items",
    "申报总金额": "total_billed_amount",
    "结算总金额": "total_billed_amount",
    "total billed amount": "total_billed_amount",
    "币种": "currency",
    "currency": "currency",
    "临床文书摘录": "clinical_documentation",
    "病历证据": "clinical_documentation",
    "clinical documentation": "clinical_documentation",
    "支付方要求": "payer_requirements",
    "医保规则条款": "payer_requirements",
    "payer requirements": "payer_requirements",
    "支付政策编号": "policy_identifier",
    "医保政策编号": "policy_identifier",
    "policy identifier": "policy_identifier",
    "支付政策版本": "policy_version",
    "医保政策版本": "policy_version",
    "policy version": "policy_version",
    "政策生效日期": "policy_effective_date",
    "effective date": "policy_effective_date",
    "政策来源": "policy_source",
    "policy source": "policy_source",
    "已记录拒付原因": "denial_reason",
    "拒付原因": "denial_reason",
    "denial reason": "denial_reason",
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
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]+)"
)

_CORE_FIELDS = {
    "claim_id": "结算单号/理赔单号",
    "claim_type": "结算类型/理赔类型",
    "service_date": "服务日期/就诊日期",
    "member_id": "参保人编号/医保编号",
    "facility": "医疗机构/结算机构",
    "provider_name": "申请医师/经治医师",
    "provider_identifier": "医师执业编号",
    "payer_name": "支付方/医保经办机构",
    "payer_region": "统筹区/参保地",
    "clinical_documentation": "临床文书摘录/病历证据",
}
_CLAIM_CONTENT_FIELDS = {
    "billed_diagnoses": "拟报诊断",
    "billed_procedures": "拟报手术",
    "billed_items": "拟报项目/费用明细",
}
_POLICY_FIELDS = {
    "payer_requirements": "支付方要求/医保规则条款",
    "policy_identifier": "支付政策编号",
    "policy_version": "支付政策版本",
    "policy_effective_date": "政策生效日期",
    "policy_source": "政策来源",
}
_PUBLIC_FIELDS = (
    "review_status",
    "claim_information",
    "patient_information",
    "provider_information",
    "payer_information",
    "billed_diagnoses",
    "billed_procedures",
    "billed_items",
    "clinical_documentation",
    "provided_policy",
    "documented_denial_reason",
    "missing_required_fields",
    "missing_policy_items",
    "claim_review_packet",
    "policy_evaluation_status",
    "evidence_consistency_status",
    "comparison_basis",
    "evidence_items",
    "limitations",
    "clinical_support_assessed",
    "medical_necessity_assessed",
    "benefit_eligibility_determined",
    "code_assignment_performed",
    "drg_dip_grouping_performed",
    "external_knowledge_used",
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


def verify_claim_check_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "payer_policy_lookup_performed": False,
        "clinical_support_assessed": False,
        "medical_necessity_assessed": False,
        "benefit_eligibility_determined": False,
        "code_assignment_performed": False,
        "drg_dip_grouping_performed": False,
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
        leading = _LEADING_ITEM_RE.match(section.value[raw_start:raw_end])
        if leading:
            raw_start += leading.end()
        value, span = _trim_span(
            source, section.span[0] + raw_start, section.span[0] + raw_end
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


def _blank_result(trace_id: str) -> dict[str, Any]:
    return {
        "review_status": "INPUT_REQUIRED",
        "claim_information": {
            "claim_id": _fact(), "encounter_id": _fact(),
            "claim_type": _fact(), "service_date": _fact(),
            "total_billed_amount": _fact(), "currency": _fact(),
        },
        "patient_information": {"name": _fact(), "member_id": _fact()},
        "provider_information": {
            "name": _fact(), "provider_identifier": _fact(), "facility": _fact(),
        },
        "payer_information": {
            "payer_name": _fact(), "plan_name": _fact(), "region": _fact(),
        },
        "billed_diagnoses": [],
        "billed_procedures": [],
        "billed_items": [],
        "clinical_documentation": [],
        "provided_policy": {
            "requirements": [], "policy_identifier": _fact(),
            "version": _fact(), "effective_date": _fact(), "source": _fact(),
        },
        "documented_denial_reason": _fact(),
        "missing_required_fields": list(_CORE_FIELDS.values()),
        "missing_policy_items": list(_POLICY_FIELDS.values()),
        "claim_review_packet": "",
        "policy_evaluation_status": "POLICY_NOT_PROVIDED",
        "evidence_consistency_status": "NOT_ASSESSED_LITERAL_PACKET_ONLY",
        "comparison_basis": "DOCUMENTED_CLAIM_AND_POLICY_ONLY",
        "evidence_items": [],
        "limitations": [
            "仅解析明确的中英文结算、病历和政策字段标题；未标注自由叙事不会被自动总结。",
            "仅逐字装配已报账内容、病历摘录和用户提供的政策条款；未判断病历是否支持编码或费用。",
            "未调用医保/商保网站、药品耗材目录、编码目录、HCC映射、DRG/DIP分组器或其他外部知识。",
            "未判断医疗必要性、待遇资格、支付范围、拒付概率、高套/低套或收入机会。",
            "未新增或修改诊断、手术、项目、金额、编码、政策条款或拒付理由。",
            "未连接真实HIS/EMR、医保/商保结算平台、清单上传或申诉接口。",
            "核查包禁止自动提交或写回，必须由编码员、临床人员和医保/商保专员逐项复核。",
        ],
        "clinical_support_assessed": False,
        "medical_necessity_assessed": False,
        "benefit_eligibility_determined": False,
        "code_assignment_performed": False,
        "drg_dip_grouping_performed": False,
        "external_knowledge_used": False,
        "production_submission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-claim-check"],
        },
    }


_SCALAR_TARGETS = {
    "claim_id": ("claim_information", "claim_id"),
    "encounter_id": ("claim_information", "encounter_id"),
    "claim_type": ("claim_information", "claim_type"),
    "service_date": ("claim_information", "service_date"),
    "total_billed_amount": ("claim_information", "total_billed_amount"),
    "currency": ("claim_information", "currency"),
    "patient_name": ("patient_information", "name"),
    "member_id": ("patient_information", "member_id"),
    "provider_name": ("provider_information", "name"),
    "provider_identifier": ("provider_information", "provider_identifier"),
    "facility": ("provider_information", "facility"),
    "payer_name": ("payer_information", "payer_name"),
    "plan_name": ("payer_information", "plan_name"),
    "payer_region": ("payer_information", "region"),
    "policy_identifier": ("provided_policy", "policy_identifier"),
    "policy_version": ("provided_policy", "version"),
    "policy_effective_date": ("provided_policy", "effective_date"),
    "policy_source": ("provided_policy", "source"),
    "denial_reason": ("documented_denial_reason",),
}
_LIST_TARGETS = {
    "billed_diagnoses": "billed_diagnoses",
    "billed_procedures": "billed_procedures",
    "billed_items": "billed_items",
    "clinical_documentation": "clinical_documentation",
    "payer_requirements": "provided_policy.requirements",
}


def _get_target(result: dict[str, Any], target: tuple[str, ...]) -> Any:
    value: Any = result
    for key in target:
        value = value[key]
    return value


def _set_fact(result: dict[str, Any], target: tuple[str, ...], value: str, ref: str) -> None:
    fact = _get_target(result, target)
    fact["documented_text"] = (
        f"{fact['documented_text']}\n{value}" if fact["documented_text"] else value
    )
    fact["evidence_ref"] = ref


def _documented(result: dict[str, Any], field: str) -> bool:
    if field in _SCALAR_TARGETS:
        return bool(_get_target(result, _SCALAR_TARGETS[field])["documented_text"])
    target = _LIST_TARGETS.get(field)
    if target == "provided_policy.requirements":
        return bool(result["provided_policy"]["requirements"])
    return bool(result.get(target or ""))


def _add_evidence(
    items: list[dict[str, Any]], *, field: str, source_label: str,
    evidence_text: str, char_span: list[int]
) -> str:
    evidence_id = f"claim-check-evidence-{len(items) + 1}"
    items.append({
        "evidence_id": evidence_id, "field": field,
        "source_label": source_label, "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _packet(result: dict[str, Any]) -> str:
    def text(fact: dict[str, str]) -> str:
        return fact["documented_text"] or "未记录"

    def joined(items: list[dict[str, str]]) -> str:
        return "；".join(item["documented_text"] for item in items) or "未记录"

    claim = result["claim_information"]
    policy = result["provided_policy"]
    return "\n".join([
        "## 结算提交前核查包",
        f"结算单号：{text(claim['claim_id'])}",
        f"就诊编号：{text(claim['encounter_id'])}",
        f"结算类型：{text(claim['claim_type'])}",
        f"服务日期：{text(claim['service_date'])}",
        f"患者/参保编号：{text(result['patient_information']['name'])} / {text(result['patient_information']['member_id'])}",
        f"医师/执业编号：{text(result['provider_information']['name'])} / {text(result['provider_information']['provider_identifier'])}",
        f"医疗机构：{text(result['provider_information']['facility'])}",
        f"支付方/计划/统筹区：{text(result['payer_information']['payer_name'])} / {text(result['payer_information']['plan_name'])} / {text(result['payer_information']['region'])}",
        f"拟报诊断：{joined(result['billed_diagnoses'])}",
        f"拟报手术：{joined(result['billed_procedures'])}",
        f"拟报项目：{joined(result['billed_items'])}",
        f"总金额/币种：{text(claim['total_billed_amount'])} / {text(claim['currency'])}",
        f"临床文书摘录：{joined(result['clinical_documentation'])}",
        f"支付方要求：{joined(policy['requirements'])}",
        f"政策编号/版本/生效日期：{text(policy['policy_identifier'])} / {text(policy['version'])} / {text(policy['effective_date'])}",
        f"政策来源：{text(policy['source'])}",
        f"已记录拒付原因：{text(result['documented_denial_reason'])}",
        f"政策状态：{result['policy_evaluation_status']}",
        "声明：本核查包只呈现已提供材料，不构成编码支持、医疗必要性、待遇资格、支付或拒付结论；禁止自动提交或写回。",
    ])


def build_claim_check(text: str, *, run_id: str | None = None) -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    trace_id = run_id or f"claim-check-{uuid.uuid4().hex}"
    result = _blank_result(trace_id)
    evidence_items: list[dict[str, Any]] = []

    for section in _sections(source):
        if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
            truncated = True
            break
        if section.field in _SCALAR_TARGETS:
            ref = _add_evidence(
                evidence_items, field=section.field, source_label=section.label,
                evidence_text=section.value, char_span=section.span,
            )
            _set_fact(result, _SCALAR_TARGETS[section.field], section.value, ref)
            continue
        target = _LIST_TARGETS.get(section.field)
        if not target:
            continue
        destination = (
            result["provided_policy"]["requirements"]
            if target == "provided_policy.requirements" else result[target]
        )
        for value, span in _split_items(source, section):
            if len(evidence_items) >= MAX_EVIDENCE_ITEMS:
                truncated = True
                break
            ref = _add_evidence(
                evidence_items, field=section.field, source_label=section.label,
                evidence_text=value, char_span=span,
            )
            destination.append(_fact(value, ref))

    result["missing_required_fields"] = [
        label for field, label in _CORE_FIELDS.items() if not _documented(result, field)
    ]
    if not any(_documented(result, field) for field in _CLAIM_CONTENT_FIELDS):
        result["missing_required_fields"].append("拟报诊断/手术/项目至少一项")
    result["missing_policy_items"] = [
        label for field, label in _POLICY_FIELDS.items() if not _documented(result, field)
    ]
    provided_policy_count = len(_POLICY_FIELDS) - len(result["missing_policy_items"])
    if provided_policy_count == 0:
        result["policy_evaluation_status"] = "POLICY_NOT_PROVIDED"
    elif result["missing_policy_items"]:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_INCOMPLETE"
    else:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_ONLY"

    if result["missing_required_fields"]:
        result["review_status"] = "INPUT_REQUIRED"
    elif result["missing_policy_items"]:
        result["review_status"] = "POLICY_REQUIRED"
        result["claim_review_packet"] = _packet(result)
    else:
        result["review_status"] = "READY_FOR_REVIEW"
        result["claim_review_packet"] = _packet(result)

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
        "medical_coding_calls": 0,
        "drg_dip_grouping_calls": 0,
        "submission_calls": 0,
        "writeback_calls": 0,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF", "LOCAL_RUNTIME_MODE", "OUTPUT_CONTRACT_REF",
    "build_claim_check", "to_pack_output", "verify_claim_check_health",
]
