"""Evidence-bound local denial-appeal and corrected-claim packet assembly.

Only explicitly headed denial, claim, record, and user-provided policy fields
are copied into a fixed review-only template.  The implementation never
classifies a denial, infers a root cause, validates codes, evaluates clinical
support, medical necessity, eligibility, or payer policy, and never submits or
writes back.  Every copied fact is bound to an exact span in the redacted
request.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/denial-appeals@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_denial_appeal"
OUTPUT_CONTRACT_REF = "icoder/DenialAppealOutput/v3"
MAX_INPUT_CHARS = 40_000
MAX_EVIDENCE_ITEMS = 200
MAX_ITEMS_PER_SECTION = 80
DRAFT_GENERATION_STATUS = "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"

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
    "拒付通知编号": "denial_notice_id",
    "拒付单号": "denial_notice_id",
    "eob/era reference": "denial_notice_id",
    "denial notice id": "denial_notice_id",
    "拒付日期": "denial_date",
    "denial date": "denial_date",
    "服务日期": "service_date",
    "就诊日期": "service_date",
    "date of service": "service_date",
    "dos": "service_date",
    "拒付代码": "denial_reason_code",
    "拒绝代码": "denial_reason_code",
    "denial reason code": "denial_reason_code",
    "拒付原因": "denial_reason_description",
    "拒绝原因": "denial_reason_description",
    "支付方原文": "denial_reason_description",
    "denial reason": "denial_reason_description",
    "payer wording": "denial_reason_description",
    "拒付类别": "documented_denial_category",
    "拒绝类别": "documented_denial_category",
    "denial category": "documented_denial_category",
    "拒付金额": "denied_amount",
    "申诉金额": "denied_amount",
    "denied amount": "denied_amount",
    "币种": "currency",
    "currency": "currency",
    "申诉截止日期": "appeal_deadline",
    "申诉期限": "appeal_deadline",
    "filing deadline": "appeal_deadline",
    "appeal deadline": "appeal_deadline",
    "申诉层级": "appeal_level",
    "appeal level": "appeal_level",
    "申诉渠道": "submission_channel",
    "提交渠道": "submission_channel",
    "submission channel": "submission_channel",
    "患者姓名": "patient_name",
    "姓名": "patient_name",
    "patient name": "patient_name",
    "参保人编号": "member_id",
    "医保编号": "member_id",
    "保险会员号": "member_id",
    "member id": "member_id",
    "医疗机构": "facility",
    "申诉机构": "facility",
    "facility": "facility",
    "经治医师": "provider_name",
    "申诉医师": "provider_name",
    "provider name": "provider_name",
    "医师执业编号": "provider_identifier",
    "医师编号": "provider_identifier",
    "npi": "provider_identifier",
    "provider identifier": "provider_identifier",
    "申诉方联系方式": "provider_contact",
    "机构联系方式": "provider_contact",
    "provider contact": "provider_contact",
    "支付方": "payer_name",
    "医保经办机构": "payer_name",
    "保险公司": "payer_name",
    "payer": "payer_name",
    "保险计划": "plan_name",
    "医保计划": "plan_name",
    "plan name": "plan_name",
    "支付类型": "payer_type",
    "医保类型": "payer_type",
    "payer type": "payer_type",
    "统筹区": "payer_region",
    "参保地": "payer_region",
    "payer region": "payer_region",
    "经办机构": "managing_agency",
    "managing agency": "managing_agency",
    "拒付明细": "denied_claim_lines",
    "拒付行": "denied_claim_lines",
    "denied claim lines": "denied_claim_lines",
    "拟申诉诊断": "denied_diagnoses",
    "拒付诊断": "denied_diagnoses",
    "denied diagnoses": "denied_diagnoses",
    "拟申诉手术": "denied_procedures",
    "拒付手术": "denied_procedures",
    "denied procedures": "denied_procedures",
    "拟申诉项目": "denied_items",
    "拒付项目": "denied_items",
    "denied items": "denied_items",
    "病历证据": "clinical_documentation",
    "临床文书摘录": "clinical_documentation",
    "supporting documentation": "clinical_documentation",
    "clinical documentation": "clinical_documentation",
    "已提交材料": "submitted_documents",
    "随附材料": "submitted_documents",
    "submitted documents": "submitted_documents",
    "既往授权信息": "prior_authorization_information",
    "预授权信息": "prior_authorization_information",
    "prior authorization information": "prior_authorization_information",
    "待遇资格信息": "eligibility_information",
    "参保资格信息": "eligibility_information",
    "eligibility information": "eligibility_information",
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
    "处理路径": "resolution_path",
    "申诉路径": "resolution_path",
    "primary resolution path": "resolution_path",
    "requested resolution path": "resolution_path",
    "请求事项": "requested_resolution",
    "申诉请求": "requested_resolution",
    "requested resolution": "requested_resolution",
    "拟更正内容": "documented_corrections",
    "更正清单": "documented_corrections",
    "documented corrections": "documented_corrections",
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
    "denial_date": "拒付日期",
    "service_date": "服务日期/就诊日期",
    "patient_name": "患者姓名",
    "member_id": "参保人编号/医保编号",
    "provider_name": "经治医师/申诉医师",
    "payer_name": "支付方/医保经办机构",
    "denial_reason_description": "拒付原因/支付方原文",
    "clinical_documentation": "病历证据/临床文书摘录",
}
_POLICY_FIELDS = {
    "payer_requirements": "支付方要求/医保规则条款",
    "policy_identifier": "支付政策编号",
    "policy_version": "支付政策版本",
    "policy_effective_date": "政策生效日期",
    "policy_source": "政策来源",
}
_SUPPORTING_FIELDS = {
    "denial_notice_id": "拒付通知编号",
    "denial_reason_code": "拒付代码",
    "documented_denial_category": "拒付类别",
    "denied_amount": "拒付/申诉金额",
    "appeal_deadline": "申诉截止日期",
    "appeal_level": "申诉层级",
    "submitted_documents": "已提交/随附材料",
    "prior_authorization_information": "既往授权信息",
    "eligibility_information": "待遇资格信息",
    "requested_resolution": "请求事项/申诉请求",
}
_CLAIM_CONTENT_FIELDS = {
    "denied_claim_lines", "denied_diagnoses", "denied_procedures", "denied_items"
}

_PUBLIC_FIELDS = (
    "appeal_status",
    "denial_snapshot",
    "patient_information",
    "provider_information",
    "payer_information",
    "denied_claim_lines",
    "denied_diagnoses",
    "denied_procedures",
    "denied_items",
    "clinical_documentation",
    "submitted_documents",
    "prior_authorization_information",
    "eligibility_information",
    "provided_policy",
    "documented_resolution_path",
    "requested_resolution",
    "documented_corrections",
    "missing_required_fields",
    "missing_supporting_items",
    "missing_policy_items",
    "denial_classification_status",
    "resolution_path_status",
    "policy_evaluation_status",
    "appeal_letter_draft",
    "corrected_claim_checklist",
    "evidence_items",
    "limitations",
    "draft_generation_status",
    "clinical_support_assessed",
    "medical_necessity_assessed",
    "benefit_eligibility_determined",
    "denial_root_cause_inferred",
    "payer_policy_lookup_performed",
    "medical_coding_validation_performed",
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


def verify_denial_appeal_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "payer_policy_lookup_performed": False,
        "denial_classification_performed": False,
        "denial_root_cause_inferred": False,
        "clinical_support_assessed": False,
        "medical_necessity_assessed": False,
        "benefit_eligibility_determined": False,
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
        "appeal_status": "INPUT_REQUIRED",
        "denial_snapshot": {
            "claim_id": _fact(), "denial_notice_id": _fact(),
            "denial_date": _fact(), "service_date": _fact(),
            "denial_reason_code": _fact(), "denial_reason_description": _fact(),
            "documented_denial_category": _fact(), "denied_amount": _fact(),
            "currency": _fact(), "appeal_deadline": _fact(),
            "appeal_level": _fact(), "submission_channel": _fact(),
        },
        "patient_information": {"name": _fact(), "member_id": _fact()},
        "provider_information": {
            "name": _fact(), "provider_identifier": _fact(),
            "facility": _fact(), "contact": _fact(),
        },
        "payer_information": {
            "payer_name": _fact(), "plan_name": _fact(), "payer_type": _fact(),
            "region": _fact(), "managing_agency": _fact(),
        },
        "denied_claim_lines": [],
        "denied_diagnoses": [],
        "denied_procedures": [],
        "denied_items": [],
        "clinical_documentation": [],
        "submitted_documents": [],
        "prior_authorization_information": [],
        "eligibility_information": [],
        "provided_policy": {
            "requirements": [], "policy_identifier": _fact(),
            "version": _fact(), "effective_date": _fact(), "source": _fact(),
        },
        "documented_resolution_path": _fact(),
        "requested_resolution": _fact(),
        "documented_corrections": [],
        "missing_required_fields": list(_CORE_FIELDS.values()),
        "missing_supporting_items": list(_SUPPORTING_FIELDS.values()),
        "missing_policy_items": list(_POLICY_FIELDS.values()),
        "denial_classification_status": "DOCUMENTED_ONLY_NO_INFERENCE",
        "resolution_path_status": "RESOLUTION_PATH_NOT_PROVIDED",
        "policy_evaluation_status": "POLICY_NOT_PROVIDED",
        "appeal_letter_draft": "",
        "corrected_claim_checklist": [],
        "evidence_items": [],
        "limitations": [
            "仅解析明确的中英文拒付、结算、病历和政策字段标题；未标注自由叙事不会被自动总结。",
            "拒付类别和处理路径仅呈现用户明确提供的内容；未自动分类拒付、推断根因或选择处理路径。",
            "仅逐字装配已提供事实；未判断病历是否支持编码、服务、医疗必要性、待遇资格或支付范围。",
            "未调用支付方网站、医保/商保政策、NCCI、编码目录、PubMed、指南或其他外部知识。",
            "未校验 ICD、CPT/HCPCS、ICD-9-CM-3、医保项目、药品、耗材、修饰符、单位或金额。",
            "未新增诊断、服务、日期、编码、授权、资格、政策条款、缺失材料或申诉论点。",
            "未连接真实 HIS/EMR、EOB/ERA、医保/商保结算、传真、邮件或申诉提交接口。",
            "草案和清单禁止自动提交或写回，必须由临床、编码、医保/商保及合规人员逐项复核。",
        ],
        "draft_generation_status": DRAFT_GENERATION_STATUS,
        "clinical_support_assessed": False,
        "medical_necessity_assessed": False,
        "benefit_eligibility_determined": False,
        "denial_root_cause_inferred": False,
        "payer_policy_lookup_performed": False,
        "medical_coding_validation_performed": False,
        "external_knowledge_used": False,
        "production_submission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": trace_id,
            "provider_trace_refs": [f"{trace_id}:governed-denial-appeals"],
        },
    }


_SCALAR_TARGETS = {
    "claim_id": ("denial_snapshot", "claim_id"),
    "denial_notice_id": ("denial_snapshot", "denial_notice_id"),
    "denial_date": ("denial_snapshot", "denial_date"),
    "service_date": ("denial_snapshot", "service_date"),
    "denial_reason_code": ("denial_snapshot", "denial_reason_code"),
    "denial_reason_description": ("denial_snapshot", "denial_reason_description"),
    "documented_denial_category": ("denial_snapshot", "documented_denial_category"),
    "denied_amount": ("denial_snapshot", "denied_amount"),
    "currency": ("denial_snapshot", "currency"),
    "appeal_deadline": ("denial_snapshot", "appeal_deadline"),
    "appeal_level": ("denial_snapshot", "appeal_level"),
    "submission_channel": ("denial_snapshot", "submission_channel"),
    "patient_name": ("patient_information", "name"),
    "member_id": ("patient_information", "member_id"),
    "provider_name": ("provider_information", "name"),
    "provider_identifier": ("provider_information", "provider_identifier"),
    "facility": ("provider_information", "facility"),
    "provider_contact": ("provider_information", "contact"),
    "payer_name": ("payer_information", "payer_name"),
    "plan_name": ("payer_information", "plan_name"),
    "payer_type": ("payer_information", "payer_type"),
    "payer_region": ("payer_information", "region"),
    "managing_agency": ("payer_information", "managing_agency"),
    "policy_identifier": ("provided_policy", "policy_identifier"),
    "policy_version": ("provided_policy", "version"),
    "policy_effective_date": ("provided_policy", "effective_date"),
    "policy_source": ("provided_policy", "source"),
    "resolution_path": ("documented_resolution_path",),
    "requested_resolution": ("requested_resolution",),
}
_LIST_TARGETS = {
    "denied_claim_lines": "denied_claim_lines",
    "denied_diagnoses": "denied_diagnoses",
    "denied_procedures": "denied_procedures",
    "denied_items": "denied_items",
    "clinical_documentation": "clinical_documentation",
    "submitted_documents": "submitted_documents",
    "prior_authorization_information": "prior_authorization_information",
    "eligibility_information": "eligibility_information",
    "payer_requirements": "provided_policy.requirements",
    "documented_corrections": "documented_corrections",
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
    evidence_id = f"denial-appeals-evidence-{len(items) + 1}"
    items.append({
        "evidence_id": evidence_id,
        "field": field,
        "source_label": source_label,
        "evidence_text": evidence_text,
        "char_span": char_span,
    })
    return evidence_id


def _text(fact: dict[str, str]) -> str:
    return fact["documented_text"] or "未记录"


def _joined(items: list[dict[str, str]]) -> str:
    return "；".join(item["documented_text"] for item in items) or "未记录"


def _is_appeal_path(result: dict[str, Any]) -> bool:
    path = result["documented_resolution_path"]["documented_text"].casefold()
    return any(term in path for term in ("申诉", "复议", "appeal", "reconsider"))


def _is_corrected_claim_path(result: dict[str, Any]) -> bool:
    path = result["documented_resolution_path"]["documented_text"].casefold()
    return any(term in path for term in ("更正", "重报", "corrected", "resubmit"))


def _appeal_draft(result: dict[str, Any]) -> str:
    snap = result["denial_snapshot"]
    policy = result["provided_policy"]
    return "\n".join([
        "## 拒付申诉草案（人工复核）",
        "日期：未记录",
        f"支付方：{_text(result['payer_information']['payer_name'])}",
        f"主题：结算/理赔单号 {_text(snap['claim_id'])}；服务日期 {_text(snap['service_date'])}",
        f"患者/参保编号：{_text(result['patient_information']['name'])} / {_text(result['patient_information']['member_id'])}",
        "",
        "致审核人员：",
        f"我方就上述结算/理赔记录提出人工复核申诉。支付方已记录的拒付代码为“{_text(snap['denial_reason_code'])}”，拒付原因为“{_text(snap['denial_reason_description'])}”。",
        f"本次涉及的拒付明细为：{_joined(result['denied_claim_lines'])}。拟申诉诊断/手术/项目为：{_joined(result['denied_diagnoses'])} / {_joined(result['denied_procedures'])} / {_joined(result['denied_items'])}。",
        f"已提供的病历证据为：{_joined(result['clinical_documentation'])}。既往授权信息为：{_joined(result['prior_authorization_information'])}。待遇资格信息为：{_joined(result['eligibility_information'])}。",
        f"用户提供的支付方要求为：{_joined(policy['requirements'])}。政策编号/版本/生效日期/来源为：{_text(policy['policy_identifier'])} / {_text(policy['version'])} / {_text(policy['effective_date'])} / {_text(policy['source'])}。",
        f"请求事项：{_text(result['requested_resolution'])}。申诉截止日期/层级/渠道为：{_text(snap['appeal_deadline'])} / {_text(snap['appeal_level'])} / {_text(snap['submission_channel'])}。",
        f"随附材料：{_joined(result['submitted_documents'])}。",
        "",
        "此草案仅逐字装配已提供材料，未形成编码、医疗必要性、待遇资格、支付政策适用性或可推翻拒付的结论。禁止自动提交或写回；提交前须由临床、编码、医保/商保及合规人员核验并补齐未记录信息。",
        f"申诉机构/医师/联系方式：{_text(result['provider_information']['facility'])} / {_text(result['provider_information']['name'])} / {_text(result['provider_information']['contact'])}",
    ])


def build_denial_appeal(text: str, *, run_id: str | None = None) -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    trace_id = run_id or f"denial-appeals-{uuid.uuid4().hex}"
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
        result["missing_required_fields"].append(
            "拒付明细/拟申诉诊断/手术/项目至少一项"
        )
    result["missing_supporting_items"] = [
        label for field, label in _SUPPORTING_FIELDS.items() if not _documented(result, field)
    ]
    result["missing_policy_items"] = [
        label for field, label in _POLICY_FIELDS.items() if not _documented(result, field)
    ]

    policy_count = len(_POLICY_FIELDS) - len(result["missing_policy_items"])
    if policy_count == 0:
        result["policy_evaluation_status"] = "POLICY_NOT_PROVIDED"
    elif result["missing_policy_items"]:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_INCOMPLETE"
    else:
        result["policy_evaluation_status"] = "DOCUMENTED_POLICY_ONLY"

    has_path = _documented(result, "resolution_path")
    if has_path:
        result["resolution_path_status"] = "DOCUMENTED_PATH_ONLY"

    if result["missing_required_fields"]:
        result["appeal_status"] = "INPUT_REQUIRED"
    elif not has_path:
        result["appeal_status"] = "PATH_REVIEW_REQUIRED"
    elif _is_appeal_path(result) and result["missing_policy_items"]:
        result["appeal_status"] = "POLICY_REQUIRED"
        result["appeal_letter_draft"] = _appeal_draft(result)
    else:
        result["appeal_status"] = "READY_FOR_REVIEW"
        if _is_appeal_path(result):
            result["appeal_letter_draft"] = _appeal_draft(result)
        elif _is_corrected_claim_path(result):
            result["corrected_claim_checklist"] = list(result["documented_corrections"])

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
        "payer_policy_lookup_calls": 0,
        "submission_calls": 0,
        "writeback_calls": 0,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF", "LOCAL_RUNTIME_MODE", "OUTPUT_CONTRACT_REF",
    "build_denial_appeal", "to_pack_output", "verify_denial_appeal_health",
]
