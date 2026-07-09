"""Note Completeness Agent — LLM-based implementation (Phase 4-B).

Migrates from regex (legacy, see ``agent_legacy.py``) to ``PureLLMProvider``.
The LLM is asked to:
  1. Read the EMR text
  2. Detect 7+1 required sections per《病历书写基本规范》
  3. Output JSON matching ``NoteCompletenessOutputSchema``

The system prompt (``SYSTEM_PROMPT`` below) is written in Chinese for
the Chinese hospital context. It's based on the Corti 6-section
Markdown structure (Summary / Status / Findings / Recommendations /
Risks / Next Steps) but adapted for《病历书写基本规范》7+1 sections
(主诉/现病史/既往史/体格检查/辅助检查/诊断/治疗经过 + 手术记录
for surgical cases).

Legacy fallback: if the LLM returns ``status="fail"`` (e.g., timeout,
degraded mode, parse error), ``agent.run()`` falls back to the regex
implementation in ``agent_legacy.py`` so a working path always exists.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


AGENT_REF = "icoder/note-completeness-agent@1.0.0"


SYSTEM_PROMPT = """你是 iCoDer 病历完整性智能体 (Note Completeness Agent)。

# 角色与职责

你接收中国医院入院记录 / 出院小结 / 病程记录文本，按《病历书写基本规范》
(2010 年版卫生部修订) 检测必填章节是否齐全，输出结构化 JSON 结果。

# 必填章节 (7 + 1)

非手术病例必填 7 个章节：
1. 主诉 (Chief Complaint) — 常见标记: "主诉:" / "主诉："
2. 现病史 (HPI) — 常见标记: "现病史:" / "现病史："
3. 既往史 (PMH) — 常见标记: "既往史:" / "既往史："
4. 体格检查 (Physical Exam) — 常见标记: "体格检查:" / "查体:"
5. 辅助检查 (Auxiliary Exam) — 常见标记: "辅助检查:" / "实验室检查:"
6. 诊断 (Diagnosis) — 常见标记: "初步诊断:" / "入院诊断:" / "出院诊断:"
7. 治疗经过 (Treatment Course) — 常见标记: "治疗经过:" / "诊疗经过:" / "处理:"

手术病例 (文本含"手术"/"切除术"/"吻合术"/"修补术"/"置换术"/"剖宫产"/
"刮宫"/"介入"等关键词) 必填第 8 个章节：
8. 手术记录 (Surgical Record) — 常见标记: "手术记录:" / "手术经过:"

# 评分规则

completeness_score = present_sections 数量 / required_sections 数量
review_conclusion:
  - PASS: completeness_score >= 0.85
  - WARNING: 0.5 <= completeness_score < 0.85
  - FAIL: completeness_score < 0.5

# 输出格式 (严格 JSON,不要任何额外文字 / Markdown 标记)

输出必须是单个 JSON 对象,字段如下:

{
  "review_conclusion": "PASS" | "WARNING" | "FAIL",
  "completeness_score": <float 0..1, 4 位小数>,
  "missing_sections": [<缺失章节名列表>],
  "present_sections": [<已检测到章节名列表>],
  "required_sections": [<应检测的章节名列表,含手术记录如果适用>],
  "is_surgical_case": <true | false>,
  "manual_review_required": <true 当 missing_sections 非空且 conclusion != PASS>,
  "documentation_gaps": [
    {
      "gap_type": "missing_section",
      "description": "<对该缺失章节的简短描述>",
      "section": "<章节名>",
      "suggestion": "<补充建议,如:请补充 主诉 章节 — 《病历书写基本规范》要求>",
      "related_code": ""
    }
  ]
}

# 硬约束

- 不调用任何工具 — 你只读取文本并输出 JSON
- 不修改病历 — 只评估完整性
- 不分配 ICD 编码 — 编码由 Medical Coding Agent 完成
- 不输出任何额外文字、解释、Markdown 标记 — 只输出 JSON
- 不在输出中包含患者姓名 / 身份证号 / 联系方式等 PHI — 只输出章节级评估
- 章节名使用中文 (主诉 / 现病史 / 既往史 / 体格检查 / 辅助检查 / 诊断 / 治疗经过 / 手术记录)

# 示例

输入 (非手术病例,缺主诉):
"现病史：患者3年前出现心悸...\\n既往史：高血压10年\\n体格检查：心率90...\\n辅助检查：ECG正常\\n诊断：心律失常\\n治疗经过：药物控制"

输出:
{
  "review_conclusion": "WARNING",
  "completeness_score": 0.8571,
  "missing_sections": ["主诉"],
  "present_sections": ["现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
  "required_sections": ["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
  "is_surgical_case": false,
  "manual_review_required": true,
  "documentation_gaps": [
    {
      "gap_type": "missing_section",
      "description": "病历缺少必填章节: 主诉",
      "section": "主诉",
      "suggestion": "请补充 主诉 章节 — 《病历书写基本规范》要求",
      "related_code": ""
    }
  ]
}
"""


# ── run() — main entry point ───────────────────────────────────────


async def run(input_text: str, *, run_id: str = "") -> dict:
    """Run the Note Completeness Agent (LLM-based, Phase 4-B).

    Args:
        input_text: EMR text (Chinese hospital note).
        run_id: Optional run_id for trace correlation.

    Returns:
        NoteCompletenessOutputSchema dict. If the LLM fails or returns
        unparseable output, falls back to the legacy regex
        implementation (``agent_legacy.run``) so the caller always
        gets a valid schema dict.
    """
    text = input_text or ""
    if not text.strip():
        return _empty_input_response(run_id)

    try:
        llm_response = await _invoke_llm(text, run_id)
    except Exception as e:
        logger.warning(
            "note_completeness LLM invoke raised; falling back to legacy: %s", e,
        )
        return await _legacy_run(text, run_id)

    if llm_response is None or llm_response.get("status") == "fail":
        logger.info(
            "note_completeness LLM returned fail; falling back to legacy. "
            "finish_reason=%s",
            llm_response.get("finish_reason") if llm_response else "none",
        )
        return await _legacy_run(text, run_id)

    schema = _parse_llm_json_to_schema(
        llm_response.get("markdown", ""),
        text,
        run_id,
        is_surgical_hint=_detect_surgical(text),
    )
    if schema is None:
        logger.warning(
            "note_completeness LLM output not parseable; falling back to legacy."
        )
        return await _legacy_run(text, run_id)

    return schema


# ── Internal: LLM invoke ───────────────────────────────────────────


async def _invoke_llm(text: str, run_id: str) -> dict[str, Any] | None:
    """Invoke PureLLMProvider via the registry. Returns the BackendResponse dict."""
    from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
    from icoder_runtime.backends.registry import get_default_registry

    registry = get_default_registry()
    provider = registry.resolve_from_agent_pack(
        {"backend_provider": "icoder.pure-llm.v1"},
    )

    req = BackendRequest(
        system_prompt=SYSTEM_PROMPT,
        user_input=text,
        timeout_seconds=60.0,
    )
    ctx = AgentRunContext(
        run_id=run_id or str(uuid.uuid4()),
        context_id=str(uuid.uuid4()),
        agent_id="note-completeness-agent",
        redacted_input=text,
        agent_pack={"backend_provider": "icoder.pure-llm.v1"},
    )
    resp = await provider.invoke(req, ctx)
    return {
        "status": resp.status,
        "markdown": resp.markdown or "",
        "finish_reason": resp.finish_reason or "",
        "latency_ms": resp.latency_ms,
        "raw": resp.raw_provider_response,
    }


def _parse_llm_json_to_schema(
    markdown: str,
    input_text: str,
    run_id: str,
    *,
    is_surgical_hint: bool,
) -> dict[str, Any] | None:
    """Extract JSON from LLM markdown, validate, build schema dict.

    Returns None if the LLM output can't be parsed as JSON or is missing
    required fields. The caller falls back to legacy regex in that case.
    """
    if not markdown:
        return None

    parsed = _extract_json(markdown)
    if parsed is None:
        return None

    # Required fields per NoteCompletenessOutputSchema
    required_fields = (
        "review_conclusion", "completeness_score",
        "missing_sections", "present_sections", "required_sections",
    )
    for field in required_fields:
        if field not in parsed:
            return None

    # Normalize review_conclusion to uppercase PASS/WARNING/FAIL
    conclusion = str(parsed.get("review_conclusion", "")).upper().strip()
    if conclusion not in ("PASS", "WARNING", "FAIL"):
        return None

    missing = list(parsed.get("missing_sections") or [])
    present = list(parsed.get("present_sections") or [])
    required = list(parsed.get("required_sections") or [])
    score = float(parsed.get("completeness_score") or 0.0)

    # Re-derive conclusion from score if LLM's conclusion is inconsistent
    # (defensive — LLM may say PASS but score < 0.5)
    if score >= 0.85:
        derived_conclusion = "PASS"
    elif score >= 0.5:
        derived_conclusion = "WARNING"
    else:
        derived_conclusion = "FAIL"
    if derived_conclusion != conclusion:
        logger.info(
            "note_completeness: LLM conclusion=%s but score=%.4f → %s",
            conclusion, score, derived_conclusion,
        )
        conclusion = derived_conclusion

    gaps = parsed.get("documentation_gaps") or []
    if not isinstance(gaps, list):
        gaps = []
    # Normalize each gap to the schema shape
    normalized_gaps = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        section = str(gap.get("section") or "")
        normalized_gaps.append({
            "gap_type": "missing_section",
            "description": str(gap.get("description") or f"病历缺少必填章节: {section}"),
            "section": section,
            "suggestion": str(gap.get("suggestion") or f"请补充 {section} 章节 — 《病历书写基本规范》要求"),
            "related_code": str(gap.get("related_code") or ""),
        })

    is_surgical = bool(parsed.get("is_surgical_case", is_surgical_hint))
    manual_review = bool(missing) and conclusion != "PASS"

    return {
        "review_conclusion": conclusion,
        "documentation_gaps": normalized_gaps,
        "completeness_score": round(score, 4),
        "missing_sections": [str(s) for s in missing],
        "present_sections": [str(s) for s in present],
        "required_sections": [str(s) for s in required],
        "manual_review_required": manual_review,
        "is_surgical_case": is_surgical,
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "rule_set": "documentation_completeness",
        },
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """Pull a JSON object out of arbitrary LLM output.

    Handles three cases:
      1. Pure JSON (whole text is a JSON object)
      2. Fenced ```json ... ``` block
      3. First {...} substring
    """
    if not text:
        return None
    text = text.strip()

    # Case 1: pure JSON
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Case 2: fenced json block
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end > start:
            block = text[start:end].strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass

    # Case 3: first {...} substring
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        substr = text[start:end + 1]
        try:
            return json.loads(substr)
        except json.JSONDecodeError:
            pass

    return None


def _detect_surgical(text: str) -> bool:
    """Heuristic: detect if the EMR text mentions surgery."""
    surgical_keywords = (
        "手术", "切除术", "吻合术", "修补术", "置换术", "剖宫产", "刮宫", "介入",
    )
    return any(kw in text for kw in surgical_keywords)


async def _legacy_run(text: str, run_id: str) -> dict[str, Any]:
    """Fall back to the regex implementation."""
    from official_agents.note_completeness.agent_legacy import run as legacy_run
    return await legacy_run(text, run_id=run_id)


def _empty_input_response(run_id: str) -> dict[str, Any]:
    """Response for empty input — no need to call LLM."""
    return {
        "review_conclusion": "FAIL",
        "documentation_gaps": [
            {
                "gap_type": "missing_section",
                "description": "输入病历文本为空",
                "section": "",
                "suggestion": "请提供入院记录 / 出院小结 / 病程记录文本",
                "related_code": "",
            }
        ],
        "completeness_score": 0.0,
        "missing_sections": [],
        "present_sections": [],
        "required_sections": [],
        "manual_review_required": True,
        "is_surgical_case": False,
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "rule_set": "documentation_completeness",
        },
    }


__all__ = ["run", "SYSTEM_PROMPT", "AGENT_REF"]
