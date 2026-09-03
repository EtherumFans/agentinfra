"""Phase 5 Track D P0.5 Gate 4 — Semantic Query Necessity Reviewer.

LLM-backed reviewer that closes the gap the structural necessity gate
(``necessity_gate.py``) cannot reach:

  Structural rules (NQ-001..006) catch chart-already-answers patterns
  via regex. But they cannot judge:

    - C09 empty-chart pathology: "主诉腹痛. 建议进一步检查." has no
      diagnosis, no labs, no imaging. The model emits 4 diagnosis-
      invention queries ("请评估最可能的病因"). Structural NQ-001
      doesn't fire because the regex patterns look for clinical facts
      in the chart — and there are none, so the chart "doesn't answer
      the query" (vacuously true).

    - Symptom-only no-diagnosis-evidence: chart has "头晕乏力" but
      query asks "请明确诊断".

    - No-imaging-no-site: chart has no chest CT but query asks "左肺/
      右肺/肺叶".

    - No-severity-indicator-no-grade: chart has only "高血压" without
      BP value / target-organ damage, but query asks for "分级".

    - Lab-positive-not-equals-diagnosis: chart has "痰培养阳性" but
      query implies pathogen diagnosis without clinical correlation.

    - Complete-chart-redundant: chart already documents everything the
      query asks for — pure redundancy.

Output
======

  SemanticNecessityResult(
      verdict = "PASS" | "REVIEW_REQUIRED" | "BLOCK",
      reason_codes = ["INSUFFICIENT_CLINICAL_SUBSTRATE", ...],
      clinical_substrate_present = bool,
      existing_documentation_ambiguous = bool,
      query_answerable = bool,
      query_changes_documentation = bool,
      query_requests_new_diagnosis = bool,
      query_is_redundant = bool,
      query_is_overly_detailed = bool,
  )

BLOCK verdicts cause the orchestrator to drop the query (similar to
NQ-001 hard-fail). REVIEW_REQUIRED keeps the query but flags it.

DEGRADED on LLM failure: verdict="PASS" with ``degraded=True`` so the
gate never blocks on LLM outage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.icoder.agent_runtime.cdi.domain import ProviderQuery

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


_SEMANTIC_NECESSITY_PROMPT = """你是 CDI Provider Query 的"语义必要性"审查者. 你的任务是判断一个 Query 是否真正必要, 还是模型在没有 chart 支持的情况下"发明"问题.

输入:
  query_text: {query_text}
  query_topic: {topic}
  chart_excerpt: {chart_excerpt}
  response_options: {response_options}

请评估以下 6 个布尔指标:

1. clinical_substrate_present (true/false)
   chart 中是否有足够的临床基质 (诊断/症状/检验/影像) 支撑这个 Query?
   - 空白病历 (只有"主诉腹痛, 建议进一步检查") → false
   - 只有症状 (头晕乏力) 但无任何检验/影像 → 取决于 Query 是否需要
   - 完整诊断+检验+影像 → true

2. existing_documentation_ambiguous (true/false)
   chart 中已经记录的内容是否模糊到需要澄清?
   - "诊断: 肺炎" 但未说病原体 → true (病原体歧义)
   - "诊断: 肺炎, 痰培养: 肺炎链球菌" → false (已明确)

3. query_answerable (true/false)
   医生在本次就诊能否合理回答?
   - "请明确最可能的病因" 在空白病历 → false (医生无依据)
   - "请确认是否为左肺肺炎" 但无胸片 → false
   - "请根据痰培养结果明确病原体" 在有痰培养时 → true

4. query_changes_documentation (true/false)
   医生的答复是否会改变病历或下游编码?
   - 病历已完整, 答复不增加信息 → false
   - 答复会填补编码所需特异性 → true

5. query_requests_new_diagnosis (true/false)
   Query 是否在引导医生"发明"新诊断?
   - "请评估最可能的病因" 在空白病历 → true (诊断发明)
   - "请根据现有培养结果明确病原体" → false (澄清已有事实)

6. query_is_redundant (true/false)
   Query 是否与已记录内容重复?
   - 病历已写"急性胆囊炎" 还问 "是否急性" → true
   - 既往史已写"糖尿病" 还问 "是否有糖尿病史" → true

7. query_is_overly_detailed (true/false)
   Query 是否超出当前 CDI 文档/编码闭环的最小必要粒度?
   - 已有明确感染诊断但无培养/病原学证据, 仅为继续细分而追问病原体 → true
   - 已记录客观异常且其临床归因已明确, 再问异常的"类型/临床意义/原因" → true
   - 诊断与治疗闭环已完整, 再追严重程度、分型或病因且不改变文档/编码 → true
   - 有培养结果但病原体未写入诊断, 或存在真实矛盾/关键编码维度缺失 → false
   关键: "临床上还能继续细分"不等于"CDI 必须追问".

8. chart_fully_documented (true/false)  [Track H3.11]
   chart 是否已记录该 Query 所需的全部维度 (类型/部位/严重程度/病因/手术/病理/并发症/病程)?
   - 病历已写"急性化脓性阑尾炎(局限性),腹腔镜切除,病理确诊,无并发症,3天出院" → true
   - 病历只有"肺炎"(未说病原体/严重程度) → false
   - 注意: 如果存在矛盾 (如术后体温上升但WBC下降), 设为 false — 矛盾本身需要澄清.

判定规则:
- 如果 clinical_substrate_present=false AND query_requests_new_diagnosis=true → verdict="BLOCK", reason="INSUFFICIENT_CLINICAL_SUBSTRATE"
- 如果 query_answerable=false → verdict="BLOCK", reason="NOT_ANSWERABLE"
- 如果 query_is_redundant=true → verdict="BLOCK", reason="REDUNDANT_WITH_CHART"
- 如果 query_is_overly_detailed=true AND query_changes_documentation=false → verdict="BLOCK", reason="BEYOND_MINIMAL_DOCUMENTATION_NEED"
- 如果 chart_fully_documented=true AND query_changes_documentation=false → verdict="BLOCK", reason="CHART_ALREADY_COMPLETE"
- 如果 existing_documentation_ambiguous=false AND query_changes_documentation=false → verdict="BLOCK", reason="NO_DOCUMENTATION_IMPACT"
- 如果 query_requests_new_diagnosis=true (但 substrate 存在) → verdict="REVIEW_REQUIRED", reason="POSSIBLE_DIAGNOSIS_INVENTION"
- 否则 → verdict="PASS"

严格按以下 JSON 输出 (无其他文本):
{{
  "clinical_substrate_present": true|false,
  "existing_documentation_ambiguous": true|false,
  "query_answerable": true|false,
  "query_changes_documentation": true|false,
  "query_requests_new_diagnosis": true|false,
  "query_is_redundant": true|false,
  "query_is_overly_detailed": true|false,
  "chart_fully_documented": true|false,
  "verdict": "PASS" | "REVIEW_REQUIRED" | "BLOCK",
  "reason_codes": ["..."]
}}

红线: 如果调用本身失败, 不要编造 — 返回 verdict="PASS" + 空 reason_codes.
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class SemanticNecessityResult:
    verdict: str = "PASS"  # "PASS" | "REVIEW_REQUIRED" | "BLOCK" | "DEGRADED"
    reason_codes: list[str] = field(default_factory=list)
    clinical_substrate_present: bool = True
    existing_documentation_ambiguous: bool = False
    query_answerable: bool = True
    query_changes_documentation: bool = True
    query_requests_new_diagnosis: bool = False
    query_is_redundant: bool = False
    query_is_overly_detailed: bool = False
    chart_fully_documented: bool = False  # Track H3.11
    degraded: bool = False
    error_reason: str = ""
    provider: str = "deepseek"
    model: str = ""
    latency_ms: int = 0
    total_tokens: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def review_necessity(
    query: ProviderQuery,
    *,
    chart: str,
    llm: Any | None = None,
) -> SemanticNecessityResult:
    """LLM-backed semantic necessity review.

    DEGRADED on failure: preserves the query for local audit with
    ``degraded=True``. The orchestrator records the required-gate failure,
    and public REST/A2A adapters reject the entire result.
    """
    if llm is None:
        from app.services.llm_service import llm_service as _default_llm
        llm = _default_llm

    import time
    t0 = time.monotonic()

    if not query.query_text:
        return SemanticNecessityResult(
            verdict="DEGRADED",
            degraded=True,
            error_reason="empty query_text — nothing to review",
        )

    options = ", ".join(query.response_options) if query.response_options else "(empty)"
    system_prompt = _SEMANTIC_NECESSITY_PROMPT.format(
        query_text=query.query_text[:600],
        topic=query.topic or "(empty)",
        chart_excerpt=(chart or "")[:2500],
        response_options=options,
    )

    try:
        resp = await llm.chat(
            messages=[{"role": "user", "content": "请审查该 query 的语义必要性."}],
            system_prompt=system_prompt,
            response_format="json",
            temperature=0.0,
            max_tokens=600,
        )
    except Exception as exc:
        logger.warning("necessity_semantic LLM call failed: %s", exc)
        return SemanticNecessityResult(
            degraded=True,
            error_reason=f"{type(exc).__name__}: {exc}",
            provider=getattr(llm, "provider", "deepseek"),
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    content = (resp.get("content") or "").strip()
    usage = resp.get("usage") or {}

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("necessity_semantic LLM returned non-JSON: %r", content[:200])
        return SemanticNecessityResult(
            degraded=True,
            error_reason="llm returned non-json content",
            provider=getattr(llm, "provider", "deepseek"),
            model=getattr(llm, "model", ""),
            latency_ms=latency_ms,
            total_tokens=int(usage.get("total_tokens", 0)),
        )

    verdict_raw = str(data.get("verdict") or "PASS").upper()
    if verdict_raw not in ("PASS", "REVIEW_REQUIRED", "BLOCK"):
        verdict_raw = "PASS"
    changes_documentation = bool(data.get("query_changes_documentation", True))
    overly_detailed = bool(data.get("query_is_overly_detailed", False))
    reason_codes = [str(r) for r in (data.get("reason_codes") or [])]
    if overly_detailed and not changes_documentation:
        verdict_raw = "BLOCK"
        if "BEYOND_MINIMAL_DOCUMENTATION_NEED" not in reason_codes:
            reason_codes.append("BEYOND_MINIMAL_DOCUMENTATION_NEED")

    return SemanticNecessityResult(
        verdict=verdict_raw,
        reason_codes=reason_codes,
        clinical_substrate_present=bool(data.get("clinical_substrate_present", True)),
        existing_documentation_ambiguous=bool(data.get("existing_documentation_ambiguous", False)),
        query_answerable=bool(data.get("query_answerable", True)),
        query_changes_documentation=changes_documentation,
        query_requests_new_diagnosis=bool(data.get("query_requests_new_diagnosis", False)),
        query_is_redundant=bool(data.get("query_is_redundant", False)),
        query_is_overly_detailed=overly_detailed,
        chart_fully_documented=bool(data.get("chart_fully_documented", False)),
        degraded=False,
        provider=getattr(llm, "provider", "deepseek"),
        model=getattr(llm, "model", ""),
        latency_ms=latency_ms,
        total_tokens=int(usage.get("total_tokens", 0)),
    )


__all__ = ["SemanticNecessityResult", "review_necessity"]
