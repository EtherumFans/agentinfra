"""Legacy regex-based Note Completeness Agent.

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

Deterministic: regex-based section detection. No LLM.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

# Required sections per 《病历书写基本规范》 for an admission note
# (入院记录). Surgical sections are conditional on the case being
# surgical — detected via procedure keywords.
REQUIRED_SECTIONS: list[dict] = [
    {"key": "主诉", "patterns": [r"主诉[:：]", r"^\s*主诉\b"]},
    {"key": "现病史", "patterns": [r"现病史[:：]", r"^\s*现病史\b"]},
    {"key": "既往史", "patterns": [r"既往史[:：]", r"^\s*既往史\b"]},
    {"key": "体格检查", "patterns": [r"体格检查[:：]", r"^\s*体格检查\b", r"查体[:：]"]},
    {"key": "辅助检查", "patterns": [r"辅助检查[:：]", r"^\s*辅助检查\b", r"实验室检查[:：]"]},
    {"key": "诊断", "patterns": [r"诊断[:：]", r"^\s*初步诊断\b", r"^\s*出院诊断\b", r"^\s*入院诊断\b"]},
    {"key": "治疗经过", "patterns": [r"治疗经过[:：]", r"^\s*治疗经过\b", r"诊疗经过[:：]", r"处理[:：]"]},
]

# Surgical-section keywords — if the note mentions surgery, we also
# require 手术记录 / 术前讨论 / 术后记录.
SURGICAL_KEYWORDS = ["手术", "切除术", "吻合术", "修补术", "置换术", "剖宫产", "刮宫", "介入"]
SURGICAL_SECTIONS: list[dict] = [
    {"key": "手术记录", "patterns": [r"手术记录[:：]", r"^\s*手术记录\b", r"手术经过[:：]"]},
]


def _is_surgical_case(text: str) -> bool:
    return any(kw in text for kw in SURGICAL_KEYWORDS)


def _detect_section(text: str, section: dict) -> bool:
    """Return True if any pattern matches."""
    for p in section["patterns"]:
        if re.search(p, text, re.MULTILINE):
            return True
    return False


def _detect_sections(text: str, sections: list[dict]) -> tuple[list[str], list[str]]:
    """Return (present, missing) section keys."""
    present: list[str] = []
    missing: list[str] = []
    for section in sections:
        if _detect_section(text, section):
            present.append(section["key"])
        else:
            missing.append(section["key"])
    return present, missing


def _conclusion(score: float, missing: list[str]) -> str:
    """PASS >= 0.85, WARNING 0.5..0.85, FAIL < 0.5."""
    if score >= 0.85:
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

    present, missing = _detect_sections(text, required)
    total = len(required)
    score = (len(present) / total) if total else 1.0

    gaps = [
        {
            "gap_type": "missing_section",
            "description": f"病历缺少必填章节: {section}",
            "section": section,
            "suggestion": f"请补充 {section} 章节 — 《病历书写基本规范》要求",
            "related_code": "",
        }
        for section in missing
    ]

    conclusion = _conclusion(score, missing)
    manual_review = bool(missing) and conclusion != "PASS"

    return {
        "review_conclusion": conclusion,
        "documentation_gaps": gaps,
        "completeness_score": round(score, 4),
        "missing_sections": missing,
        "present_sections": present,
        "required_sections": [s["key"] for s in required],
        "manual_review_required": manual_review,
        "is_surgical_case": _is_surgical_case(text),
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/note-completeness-agent@1.0.0",
            "rule_set": "documentation_completeness",
        },
    }


__all__ = ["run"]
