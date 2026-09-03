"""Governed, evidence-bound review of a documented principal-diagnosis draft.

This module deliberately does not select, assign, replace, or clinically rank a
principal diagnosis.  It turns explicitly labelled coder input into an
auditable review packet and checks only deterministic set/evidence invariants.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any
from uuid import uuid4


AGENT_REF = "icoder/principal-diagnosis-review@1.1.0"
OUTPUT_CONTRACT_REF = "icoder/PrincipalDxReview/v11"
LOCAL_RUNTIME_MODE = "governed_local_documented_principal_draft_review"
MAX_INPUT_CHARS = 60_000
MAX_ITEMS = 100

REVIEW_METHOD = "DOCUMENTED_DRAFT_EVIDENCE_AND_SET_CONSISTENCY_ONLY"
DRAFT_AUTHORITY_STATUS = "CODER_DOCUMENTED_DRAFT_NOT_CLINICALLY_VALIDATED"

_SCALAR_LABELS = {
    "审核目的": "review_purpose",
    "review purpose": "review_purpose",
    "编码标准": "coding_system",
    "coding system": "coding_system",
    "编码版本": "coding_version",
    "coding version": "coding_version",
    "病案文档范围": "documentation_scope",
    "documentation scope": "documentation_scope",
    "编码员主诊断初稿": "documented_draft",
    "documented principal draft": "documented_draft",
}
_SECTION_LABELS = {
    "主诊断候选": "candidates",
    "principal diagnosis candidates": "candidates",
    "选择依据": "selection_basis",
    "documented selection basis": "selection_basis",
}
_BASIS_TYPES = {
    "ADMISSION_REASON",
    "MAIN_TREATMENT",
    "RESOURCE_USE",
    "HOSPITAL_APPROVED_OTHER",
}
_UNTRUSTED_PATTERN = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?(?:system|developer)\s+prompt|"
    r"system\s+prompt|developer\s+message|"
    r"忽略.{0,12}(?:指令|提示)|(?:系统|开发者)提示词)",
    re.IGNORECASE,
)
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,31}$")


@dataclass(frozen=True)
class Line:
    text: str
    start: int
    end: int


def verify_principal_diagnosis_review_health() -> dict[str, Any]:
    return {
        "agent_ref": AGENT_REF,
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "output_contract": OUTPUT_CONTRACT_REF,
        "review_method": REVIEW_METHOD,
        "network_required": False,
        "llm_required": False,
        "deterministic": True,
    }


def _bounded_text(value: Any) -> tuple[str, bool]:
    text = str(value or "").replace("\x00", "").strip()
    truncated = len(text) > MAX_INPUT_CHARS
    return text[:MAX_INPUT_CHARS], truncated


def _lines(source: str) -> list[Line]:
    rows: list[Line] = []
    for match in re.finditer(r"[^\r\n]+", source):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        offset = len(raw) - len(raw.lstrip())
        start = match.start() + offset
        rows.append(Line(stripped, start, start + len(stripped)))
    return rows


def _split_label(text: str) -> tuple[str, str] | None:
    match = re.match(r"^([^:：]{1,80})[:：]\s*(.*)$", text)
    if not match:
        return None
    return match.group(1).strip().lower(), match.group(2).strip()


def _value_span(line: Line, value: str) -> list[int]:
    if not value:
        return [line.end, line.end]
    relative = line.text.rfind(value)
    if relative < 0:
        return [line.start, line.end]
    return [line.start + relative, line.start + relative + len(value)]


def _evidence_item(
    evidence_id: str,
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


def _fact(value: str = "", evidence_ref: str = "") -> dict[str, str]:
    return {"documented_text": value, "evidence_ref": evidence_ref}


def _blank_result(run_id: str) -> dict[str, Any]:
    return {
        "review_status": "INPUT_REQUIRED",
        "review_purpose": _fact(),
        "coding_standard": {
            "system": _fact(),
            "version": _fact(),
        },
        "documentation_scope": _fact(),
        "documented_coding_draft": {
            "candidate_id": "",
            "code": "",
            "display": "",
            "evidence_ref": "",
            "authority_status": DRAFT_AUTHORITY_STATUS,
        },
        "candidates": [],
        "declared_selection_basis": [],
        "candidate_evidence_gaps": [],
        "input_conflicts": [],
        "draft_in_candidate_set": False,
        "draft_evidence_complete": False,
        "draft_consistency_status": "NOT_ASSESSABLE",
        "selection_basis_status": "NOT_PROVIDED",
        "review_method": REVIEW_METHOD,
        "evidence_items": [],
        "missing_required_fields": [],
        "limitations": [
            "仅核对编码员明确提供的主诊断初稿、候选集合、选择依据和原文证据。",
            "不从自由文本提取或新增诊断，不分配、推荐、替换或排序主诊断编码。",
            "不判断诊断成立、临床严重程度、病因关系、主要治疗、资源消耗或主诊断选择正确性。",
            "不验证编码目录、国家/医保/病案首页规则版本、医院政策授权或结算有效性。",
            "READY_FOR_CODER_REVIEW 只表示输入集合与证据完整，不表示主诊断正确或可提交。",
            "结果只供编码员人工复核，不自动提交、处罚、修改病历或写回系统。",
        ],
        "diagnosis_extraction_performed": False,
        "code_assignment_performed": False,
        "principal_diagnosis_selection_performed": False,
        "clinical_inference_performed": False,
        "external_rules_used": False,
        "production_submission_blocked": True,
        "production_writeback_blocked": True,
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id,
            "provider_trace_refs": [f"{run_id}:governed-principal-diagnosis-review"],
        },
        "_trace": {
            "input_truncated": False,
            "prompt_canary_detected": False,
            "evidence_items_count": 0,
            "valid_spans_count": 0,
            "candidate_count": 0,
            "selection_basis_count": 0,
        },
    }


def _parse_documented_draft(value: str) -> dict[str, str] | None:
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 3 or not all(parts):
        return None
    candidate_id, code, display = parts
    if not _CODE_PATTERN.fullmatch(code):
        return None
    return {"candidate_id": candidate_id, "code": code.upper(), "display": display}


def _parse_candidate(line: Line) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.text.split("|", 4)]
    if len(parts) != 5 or not all(parts):
        return None
    candidate_id, code, display, source_document, evidence_text = parts
    if not _CODE_PATTERN.fullmatch(code):
        return None
    return {
        "candidate_id": candidate_id,
        "code": code.upper(),
        "display": display,
        "source_document": source_document,
        "evidence_text": evidence_text,
        "char_span": _value_span(line, evidence_text),
    }


def _parse_basis(line: Line) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.text.split("|", 3)]
    if len(parts) != 4 or not all(parts):
        return None
    candidate_id, basis_type, source_document, evidence_text = parts
    basis_type = basis_type.upper()
    if basis_type not in _BASIS_TYPES:
        return None
    return {
        "candidate_id": candidate_id,
        "basis_type": basis_type,
        "source_document": source_document,
        "evidence_text": evidence_text,
        "char_span": _value_span(line, evidence_text),
    }


def build_principal_diagnosis_review(
    text: Any,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or f"run-{uuid4()}"
    result = _blank_result(run_id)
    source, truncated = _bounded_text(text)
    result["_trace"]["input_truncated"] = truncated
    if not source:
        result["missing_required_fields"] = ["input_text"]
        return result
    if _UNTRUSTED_PATTERN.search(source):
        result["missing_required_fields"] = ["safe_labelled_input"]
        result["_trace"]["prompt_canary_detected"] = True
        return result

    scalar_values: dict[str, tuple[str, Line, str]] = {}
    candidates: list[dict[str, Any]] = []
    bases: list[dict[str, Any]] = []
    invalid_candidate_lines: list[str] = []
    invalid_basis_lines: list[str] = []
    current_section = ""

    for line in _lines(source):
        labelled = _split_label(line.text)
        if labelled:
            label, value = labelled
            if label in _SCALAR_LABELS:
                field = _SCALAR_LABELS[label]
                scalar_values[field] = (value, line, label)
                current_section = ""
                continue
            if label in _SECTION_LABELS:
                current_section = _SECTION_LABELS[label]
                if value:
                    synthetic = Line(value, _value_span(line, value)[0], _value_span(line, value)[1])
                    parsed = (
                        _parse_candidate(synthetic)
                        if current_section == "candidates"
                        else _parse_basis(synthetic)
                    )
                    if parsed:
                        (candidates if current_section == "candidates" else bases).append(parsed)
                    elif current_section == "candidates":
                        invalid_candidate_lines.append(value)
                    else:
                        invalid_basis_lines.append(value)
                continue
        if current_section == "candidates":
            parsed = _parse_candidate(line)
            if parsed:
                candidates.append(parsed)
            else:
                invalid_candidate_lines.append(line.text)
        elif current_section == "selection_basis":
            parsed = _parse_basis(line)
            if parsed:
                bases.append(parsed)
            else:
                invalid_basis_lines.append(line.text)

    evidence_items: list[dict[str, Any]] = []

    def add_evidence(field: str, label: str, value: str, span: list[int]) -> str:
        evidence_id = f"principal-dx-evidence-{len(evidence_items) + 1}"
        evidence_items.append(_evidence_item(evidence_id, field, label, value, span))
        return evidence_id

    for key, target in (
        ("review_purpose", ("review_purpose",)),
        ("coding_system", ("coding_standard", "system")),
        ("coding_version", ("coding_standard", "version")),
        ("documentation_scope", ("documentation_scope",)),
    ):
        value, line, label = scalar_values.get(key, ("", Line("", 0, 0), key))
        evidence_ref = add_evidence(key, label, value, _value_span(line, value)) if value else ""
        fact = _fact(value, evidence_ref)
        if len(target) == 1:
            result[target[0]] = fact
        else:
            result[target[0]][target[1]] = fact

    draft_value, draft_line, draft_label = scalar_values.get(
        "documented_draft", ("", Line("", 0, 0), "documented_draft")
    )
    draft = _parse_documented_draft(draft_value) if draft_value else None
    if draft:
        draft_ref = add_evidence(
            "documented_draft", draft_label, draft_value, _value_span(draft_line, draft_value)
        )
        result["documented_coding_draft"].update(draft)
        result["documented_coding_draft"]["evidence_ref"] = draft_ref

    candidate_ids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_codes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in candidates[:MAX_ITEMS]:
        ref = add_evidence(
            "candidate_evidence",
            "主诊断候选",
            raw["evidence_text"],
            raw["char_span"],
        )
        item = {
            **raw,
            "evidence_ref": ref,
            "evidence_status": "EXACT_INPUT_SPAN",
            "is_documented_draft": bool(
                draft
                and raw["candidate_id"] == draft["candidate_id"]
                and raw["code"] == draft["code"]
                and raw["display"] == draft["display"]
            ),
        }
        result["candidates"].append(item)
        candidate_ids[item["candidate_id"]].append(item)
        candidate_codes[item["code"]].append(item)

    for raw in bases[:MAX_ITEMS]:
        ref = add_evidence(
            "selection_basis",
            "选择依据",
            raw["evidence_text"],
            raw["char_span"],
        )
        result["declared_selection_basis"].append({**raw, "evidence_ref": ref})

    conflicts: list[dict[str, Any]] = []
    for field, grouped in (("candidate_id", candidate_ids), ("code", candidate_codes)):
        for value, items in grouped.items():
            signatures = {
                (item["candidate_id"], item["code"], item["display"], item["evidence_text"])
                for item in items
            }
            if len(items) > 1:
                conflicts.append({
                    "field": field,
                    "documented_value": value,
                    "reason": (
                        "同一候选标识对应冲突的显式内容。"
                        if len(signatures) > 1
                        else "同一候选标识被重复提供。"
                    ),
                    "evidence_refs": [item["evidence_ref"] for item in items],
                })
    known_ids = set(candidate_ids)
    unknown_basis_ids = sorted({item["candidate_id"] for item in result["declared_selection_basis"] if item["candidate_id"] not in known_ids})
    for candidate_id in unknown_basis_ids:
        conflicts.append({
            "field": "selection_basis.candidate_id",
            "documented_value": candidate_id,
            "reason": "选择依据引用了候选集合中不存在的 candidate_id。",
            "evidence_refs": [
                item["evidence_ref"]
                for item in result["declared_selection_basis"]
                if item["candidate_id"] == candidate_id
            ],
        })
    result["input_conflicts"] = conflicts

    missing: list[str] = []
    for key in ("review_purpose", "coding_system", "coding_version", "documentation_scope"):
        if not scalar_values.get(key, ("", None, None))[0]:
            missing.append(key)
    if not draft:
        missing.append("documented_draft")
    if not result["candidates"]:
        missing.append("candidates")
    if invalid_candidate_lines:
        missing.append("valid_candidate_lines")
    if invalid_basis_lines:
        missing.append("valid_selection_basis_lines")
    if len(candidates) > MAX_ITEMS:
        missing.append("candidate_limit_exceeded")
    if len(bases) > MAX_ITEMS:
        missing.append("selection_basis_limit_exceeded")
    if truncated:
        missing.append("complete_untruncated_input")
    result["missing_required_fields"] = sorted(set(missing))

    draft_matches = [item for item in result["candidates"] if item["is_documented_draft"]]
    result["draft_in_candidate_set"] = len(draft_matches) == 1
    result["draft_evidence_complete"] = bool(
        result["draft_in_candidate_set"]
        and draft_matches[0]["evidence_text"]
        and draft_matches[0]["evidence_ref"]
    )
    result["candidate_evidence_gaps"] = [
        item["candidate_id"]
        for item in result["candidates"]
        if not item["evidence_text"] or not item["evidence_ref"]
    ]

    draft_id = draft["candidate_id"] if draft else ""
    draft_bases = [
        item for item in result["declared_selection_basis"]
        if item["candidate_id"] == draft_id
    ]
    basis_signatures: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item in draft_bases:
        basis_signatures[item["basis_type"]].add(
            (item["source_document"], item["evidence_text"])
        )
    basis_conflicting = any(len(values) > 1 for values in basis_signatures.values())
    if basis_conflicting or unknown_basis_ids:
        result["selection_basis_status"] = "CONFLICTING"
    elif draft_bases:
        result["selection_basis_status"] = "DOCUMENTED"
    else:
        result["selection_basis_status"] = "NOT_PROVIDED"

    if result["missing_required_fields"]:
        result["review_status"] = "INPUT_REQUIRED"
        result["draft_consistency_status"] = "NOT_ASSESSABLE"
    elif conflicts:
        result["review_status"] = "EVIDENCE_REVIEW_REQUIRED"
        result["draft_consistency_status"] = "DECLARED_INPUT_CONFLICT"
    elif not result["draft_in_candidate_set"]:
        result["review_status"] = "EVIDENCE_REVIEW_REQUIRED"
        result["draft_consistency_status"] = "DRAFT_NOT_IN_CANDIDATE_SET"
    elif result["candidate_evidence_gaps"] or result["selection_basis_status"] != "DOCUMENTED":
        result["review_status"] = "EVIDENCE_REVIEW_REQUIRED"
        result["draft_consistency_status"] = "DOCUMENTED_DRAFT_EVIDENCE_INCOMPLETE"
    else:
        result["review_status"] = "READY_FOR_CODER_REVIEW"
        result["draft_consistency_status"] = "DOCUMENTED_DRAFT_AND_EVIDENCE_PRESENT"

    valid_spans = sum(
        1
        for item in evidence_items
        if source[item["char_span"][0]:item["char_span"][1]] == item["text"]
    )
    result["evidence_items"] = evidence_items
    result["_trace"].update({
        "evidence_items_count": len(evidence_items),
        "valid_spans_count": valid_spans,
        "candidate_count": len(result["candidates"]),
        "selection_basis_count": len(result["declared_selection_basis"]),
    })
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    public = deepcopy(result)
    public.pop("_trace", None)
    return public


__all__ = [
    "AGENT_REF",
    "DRAFT_AUTHORITY_STATUS",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "REVIEW_METHOD",
    "build_principal_diagnosis_review",
    "to_pack_output",
    "verify_principal_diagnosis_review_health",
]
