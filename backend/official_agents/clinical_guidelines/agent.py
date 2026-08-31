"""Governed comparison of documented care with supplied guideline rules.

This local baseline evaluates only explicit, machine-readable rules supplied
with an approved guideline packet.  It can compare exact documented values
and calculate a documented time interval.  It does not retrieve guidelines,
authenticate a publisher, determine clinical applicability, infer missing
patient facts, assess clinical significance, or recommend treatment.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


AGENT_REF = "icoder/clinical-guidelines@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_guideline_comparison"
OUTPUT_CONTRACT_REF = "icoder/ClinicalGuidelinesOutput/v6"
MAX_INPUT_CHARS = 60_000
MAX_ITEMS = 100
EVALUATION_METHOD = "DECLARED_RULES_DETERMINISTIC_COMPARISON"
SOURCE_AUTHENTICITY_STATUS = (
    "USER_DOCUMENTED_METADATA_ONLY_NOT_INDEPENDENTLY_VERIFIED"
)

_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "\nignore previous",
    "ICODER_PROMPT_CANARY_",
)

_LABEL_TO_FIELD = {
    "临床问题": "clinical_question",
    "clinical question": "clinical_question",
    "指南领域": "guideline_domain",
    "guideline domain": "guideline_domain",
    "指南名称": "source_title",
    "批准来源": "source_title",
    "source title": "source_title",
    "指南版本": "source_version",
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
    "指南适用人群": "guideline_population",
    "guideline population": "guideline_population",
    "病例适用人群": "patient_population",
    "patient population": "patient_population",
    "指南范围": "source_scope",
    "材料范围": "source_scope",
    "source scope": "source_scope",
    "病例文档范围": "documentation_scope",
    "documentation scope": "documentation_scope",
    "指南条款": "criteria",
    "guideline criteria": "criteria",
    "评估规则": "evaluation_rules",
    "evaluation rules": "evaluation_rules",
    "病例事实": "documented_facts",
    "documented facts": "documented_facts",
}
_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?:#{{1,6}}[ \t]*)?"
    rf"(?P<label>{_LABEL_PATTERN})[ \t]*"
    rf"(?:[：:][ \t]*(?P<inline>[^\r\n]*)|(?P<line_end>\r?\n|$))"
)
_LEADING_ITEM_RE = re.compile(
    r"^[ \t]*(?:[-*•][ \t]*|\(?\d{1,3}\)?[.)、．][ \t]+)"
)
_APPROVED_VALUES = frozenset({"已批准"})
_COMPLETE_SCOPE_VALUES = frozenset({"完整", "完整材料", "full", "complete"})
_MISSING_VALUE_MARKERS = frozenset(
    {"", "未记录", "未提供", "未知", "不详", "not documented", "unknown"}
)

_REQUIRED_FIELDS = {
    "clinical_question": "临床问题",
    "guideline_domain": "指南领域",
    "source_title": "指南名称",
    "criteria": "指南条款",
    "evaluation_rules": "评估规则",
    "documented_facts": "病例事实",
}
_SOURCE_METADATA_FIELDS = {
    "source_version": "指南版本",
    "publication_date": "发布日期/更新日期",
    "approval_status": "医院批准状态",
    "approval_date": "医院批准日期",
    "approval_organization": "批准机构",
    "source_organization": "来源机构",
    "source_url": "来源网址/文档标识",
    "guideline_population": "指南适用人群",
    "patient_population": "病例适用人群",
    "source_scope": "指南范围",
    "documentation_scope": "病例文档范围",
}

_PUBLIC_FIELDS = (
    "guideline_status",
    "clinical_question",
    "guideline_domain",
    "guideline_source",
    "guideline_population",
    "patient_population",
    "documentation_scope",
    "guideline_source_eligible_for_review",
    "source_authenticity_status",
    "source_currency_verified",
    "applicability_status",
    "document_consistency_status",
    "evaluation_method",
    "guideline_criteria",
    "documented_facts",
    "documentation_conflicts",
    "criteria_checked",
    "aligned_items",
    "deviations",
    "not_assessable_items",
    "overall_assessment",
    "guideline_availability_status",
    "evidence_citations",
    "evidence_items",
    "missing_required_fields",
    "missing_source_metadata",
    "missing_patient_information",
    "limitations",
    "guideline_retrieval_performed",
    "web_search_performed",
    "clinical_inference_performed",
    "clinical_significance_assessed",
    "treatment_recommendations_generated",
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


def verify_clinical_guidelines_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "guideline_retrieval_performed": False,
        "source_authenticity_independently_verified": False,
        "source_currency_verified": False,
        "clinical_inference_performed": False,
        "clinical_significance_assessed": False,
        "treatment_recommendations_generated": False,
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
    while end > start and source[end - 1].isspace():
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


def _section_lines(source: str, section: Section) -> list[tuple[str, list[int]]]:
    lines: list[tuple[str, list[int]]] = []
    cursor = 0
    for raw_line in section.value.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        local_start = 0
        leading = _LEADING_ITEM_RE.match(content)
        if leading:
            local_start = leading.end()
        value, span = _trim_span(
            source,
            section.span[0] + cursor + local_start,
            section.span[0] + cursor + len(content),
        )
        if value and len(lines) < MAX_ITEMS:
            lines.append((value, span))
        cursor += len(raw_line)
    if not lines and section.value:
        lines.append((section.value, list(section.span)))
    return lines


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _blank_result(run_id: str) -> dict[str, Any]:
    return {
        "guideline_status": "INPUT_REQUIRED",
        "clinical_question": _fact(),
        "guideline_domain": _fact(),
        "guideline_source": {
            "title": _fact(),
            "version": _fact(),
            "publication_date": _fact(),
            "approval_status": _fact(),
            "approval_date": _fact(),
            "approval_organization": _fact(),
            "source_organization": _fact(),
            "source_url": _fact(),
            "scope": _fact(),
            "domain_match": False,
        },
        "guideline_population": _fact(),
        "patient_population": _fact(),
        "documentation_scope": _fact(),
        "guideline_source_eligible_for_review": False,
        "source_authenticity_status": SOURCE_AUTHENTICITY_STATUS,
        "source_currency_verified": False,
        "applicability_status": "NOT_ASSESSABLE",
        "document_consistency_status": "NOT_ASSESSED",
        "evaluation_method": EVALUATION_METHOD,
        "guideline_criteria": [],
        "documented_facts": [],
        "documentation_conflicts": [],
        "criteria_checked": [],
        "aligned_items": [],
        "deviations": [],
        "not_assessable_items": [],
        "overall_assessment": "NOT_ASSESSABLE",
        "guideline_availability_status": "SOURCE_NOT_PROVIDED",
        "evidence_citations": [],
        "evidence_items": [],
        "missing_required_fields": list(_REQUIRED_FIELDS.values()),
        "missing_source_metadata": list(_SOURCE_METADATA_FIELDS.values()),
        "missing_patient_information": [],
        "limitations": [
            "仅评估明确标题字段、结构化病例事实和用户提供的确定性评估规则。",
            "未联网检索指南，未独立验证来源真实性、许可、批准权限、版本时效或是否为最新版本。",
            "精确人群文本匹配不等于临床适用性判断；不推断诊断、病情、禁忌证或未记录行为。",
            "只支持 PRESENT、EQUALS 和 TIME_WINDOW_HOURS 规则；未提供或冲突事实返回 NOT_ASSESSABLE。",
            "偏差表示记录事实与声明规则不一致，不表示医疗错误，也不评估临床意义或建议治疗。",
            "结果仅供临床治理人工复核，不自动处罚、发布、修改病历或写回系统。",
        ],
        "guideline_retrieval_performed": False,
        "web_search_performed": False,
        "clinical_inference_performed": False,
        "clinical_significance_assessed": False,
        "treatment_recommendations_generated": False,
        "external_knowledge_used": False,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id,
            "provider_trace_refs": [f"{run_id}:governed-clinical-guidelines"],
        },
    }


_SCALAR_TARGETS = {
    "clinical_question": ("clinical_question",),
    "guideline_domain": ("guideline_domain",),
    "source_title": ("guideline_source", "title"),
    "source_version": ("guideline_source", "version"),
    "publication_date": ("guideline_source", "publication_date"),
    "approval_status": ("guideline_source", "approval_status"),
    "approval_date": ("guideline_source", "approval_date"),
    "approval_organization": ("guideline_source", "approval_organization"),
    "source_organization": ("guideline_source", "source_organization"),
    "source_url": ("guideline_source", "source_url"),
    "source_scope": ("guideline_source", "scope"),
    "guideline_population": ("guideline_population",),
    "patient_population": ("patient_population",),
    "documentation_scope": ("documentation_scope",),
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


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _domain_matches(domain: str, source_url: str) -> bool:
    domain = domain.strip().casefold().rstrip("/")
    source_url = source_url.strip().casefold()
    if not domain or not source_url:
        return False
    if "://" in domain:
        return source_url == domain or source_url.startswith(domain + "/")
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    expected = domain.removeprefix("www.").rstrip(".")
    return bool(host and (host == expected or host.endswith("." + expected)))


def _parse_datetime(value: str) -> datetime | None:
    candidate = value.strip().replace("/", "-")
    candidate = re.sub(r"年|月", "-", candidate).replace("日", "")
    candidate = candidate.replace("时", ":").replace("分", "")
    candidate = candidate.replace("T", " ")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _parse_criteria(
    source: str,
    section: Section | None,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    criteria: list[dict[str, Any]] = []
    if section is None:
        return criteria
    for index, (line, span) in enumerate(_section_lines(source, section), start=1):
        if "|" in line:
            criterion_id, text = line.split("|", 1)
            criterion_id = criterion_id.strip() or f"C{index}"
            text = text.strip()
            offset = line.find(text)
            text_span = [span[0] + offset, span[0] + offset + len(text)]
        else:
            criterion_id, text, text_span = f"C{index}", line, span
        if not text:
            continue
        evidence_id = f"clinical-guidelines-evidence-{len(evidence) + 1}"
        evidence.append(_evidence_item(
            evidence_id,
            field="guideline_criteria",
            label=section.label,
            text=text,
            span=text_span,
        ))
        criteria.append({
            "criterion_id": criterion_id,
            "guideline_text": text,
            "evidence_ref": evidence_id,
        })
    return criteria


def _parse_rules(
    source: str,
    section: Section | None,
    evidence: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    if section is None:
        return rules
    for line, span in _section_lines(source, section):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            continue
        criterion_id, rule_type = parts[0], parts[1].upper()
        evidence_id = f"clinical-guidelines-evidence-{len(evidence) + 1}"
        evidence.append(_evidence_item(
            evidence_id,
            field="evaluation_rules",
            label=section.label,
            text=line,
            span=span,
        ))
        rules.setdefault(criterion_id, {
            "criterion_id": criterion_id,
            "rule_type": rule_type,
            "arguments": parts[2:],
            "rule_text": line,
            "evidence_ref": evidence_id,
        })
    return rules


def _parse_facts(
    source: str,
    section: Section | None,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    if section is None:
        return facts
    for index, (line, span) in enumerate(_section_lines(source, section), start=1):
        if "=" not in line:
            continue
        left, value = line.split("=", 1)
        if "|" in left:
            document, field = left.split("|", 1)
        else:
            document, field = "病例记录", left
        document, field, value = document.strip(), field.strip(), value.strip()
        if not field:
            continue
        evidence_id = f"clinical-guidelines-evidence-{len(evidence) + 1}"
        evidence.append(_evidence_item(
            evidence_id,
            field="documented_facts",
            label=section.label,
            text=line,
            span=span,
        ))
        facts.append({
            "fact_id": f"fact-{index}",
            "source_document": document or "病例记录",
            "field": field,
            "documented_value": value,
            "evidence_text": line,
            "evidence_ref": evidence_id,
        })
    return facts


def _index_facts(facts: list[dict[str, Any]]) -> tuple[
    dict[str, list[dict[str, Any]]], list[dict[str, Any]]
]:
    by_field: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_field.setdefault(_normalize(fact["field"]), []).append(fact)
    conflicts: list[dict[str, Any]] = []
    for items in by_field.values():
        values = {_normalize(item["documented_value"]) for item in items}
        if len(values) > 1:
            conflicts.append({
                "field": items[0]["field"],
                "documented_values": [item["documented_value"] for item in items],
                "source_documents": [item["source_document"] for item in items],
                "evidence_refs": [item["evidence_ref"] for item in items],
            })
    return by_field, conflicts


def _single_fact(
    by_field: dict[str, list[dict[str, Any]]], field: str
) -> tuple[dict[str, Any] | None, str]:
    items = by_field.get(_normalize(field)) or []
    if not items:
        return None, "missing"
    if len({_normalize(item["documented_value"]) for item in items}) > 1:
        return None, "conflicting"
    return items[0], "ok"


def _not_assessable(
    criterion: dict[str, Any],
    rule: dict[str, Any] | None,
    reason: str,
    patient_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "criterion_id": criterion["criterion_id"],
        "guideline_criteria": criterion["guideline_text"],
        "evaluation_rule": (rule or {}).get("rule_text", ""),
        "observed_evidence": [],
        "assessment": "NOT_ASSESSABLE",
        "computed_value": "",
        "deviations": "",
        "uncertainty": reason,
        "citations": criterion["criterion_id"],
        "source_criterion_evidence_ref": criterion["evidence_ref"],
        "rule_evidence_ref": (rule or {}).get("evidence_ref", ""),
        "patient_evidence_refs": patient_refs or [],
    }


def _evaluate_criterion(
    criterion: dict[str, Any],
    rule: dict[str, Any] | None,
    by_field: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if rule is None:
        return _not_assessable(criterion, None, "未提供与该条款对应的确定性评估规则。"), missing
    args = rule["arguments"]
    rule_type = rule["rule_type"]
    observed: list[dict[str, str]] = []
    refs: list[str] = []

    if rule_type == "TIME_WINDOW_HOURS" and len(args) == 3:
        start_field, end_field, threshold_text = args
        start_fact, start_state = _single_fact(by_field, start_field)
        end_fact, end_state = _single_fact(by_field, end_field)
        for field, fact, state in (
            (start_field, start_fact, start_state),
            (end_field, end_fact, end_state),
        ):
            if state != "ok" or fact is None:
                missing.append(f"{field}（{state}）")
            else:
                observed.append({
                    "field": fact["field"],
                    "documented_value": fact["documented_value"],
                    "source_document": fact["source_document"],
                })
                refs.append(fact["evidence_ref"])
        if missing:
            return _not_assessable(
                criterion,
                rule,
                "时间比较所需病例事实缺失或相互冲突。",
                refs,
            ), missing
        start = _parse_datetime(start_fact["documented_value"])
        end = _parse_datetime(end_fact["documented_value"])
        try:
            threshold = float(threshold_text)
        except ValueError:
            threshold = -1
        if start is None or end is None or threshold < 0 or end < start:
            return _not_assessable(
                criterion,
                rule,
                "时间格式、阈值或时间先后关系无法确定性计算。",
                refs,
            ), missing
        elapsed = (end - start).total_seconds() / 3600
        met = elapsed <= threshold
        elapsed_text = f"{elapsed:g}小时"
        threshold_display = f"{threshold:g}小时"
        deviation = "" if met else (
            f"已记录时间间隔为{elapsed_text}，超过声明规则阈值{threshold_display}。"
        )
        return {
            "criterion_id": criterion["criterion_id"],
            "guideline_criteria": criterion["guideline_text"],
            "evaluation_rule": rule["rule_text"],
            "observed_evidence": observed,
            "assessment": "MET" if met else "NOT_MET",
            "computed_value": elapsed_text,
            "deviations": deviation,
            "uncertainty": "仅比较用户提供的记录时间与声明阈值，未验证临床适用性或记录真实性。",
            "citations": criterion["criterion_id"],
            "source_criterion_evidence_ref": criterion["evidence_ref"],
            "rule_evidence_ref": rule["evidence_ref"],
            "patient_evidence_refs": refs,
        }, missing

    if rule_type in {"EQUALS", "PRESENT"}:
        expected = args[1] if rule_type == "EQUALS" and len(args) == 2 else ""
        if (rule_type == "EQUALS" and len(args) != 2) or (
            rule_type == "PRESENT" and len(args) != 1
        ):
            return _not_assessable(criterion, rule, "评估规则参数数量无效。"), missing
        field = args[0]
        fact, state = _single_fact(by_field, field)
        if state != "ok" or fact is None:
            missing.append(f"{field}（{state}）")
            return _not_assessable(
                criterion,
                rule,
                "比较所需病例事实缺失或相互冲突。",
            ), missing
        observed = [{
            "field": fact["field"],
            "documented_value": fact["documented_value"],
            "source_document": fact["source_document"],
        }]
        refs = [fact["evidence_ref"]]
        if rule_type == "PRESENT":
            met = _normalize(fact["documented_value"]) not in {
                _normalize(marker) for marker in _MISSING_VALUE_MARKERS
            }
            expected = "有明确记录"
        else:
            met = _normalize(fact["documented_value"]) == _normalize(expected)
        deviation = "" if met else (
            f"字段“{field}”已记录值“{fact['documented_value']}”与声明规则期望“{expected}”不一致。"
        )
        return {
            "criterion_id": criterion["criterion_id"],
            "guideline_criteria": criterion["guideline_text"],
            "evaluation_rule": rule["rule_text"],
            "observed_evidence": observed,
            "assessment": "MET" if met else "NOT_MET",
            "computed_value": fact["documented_value"],
            "deviations": deviation,
            "uncertainty": "只进行显式字段比较，不判断未记录是否等于未实施。",
            "citations": criterion["criterion_id"],
            "source_criterion_evidence_ref": criterion["evidence_ref"],
            "rule_evidence_ref": rule["evidence_ref"],
            "patient_evidence_refs": refs,
        }, missing

    return _not_assessable(
        criterion,
        rule,
        "规则类型不受支持；仅支持 PRESENT、EQUALS 和 TIME_WINDOW_HOURS。",
    ), missing


def build_clinical_guidelines(text: Any, *, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or f"clinical-guidelines-{uuid.uuid4()}"
    source, truncated = _bounded_text(text)
    result = _blank_result(run_id)
    sections = _sections(source)
    first_by_field: dict[str, Section] = {}
    evidence: list[dict[str, Any]] = []

    for section in sections:
        first_by_field.setdefault(section.field, section)
        if section.field in {"criteria", "evaluation_rules", "documented_facts"}:
            continue
        evidence_id = f"clinical-guidelines-evidence-{len(evidence) + 1}"
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

    criteria = _parse_criteria(source, first_by_field.get("criteria"), evidence)
    rules = _parse_rules(source, first_by_field.get("evaluation_rules"), evidence)
    facts = _parse_facts(source, first_by_field.get("documented_facts"), evidence)
    result["guideline_criteria"] = criteria
    result["documented_facts"] = facts
    by_field, conflicts = _index_facts(facts)
    result["documentation_conflicts"] = conflicts
    result["document_consistency_status"] = (
        "CONFLICTS_DETECTED" if conflicts else (
            "NO_CONFLICTS_DETECTED" if facts else "NOT_ASSESSED"
        )
    )

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

    domain = result["guideline_domain"]["documented_text"]
    source_url = result["guideline_source"]["source_url"]["documented_text"]
    domain_match = _domain_matches(domain, source_url)
    result["guideline_source"]["domain_match"] = domain_match
    approval = result["guideline_source"]["approval_status"]["documented_text"]
    approved = _normalize(approval) in {_normalize(value) for value in _APPROVED_VALUES}
    source_eligible = not missing_metadata and approved and domain_match
    result["guideline_source_eligible_for_review"] = source_eligible

    guideline_population = result["guideline_population"]["documented_text"]
    patient_population = result["patient_population"]["documented_text"]
    population_matches = bool(
        guideline_population
        and patient_population
        and _normalize(guideline_population) == _normalize(patient_population)
    )
    result["applicability_status"] = (
        "DOCUMENTED_POPULATION_MATCH"
        if population_matches
        else "DOCUMENTED_POPULATION_MISMATCH_OR_MISSING"
    )

    scope = result["guideline_source"]["scope"]["documented_text"]
    complete_scope = _normalize(scope) in {
        _normalize(value) for value in _COMPLETE_SCOPE_VALUES
    }

    if missing_required:
        result["guideline_status"] = "INPUT_REQUIRED"
        result["guideline_availability_status"] = "SOURCE_NOT_PROVIDED"
    elif not source_eligible:
        result["guideline_status"] = "SOURCE_REVIEW_REQUIRED"
        result["guideline_availability_status"] = "DOCUMENTED_SOURCE_NOT_ELIGIBLE"
    elif not population_matches:
        result["guideline_status"] = "APPLICABILITY_REVIEW_REQUIRED"
        result["guideline_availability_status"] = (
            "DOCUMENTED_GUIDELINE_APPLICABILITY_UNCONFIRMED"
        )
    else:
        result["guideline_status"] = "READY_FOR_REVIEW"
        result["guideline_availability_status"] = "DOCUMENTED_GUIDELINE_AVAILABLE"

    source_title = result["guideline_source"]["title"]["documented_text"]
    source_version = result["guideline_source"]["version"]["documented_text"]
    for criterion in criteria:
        result["evidence_citations"].append({
            "criterion_id": criterion["criterion_id"],
            "source_title": source_title,
            "source_version": source_version,
            "source_url": source_url,
            "guideline_text": criterion["guideline_text"],
            "evidence_ref": criterion["evidence_ref"],
        })

    can_evaluate = result["guideline_status"] == "READY_FOR_REVIEW"
    missing_patient: list[str] = []
    for criterion in criteria:
        rule = rules.get(criterion["criterion_id"])
        if can_evaluate:
            checked, missing = _evaluate_criterion(criterion, rule, by_field)
        else:
            reason = (
                "指南来源、批准、领域或适用人群尚未通过开发环境评估门禁。"
            )
            checked, missing = _not_assessable(criterion, rule, reason), []
        result["criteria_checked"].append(checked)
        missing_patient.extend(item for item in missing if item not in missing_patient)
        if checked["assessment"] == "MET":
            result["aligned_items"].append({
                "criterion_id": checked["criterion_id"],
                "documented_alignment": checked["computed_value"],
            })
        elif checked["assessment"] == "NOT_MET":
            result["deviations"].append({
                "criterion_id": checked["criterion_id"],
                "documented_deviation": checked["deviations"],
            })
        else:
            result["not_assessable_items"].append({
                "criterion_id": checked["criterion_id"],
                "reason": checked["uncertainty"],
            })
    result["missing_patient_information"] = missing_patient

    assessments = [item["assessment"] for item in result["criteria_checked"]]
    if can_evaluate and "NOT_MET" in assessments:
        result["overall_assessment"] = "NOT_MET"
    elif can_evaluate and assessments and all(value == "MET" for value in assessments):
        result["overall_assessment"] = "MET"
    else:
        result["overall_assessment"] = "NOT_ASSESSABLE"

    if not complete_scope:
        result["limitations"].append(
            "用户未声明指南材料范围完整；结果不能代表完整指南覆盖。"
        )
    if truncated:
        result["limitations"].append(
            "输入在长度上限或不可信指令边界被截断；截断后内容未参与评估。"
        )
    result["evidence_items"] = evidence
    result["_trace"] = {
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "source_char_count": len(source),
        "evidence_items_count": len(evidence),
        "valid_spans_count": sum(
            1 for item in evidence
            if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
        ),
        "criteria_count": len(criteria),
        "evaluated_criteria_count": sum(
            1 for item in result["criteria_checked"]
            if item["assessment"] != "NOT_ASSESSABLE"
        ),
        "llm_calls": 0,
        "network_calls": 0,
        "web_search_calls": 0,
        "production_writebacks": 0,
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "build_clinical_guidelines",
    "to_pack_output",
    "verify_clinical_guidelines_health",
]
