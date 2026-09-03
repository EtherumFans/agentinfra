"""Deterministic Note Completeness rules for Chinese medical records.

Phase 4-B (2026-07-08): replaced by ``agent.py`` (LLM-based via
``PureLLMProvider``). Kept for A/B fallback and regression
comparison. The new ``agent.run()`` calls this legacy implementation
when the LLM returns ``status="fail"`` — so a working path always
exists even if the LLM is unavailable.

To use directly (e.g., for A/B comparison):
    from official_agents.note_completeness.agent_legacy import run
    result = await run(emr_text, run_id="...")

Input: EMR text (Chinese hospital note).

Output (NoteCompletenessOutputSchema):
  {
    "review_conclusion": "PASS" | "WARNING" | "FAIL",
    "documentation_gaps": [
      {"gap_type": "missing_section", "description": "...", "section": "主诉",
       "suggestion": "..."}
    ],
    "completeness_score": float (0.0 - 1.0),
    "missing_sections": ["主诉", ...],
    "present_sections": ["现病史", ...],
    "required_sections": ["主诉", ...],
    "trace_refs": {"run_id", "agent_ref"}
  }

Deterministic: section-boundary and non-empty-content detection. No LLM.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

# Required sections per 《病历书写基本规范》 for an admission note
# (入院记录). Surgical sections are conditional on the case being
# surgical — detected via procedure keywords.
REQUIRED_SECTIONS: list[dict[str, Any]] = [
    {"key": "主诉", "labels": ["主诉"]},
    {"key": "现病史", "labels": ["现病史"]},
    {"key": "既往史", "labels": ["既往史"]},
    {"key": "体格检查", "labels": ["体格检查", "查体"]},
    {"key": "辅助检查", "labels": ["辅助检查", "实验室检查"]},
    {"key": "诊断", "labels": ["入院诊断", "出院诊断", "初步诊断", "诊断"]},
    {"key": "治疗经过", "labels": ["治疗经过", "诊疗经过", "处理"]},
]

# Surgical-section keywords — if the note mentions surgery, we also
# require 手术记录 / 术前讨论 / 术后记录.
SURGICAL_KEYWORDS = [
    "手术记录", "手术经过", "术中", "术后", "切除术", "吻合术", "修补术",
    "置换术", "剖宫产", "刮宫术", "介入治疗", "行手术", "拟行手术",
]
SURGICAL_NEGATIONS = re.compile(
    r"(?:无|否认|未行|无需|不考虑|未计划)(?:任何)?手术(?:史|治疗|指征|计划)?"
)
SURGICAL_SECTIONS: list[dict[str, Any]] = [
    {"key": "手术记录", "labels": ["手术记录", "手术经过"]},
]


_LABEL_TO_SECTION = {
    label: str(section["key"])
    for section in [*REQUIRED_SECTIONS, *SURGICAL_SECTIONS]
    for label in section["labels"]
}
_LABEL_ALTERNATION = "|".join(
    re.escape(label)
    for label in sorted(_LABEL_TO_SECTION, key=len, reverse=True)
)
_SECTION_HEADER_RE = re.compile(
    rf"(?:^|[\r\n。；;])\s*(?P<label>{_LABEL_ALTERNATION})\s*"
    rf"(?:[:：]|(?=\r?$))",
    re.MULTILINE,
)
_SPINAL_LEVEL_RE = re.compile(r"(?<![A-Z0-9])([CTLS])\s*(1[0-2]|[1-9])(?![A-Z0-9])", re.IGNORECASE)


def _is_surgical_case(text: str) -> bool:
    unnegated = SURGICAL_NEGATIONS.sub("", text)
    return any(keyword in unnegated for keyword in SURGICAL_KEYWORDS)


def _section_bodies(text: str) -> dict[str, str]:
    """Extract canonical section names and their bounded body text."""
    matches = list(_SECTION_HEADER_RE.finditer(text))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        section = _LABEL_TO_SECTION[match.group("label")]
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip(" \t\r\n:：。；;")
        if section not in bodies or len(body) > len(bodies[section]):
            bodies[section] = body
    return bodies


def _has_meaningful_content(body: str) -> bool:
    """A heading alone is incomplete; a documented negation such as 无 is valid."""
    return bool(re.search(r"[\w\u3400-\u9fff]", body, re.UNICODE))


def _detect_sections(
    text: str,
    sections: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Return complete, absent and present-but-empty required sections."""
    bodies = _section_bodies(text)
    present: list[str] = []
    missing: list[str] = []
    incomplete: list[dict[str, str]] = []
    for section in sections:
        key = str(section["key"])
        if key not in bodies:
            missing.append(key)
        elif _has_meaningful_content(bodies[key]):
            present.append(key)
        else:
            incomplete.append({
                "section": key,
                "deficit_note": f"{key}章节存在标题但未记录有效内容",
            })
    return present, missing, incomplete


def _spinal_levels(value: str) -> set[str]:
    return {
        f"{region.upper()}{number}"
        for region, number in _SPINAL_LEVEL_RE.findall(str(value or ""))
    }


def _semantic_findings(
    text: str,
    *,
    is_surgical: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return bounded deterministic completeness and consistency findings.

    These rules deliberately cover only document structure and explicit spinal
    level literals. They do not infer diagnoses, procedure appropriateness, or
    broader clinical consistency.
    """
    bodies = _section_bodies(text)
    incomplete: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []

    diagnosis_body = bodies.get("诊断", "")
    if is_surgical and diagnosis_body and not (
        re.search(r"(?:^|[\r\n。；;])\s*入院诊断\s*[:：]", text)
        and re.search(r"(?:^|[\r\n。；;])\s*出院诊断\s*[:：]", text)
    ):
        incomplete.append({
            "section": "诊断",
            "deficit_note": "诊断章节未明确区分入院诊断与出院诊断。",
        })

    treatment_body = bodies.get("治疗经过", "")
    operative_body = bodies.get("手术记录", "")
    if is_surgical and treatment_body and not (
        ("术前" in treatment_body or "术前" in operative_body)
        and ("术中" in treatment_body or "术中" in operative_body)
    ):
        incomplete.append({
            "section": "治疗经过",
            "deficit_note": "手术病例的治疗经过缺少明确的术前准备或术中情况。",
        })

    diagnosis_levels = _spinal_levels(diagnosis_body)
    treatment_levels = _spinal_levels(f"{treatment_body}\n{operative_body}")
    if diagnosis_levels and treatment_levels and diagnosis_levels != treatment_levels:
        diagnosis_text = "、".join(sorted(diagnosis_levels))
        treatment_text = "、".join(sorted(treatment_levels))
        conflicts.append({
            "section": "诊断与治疗经过",
            "note": (
                f"诊断记录的脊柱节段为 {diagnosis_text}，治疗/手术记录为 "
                f"{treatment_text}；存在显式节段冲突，需人工核对。"
            ),
        })
    return incomplete, conflicts


def _conclusion(
    score: float,
    *,
    has_findings: bool,
) -> str:
    """Fail below 0.5; any explicit gap/conflict prevents a PASS."""
    if score >= 0.85 and not has_findings:
        return "PASS"
    if score >= 0.5:
        return "WARNING"
    return "FAIL"


async def run(input_text: str, *, run_id: str = "") -> dict:
    """Run the Note Completeness Agent.

    Args:
        input_text: EMR text (Chinese hospital note).
        run_id: Optional run_id for trace correlation.

    Returns:
        NoteCompletenessOutputSchema dict.
    """
    text = input_text or ""
    required = list(REQUIRED_SECTIONS)
    if _is_surgical_case(text):
        required.extend(SURGICAL_SECTIONS)

    present, missing, empty_sections = _detect_sections(text, required)
    semantic_incomplete, conflicts = _semantic_findings(
        text,
        is_surgical=_is_surgical_case(text),
    )
    incomplete = [*empty_sections, *semantic_incomplete]
    total = len(required)
    score = (len(present) / total) if total else 1.0

    gaps = [
        {
            "gap_type": "missing_section",
            "description": f"病历缺少必填章节: {section}",
            "section": section,
        }
        for section in missing
    ]
    gaps.extend({
        "gap_type": "incomplete_section",
        "description": item["deficit_note"],
        "section": item["section"],
    } for item in incomplete)
    gaps.extend({
        "gap_type": "conflict",
        "description": item["note"],
        "section": item["section"],
    } for item in conflicts)

    conclusion = _conclusion(
        score,
        has_findings=bool(missing or incomplete or conflicts),
    )
    manual_review = bool(missing or incomplete or conflicts)

    return {
        "review_conclusion": conclusion,
        "documentation_gaps": gaps,
        "completeness_score": round(score, 4),
        "missing_sections": missing,
        "present_sections": present,
        "required_sections": [s["key"] for s in required],
        "incomplete_sections": incomplete,
        "conflicts": conflicts,
        "corrected_draft": "",
        "manual_review_required": manual_review,
        "is_surgical_case": _is_surgical_case(text),
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/note-completeness-agent@1.0.0",
            "rule_set": "documentation_completeness",
        },
    }


__all__ = ["run"]
