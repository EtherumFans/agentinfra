"""Source-bound clinical education assembly for approved hospital material.

The local baseline copies explicitly labelled source metadata and statements
into fixed teaching templates. It never retrieves literature, classifies a
clinical question, supplies medical knowledge, performs clinical reasoning,
or generates patient-specific advice. Every clinical statement remains bound
to an exact span in the redacted request.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


AGENT_REF = "icoder/clinical-education@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_approved_source_clinical_education"
OUTPUT_CONTRACT_REF = "icoder/ClinicalEducationOutput/v6"
MAX_INPUT_CHARS = 40_000
MAX_SOURCE_STATEMENTS = 80
CONTENT_GENERATION_STATUS = "SOURCE_BOUND_TEMPLATE_ONLY"

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "\nignore previous",
    "ICODER_PROMPT_CANARY_",
)

_LABEL_TO_FIELD = {
    "主题": "topic",
    "topic": "topic",
    "受众": "audience",
    "audience": "audience",
    "回答模式": "response_mode",
    "学习模式": "response_mode",
    "response mode": "response_mode",
    "学习者层级": "learner_level",
    "learner level": "learner_level",
    "批准来源名称": "source_title",
    "来源名称": "source_title",
    "source title": "source_title",
    "来源版本": "source_version",
    "source version": "source_version",
    "发布日期": "publication_date",
    "更新日期": "publication_date",
    "publication date": "publication_date",
    "医院批准状态": "approval_status",
    "批准状态": "approval_status",
    "approval status": "approval_status",
    "医院批准日期": "approval_date",
    "批准日期": "approval_date",
    "approval date": "approval_date",
    "批准机构": "approval_organization",
    "approval organization": "approval_organization",
    "来源机构": "source_organization",
    "source organization": "source_organization",
    "来源网址": "source_url",
    "source url": "source_url",
    "材料范围": "source_scope",
    "source scope": "source_scope",
    "来源原文": "source_text",
    "批准材料原文": "source_text",
    "source text": "source_text",
}
_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*"
    rf"(?:[：:][ \t]*(?P<inline>[^\r\n]*)|(?P<line_end>\r?\n|$))"
)
_STATEMENT_SEPARATOR_RE = re.compile(r"[；;]\s*|\r?\n+")
_LEADING_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]+)"
)

_REQUIRED_FIELDS = {
    "topic": "主题",
    "audience": "受众",
    "source_title": "批准来源名称",
    "source_text": "来源原文",
}
_SOURCE_METADATA_FIELDS = {
    "source_version": "来源版本",
    "publication_date": "发布日期/更新日期",
    "approval_status": "医院批准状态",
    "approval_date": "医院批准日期",
    "approval_organization": "批准机构",
    "source_organization": "来源机构",
    "source_url": "来源网址/文档标识",
    "source_scope": "材料范围",
}
_APPROVED_VALUES = frozenset({"已批准"})
_COMPLETE_SCOPE_VALUES = frozenset({"完整", "完整材料", "full", "complete"})

_PUBLIC_FIELDS = (
    "education_status",
    "topic",
    "audience",
    "response_mode",
    "learner_level",
    "approved_source",
    "source_statements",
    "learning_objectives",
    "key_points",
    "evidence_citations",
    "knowledge_checks",
    "evidence_items",
    "missing_required_fields",
    "missing_source_metadata",
    "limitations",
    "source_insufficient",
    "source_sufficiency_status",
    "content_generation_status",
    "question_classification_performed",
    "clinical_reasoning_performed",
    "diagnostic_advice_generated",
    "treatment_advice_generated",
    "drug_interaction_assessed",
    "medical_calculator_used",
    "pubmed_lookup_performed",
    "web_search_performed",
    "external_knowledge_used",
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


def verify_clinical_education_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "question_classification_performed": False,
        "clinical_reasoning_performed": False,
        "diagnostic_advice_generated": False,
        "treatment_advice_generated": False,
        "drug_interaction_assessed": False,
        "medical_calculator_used": False,
        "pubmed_lookup_performed": False,
        "web_search_performed": False,
        "production_writeback_blocked": True,
    }


def _bounded_text(value: Any) -> tuple[str, bool]:
    raw = str(value or "")
    source = raw[:MAX_INPUT_CHARS]
    truncated = len(source) < len(raw)
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
    result: list[Section] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        start = match.start("inline") if match.group("inline") is not None else match.end()
        value, span = _trim_span(source, start, end)
        if value:
            result.append(Section(
                field=_LABEL_TO_FIELD[match.group("label").casefold()],
                label=match.group("label"),
                value=value,
                span=span,
            ))
    return result


def _split_statements(source: str, section: Section) -> list[tuple[str, list[int]]]:
    statements: list[tuple[str, list[int]]] = []
    cursor = 0
    for separator in list(_STATEMENT_SEPARATOR_RE.finditer(section.value)) + [None]:
        raw_end = separator.start() if separator is not None else len(section.value)
        raw_start = cursor
        leading = _LEADING_ITEM_RE.match(section.value[raw_start:raw_end])
        if leading:
            raw_start += leading.end()
        value, span = _trim_span(
            source,
            section.span[0] + raw_start,
            section.span[0] + raw_end,
        )
        value = value.rstrip("。.").rstrip()
        span[1] = span[0] + len(value)
        if value and len(statements) < MAX_SOURCE_STATEMENTS:
            statements.append((value, span))
        if separator is None:
            break
        cursor = separator.end()
    return statements


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _blank_result(run_id: str) -> dict[str, Any]:
    return {
        "education_status": "INPUT_REQUIRED",
        "topic": _fact(),
        "audience": _fact(),
        "response_mode": _fact(),
        "learner_level": _fact(),
        "approved_source": {
            "title": _fact(),
            "version": _fact(),
            "publication_date": _fact(),
            "approval_status": _fact(),
            "approval_date": _fact(),
            "approval_organization": _fact(),
            "source_organization": _fact(),
            "source_url": _fact(),
            "scope": _fact(),
        },
        "source_statements": [],
        "learning_objectives": [],
        "key_points": [],
        "evidence_citations": [],
        "knowledge_checks": [],
        "evidence_items": [],
        "missing_required_fields": list(_REQUIRED_FIELDS.values()),
        "missing_source_metadata": list(_SOURCE_METADATA_FIELDS.values()),
        "limitations": [
            "仅解析明确标题字段和医院批准材料原文；自由叙事不会被自动总结。",
            "教学内容只使用用户提供原文，不调用模型记忆、PubMed、Web Search、指南库或医学计算器。",
            "未分类临床问题，未生成诊断、鉴别诊断、机制、检查、用药、剂量、禁忌证或治疗建议。",
            "知识检查为开放式逐字复述题，不生成未经来源支持的选项或临床推理答案。",
            "未验证来源真实性、许可、版本时效、医院批准权限或对目标学习者的适用性。",
            "本内容仅供教学材料人工复核，不用于具体患者决策，也不自动发布或写回。",
        ],
        "source_insufficient": True,
        "source_sufficiency_status": "SOURCE_NOT_PROVIDED",
        "content_generation_status": CONTENT_GENERATION_STATUS,
        "question_classification_performed": False,
        "clinical_reasoning_performed": False,
        "diagnostic_advice_generated": False,
        "treatment_advice_generated": False,
        "drug_interaction_assessed": False,
        "medical_calculator_used": False,
        "pubmed_lookup_performed": False,
        "web_search_performed": False,
        "external_knowledge_used": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id,
            "provider_trace_refs": [f"{run_id}:governed-clinical-education"],
        },
    }


_SCALAR_TARGETS = {
    "topic": ("topic",),
    "audience": ("audience",),
    "response_mode": ("response_mode",),
    "learner_level": ("learner_level",),
    "source_title": ("approved_source", "title"),
    "source_version": ("approved_source", "version"),
    "publication_date": ("approved_source", "publication_date"),
    "approval_status": ("approved_source", "approval_status"),
    "approval_date": ("approved_source", "approval_date"),
    "approval_organization": ("approved_source", "approval_organization"),
    "source_organization": ("approved_source", "source_organization"),
    "source_url": ("approved_source", "source_url"),
    "source_scope": ("approved_source", "scope"),
}


def _set_target(result: dict[str, Any], target: tuple[str, ...], value: Any) -> None:
    if len(target) == 1:
        result[target[0]] = value
    else:
        result[target[0]][target[1]] = value


def _evidence_item(
    evidence_id: str,
    *,
    field: str,
    label: str,
    text: str,
    span: list[int],
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "field": field,
        "label": label,
        "text": text,
        "char_span": span,
    }


def build_clinical_education(text: Any, *, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or f"clinical-education-{uuid.uuid4()}"
    source, truncated = _bounded_text(text)
    result = _blank_result(run_id)
    sections = _sections(source)
    first_by_field: dict[str, Section] = {}
    evidence: list[dict[str, Any]] = []

    for section in sections:
        first_by_field.setdefault(section.field, section)
        if section.field == "source_text":
            continue
        evidence_id = f"clinical-education-evidence-{len(evidence) + 1}"
        evidence.append(_evidence_item(
            evidence_id,
            field=section.field,
            label=section.label,
            text=section.value,
            span=section.span,
        ))
        target = _SCALAR_TARGETS.get(section.field)
        if target is not None:
            _set_target(result, target, _fact(section.value, evidence_id))

    source_section = first_by_field.get("source_text")
    if source_section is not None:
        source_title = result["approved_source"]["title"]["documented_text"]
        source_version = result["approved_source"]["version"]["documented_text"]
        source_url = result["approved_source"]["source_url"]["documented_text"]
        for index, (statement, span) in enumerate(
            _split_statements(source, source_section), start=1
        ):
            evidence_id = f"clinical-education-evidence-{len(evidence) + 1}"
            statement_id = f"source-statement-{index}"
            evidence.append(_evidence_item(
                evidence_id,
                field="source_statements",
                label=source_section.label,
                text=statement,
                span=span,
            ))
            result["source_statements"].append({
                "statement_id": statement_id,
                "documented_text": statement,
                "evidence_ref": evidence_id,
            })
            result["evidence_citations"].append({
                "citation_id": f"citation-{index}",
                "source_title": source_title,
                "source_version": source_version,
                "source_url": source_url,
                "evidence": statement,
                "evidence_ref": evidence_id,
            })

    result["evidence_items"] = evidence
    missing_required = [
        label for field, label in _REQUIRED_FIELDS.items()
        if field not in first_by_field
    ]
    missing_metadata = [
        label for field, label in _SOURCE_METADATA_FIELDS.items()
        if field not in first_by_field
    ]
    result["missing_required_fields"] = missing_required
    result["missing_source_metadata"] = missing_metadata

    approval = result["approved_source"]["approval_status"]["documented_text"].casefold()
    approved = approval in {value.casefold() for value in _APPROVED_VALUES}
    scope = result["approved_source"]["scope"]["documented_text"].casefold()
    complete_scope = scope in {value.casefold() for value in _COMPLETE_SCOPE_VALUES}

    if missing_required:
        result["education_status"] = "INPUT_REQUIRED"
        result["source_sufficiency_status"] = "SOURCE_NOT_PROVIDED"
        result["source_statements"] = []
        result["evidence_citations"] = []
    elif missing_metadata or not approved:
        result["education_status"] = "SOURCE_REVIEW_REQUIRED"
        result["source_sufficiency_status"] = "SOURCE_METADATA_OR_APPROVAL_INCOMPLETE"
    else:
        result["education_status"] = "READY_FOR_REVIEW"
        result["source_sufficiency_status"] = (
            "DOCUMENTED_SOURCE_READY_FOR_REVIEW"
            if complete_scope else "DOCUMENTED_SOURCE_SCOPE_LIMITED"
        )
        source_title = result["approved_source"]["title"]["documented_text"]
        for item in result["source_statements"]:
            statement = item["documented_text"]
            statement_id = item["statement_id"]
            evidence_ref = item["evidence_ref"]
            result["learning_objectives"].append({
                "objective": f"能够依据{source_title}准确复述已提供要点：{statement}",
                "source_statement_ids": [statement_id],
            })
            result["key_points"].append(_fact(statement, evidence_ref))
            result["knowledge_checks"].append({
                "question": f"请依据{source_title}复述已提供要点 {statement_id}。",
                "answer": statement,
                "source_statement_id": statement_id,
                "evidence_ref": evidence_ref,
            })

    result["source_insufficient"] = bool(
        missing_required or missing_metadata or not approved or not complete_scope
    )
    if truncated:
        result["limitations"].append(
            "输入在长度上限或不可信指令边界被截断；截断后内容未参与教学材料生成。"
        )
        result["source_insufficient"] = True
    result["_trace"] = {
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "source_char_count": len(source),
        "evidence_items_count": len(evidence),
        "valid_spans_count": sum(
            1 for item in evidence
            if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
        ),
        "llm_calls": 0,
        "network_calls": 0,
        "pubmed_calls": 0,
        "web_search_calls": 0,
        "medical_calculator_calls": 0,
        "production_writebacks": 0,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_clinical_education",
    "to_pack_output",
    "verify_clinical_education_health",
]
