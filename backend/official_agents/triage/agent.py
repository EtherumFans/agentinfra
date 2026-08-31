"""Deterministic review of caller-supplied triage questionnaires and answers.

The local baseline does not extract answers from a transcript and does not
invent or validate a clinical protocol.  It validates a bounded questionnaire
definition, binds explicitly supplied answers to exact source-record spans,
and follows the declared branch graph.  Any reached endpoint is a development
protocol candidate that must be confirmed by an on-site triage professional.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from uuid import uuid4


AGENT_REF = "icoder/triage@1.1.2"
OUTPUT_CONTRACT_REF = "icoder/TriageOutput/v5"
LOCAL_RUNTIME_MODE = "governed_local_explicit_triage_questionnaire_review"
REVIEW_METHOD = "EXPLICIT_ANSWER_DETERMINISTIC_QUESTIONNAIRE_PATH_REVIEW"
MAX_INPUT_CHARS = 60_000
MAX_QUESTIONS = 64
MAX_ENDPOINTS = 16
MAX_BRANCHES_PER_QUESTION = 16
MAX_PATH_STEPS = 64
MAX_EVIDENCE_ITEMS = 100

_DECLARED_PROTOCOL_STATUSES = {
    "DEVELOPMENT_FIXTURE",
    "HOSPITAL_APPROVED_ATTESTED",
}
_CANDIDATE_LEVELS = {"IMMEDIATE", "URGENT", "STANDARD", "LOWER_ACUITY"}
_ANSWER_TYPES = {"boolean", "number", "enum"}
_OPERATORS = {"equals", "in", "lt", "lte", "gt", "gte", "default"}
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_RED_FLAG_CODE_RE = re.compile(r"^RF_[A-Z0-9_]{1,60}$")
_UNTRUSTED_PATTERN = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?(?:system|developer)\s+prompt|"
    r"system\s+prompt|developer\s+message|"
    r"忽略.{0,12}(?:指令|提示)|(?:系统|开发者)提示词)",
    re.IGNORECASE,
)

_LABEL_TO_FIELD = {
    "审核目的": "review_purpose",
    "review purpose": "review_purpose",
    "协议标识": "protocol_id",
    "protocol id": "protocol_id",
    "协议版本": "protocol_version",
    "protocol version": "protocol_version",
    "协议声明状态": "declared_status",
    "protocol declared status": "declared_status",
    "协议来源": "protocol_source",
    "protocol source": "protocol_source",
    "批准证明编号": "approval_attestation_id",
    "approval attestation id": "approval_attestation_id",
    "来源记录": "source_record",
    "source record": "source_record",
    "问卷定义json": "questionnaire_json",
    "questionnaire json": "questionnaire_json",
    "问卷回答json": "answers_json",
    "questionnaire answers json": "answers_json",
}
_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABEL_TO_FIELD, key=len, reverse=True)
)
_HEADING_RE = re.compile(
    rf"(?im)^[ \t]*(?P<label>{_LABEL_PATTERN})[ \t]*[：:][ \t]*"
)

_PUBLIC_FIELDS = (
    "assessment_status",
    "review_method",
    "acuity_level",
    "red_flags",
    "supporting_evidence",
    "recommended_disposition",
    "immediate_actions",
    "missing_information",
    "uncertainty",
    "protocol_governance",
    "questionnaire_validation",
    "decision_path",
    "protocol_candidate",
    "clarification_questions",
    "input_conflicts",
    "evidence_items",
    "limitations",
    "transcript_extraction_performed",
    "questionnaire_answer_inference_performed",
    "clinical_inference_performed",
    "medical_calculator_used",
    "external_knowledge_used",
    "final_acuity_assignment_performed",
    "production_action_blocked",
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


def verify_triage_questionnaire_health() -> dict[str, Any]:
    return {
        "agent_ref": AGENT_REF,
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "output_contract": OUTPUT_CONTRACT_REF,
        "review_method": REVIEW_METHOD,
        "network_required": False,
        "llm_required": False,
        "deterministic": True,
        "transcript_extraction_performed": False,
        "questionnaire_answer_inference_performed": False,
        "clinical_inference_performed": False,
        "medical_calculator_used": False,
        "final_acuity_assignment_performed": False,
        "production_action_blocked": True,
        "production_writeback_blocked": True,
    }


def _bounded_text(value: Any) -> tuple[str, bool]:
    raw = str(value or "").replace("\x00", "")
    return raw[:MAX_INPUT_CHARS], len(raw) > MAX_INPUT_CHARS


def _trimmed(source: str, start: int, end: int) -> tuple[str, list[int]]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    value = source[start:end]
    if value.startswith("<<<") and value.endswith(">>>"):
        start += 3
        end -= 3
        while start < end and source[start] in " \t\r\n":
            start += 1
        while end > start and source[end - 1] in " \t\r\n":
            end -= 1
        value = source[start:end]
    return value, [start, end]


def _sections(source: str) -> dict[str, Section]:
    matches = list(_HEADING_RE.finditer(source))
    sections: dict[str, Section] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        value, span = _trimmed(source, match.end(), end)
        field = _LABEL_TO_FIELD[match.group("label").casefold()]
        if field not in sections and value:
            sections[field] = Section(field, match.group("label"), value, span)
    return sections


def _blank_result(run_id: str) -> dict[str, Any]:
    return {
        "assessment_status": "INPUT_REQUIRED",
        "review_method": REVIEW_METHOD,
        "acuity_level": "NOT_ASSIGNED",
        "red_flags": [],
        "supporting_evidence": "未执行问卷路径。",
        "recommended_disposition": (
            "信息不足；请由现场分诊专业人员立即复核，不得据此降低紧急程度。"
        ),
        "immediate_actions": ["由现场分诊专业人员复核并补齐协议要求的信息"],
        "missing_information": [],
        "uncertainty": "缺少可验证的问卷配置或明确回答，未生成分诊级别。",
        "protocol_governance": {
            "protocol_id": "",
            "protocol_version": "",
            "declared_status": "",
            "protocol_source": "",
            "approval_attestation_id": "",
            "verification_status": "NOT_VERIFIED",
            "jurisdiction": "CN_HOSPITAL_LOCAL_DECLARATION",
        },
        "questionnaire_validation": {
            "valid": False,
            "errors": [],
            "question_count": 0,
            "endpoint_count": 0,
            "all_references_resolved": False,
            "cycle_free": False,
        },
        "decision_path": [],
        "protocol_candidate": {
            "reached": False,
            "endpoint_id": "",
            "candidate_level": "NOT_ASSIGNED",
            "disposition": "",
            "red_flag_codes": [],
            "result_status": "NOT_ASSESSED",
        },
        "clarification_questions": [],
        "input_conflicts": [],
        "evidence_items": [],
        "limitations": [
            "仅验证调用方明确提供的问卷定义和结构化回答，不从访谈或自由文本抽取回答。",
            "协议状态、来源和批准证明均为调用方声明，平台未验证其临床有效性、授权或医院批准状态。",
            "不计算 qSOFA、HEART、CURB-65、ESI 或其他临床评分；数值分支仅机械执行调用方规则。",
            "到达的终点只是开发期协议路径候选，不是最终分诊级别、诊断、检查或治疗建议。",
            "缺失、冲突、无匹配分支或协议无效时禁止降低紧急程度，必须现场人工复核。",
            "禁止自动处置、影像建议、药物/剂量/操作建议、患者分流、转运、出院或写回。",
        ],
        "transcript_extraction_performed": False,
        "questionnaire_answer_inference_performed": False,
        "clinical_inference_performed": False,
        "medical_calculator_used": False,
        "external_knowledge_used": False,
        "final_acuity_assignment_performed": False,
        "production_action_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id or str(uuid4()),
            "provider_trace_refs": [
                f"{run_id or 'local'}:governed-triage-questionnaire-review"
            ],
        },
        "_trace": {
            "input_truncated": False,
            "prompt_canary_detected": False,
            "evidence_items_count": 0,
            "valid_spans_count": 0,
            "question_count": 0,
            "endpoint_count": 0,
            "path_steps": 0,
        },
    }


def _add_section_evidence(
    result: dict[str, Any],
    section: Section,
) -> str:
    if len(result["evidence_items"]) >= MAX_EVIDENCE_ITEMS:
        return ""
    evidence_id = f"triage-evidence-{len(result['evidence_items']) + 1}"
    result["evidence_items"].append({
        "evidence_id": evidence_id,
        "field": section.field,
        "source_document": "triage_request",
        "text": section.value,
        "char_span": list(section.span),
        "evidence_status": "EXACT_INPUT_SPAN",
    })
    return evidence_id


def _add_answer_evidence(
    result: dict[str, Any],
    *,
    source: str,
    source_section: Section,
    question_id: str,
    source_document: str,
    evidence_text: str,
) -> tuple[str, str]:
    if not evidence_text:
        return "", "empty_evidence_text"
    relative_positions = [
        match.start() for match in re.finditer(re.escape(evidence_text), source_section.value)
    ]
    if not relative_positions:
        return "", "evidence_not_found_in_source_record"
    if len(relative_positions) != 1:
        return "", "evidence_not_unique_in_source_record"
    start = source_section.span[0] + relative_positions[0]
    end = start + len(evidence_text)
    if source[start:end] != evidence_text:
        return "", "evidence_span_mismatch"
    if len(result["evidence_items"]) >= MAX_EVIDENCE_ITEMS:
        return "", "evidence_limit_exceeded"
    evidence_id = f"triage-evidence-{len(result['evidence_items']) + 1}"
    result["evidence_items"].append({
        "evidence_id": evidence_id,
        "field": f"answer:{question_id}",
        "source_document": source_document,
        "text": evidence_text,
        "char_span": [start, end],
        "evidence_status": "EXACT_INPUT_SPAN",
    })
    return evidence_id, ""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_questionnaire(value: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, dict):
        return {}, ["questionnaire_must_be_object"]
    questions = value.get("questions")
    endpoints = value.get("endpoints")
    start_id = value.get("start_question_id")
    errors: list[str] = []
    if not isinstance(start_id, str) or not _ID_RE.fullmatch(start_id):
        errors.append("invalid_start_question_id")
    if not isinstance(questions, list) or not (1 <= len(questions) <= MAX_QUESTIONS):
        errors.append("invalid_question_count")
        questions = []
    if not isinstance(endpoints, list) or not (1 <= len(endpoints) <= MAX_ENDPOINTS):
        errors.append("invalid_endpoint_count")
        endpoints = []

    question_by_id: dict[str, dict[str, Any]] = {}
    endpoint_by_id: dict[str, dict[str, Any]] = {}
    for item in questions:
        if not isinstance(item, dict):
            errors.append("question_must_be_object")
            continue
        question_id = item.get("id")
        answer_type = item.get("answer_type")
        branches = item.get("branches")
        if not isinstance(question_id, str) or not _ID_RE.fullmatch(question_id):
            errors.append("invalid_question_id")
            continue
        if question_id in question_by_id:
            errors.append(f"duplicate_question_id:{question_id}")
            continue
        if answer_type not in _ANSWER_TYPES:
            errors.append(f"invalid_answer_type:{question_id}")
        if item.get("required") is not True:
            errors.append(f"question_must_be_required:{question_id}")
        if not isinstance(branches, list) or not (
            1 <= len(branches) <= MAX_BRANCHES_PER_QUESTION
        ):
            errors.append(f"invalid_branches:{question_id}")
            branches = []
        allowed_values = item.get("allowed_values")
        if answer_type == "enum" and not (
            isinstance(allowed_values, list)
            and allowed_values
            and all(isinstance(v, str) and 0 < len(v) <= 64 for v in allowed_values)
            and len(set(allowed_values)) == len(allowed_values)
        ):
            errors.append(f"invalid_enum_values:{question_id}")
        default_count = 0
        for branch in branches:
            if not isinstance(branch, dict):
                errors.append(f"branch_must_be_object:{question_id}")
                continue
            operator = branch.get("operator")
            if operator not in _OPERATORS:
                errors.append(f"invalid_branch_operator:{question_id}")
            if operator == "default":
                default_count += 1
            next_id = branch.get("next")
            if not isinstance(next_id, str) or not _ID_RE.fullmatch(next_id):
                errors.append(f"invalid_branch_target:{question_id}")
            branch_value = branch.get("value")
            if operator in {"lt", "lte", "gt", "gte"} and not _is_number(branch_value):
                errors.append(f"numeric_branch_value_required:{question_id}")
            if answer_type == "boolean" and operator == "equals" and not isinstance(
                branch_value, bool
            ):
                errors.append(f"boolean_branch_value_required:{question_id}")
        if default_count > 1:
            errors.append(f"multiple_default_branches:{question_id}")
        if answer_type == "number" and default_count != 1:
            errors.append(f"number_question_requires_one_default:{question_id}")
        question_by_id[question_id] = item

    for item in endpoints:
        if not isinstance(item, dict):
            errors.append("endpoint_must_be_object")
            continue
        endpoint_id = item.get("id")
        candidate_level = item.get("candidate_level")
        red_flag_codes = item.get("red_flag_codes", [])
        if not isinstance(endpoint_id, str) or not _ID_RE.fullmatch(endpoint_id):
            errors.append("invalid_endpoint_id")
            continue
        if endpoint_id in endpoint_by_id or endpoint_id in question_by_id:
            errors.append(f"duplicate_node_id:{endpoint_id}")
            continue
        if candidate_level not in _CANDIDATE_LEVELS:
            errors.append(f"invalid_candidate_level:{endpoint_id}")
        if not isinstance(red_flag_codes, list) or not all(
            isinstance(code, str) and _RED_FLAG_CODE_RE.fullmatch(code)
            for code in red_flag_codes
        ):
            errors.append(f"invalid_red_flag_codes:{endpoint_id}")
        endpoint_by_id[endpoint_id] = item

    if isinstance(start_id, str) and start_id not in question_by_id:
        errors.append("start_question_not_found")
    all_ids = set(question_by_id) | set(endpoint_by_id)
    for question_id, item in question_by_id.items():
        for branch in item.get("branches") or []:
            if isinstance(branch, dict) and branch.get("next") not in all_ids:
                errors.append(f"unresolved_branch_target:{question_id}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(question_id: str) -> None:
        if question_id in visiting:
            errors.append(f"questionnaire_cycle:{question_id}")
            return
        if question_id in visited or question_id not in question_by_id:
            return
        visiting.add(question_id)
        for branch in question_by_id[question_id].get("branches") or []:
            if isinstance(branch, dict) and isinstance(branch.get("next"), str):
                visit(branch["next"])
        visiting.remove(question_id)
        visited.add(question_id)

    if isinstance(start_id, str):
        visit(start_id)
    return {
        "start_question_id": start_id,
        "question_by_id": question_by_id,
        "endpoint_by_id": endpoint_by_id,
    }, sorted(set(errors))


def _answer_matches_type(value: Any, question: dict[str, Any]) -> bool:
    answer_type = question.get("answer_type")
    if answer_type == "boolean":
        return isinstance(value, bool)
    if answer_type == "number":
        return _is_number(value)
    if answer_type == "enum":
        return isinstance(value, str) and value in (question.get("allowed_values") or [])
    return False


def _branch_matches(value: Any, branch: dict[str, Any]) -> bool:
    operator = branch.get("operator")
    expected = branch.get("value")
    if operator == "equals":
        return value == expected
    if operator == "in":
        return isinstance(expected, list) and value in expected
    if operator == "lt":
        return _is_number(value) and _is_number(expected) and value < expected
    if operator == "lte":
        return _is_number(value) and _is_number(expected) and value <= expected
    if operator == "gt":
        return _is_number(value) and _is_number(expected) and value > expected
    if operator == "gte":
        return _is_number(value) and _is_number(expected) and value >= expected
    return False


def _safe_disposition(candidate_level: str) -> tuple[str, list[str]]:
    if candidate_level == "IMMEDIATE":
        return (
            "协议路径候选：立即现场人工紧急评估；不是最终分诊级别。",
            [
                "立即通知现场分诊护士和急诊医师",
                "进入医院批准的抢救或紧急评估流程",
                "由现场人员持续观察并按批准协议复测关键参数",
            ],
        )
    if candidate_level == "URGENT":
        return (
            "协议路径候选：尽快现场人工评估；不是最终分诊级别。",
            ["通知现场分诊护士复核", "按医院批准协议完成缺失问题和关键参数复测"],
        )
    if candidate_level == "STANDARD":
        return (
            "协议路径候选：现场标准分诊复核；不得据此延迟临床评估。",
            ["由现场分诊护士确认问卷路径和患者当前状态"],
        )
    return (
        "协议路径候选：较低紧急度待现场确认；不得自动分流或出院。",
        ["由现场分诊护士确认全部协议条件后再决定最终级别"],
    )


def build_triage_questionnaire_review(text: Any, *, run_id: str = "") -> dict[str, Any]:
    source, truncated = _bounded_text(text)
    result = _blank_result(run_id)
    result["_trace"]["input_truncated"] = truncated
    result["_trace"]["prompt_canary_detected"] = bool(_UNTRUSTED_PATTERN.search(source))
    sections = _sections(source)

    required_fields = {
        "review_purpose": "审核目的",
        "protocol_id": "协议标识",
        "protocol_version": "协议版本",
        "declared_status": "协议声明状态",
        "protocol_source": "协议来源",
        "source_record": "来源记录",
        "questionnaire_json": "问卷定义JSON",
        "answers_json": "问卷回答JSON",
    }
    missing = [label for field, label in required_fields.items() if field not in sections]
    result["missing_information"] = missing
    result["clarification_questions"] = [f"请提供：{label}" for label in missing]

    governance = result["protocol_governance"]
    for field in (
        "protocol_id",
        "protocol_version",
        "declared_status",
        "protocol_source",
        "approval_attestation_id",
    ):
        if field in sections:
            governance[field] = sections[field].value[:256]
            _add_section_evidence(result, sections[field])
    declared_status = governance["declared_status"]
    if declared_status == "DEVELOPMENT_FIXTURE":
        governance["verification_status"] = "DEVELOPMENT_ONLY_UNVERIFIED"
    elif declared_status == "HOSPITAL_APPROVED_ATTESTED":
        governance["verification_status"] = "CALLER_DECLARED_APPROVAL_NOT_PLATFORM_VERIFIED"
        if not governance["approval_attestation_id"]:
            result["input_conflicts"].append(
                "approval_attestation_id_required_for_declared_hospital_approval"
            )
    elif declared_status:
        result["input_conflicts"].append("unsupported_protocol_declared_status")

    if missing:
        result["questionnaire_validation"]["errors"] = ["required_input_missing"]
        _finish_trace(result)
        return result

    try:
        questionnaire_raw = json.loads(sections["questionnaire_json"].value)
    except (json.JSONDecodeError, TypeError, ValueError):
        result["assessment_status"] = "PROTOCOL_INVALID"
        result["questionnaire_validation"]["errors"] = ["questionnaire_json_invalid"]
        result["input_conflicts"].append("questionnaire_json_invalid")
        _finish_trace(result)
        return result
    try:
        answers_raw = json.loads(sections["answers_json"].value)
    except (json.JSONDecodeError, TypeError, ValueError):
        result["assessment_status"] = "INPUT_REQUIRED"
        result["questionnaire_validation"]["errors"] = ["answers_json_invalid"]
        result["input_conflicts"].append("answers_json_invalid")
        _finish_trace(result)
        return result

    graph, definition_errors = _validate_questionnaire(questionnaire_raw)
    question_count = len(graph.get("question_by_id") or {})
    endpoint_count = len(graph.get("endpoint_by_id") or {})
    result["questionnaire_validation"] = {
        "valid": not definition_errors,
        "errors": definition_errors,
        "question_count": question_count,
        "endpoint_count": endpoint_count,
        "all_references_resolved": not any(
            error.startswith("unresolved_branch_target") for error in definition_errors
        ),
        "cycle_free": not any(
            error.startswith("questionnaire_cycle") for error in definition_errors
        ),
    }
    result["_trace"]["question_count"] = question_count
    result["_trace"]["endpoint_count"] = endpoint_count
    if definition_errors:
        result["assessment_status"] = "PROTOCOL_INVALID"
        result["input_conflicts"].extend(definition_errors)
        result["uncertainty"] = "问卷定义无效，未执行协议路径。"
        _finish_trace(result)
        return result
    if not isinstance(answers_raw, list) or len(answers_raw) > MAX_QUESTIONS:
        result["assessment_status"] = "INPUT_REQUIRED"
        result["input_conflicts"].append("answers_must_be_bounded_array")
        _finish_trace(result)
        return result

    answers_by_id: dict[str, dict[str, Any]] = {}
    for answer in answers_raw:
        if not isinstance(answer, dict):
            result["input_conflicts"].append("answer_must_be_object")
            continue
        question_id = answer.get("question_id")
        if not isinstance(question_id, str) or question_id not in graph["question_by_id"]:
            result["input_conflicts"].append("answer_references_unknown_question")
            continue
        if question_id in answers_by_id:
            result["input_conflicts"].append(f"duplicate_answer:{question_id}")
            continue
        answers_by_id[question_id] = answer
    if result["input_conflicts"]:
        result["assessment_status"] = "CONFLICT_REVIEW_REQUIRED"
        _finish_trace(result)
        return result

    current = graph["start_question_id"]
    reached_endpoint: dict[str, Any] | None = None
    for step_index in range(MAX_PATH_STEPS):
        if current in graph["endpoint_by_id"]:
            reached_endpoint = graph["endpoint_by_id"][current]
            break
        question = graph["question_by_id"][current]
        answer = answers_by_id.get(current)
        if answer is None:
            result["missing_information"].append(f"question:{current}")
            result["clarification_questions"].append(
                f"请由现场人员按批准问卷补充问题 {current} 的明确回答"
            )
            result["assessment_status"] = "INPUT_REQUIRED"
            result["uncertainty"] = "协议路径因缺少必答问题而停止，未生成分诊级别。"
            break
        answer_value = answer.get("value")
        if not _answer_matches_type(answer_value, question):
            result["input_conflicts"].append(f"invalid_answer_type:{current}")
            result["assessment_status"] = "CONFLICT_REVIEW_REQUIRED"
            break
        evidence_text = str(answer.get("evidence_text") or "")
        source_document = str(answer.get("source_document") or "triage_record")[:128]
        evidence_ref, evidence_error = _add_answer_evidence(
            result,
            source=source,
            source_section=sections["source_record"],
            question_id=current,
            source_document=source_document,
            evidence_text=evidence_text,
        )
        if evidence_error:
            result["input_conflicts"].append(f"{evidence_error}:{current}")
            result["assessment_status"] = "CONFLICT_REVIEW_REQUIRED"
            break

        branches = question.get("branches") or []
        matches = [
            (index, branch) for index, branch in enumerate(branches)
            if isinstance(branch, dict)
            and branch.get("operator") != "default"
            and _branch_matches(answer_value, branch)
        ]
        if not matches:
            matches = [
                (index, branch) for index, branch in enumerate(branches)
                if isinstance(branch, dict) and branch.get("operator") == "default"
            ]
        if len(matches) != 1:
            result["input_conflicts"].append(f"ambiguous_or_missing_branch:{current}")
            result["assessment_status"] = "CONFLICT_REVIEW_REQUIRED"
            break
        branch_index, matched_branch = matches[0]
        next_node = str(matched_branch["next"])
        result["decision_path"].append({
            "step_index": step_index,
            "question_id": current,
            "answer_type": question["answer_type"],
            "documented_value": (
                answer_value
                if isinstance(answer_value, str)
                else json.dumps(answer_value, ensure_ascii=False, separators=(",", ":"))
            ),
            "evidence_ref": evidence_ref,
            "matched_branch_index": branch_index,
            "matched_operator": str(matched_branch["operator"]),
            "next_node": next_node,
        })
        current = next_node
    else:
        result["assessment_status"] = "PROTOCOL_INVALID"
        result["input_conflicts"].append("path_step_limit_exceeded")

    if reached_endpoint is not None and not result["input_conflicts"]:
        candidate_level = str(reached_endpoint["candidate_level"])
        disposition, actions = _safe_disposition(candidate_level)
        red_flag_codes = list(reached_endpoint.get("red_flag_codes") or [])
        result["assessment_status"] = "READY_FOR_ONSITE_REVIEW"
        result["acuity_level"] = f"DEVELOPMENT_PROTOCOL_CANDIDATE_{candidate_level}"
        result["red_flags"] = red_flag_codes
        result["supporting_evidence"] = (
            f"已沿调用方声明问卷执行 {len(result['decision_path'])} 个明确回答；"
            "未从自由文本提取或推断。"
        )
        result["recommended_disposition"] = disposition
        result["immediate_actions"] = actions
        result["uncertainty"] = (
            "候选完全依赖调用方声明的问卷规则、版本和回答；平台未验证临床有效性，"
            "最终级别必须由现场分诊专业人员确认。"
        )
        result["protocol_candidate"] = {
            "reached": True,
            "endpoint_id": str(reached_endpoint["id"]),
            "candidate_level": candidate_level,
            "disposition": disposition,
            "red_flag_codes": red_flag_codes,
            "result_status": "DEVELOPMENT_UNVERIFIED_PROTOCOL_CANDIDATE",
        }

    _finish_trace(result)
    return result


def _finish_trace(result: dict[str, Any]) -> None:
    evidence = result.get("evidence_items") or []
    result["_trace"]["evidence_items_count"] = len(evidence)
    result["_trace"]["valid_spans_count"] = sum(
        1 for item in evidence if item.get("evidence_status") == "EXACT_INPUT_SPAN"
    )
    result["_trace"]["path_steps"] = len(result.get("decision_path") or [])


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {field: result[field] for field in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "OUTPUT_CONTRACT_REF",
    "LOCAL_RUNTIME_MODE",
    "REVIEW_METHOD",
    "build_triage_questionnaire_review",
    "to_pack_output",
    "verify_triage_questionnaire_health",
]
