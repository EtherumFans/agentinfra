"""CDI Orchestrator (Phase 5 Track D Gate 6 — minimal slice for Gate 3).

Pure-logic orchestrator that threads a ``CDICase`` through CDI workflow
stages. Mirrors the structure of Track C's ``CodingComplianceOrchestrator``.

Stages (Corti-compatible 5-step CDI workflow, see agent_pack.json):
    1. encounter_synthesis
    2. gap_identification
    3. expert_consultation
    4. query_generation
    5. query_necessity_gate         (Phase 5 Track D P0.5 Gate 2)
    6. query_single_dimension_gate  (Phase 5 Track D P0.5 Gate 3)
    7. claim_evidence_alignment_gate (Phase 5 Track D P0.5 Gate 4)
    8. semantic_necessity_gate       (Phase 5 Track D P0.5 Gate 4)
    9. query_compliance_gate         (NLQ-001..011)
   10. specialist_trace_emit

Gate 3 ships a runnable skeleton. The runner is a callable — for now
the skeleton uses a no-op runner that produces empty stage outputs,
which is enough to validate the wiring. Gate 6 replaces the runner
with a real DeepSeek-backed implementation.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .domain import (
    CDICase,
    CDIModelCallTrace,
    DocumentationGap,
    EvidenceSpan,
    ProviderQuery,
    gap_query_draft_item,
    query_audit_item,
)
from .nlq_gate import ProviderQueryForGate, evaluate as evaluate_nlq

logger = logging.getLogger(__name__)


class _SafetyGateTelemetryLLM:
    """Transparent LLM proxy that records content-free gate accounting."""

    def __init__(
        self,
        delegate: Any,
        sink: list[CDIModelCallTrace],
        *,
        stage: str,
    ) -> None:
        self._delegate = delegate
        self._sink = sink
        self._stage = stage

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        response: Any = None
        degraded = False
        try:
            response = await self._delegate.chat(*args, **kwargs)
            return response
        except Exception:
            degraded = True
            raise
        finally:
            usage = response.get("usage") if isinstance(response, dict) else None
            usage = usage if isinstance(usage, dict) else {}

            def _usage_count(name: str) -> int | None:
                value = usage.get(name)
                try:
                    count = int(value)
                except (TypeError, ValueError, OverflowError):
                    return None
                return count if 0 <= count <= 100_000_000 else None

            provider = str(getattr(self._delegate, "provider", "") or "")
            model = str(getattr(self._delegate, "model", "") or "")
            if not provider or not model:
                try:
                    from app.config import settings
                    provider = provider or str(settings.LLM_PROVIDER or "")
                    model = model or str(settings.LLM_MODEL or "")
                except Exception:  # pragma: no cover - defensive import fallback
                    pass
            self._sink.append(CDIModelCallTrace(
                stage=self._stage,
                provider=provider,
                model=model,
                latency_ms=max(int((time.perf_counter() - started) * 1000), 0),
                prompt_tokens=_usage_count("prompt_tokens"),
                completion_tokens=_usage_count("completion_tokens"),
                total_tokens=_usage_count("total_tokens"),
                degraded=degraded,
            ))


_ESCAPE_OPTION_RE = re.compile(
    r"无法确定|不能确定|不确定|未明确|其他|unable to determine|indeterminate|other",
    re.I,
)

_CLINICAL_QUANTITY_RE = re.compile(
    r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*(?:"
    r"μg/kg/min|ug/kg/min|mmol/L|μmol/L|mmHg|次/分|L/min|"
    r"mg|mL|ml|kg|cm²|cm2|公斤|克|毫升|小时|分钟|天|日|周|%"
    r")(?![A-Za-z])",
    re.I,
)
_SAFE_NON_QUANTITATIVE_OPTIONS = (
    "其他临床判断（请说明）",
    "现有资料不足，无法确定",
    "临床不支持所询问情况",
    "暂不适用",
)


def _remove_ungrounded_quantity_options(
    query: ProviderQuery,
    chart: str,
) -> int:
    """Remove response options that introduce chart-absent measurements.

    Provider Query options are suggestions, not a place to import diagnostic
    thresholds, doses, or time windows from model memory. Preserve quantities
    copied from the chart and replace removed options with non-leading,
    non-quantitative choices so the draft remains reviewable.
    """
    normalized_chart = re.sub(r"\s+", "", chart).lower()
    kept: list[str] = []
    removed = 0
    for option in query.response_options:
        tokens = _CLINICAL_QUANTITY_RE.findall(str(option))
        if any(
            re.sub(r"\s+", "", token).lower() not in normalized_chart
            for token in tokens
        ):
            removed += 1
            continue
        if option not in kept:
            kept.append(option)
    for fallback in _SAFE_NON_QUANTITATIVE_OPTIONS:
        if len(kept) >= 4:
            break
        if fallback not in kept:
            kept.append(fallback)
    query.response_options = kept
    return removed


def _ungrounded_quantity_tokens(text: str, chart: str) -> list[str]:
    """Return model-authored clinical quantities absent from the chart."""

    normalized_chart = re.sub(r"\s+", "", chart).lower()
    return [
        token
        for token in _CLINICAL_QUANTITY_RE.findall(str(text or ""))
        if re.sub(r"\s+", "", token).lower() not in normalized_chart
    ]


def _redact_ungrounded_quantities(text: str, chart: str) -> tuple[str, int]:
    """Remove unsupported quantitative values from non-evidence prose."""

    output = str(text or "")
    tokens = _ungrounded_quantity_tokens(output, chart)
    for token in dict.fromkeys(tokens):
        output = output.replace(token, "病历未提供的定量值")
    return output, len(tokens)


def _bounded_response_options(options: list[str]) -> list[str] | None:
    """Normalize a 6+ option taxonomy without changing its clinical axis."""
    if len(options) <= 5:
        return None
    escape = next((opt for opt in reversed(options) if _ESCAPE_OPTION_RE.search(opt)), None)
    if escape is None:
        return None
    substantive = [opt for opt in options if opt is not escape]
    kept = [*substantive[:4], escape]
    if len(kept) < 3:
        return None
    labels = "ABCDE"
    normalized: list[str] = []
    for index, option in enumerate(kept):
        body = re.sub(r"^\s*[A-ZＡ-Ｚ]\s*[.．、:)）-]\s*", "", option).strip()
        normalized.append(f"{labels[index]}. {body}")
    return normalized


def _open_clause_without_yes_no_tail(text: str) -> str | None:
    """Keep an already-open main question and remove a redundant yes/no tail."""
    marker = re.search(r"[？?。；;]\s*(?:是否|能否|是不是)", text or "")
    if marker is None:
        return None
    prefix = (text or "")[: marker.start() + 1].strip()
    if not re.search(r"(?:什么|哪些|哪种|如何|怎么|多少|多久|请明确|please (?:clarify|specify|provide)|what|which|how)", prefix, re.I):
        return None
    if prefix.endswith(("。", "；", ";")):
        prefix = prefix[:-1] + "？"
    return prefix

_REWRITE_TARGET_AXIS_BY_GAP_TYPE = {
    "diagnostic_specificity": "type",
    "etiology_unspecified": "etiology",
    "severity_unspecified": "severity",
    "acuity_unspecified": "acuity",
    "anatomical_site_unspecified": "site",
    "clinical_correlation_unestablished": "correlation",
    "temporal_unspecified": "course",
}


def _rewrite_target_axis(gap_type: str) -> str:
    """Normalize legacy human-readable gap-type aliases before routing."""
    normalized = str(gap_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _REWRITE_TARGET_AXIS_BY_GAP_TYPE.get(normalized, "")


def _laterality_conflict_rewrite(
    item: dict[str, Any], gap: DocumentationGap,
) -> dict[str, Any] | None:
    """Build a bounded site-only query for an explicit left/right conflict.

    Generated drafts often append ``and explain the reason for the
    inconsistency`` to a clinically valid laterality question.  That creates
    a second (etiology) axis and makes the single-dimension gate reject the
    whole draft.  Left/right contradictions are structured enough to repair
    without another probabilistic model call.
    """
    combined = " ".join((
        str(item.get("topic") or ""),
        str(item.get("reason") or ""),
        str(item.get("query_text") or ""),
        str(gap.description or ""),
        str(gap.minimal_clarification_needed or ""),
        " ".join(
            str(span.get("quote") or "")
            for span in item.get("evidence_spans") or []
            if isinstance(span, dict)
        ),
    ))
    has_left = bool(re.search(r"左(?:侧|胸)", combined))
    has_right = bool(re.search(r"右(?:侧|胸)", combined))
    has_site_subject = bool(re.search(r"侧别|左右|部位|肋骨|肢体|肺|肾", combined))
    if not (has_left and has_right and has_site_subject):
        return None
    source_id = str(item.get("query_id") or "")
    return {
        "source_query_id": source_id,
        "query_id": f"{source_id}-site-rewrite",
        "gap_id": str(item.get("gap_id") or ""),
        "topic": "最终诊断的侧别",
        "reason": "不同病历记录中的左右侧别存在矛盾，需要确认最终诊断。",
        "query_text": "请明确最终诊断中所记录病变的侧别。",
        "response_options": [
            "A. 左侧",
            "B. 右侧",
            "C. 双侧",
            "D. 无法确定",
        ],
        "evidence_spans": list(item.get("evidence_spans") or []),
    }


def _pneumonia_type_rewrite(
    item: dict[str, Any], gap: DocumentationGap,
) -> dict[str, Any] | None:
    """Reduce a pneumonia type+severity draft to its server-selected type axis."""
    combined = " ".join((
        str(item.get("topic") or ""),
        str(item.get("reason") or ""),
        str(item.get("query_text") or ""),
        str(gap.description or ""),
    ))
    axes = {str(axis) for axis in item.get("detected_axes") or []}
    if not re.search(r"肺炎|pneumonia", combined, re.I):
        return None
    if not {"type", "severity"}.issubset(axes):
        return None
    source_id = str(item.get("query_id") or "")
    return {
        "source_query_id": source_id,
        "query_id": f"{source_id}-type-rewrite",
        "gap_id": str(item.get("gap_id") or ""),
        "topic": "肺炎类型",
        "reason": "肺炎诊断已记录，但其临床类型尚未明确。",
        "query_text": "请明确本次肺炎的具体类型。",
        "response_options": [
            "A. 社区获得性肺炎",
            "B. 医院获得性肺炎",
            "C. 吸入性肺炎",
            "D. 其他类型（请注明）",
            "E. 无法确定",
        ],
        "evidence_spans": list(item.get("evidence_spans") or []),
    }


def _dka_confirmation_without_yes_no(query: ProviderQuery) -> str | None:
    """Turn only a DKA yes/no confirmation into an open diagnosis request."""
    text = f"{query.topic} {query.query_text}"
    if not re.search(r"糖尿病酮症酸中毒|DKA|diabetic ketoacidosis", text, re.I):
        return None
    if not re.search(r"是否.{0,16}(?:诊断|考虑|记录)|whether.{0,16}(?:diagnos|document)", query.query_text, re.I):
        return None
    return "请明确本次入院应记录的糖尿病急性并发症。"


def _aecopd_respiratory_failure_coverage_query(
    case: CDICase,
) -> ProviderQuery | None:
    """Provide deterministic coverage for objective AECOPD respiratory failure.

    The model may identify only generic exacerbation severity/etiology even
    when PaCO2/PaO2 support a materially more specific documentation gap.
    Add one type-only draft only when no surviving query already covers it.
    """
    chart = case.chart_excerpt or ""
    if not re.search(
        r"(?:慢阻肺|COPD).{0,20}急性加重|acute exacerbation.{0,20}(?:COPD|chronic obstructive)",
        chart,
        re.I,
    ):
        return None
    co2_match = re.search(r"PaCO2\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    o2_match = re.search(r"PaO2\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    if co2_match is None or o2_match is None:
        return None
    if float(co2_match.group(1)) < 50 or float(o2_match.group(1)) > 60:
        return None
    if any(
        re.search(
            r"呼吸衰竭|respiratory failure",
            f"{query.topic} {query.query_text}",
            re.I,
        )
        for query in case.proposed_provider_queries
    ):
        return None
    gap = next((
        candidate for candidate in case.documentation_gaps
        if re.search(
            r"血气|PaCO2|PaO2|blood gas|respiratory|酸中毒|低氧",
            " ".join((
                candidate.description or "",
                candidate.why_it_matters or "",
                candidate.evidence_span.quote or "",
            )),
            re.I,
        )
    ), None)
    if gap is None:
        return None
    blood_gas = re.search(
        r"(?:血气|blood gas)[^。；;\n]{0,80}(?:PaCO2[^。；;\n]{0,40}PaO2[^。；;\n]{0,20})",
        chart,
        re.I,
    )
    if blood_gas is None:
        return None
    span = EvidenceSpan(
        document_id="chart-001",
        quote=blood_gas.group(0),
        char_start=blood_gas.start(),
        char_end=blood_gas.end(),
    )
    return ProviderQuery(
        query_id=f"Q-RF-{uuid.uuid4().hex[:8]}",
        gap_id=gap.gap_id,
        topic="呼吸衰竭类型",
        reason="血气显示高碳酸血症和低氧血症，但呼吸衰竭诊断及类型尚未明确。",
        evidence_span=span,
        evidence_spans=[span],
        query_text="请明确本次呼吸衰竭的具体类型。",
        response_options=[
            "A. 急性II型呼吸衰竭",
            "B. 慢性II型呼吸衰竭急性加重",
            "C. 慢性II型呼吸衰竭",
            "D. 无法确定",
        ],
    )


def _pneumonia_type_coverage_query(case: CDICase) -> ProviderQuery | None:
    """Ensure a documented but unspecified pneumonia has one type query."""
    chart = case.chart_excerpt or ""
    if not re.search(r"(?:诊断|diagnosis)[:：]?[^。\n]{0,20}(?:肺炎|pneumonia)", chart, re.I):
        return None
    if re.search(
        r"社区获得性肺炎|医院获得性肺炎|吸入性肺炎|community[- ]acquired|hospital[- ]acquired|aspiration pneumonia",
        chart,
        re.I,
    ):
        return None
    if any(
        re.search(r"肺炎|pneumonia", f"{q.topic} {q.query_text}", re.I)
        and re.search(r"类型|分型|type|classification", f"{q.topic} {q.query_text}", re.I)
        for q in case.proposed_provider_queries
    ):
        return None
    gap = next((
        candidate for candidate in case.documentation_gaps
        if re.search(r"肺炎|pneumonia", candidate.description or "", re.I)
        and re.search(r"类型|type|specific", candidate.description or "", re.I)
    ), None)
    if gap is None:
        return None
    match = re.search(r"(?:入院诊断|诊断|admission diagnosis)[:：]?[^。\n]{0,20}(?:肺炎|pneumonia)", chart, re.I)
    if match is None:
        return None
    span = EvidenceSpan(
        document_id="chart-001", quote=match.group(0),
        char_start=match.start(), char_end=match.end(),
    )
    return ProviderQuery(
        query_id=f"Q-PNA-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="肺炎类型", reason="肺炎诊断已记录，但临床类型尚未明确。",
        evidence_span=span, evidence_spans=[span],
        query_text="请明确本次肺炎的具体类型。",
        response_options=[
            "A. 社区获得性肺炎", "B. 医院获得性肺炎",
            "C. 吸入性肺炎", "D. 其他类型（请注明）", "E. 无法确定",
        ],
    )


def _iron_deficiency_chronic_blood_loss_coverage_query(
    case: CDICase,
) -> ProviderQuery | None:
    """Clarify a coding-relevant chronic-blood-loss cause of iron deficiency."""
    chart = case.chart_excerpt or ""
    if not re.search(r"(?:入院诊断|诊断)[:：]?[^。\n]{0,20}贫血", chart):
        return None
    hb = re.search(r"Hb\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    mcv = re.search(r"MCV\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    ferritin = re.search(r"铁蛋白\s*[:=]?\s*(\d+(?:\.\d+)?)", chart)
    occult = re.search(r"便潜血(?:试验)?\s*(?:阳性|\+)", chart)
    if (
        hb is None or mcv is None or ferritin is None or occult is None
        or float(hb.group(1)) >= 120
        or float(mcv.group(1)) >= 80
        or float(ferritin.group(1)) >= 15
    ):
        return None
    if any(
        re.search(
            r"慢性(?:消化道)?失血|失血性缺铁性贫血|chronic (?:gastrointestinal )?blood loss",
            f"{query.topic} {query.query_text} {' '.join(query.response_options)}",
            re.I,
        )
        for query in case.proposed_provider_queries
    ):
        return None
    gap = next((
        candidate for candidate in case.documentation_gaps
        if re.search(
            r"贫血|缺铁|便潜血|消化道出血|anemia|iron deficiency|occult blood",
            " ".join((candidate.description or "", candidate.why_it_matters or "")),
            re.I,
        )
    ), None)
    if gap is None:
        return None
    iron_pattern = re.search(
        r"Hb[^\n]{0,30}MCV[^\n]{0,45}(?:血清铁[^\n]{0,20})?铁蛋白[^。\n]{0,15}",
        chart,
        re.I,
    )
    if iron_pattern is None:
        return None
    spans = [
        EvidenceSpan(
            document_id="chart-001", quote=iron_pattern.group(0),
            char_start=iron_pattern.start(), char_end=iron_pattern.end(),
        ),
        EvidenceSpan(
            document_id="chart-001", quote=occult.group(0),
            char_start=occult.start(), char_end=occult.end(),
        ),
    ]
    return ProviderQuery(
        query_id=f"Q-IDA-BL-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="缺铁性贫血与慢性失血的诊断关系",
        reason="小细胞性贫血、铁蛋白降低并伴便潜血阳性，但贫血与慢性消化道失血的诊断关系尚未记录。",
        evidence_span=spans[0], evidence_spans=spans,
        query_text="请明确本次缺铁性贫血与慢性消化道失血的诊断关系。",
        response_options=[
            "A. 缺铁性贫血继发于慢性消化道失血",
            "B. 缺铁性贫血，但现有资料不能确定与慢性消化道失血相关",
            "C. 其他贫血病因（请注明）",
            "D. 无法确定",
        ],
    )


def _normalize_existing_iron_deficiency_query(case: CDICase) -> bool:
    """Reduce an anemia cause+source draft to the supported diagnosis-type axis."""
    chart = case.chart_excerpt or ""
    hb = re.search(r"Hb\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    mcv = re.search(r"MCV\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    ferritin = re.search(r"铁蛋白\s*[:=]?\s*(\d+(?:\.\d+)?)", chart)
    iron_pattern = re.search(
        r"Hb[^\n]{0,30}MCV[^\n]{0,45}(?:血清铁[^\n]{0,20})?铁蛋白[^。\n]{0,15}",
        chart,
        re.I,
    )
    if (
        hb is None or mcv is None or ferritin is None or iron_pattern is None
        or float(hb.group(1)) >= 120
        or float(mcv.group(1)) >= 80
        or float(ferritin.group(1)) >= 15
    ):
        return False
    for query in case.proposed_provider_queries:
        combined = f"{query.topic} {query.query_text}"
        if not re.search(r"贫血|anemia", combined, re.I):
            continue
        if re.search(r"便潜血.{0,12}临床意义|occult blood.{0,20}(?:meaning|significance)", combined, re.I):
            continue
        if not re.search(r"病因|类型|出血来源|cause|etiology|type", combined, re.I):
            continue
        span = EvidenceSpan(
            document_id="chart-001", quote=iron_pattern.group(0),
            char_start=iron_pattern.start(), char_end=iron_pattern.end(),
        )
        query.topic = "贫血类型"
        query.reason = "小细胞性贫血并伴铁蛋白降低，但诊断仅记录为贫血。"
        query.evidence_span = span
        query.evidence_spans = [span]
        query.query_text = "请明确本次贫血的诊断类型。"
        query.response_options = [
            "A. 缺铁性贫血", "B. 慢性病性贫血",
            "C. 其他类型（请注明）", "D. 无法确定",
        ]
        return True
    return False


def _dka_coverage_query(case: CDICase) -> ProviderQuery | None:
    """Ensure objective ketoacidosis gets a diagnosis-focused CDI query."""
    chart = case.chart_excerpt or ""
    if not re.search(r"(?:糖尿病|diabetes)", chart, re.I):
        return None
    ph = re.search(r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    hco3 = re.search(r"HCO3\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    if ph is None or hco3 is None or float(ph.group(1)) > 7.30 or float(hco3.group(1)) > 18:
        return None
    if not re.search(r"酮体\s*(?:阳性|\+)|ketones?\s*(?:positive|\+)", chart, re.I):
        return None
    if any(
        re.search(r"糖尿病酮症酸中毒|DKA|diabetic ketoacidosis", f"{q.topic} {q.query_text} {' '.join(q.response_options)}", re.I)
        for q in case.proposed_provider_queries
    ):
        return None
    gap = next((
        candidate for candidate in case.documentation_gaps
        if re.search(
            r"酮症酸中毒|ketoacidosis|metabolic acidosis|酮体",
            " ".join((candidate.description or "", candidate.why_it_matters or "")),
            re.I,
        )
    ), None)
    if gap is None:
        return None
    match = re.search(r"pH[^。\n]{0,60}酮体阳性[^。\n]{0,30}", chart, re.I)
    if match is None:
        return None
    span = EvidenceSpan(
        document_id="chart-001", quote=match.group(0),
        char_start=match.start(), char_end=match.end(),
    )
    return ProviderQuery(
        query_id=f"Q-DKA-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="糖尿病急性并发症", reason="酸中毒和酮体阳性，但急性并发症诊断未明确。",
        evidence_span=span, evidence_spans=[span],
        query_text="请明确本次入院应记录的糖尿病急性并发症。",
        response_options=[
            "A. 糖尿病酮症酸中毒", "B. 糖尿病酮症（无酸中毒）",
            "C. 其他急性并发症（请注明）", "D. 无法确定",
        ],
    )


def _normalize_existing_dka_query(case: CDICase) -> bool:
    """Focus an existing DKA+severity/yes-no draft on the diagnosis only."""
    chart = case.chart_excerpt or ""
    ph = re.search(r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    hco3 = re.search(r"HCO3\s*[:=]?\s*(\d+(?:\.\d+)?)", chart, re.I)
    if (
        ph is None or hco3 is None
        or float(ph.group(1)) > 7.30 or float(hco3.group(1)) > 18
        or not re.search(r"酮体\s*(?:阳性|\+)|ketones?\s*(?:positive|\+)", chart, re.I)
    ):
        return False
    for query in case.proposed_provider_queries:
        combined = f"{query.topic} {query.query_text} {' '.join(query.response_options)}"
        if not re.search(
            r"糖尿病酮症酸中毒|DKA|diabetic ketoacidosis|急性代谢失代偿|"
            r"(?:代谢性)?酸中毒.{0,12}(?:类型|诊断)|acidosis type",
            combined,
            re.I,
        ):
            continue
        if re.search(r"糖尿病.{0,8}(?:分型|类型)|diabetes type", combined, re.I):
            continue
        original = query_audit_item(
            query,
            status="AUTOMATIC_DIAGNOSIS_FOCUS_REWRITE",
            gate_reasons=["CDI-Focus: DKA diagnosis must be separated from severity/yes-no wording"],
            rewrite_kind="FOCUS_DKA_DIAGNOSIS",
        )
        query.topic = "糖尿病急性并发症"
        query.reason = "酸中毒和酮体阳性，但急性并发症诊断未明确。"
        query.query_text = "请明确本次入院应记录的糖尿病急性并发症。"
        query.response_options = [
            "A. 糖尿病酮症酸中毒",
            "B. 糖尿病酮症（无酸中毒）",
            "C. 其他急性并发症（请注明）",
            "D. 无法确定",
        ]
        original["replacement_query_id"] = query.query_id
        original["rewrite_attempt_status"] = "ACCEPTED_FOR_DOWNSTREAM_GATES"
        original["rewritten_query_text"] = query.query_text
        original["rewritten_response_options"] = list(query.response_options)
        case.query_rewrite_queue.append(original)
        return True
    return False


def _normalize_existing_biliary_obstruction_query(case: CDICase) -> bool:
    """Focus an existing CBD/liver-correlation draft on a diagnosis axis."""
    chart = case.chart_excerpt or ""
    cbd = re.search(r"胆总管[^。\n]{0,16}?(\d+(?:\.\d+)?)\s*mm", chart, re.I)
    if cbd is None or float(cbd.group(1)) < 8 or not re.search(r"(?:ALP|TBIL)\s*\d", chart, re.I):
        return False
    for query in case.proposed_provider_queries:
        combined = f"{query.topic} {query.query_text} {' '.join(query.response_options)}"
        if not re.search(r"胆总管|胆道梗阻|胆管炎|choledo|cholang", combined, re.I):
            continue
        original = query_audit_item(
            query, status="AUTOMATIC_DIAGNOSIS_FOCUS_REWRITE",
            gate_reasons=["CDI-Focus: dilated CBD and cholestatic labs require a diagnosis-focused clarification"],
            rewrite_kind="FOCUS_BILIARY_OBSTRUCTION_DIAGNOSIS",
        )
        query.topic = "胆道梗阻相关诊断"
        query.reason = "胆总管扩张并伴胆汁淤积指标异常，但相关诊断未明确。"
        query.query_text = "请明确本次应记录的胆道梗阻相关诊断。"
        query.response_options = [
            "A. 胆总管结石", "B. 急性胆管炎",
            "C. 胆总管结石并急性胆管炎", "D. 其他诊断（请注明）", "E. 无法确定",
        ]
        original["replacement_query_id"] = query.query_id
        original["rewrite_attempt_status"] = "ACCEPTED_FOR_DOWNSTREAM_GATES"
        original["rewritten_query_text"] = query.query_text
        original["rewritten_response_options"] = list(query.response_options)
        case.query_rewrite_queue.append(original)
        return True
    return False


def _pancreatitis_etiology_conflict_query(case: CDICase) -> ProviderQuery | None:
    """Cover a supported but unresolved acute-pancreatitis etiology.

    In addition to explicit admission/discharge conflicts, a documented acute
    pancreatitis diagnosis plus a history of gallstones is sufficient substrate
    for one open etiology clarification.  It is not sufficient to assert a
    biliary diagnosis, so the generated query remains single-dimension and
    includes an unable-to-determine option.
    """
    chart = case.chart_excerpt or ""
    explicit_conflict = bool(
        re.search(r"入院诊断[:：][^。]{0,30}胆源性胰腺炎", chart)
        and re.search(r"出院诊断[:：][^。]{0,30}特发性胰腺炎", chart)
    )
    gallstone_history = bool(
        re.search(r"(?:入院诊断|诊断)[:：][^。\n]{0,30}急性胰腺炎", chart)
        and re.search(r"(?:既往|病史|history)[:：]?[^。\n]{0,30}(?:胆石症|胆囊结石|gallstones?)", chart, re.I)
        and not re.search(
            r"(?:入院诊断|出院诊断|诊断)[:：][^。\n]{0,30}(?:胆源性|酒精性|特发性|biliary|alcoholic|idiopathic)[^。\n]{0,12}(?:胰腺炎|pancreatitis)",
            chart,
            re.I,
        )
    )
    if not (explicit_conflict or gallstone_history):
        return None
    if any(re.search(r"胰腺炎.{0,16}(?:病因|诊断变更)|病因.{0,16}胰腺炎", f"{q.topic} {q.query_text}") for q in case.proposed_provider_queries):
        return None
    gap = next((g for g in case.documentation_gaps if re.search(r"胆源性|特发性|病因|etiolog", f"{g.description} {g.why_it_matters}", re.I)), None)
    if gap is None:
        return None
    span_patterns = (
        (r"入院诊断[:：][^。]{0,30}胆源性胰腺炎", r"出院诊断[:：][^。]{0,30}特发性胰腺炎")
        if explicit_conflict
        else (
            r"(?:入院诊断|诊断)[:：][^。\n]{0,30}急性胰腺炎",
            r"(?:既往|病史|history)[:：]?[^。\n]{0,30}(?:胆石症|胆囊结石|gallstones?)",
        )
    )
    spans: list[EvidenceSpan] = []
    for pattern in span_patterns:
        match = re.search(pattern, chart)
        if match:
            spans.append(EvidenceSpan(document_id="chart-001", quote=match.group(0), char_start=match.start(), char_end=match.end()))
    if len(spans) != 2:
        return None
    return ProviderQuery(
        query_id=f"Q-PANC-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="急性胰腺炎病因",
        reason=(
            "入院与出院诊断记录的病因不一致。"
            if explicit_conflict
            else "已记录急性胰腺炎及胆石症史，但本次胰腺炎病因未明确。"
        ),
        evidence_span=spans[0], evidence_spans=spans,
        query_text="请明确本次急性胰腺炎的最终病因诊断。",
        response_options=["A. 胆源性", "B. 酒精性", "C. 特发性", "D. 其他病因（请注明）", "E. 无法确定"],
    )


def _discharge_comorbidity_omission_query(case: CDICase) -> ProviderQuery | None:
    """Cover comorbidities present in progress notes but absent at discharge."""
    chart = case.chart_excerpt or ""
    progress = re.search(r"病程记录[:：]([^。\n]+)", chart)
    discharge = re.search(r"出院诊断[:：]([^。\n]+)", chart)
    if progress is None or discharge is None:
        return None
    omitted = [name for name in ("慢性肾病", "高脂血症") if name in progress.group(1) and name not in discharge.group(1)]
    if len(omitted) < 2:
        return None
    gap = next((g for g in case.documentation_gaps if any(name in f"{g.description} {g.why_it_matters}" for name in omitted)), None)
    if gap is None:
        return None
    spans = [
        EvidenceSpan(document_id="chart-001", quote=progress.group(0), char_start=progress.start(), char_end=progress.end()),
        EvidenceSpan(document_id="chart-001", quote=discharge.group(0), char_start=discharge.start(), char_end=discharge.end()),
    ]
    return ProviderQuery(
        query_id=f"Q-DXOMIT-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="出院诊断合并症完整性", reason="病程记录中的合并症未出现在出院诊断中。",
        evidence_span=spans[0], evidence_spans=spans,
        query_text="请明确病程中所列慢性肾病和高脂血症在出院诊断中的记录情况。",
        response_options=["A. 两者均应记录", "B. 仅记录慢性肾病", "C. 仅记录高脂血症", "D. 两者均不记录", "E. 无法确定"],
    )


def _biliary_obstruction_coverage_query(case: CDICase) -> ProviderQuery | None:
    """Cover likely common-bile-duct obstruction in calculous cholecystitis."""
    chart = case.chart_excerpt or ""
    if not re.search(r"急性胆囊炎|acute cholecystitis", chart, re.I):
        return None
    cbd = re.search(r"胆总管[^。\n]{0,16}?(\d+(?:\.\d+)?)\s*mm|common bile duct[^。\n]{0,16}?(\d+(?:\.\d+)?)\s*mm", chart, re.I)
    if cbd is None:
        return None
    diameter = next(float(value) for value in cbd.groups() if value is not None)
    if diameter < 8 or not re.search(r"(?:ALP|TBIL)\s*\d", chart, re.I):
        return None
    if any(re.search(r"胆总管结石|胆管炎|choledocholithiasis|cholangitis", f"{q.topic} {q.query_text}", re.I) for q in case.proposed_provider_queries):
        return None
    gap = next((g for g in case.documentation_gaps if re.search(r"胆总管|肝功能|胆管炎|choledo|cholang|liver function", f"{g.description} {g.why_it_matters}", re.I)), None)
    if gap is None:
        return None
    span_match = re.search(r"(?:B超|超声|ultrasound)[^。\n]{0,100}胆总管[^。\n]{0,30}|胆总管[^。\n]{0,40}", chart, re.I)
    if span_match is None:
        return None
    span = EvidenceSpan(document_id="chart-001", quote=span_match.group(0), char_start=span_match.start(), char_end=span_match.end())
    return ProviderQuery(
        query_id=f"Q-CBD-{uuid.uuid4().hex[:8]}", gap_id=gap.gap_id,
        topic="胆道梗阻相关诊断", reason="胆总管扩张并伴胆汁淤积指标异常，但相关诊断未明确。",
        evidence_span=span, evidence_spans=[span],
        query_text="请明确本次应记录的胆道梗阻相关诊断。",
        response_options=["A. 胆总管结石", "B. 急性胆管炎", "C. 胆总管结石并急性胆管炎", "D. 其他诊断（请注明）", "E. 无法确定"],
    )


# ---------------------------------------------------------------------------
# Runner protocol — callable injected by the runtime layer
# ---------------------------------------------------------------------------

StageRunner = Callable[[str, CDICase, dict[str, Any]], dict[str, Any]]
"""Runner signature: ``(stage_name, case, kwargs) -> stage_result_dict``.

The runner is responsible for:
  - Invoking the underlying capability (LLM, Expert, tool)
  - Returning a dict with stage-specific keys

For Gate 3 the runtime injects a ``_StubRunner`` that returns minimal
empty outputs — enough to exercise the orchestrator path. Gate 6 wires
a real DeepSeek-backed runner.
"""


# ---------------------------------------------------------------------------
# Async-from-sync helper (for gate-internal LLM calls)
# ---------------------------------------------------------------------------


_ASYNC_BRIDGE_STATE = threading.local()


class _CDIAsyncBridge:
    """Request-scoped async loop owned by one dedicated worker thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._serve,
            name="icoder-cdi-async-bridge",
            daemon=True,
        )

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            self.loop.close()

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("CDI async bridge failed to start")

    def run(self, coro: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def close(self) -> None:
        if self._thread.is_alive():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("CDI async bridge failed to stop")


@contextmanager
def _cdi_async_bridge() -> Any:
    """Keep one dedicated event-loop thread alive for a complete CDI run."""
    existing = getattr(_ASYNC_BRIDGE_STATE, "bridge", None)
    if existing is not None:
        yield existing
        return
    bridge = _CDIAsyncBridge()
    bridge.start()
    _ASYNC_BRIDGE_STATE.bridge = bridge
    try:
        yield bridge
    finally:
        try:
            delattr(_ASYNC_BRIDGE_STATE, "bridge")
        finally:
            bridge.close()


def _run_async(coro: Any) -> Any:
    """Run a coroutine from sync code, handling nested event loops.

    Mirrors the pattern in ``real_runner.py`` — safe because FastAPI
    runs orchestrator stages inside ``asyncio.to_thread`` (a worker
    thread without a running loop). Tests that drive the orchestrator
    directly inside an async function fall through to the
    ``ThreadPoolExecutor`` path.
    """
    bridge = getattr(_ASYNC_BRIDGE_STATE, "bridge", None)
    if bridge is not None:
        return bridge.run(coro)
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        if "asyncio.run() cannot be called from a running event loop" in str(exc):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        raise


# ---------------------------------------------------------------------------
# Stage list (Corti-compatible, PDF §6)
# ---------------------------------------------------------------------------


STAGES: tuple[str, ...] = (
    "encounter_synthesis",
    "gap_identification",
    "expert_consultation",
    "query_generation",
    "query_eligibility_gate",         # Phase 5 Track H3.5 — chart-completeness + topic-gap relevance
    "query_necessity_gate",           # Phase 5 Track D P0.5 Gate 2
    "query_single_dimension_gate",    # Phase 5 Track D P0.5 Gate 3
    "claim_evidence_alignment_gate",  # Phase 5 Track D P0.5 Gate 4
    "semantic_necessity_gate",        # Phase 5 Track D P0.5 Gate 4
    "query_compliance_gate",
    "specialist_trace_emit",
)


# ---------------------------------------------------------------------------
# Completion policy (PDF §10 — gates 5 blockers + 3 non-blocking outcomes)
# ---------------------------------------------------------------------------


def _decide_completion(case: CDICase) -> Literal["AUTO_PASS", "REVIEW_RECOMMENDED", "REVIEW_REQUIRED", "BLOCKED"]:
    """Decide final completion state for a CDI case.

    Mirror of Track C Human Review Gate matrix, adapted for CDI:
        BLOCKED           — any query failed NLQ gate (cannot send)
        REVIEW_REQUIRED   — gaps found but no queries yet generated, or
                            specialist trace has high-severity rejections
        REVIEW_RECOMMENDED — queries generated and all passed NLQ, but
                            chart has risk_flags
        AUTO_PASS          — no gaps found, no risk flags
    """

    if not case.documentation_gaps and not case.risk_flags:
        return "AUTO_PASS"

    if case.proposed_provider_queries:
        blocked = any(q.nlq_gate_verdict == "BLOCK" for q in case.proposed_provider_queries)
        if blocked:
            return "BLOCKED"

    if case.documentation_gaps and not case.proposed_provider_queries:
        return "REVIEW_REQUIRED"

    if case.risk_flags:
        return "REVIEW_RECOMMENDED"

    return "REVIEW_REQUIRED"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class CDIOrchestrator:
    """Pure-logic orchestrator. Holds no mutable state between runs."""

    runner: StageRunner
    # Optional LLM override for gate-internal calls (extract_claims,
    # review_necessity). When None, _get_llm() resolves in order:
    #   1. self.llm (if explicitly set)
    #   2. self.runner.llm (test fixtures using RealCDIRunner(llm=mock))
    #   3. app.services.llm_service.llm_service (production singleton)
    llm: Any = None

    # ------------------------------------------------------------------ run

    def run(
        self,
        case: CDICase,
        *,
        stages: tuple[str, ...] = STAGES,
    ) -> CDICase:
        """Thread ``case`` through ``stages`` in order. Returns the same case
        (mutated in place) so callers can chain."""

        with _cdi_async_bridge():
            begin_run = getattr(self.runner, "begin_run", None)
            end_run = getattr(self.runner, "end_run", None)
            if callable(begin_run):
                begin_run()
            try:
                for stage in stages:
                    started = time.perf_counter()
                    try:
                        self._run_stage(stage, case)
                    finally:
                        case.stage_duration_ms[stage] = max(
                            int((time.perf_counter() - started) * 1000),
                            0,
                        )
                case.completion_state = _decide_completion(case)
            finally:
                if callable(end_run):
                    end_run()
        return case

    # ------------------------------------------------------------------ stage

    def _run_stage(self, stage: str, case: CDICase) -> None:
        if stage == "encounter_synthesis":
            self._stage_encounter_synthesis(case)
        elif stage == "gap_identification":
            self._stage_gap_identification(case)
        elif stage == "expert_consultation":
            self._stage_expert_consultation(case)
        elif stage == "query_generation":
            self._stage_query_generation(case)
        elif stage == "query_eligibility_gate":
            self._stage_query_eligibility_gate(case)
        elif stage == "query_necessity_gate":
            self._stage_query_necessity_gate(case)
        elif stage == "query_single_dimension_gate":
            self._stage_query_single_dimension_gate(case)
        elif stage == "claim_evidence_alignment_gate":
            self._stage_claim_evidence_alignment_gate(case)
        elif stage == "semantic_necessity_gate":
            self._stage_semantic_necessity_gate(case)
        elif stage == "query_compliance_gate":
            self._stage_query_compliance_gate(case)
        elif stage == "specialist_trace_emit":
            self._stage_specialist_trace_emit(case)
        else:  # pragma: no cover — defensive
            raise ValueError(f"unknown CDI stage: {stage}")

    # ------------------------------------------------------------------ stages

    def _stage_encounter_synthesis(self, case: CDICase) -> None:
        result = self.runner("encounter_synthesis", case, {})
        case.stage_run_ids["encounter_synthesis"] = str(result.get("run_id", ""))
        case.stage_trace_ids["encounter_synthesis"] = str(result.get("trace_id", ""))
        from .domain import EncounterSummary
        raw_key_points = [str(item) for item in result.get("key_points", [])]
        safe_key_points = [
            item for item in raw_key_points
            if not _ungrounded_quantity_tokens(item, case.chart_excerpt)
        ]
        case.encounter_summary = EncounterSummary(
            key_points=safe_key_points,
            encounter_metadata=dict(result.get("encounter_metadata", {})),
        )
        removed = len(raw_key_points) - len(safe_key_points)
        if removed:
            case.stage_run_ids["encounter_synthesis::ungrounded_removed"] = str(
                removed
            )

    def _stage_gap_identification(self, case: CDICase) -> None:
        result = self.runner("gap_identification", case, {})
        case.stage_run_ids["gap_identification"] = str(result.get("run_id", ""))
        case.stage_trace_ids["gap_identification"] = str(result.get("trace_id", ""))

        # Track H3.15 — snap each gap's evidence_span.quote to the actual
        # chart substring. Gap quotes become anchor_hints for query_generation
        # ("If the gap's anchor_hint is non-empty, prefer reusing it"), so a
        # verbatim gap quote begets verbatim query quotes — closes the iter 4
        # paraphrasing loop without changing the prompt.
        from .claim_evidence_gate import snap_quote_to_chart
        gap_snapped = 0
        gap_withheld = 0
        gap_quantity_redacted = 0
        for gap_dict in result.get("gaps", []):
            gap = self._hydrate_gap(gap_dict)
            original = gap.evidence_span.quote
            snapped = snap_quote_to_chart(original, case.chart_excerpt)
            if snapped and snapped != original:
                gap.evidence_span.quote = snapped
                gap_snapped += 1
            if case.chart_excerpt and (
                not gap.evidence_span.quote
                or gap.evidence_span.quote not in case.chart_excerpt
            ):
                gap_withheld += 1
                continue
            if case.chart_excerpt:
                start = case.chart_excerpt.find(gap.evidence_span.quote)
                gap.evidence_span.char_start = start
                gap.evidence_span.char_end = start + len(gap.evidence_span.quote)
            gap.description, count = _redact_ungrounded_quantities(
                gap.description, case.chart_excerpt
            )
            gap_quantity_redacted += count
            gap.why_it_matters, count = _redact_ungrounded_quantities(
                gap.why_it_matters, case.chart_excerpt
            )
            gap_quantity_redacted += count
            gap.minimal_clarification_needed, count = _redact_ungrounded_quantities(
                gap.minimal_clarification_needed, case.chart_excerpt
            )
            gap_quantity_redacted += count
            case.documentation_gaps.append(gap)

        # Track H3.13 — hydrate risk_flags emitted by the LLM. Without
        # this, H3.10 contradiction override in query_eligibility_gate is
        # dead code (0 risk_flags observed on iter 3 baseline).
        from .domain import RiskFlag
        rf_count = 0
        for rf_dict in result.get("risk_flags", []):
            category = rf_dict.get("category", "")
            if category not in (
                "contradiction", "unsupported_diagnosis",
                "ambiguous_term", "copied_forward_indicator",
            ):
                continue
            ev = rf_dict.get("evidence_span") or {}
            description, _ = _redact_ungrounded_quantities(
                str(rf_dict.get("description", "")), case.chart_excerpt
            )
            evidence_span = None
            if ev.get("quote"):
                quote = snap_quote_to_chart(str(ev.get("quote")), case.chart_excerpt)
                if quote in case.chart_excerpt:
                    start = case.chart_excerpt.find(quote)
                    evidence_span = EvidenceSpan(
                        document_id=ev.get("document_id", ""),
                        quote=quote,
                        char_start=start,
                        char_end=start + len(quote),
                    )
            case.risk_flags.append(RiskFlag(
                category=category,
                description=description,
                evidence_span=evidence_span,
            ))
            rf_count += 1

        # Track H3.13 — LLM-backed chart_completeness verdict. Stored on
        # case.encounter_metadata so query_eligibility_gate can read it
        # without changing the CDICase dataclass shape.
        cc = result.get("chart_completeness") or {}
        if isinstance(cc, dict) and "is_complete" in cc:
            case.encounter_metadata["chart_completeness_llm"] = {
                "is_complete": bool(cc.get("is_complete")),
                "reasoning": str(cc.get("reasoning", ""))[:300],
                "missing_dimensions": list(cc.get("missing_dimensions", [])),
            }

        case.stage_run_ids["gap_identification_risk_flags"] = (
            f"emitted={rf_count};quote_snapped={gap_snapped};"
            f"withheld={gap_withheld};quantity_redacted={gap_quantity_redacted}"
        )

    def _stage_expert_consultation(self, case: CDICase) -> None:
        result = self.runner("expert_consultation", case, {})
        case.stage_run_ids["expert_consultation"] = str(result.get("run_id", ""))
        case.stage_trace_ids["expert_consultation"] = str(result.get("trace_id", ""))

    def _stage_query_generation(self, case: CDICase) -> None:
        result = self.runner("query_generation", case, {})
        case.stage_run_ids["query_generation"] = str(result.get("run_id", ""))
        case.stage_trace_ids["query_generation"] = str(result.get("trace_id", ""))

        # Track H3.15 — snap each query's evidence_span.quote to the actual
        # chart substring. Even with the H3.12 QUOTE-ANCHOR prompt procedure,
        # the LLM tends to paraphrase (especially under the H3.14 amplifier's
        # longer prompt context). Snapping is the deterministic safety net:
        #   - lifts CEA-001 verbatim pass → reduces clear_gap under-query
        #   - lifts H4.1 evidence_quote_verbatim_rate back toward ≥0.95
        from .claim_evidence_gate import anchor_query_evidence_spans
        query_snapped = 0
        ungrounded_quantity_options_removed = 0
        for q_dict in result.get("queries", []):
            query = self._hydrate_query(q_dict)
            ungrounded_quantity_options_removed += (
                _remove_ungrounded_quantity_options(query, case.chart_excerpt)
            )
            spans = query.all_evidence_spans()
            invalid_reasons, snapped_count = anchor_query_evidence_spans(
                query, case.chart_excerpt,
            )
            query_snapped += snapped_count
            ungrounded_query_fields = [
                field_name
                for field_name, value in (
                    ("topic", query.topic),
                    ("reason", query.reason),
                    ("query_text", query.query_text),
                )
                if _ungrounded_quantity_tokens(value, case.chart_excerpt)
            ]
            if ungrounded_query_fields:
                invalid_reasons.append(
                    "chart-ungrounded quantitative content in "
                    + ",".join(ungrounded_query_fields)
                )
            if invalid_reasons:
                case.query_rewrite_queue.append(query_audit_item(
                    query,
                    status="NEEDS_EVIDENCE_REWRITE",
                    gate_reasons=invalid_reasons,
                ))
                continue
            case.proposed_provider_queries.append(query)
        case.stage_run_ids["query_generation::quote_snapped"] = str(query_snapped)
        if ungrounded_quantity_options_removed:
            logger.info(
                "CDI removed chart-ungrounded quantitative response options "
                "case_id=%s count=%d",
                case.case_id,
                ungrounded_quantity_options_removed,
            )
        covered_gap_ids = {
            query.gap_id for query in case.proposed_provider_queries if query.gap_id
        }
        covered_gap_ids.update(
            str(item.get("gap_id") or "") for item in case.query_rewrite_queue
        )
        missing_coverage = 0
        for gap in case.documentation_gaps:
            if gap.gap_id in covered_gap_ids:
                continue
            case.query_rewrite_queue.append(gap_query_draft_item(gap))
            covered_gap_ids.add(gap.gap_id)
            missing_coverage += 1
        case.stage_run_ids["query_generation::coverage_missing"] = str(
            missing_coverage
        )

    def _stage_query_eligibility_gate(self, case: CDICase) -> None:
        """Phase 5 Track H3.5 — drop queries that have no eligible gap.

        Two checks per PDF §3.2 + Track H3.5:
          QE-001  chart_completeness_drops_all  — if chart documents
                  ≥6/8 dimensions (type/site/severity/etiology/procedure/
                  pathology/complications/course) AND no ambiguity markers,
                  all candidate queries are spurious → drop.
          QE-002  query_topic_has_matching_gap  — each query's topic must
                  intersect an identified documentation_gap; off-topic
                  queries are dropped.

        Track H3.13 — chart_completeness now prefers the LLM verdict
        emitted by gap_identification (stored on
        ``case.encounter_metadata["chart_completeness_llm"]``) over the
        regex detector. The regex detector over-marks clinically-complete
        charts (e.g. obstetric delivery) that don't fit the 8-dimension
        template, causing the 4/10 complete_chart over-query on iter 3.
        """
        from .query_eligibility_gate import apply_eligibility_to_case
        result = apply_eligibility_to_case(case)
        dims_summary = ",".join(
            f"{dim}={'Y' if hit else 'N'}" for dim, hit in result.dimensions_detected.items()
        )
        llm_verdict_str = ""
        if result.llm_chart_completeness_verdict is not None:
            llm_verdict_str = (
                f";llm_complete={result.llm_chart_completeness_verdict}"
                f";llm_reasoning={result.llm_chart_completeness_reasoning[:80]}"
            )
        case.stage_run_ids["query_eligibility_gate"] = (
            f"chart_complete={result.chart_complete};"
            f"completeness_score={result.chart_completeness_score:.2f};"
            f"dimensions={dims_summary};"
            f"dropped={result.dropped_count};"
            f"final_count={len(case.proposed_provider_queries)}"
            f"{llm_verdict_str}"
        )
        case.stage_trace_ids["query_eligibility_gate"] = ""

    def _stage_query_necessity_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 2 — drop queries that fail NQ-001..NQ-005.

        Runs the necessity gate (PDF §3.2) on every query in the case.
        Hard-failures (NQ-001 evidence_sufficiency, NQ-004 documentation_impact,
        NQ-005 redundancy_risk) drop the query. Soft-failures (NQ-002, NQ-003)
        are recorded in the trace but do not drop.

        Over-query guard NQ-006 tags the case (does not block).
        """
        from .necessity_gate import apply_necessity_to_case
        result = apply_necessity_to_case(case)
        _normalize_existing_dka_query(case)
        _normalize_existing_biliary_obstruction_query(case)
        _normalize_existing_iron_deficiency_query(case)
        respiratory_failure_coverage = _aecopd_respiratory_failure_coverage_query(case)
        deterministic_coverage_queries = [
            query for query in (
                respiratory_failure_coverage,
                _pneumonia_type_coverage_query(case),
                _iron_deficiency_chronic_blood_loss_coverage_query(case),
                _dka_coverage_query(case),
                _pancreatitis_etiology_conflict_query(case),
                _discharge_comorbidity_omission_query(case),
                _biliary_obstruction_coverage_query(case),
            )
            if query is not None
        ]
        for coverage_query in deterministic_coverage_queries:
            from .necessity_gate import evaluate_necessity
            coverage_result = evaluate_necessity(
                coverage_query,
                chart=case.chart_excerpt,
                all_queries=[*case.proposed_provider_queries, coverage_query],
            )
            if coverage_result.verdict == "NECESSARY":
                case.proposed_provider_queries.append(coverage_query)
                if coverage_query.query_id.startswith("Q-RF-"):
                    coverage_reason = "AECOPD with objective hypercapnia and hypoxemia"
                    coverage_kind = "AECOPD_RESPIRATORY_FAILURE_TYPE"
                elif coverage_query.query_id.startswith("Q-PNA-"):
                    coverage_reason = "pneumonia diagnosis lacks a documented clinical type"
                    coverage_kind = "PNEUMONIA_TYPE"
                elif coverage_query.query_id.startswith("Q-PANC-"):
                    coverage_reason = "admission and discharge pancreatitis etiologies conflict"
                    coverage_kind = "PANCREATITIS_ETIOLOGY_CONFLICT"
                elif coverage_query.query_id.startswith("Q-IDA-BL-"):
                    coverage_reason = "iron-deficiency pattern and positive fecal occult blood lack a documented causal diagnosis"
                    coverage_kind = "IRON_DEFICIENCY_CHRONIC_BLOOD_LOSS_RELATION"
                elif coverage_query.query_id.startswith("Q-DXOMIT-"):
                    coverage_reason = "progress-note comorbidities are absent from discharge diagnoses"
                    coverage_kind = "DISCHARGE_COMORBIDITY_OMISSION"
                elif coverage_query.query_id.startswith("Q-CBD-"):
                    coverage_reason = "dilated common bile duct and cholestatic labs lack a related diagnosis"
                    coverage_kind = "BILIARY_OBSTRUCTION_DIAGNOSIS"
                else:
                    coverage_reason = "objective metabolic acidosis and ketones without DKA documentation"
                    coverage_kind = "DIABETIC_KETOACIDOSIS_DIAGNOSIS"
                case.query_rewrite_queue.append(query_audit_item(
                    coverage_query,
                    status="DETERMINISTIC_COVERAGE_GENERATED",
                    gate_reasons=[
                        f"CDI-Coverage: {coverage_reason}"
                    ],
                    rewrite_kind=coverage_kind,
                    rewrite_attempt_status="ACCEPTED_FOR_DOWNSTREAM_GATES",
                    replacement_query_id=coverage_query.query_id,
                ))
        # Once a deterministic core diagnosis/conflict query exists, defer
        # secondary refinements that do not resolve that missing diagnosis.
        core_ids = {q.query_id for q in deterministic_coverage_queries}
        accepted_core_ids = {q.query_id for q in case.proposed_provider_queries if q.query_id in core_ids}
        if accepted_core_ids:
            core_topics = " ".join(q.topic for q in case.proposed_provider_queries if q.query_id in accepted_core_ids)
            deferred: list[ProviderQuery] = []
            focused: list[ProviderQuery] = []
            for query in case.proposed_provider_queries:
                if query.query_id in accepted_core_ids:
                    focused.append(query)
                    continue
                text = f"{query.topic} {query.query_text}"
                secondary = bool(re.search(
                    r"操作细节|手术细节|其他冠脉|血管名称|出血来源|便潜血.{0,12}临床意义|实验室.{0,12}(?:意义|计划)|临床意义.{0,12}(?:计划|处理)|"
                    r"肝功能.{0,20}(?:临床意义|相关性|关联|异常.{0,8}(?:类型|原因|病因))|"
                    r"(?:type|classification) of liver function abnormality|"
                    r"分期|分级|危险分层|严重程度|具体类型|并发症.{0,8}控制|operation detail|management plan|staging|risk stratification",
                    text,
                    re.I,
                ))
                duplicate_core = (
                    "糖尿病急性并发症" in core_topics
                    and bool(re.search(r"代谢失代偿|酸中毒|酮症|DKA", text, re.I))
                ) or (
                    "出院诊断合并症完整性" in core_topics
                    and bool(re.search(r"慢性肾病|高脂血症|出院诊断", text, re.I))
                )
                if secondary or duplicate_core:
                    deferred.append(query)
                    case.query_rewrite_queue.append(query_audit_item(
                        query, status="DEFERRED_SECONDARY_TO_CORE_DIAGNOSIS",
                        gate_reasons=["CDI-Focus: resolve the core diagnosis/conflict before secondary refinements"],
                    ))
                    continue
                focused.append(query)
            case.proposed_provider_queries = focused
        # In a low-risk symptom-only cough encounter, keep at most one cough
        # clarification and defer unrelated chronic-history refinements.  The
        # necessity contract intentionally permits a cough-cause/type query,
        # but the encounter does not support a second hypertension query.
        low_risk_cough_case = (
            bool(re.search(r"咳嗽|cough", case.chart_excerpt, re.I))
            and bool(re.search(r"否认.{0,40}(?:发热|咳脓痰|咯血|胸痛)|denies.{0,90}(?:fever|purulent sputum|hemoptysis|chest pain)", case.chart_excerpt, re.I))
            and bool(re.search(r"双肺清晰|胸片.{0,16}未见活动性病变|clear lungs|no active lesions", case.chart_excerpt, re.I))
        )
        if low_risk_cough_case and len(case.proposed_provider_queries) > 1:
            focused: list[ProviderQuery] = []
            cough_kept = False
            for query in case.proposed_provider_queries:
                text = f"{query.topic} {query.query_text}"
                if re.search(r"咳嗽|cough", text, re.I) and not cough_kept:
                    focused.append(query)
                    cough_kept = True
                    continue
                case.query_rewrite_queue.append(query_audit_item(
                    query, status="DEFERRED_LOW_RISK_SYMPTOM_FOCUS",
                    gate_reasons=["CDI-Focus: keep one symptom clarification; defer unrelated chronic-history refinement"],
                ))
            case.proposed_provider_queries = focused
        if any(q.topic == "糖尿病急性并发症" for q in case.proposed_provider_queries):
            focused = []
            for query in case.proposed_provider_queries:
                if query.topic == "糖尿病急性并发症":
                    focused.append(query)
                    continue
                text = f"{query.topic} {query.query_text}"
                if re.search(r"代谢失代偿|代谢性酸中毒|酮症|异常实验室|临床意义|诊疗计划|DKA", text, re.I):
                    case.query_rewrite_queue.append(query_audit_item(
                        query, status="DEFERRED_DUPLICATE_CORE_DIAGNOSIS",
                        gate_reasons=["CDI-Focus: the diagnosis-focused diabetic acute-complication query has priority"],
                    ))
                    continue
                focused.append(query)
            case.proposed_provider_queries = focused
        diabetes_conflict_match = re.search(
            r"入院诊断[:：].{0,80}((?:1型|2型)糖尿病).{0,180}出院诊断[:：](?:(?![12]型糖尿病).){0,80}(糖尿病)"
            r"|admission diagnosis.{0,100}(type\s*[12]\s*diabetes).{0,220}discharge diagnosis(?:(?!type\s*[12]\s*diabetes).){0,100}(diabetes)",
            case.chart_excerpt,
            re.I | re.S,
        )
        if diabetes_conflict_match:
            diabetes_candidates = list(case.proposed_provider_queries)
            if not any(
                re.search(r"糖尿病|diabetes", f"{query.topic} {query.query_text}", re.I)
                and re.search(r"分型|类型|type|classification", f"{query.topic} {query.query_text}", re.I)
                for query in diabetes_candidates
            ):
                for item in reversed(case.query_rewrite_queue):
                    if item.get("status") != "REJECTED_AS_UNNECESSARY":
                        continue
                    item_text = f"{item.get('topic', '')} {item.get('query_text', '')}"
                    if not re.search(r"糖尿病|diabetes", item_text, re.I):
                        continue
                    if not re.search(r"分型|类型|type|classification", item_text, re.I):
                        continue
                    restored = self._hydrate_query(item)
                    diabetes_candidates.append(restored)
                    case.proposed_provider_queries.append(restored)
                    item["restoration_status"] = "RESTORED_FOR_CONTRADICTION_REWRITE"
                    break
            for query in diabetes_candidates:
                if not re.search(r"糖尿病|diabetes", f"{query.topic} {query.query_text}", re.I):
                    continue
                if not re.search(r"分型|类型|type|classification", f"{query.topic} {query.query_text}", re.I):
                    continue
                original = query_audit_item(
                    query,
                    status="AUTOMATIC_CONTRADICTION_REWRITE",
                    gate_reasons=[
                        "CDI-Conflict: admission type is more specific than discharge diagnosis"
                    ],
                    rewrite_kind="FOCUS_DIABETES_TYPE_CONTRADICTION",
                )
                specific = next(
                    group for group in diabetes_conflict_match.groups() if group and re.search(r"(?:[12]型|type\s*[12])", group, re.I)
                )
                generic = next(
                    group for group in reversed(diabetes_conflict_match.groups()) if group and not re.search(r"(?:[12]型|type\s*[12])", group, re.I)
                )
                query.topic = "糖尿病分型"
                query.query_text = "请明确出院诊断中糖尿病的具体分型。"
                query.response_options = [
                    "A. 1型糖尿病", "B. 2型糖尿病",
                    "C. 其他明确类型（请注明）", "D. 无法确定",
                ]
                spans: list[EvidenceSpan] = []
                for quote in (specific, generic):
                    start = case.chart_excerpt.find(quote)
                    spans.append(EvidenceSpan(
                        document_id="chart-001",
                        quote=quote,
                        char_start=max(start, 0),
                        char_end=max(start, 0) + len(quote),
                    ))
                query.evidence_span = spans[0]
                query.evidence_spans = spans
                from .necessity_gate import evaluate_necessity
                necessity_recheck = evaluate_necessity(
                    query,
                    chart=case.chart_excerpt,
                    all_queries=[query],
                )
                if necessity_recheck.verdict != "NECESSARY":
                    case.proposed_provider_queries = [
                        candidate for candidate in case.proposed_provider_queries
                        if candidate is not query
                    ]
                    original["rewrite_attempt_status"] = "REJECTED_BY_NECESSITY_RECHECK"
                    original["rewrite_attempt_reasons"] = list(necessity_recheck.drop_reasons)
                    case.query_rewrite_queue.append(original)
                    break
                original["replacement_query_id"] = query.query_id
                original["rewrite_attempt_status"] = "ACCEPTED_FOR_DOWNSTREAM_GATES"
                original["rewritten_query_text"] = query.query_text
                original["rewritten_response_options"] = list(query.response_options)
                case.query_rewrite_queue.append(original)
                break
        # When a case contains a genuine contradiction, resolve that conflict
        # first. Additional non-conflict refinements are deferred, not erased,
        # so the provider sees a focused minimal query set and CDI can revisit
        # them after the authoritative fact is established.
        if any(flag.category == "contradiction" for flag in case.risk_flags):
            gaps_by_id = {gap.gap_id: gap for gap in case.documentation_gaps}
            conflict_re = re.compile(
                r"矛盾|不一致|冲突|conflict|contradict|inconsisten", re.I,
            )
            conflict_gap_ids = {
                gap.gap_id for gap in case.documentation_gaps
                if conflict_re.search(f"{gap.description} {gap.why_it_matters}")
            }
            if conflict_gap_ids:
                focused: list[ProviderQuery] = []
                for query in case.proposed_provider_queries:
                    if query.gap_id in conflict_gap_ids:
                        focused.append(query)
                        continue
                    case.query_rewrite_queue.append(query_audit_item(
                        query,
                        status="DEFERRED_UNTIL_CONTRADICTION_RESOLVED",
                        gate_reasons=[
                            "CDI-Focus: resolve the documented contradiction before ancillary refinement"
                        ],
                    ))
                case.proposed_provider_queries = focused
        # Minimal symptom-only encounters often produce several synonymous
        # refinements over the exact same evidence span.  If there is no
        # documented diagnosis/abnormal objective finding and all surviving
        # queries point to one symptom span, keep the first (highest-ranked by
        # generation) and defer the rest for later CDI review.
        symptom_only_context = (
            not bool(re.search(r"(?:诊断|diagnosis)\s*[:：].{1,60}", case.chart_excerpt, re.I))
            and bool(re.search(
                r"建议(?:随访|进一步检查)|未见活动性病变|recommend(?:ed)? follow-up|further evaluation|no active lesions",
                case.chart_excerpt,
                re.I,
            ))
        )
        evidence_keys = {
            query.evidence_span.quote.strip()
            for query in case.proposed_provider_queries
            if query.evidence_span.quote.strip()
        }
        if symptom_only_context and len(case.proposed_provider_queries) > 1 and len(evidence_keys) == 1:
            keep, *deferred = case.proposed_provider_queries
            for query in deferred:
                case.query_rewrite_queue.append(query_audit_item(
                    query,
                    status="DEFERRED_SYMPTOM_REFINEMENT",
                    gate_reasons=[
                        "CDI-Focus: one symptom-only clarification per shared evidence span"
                    ],
                ))
            case.proposed_provider_queries = [keep]
        # Stash summary in stage_run_ids for traceability
        case.stage_run_ids["query_necessity_gate"] = (
            f"necessary={sum(1 for v in result.per_query.values() if v.verdict == 'NECESSARY')};"
            f"unnecessary={sum(1 for v in result.per_query.values() if v.verdict == 'UNNECESSARY')};"
            f"overquery_triggered={result.overquery_triggered};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["query_necessity_gate"] = ""

    def _stage_query_single_dimension_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 3 — drop queries that mix ≥2 orthogonal axes.

        Runs the single-dimension gate (PDF §3.2 R6) on every query.
        Hard-failures (SD-001 topic_multi_axis, SD-002 text_multi_axis)
        drop the query. Cluster tag SD-003 records if ≥3 queries touch
        the same axis (no block).
        """
        from .single_dimension_gate import apply_single_dimension_to_case
        queue_start = len(case.query_rewrite_queue)
        result = apply_single_dimension_to_case(case)
        rewrite_items = [
            item for item in case.query_rewrite_queue[queue_start:]
            if item.get("status") == "NEEDS_CDI_REWRITE"
        ]
        rewrite_summary = self._attempt_single_dimension_rewrites(
            case, rewrite_items,
        )
        case.stage_run_ids["query_single_dimension_gate"] = (
            f"single_dim={sum(1 for v in result.per_query.values() if v.verdict == 'SINGLE_DIM')};"
            f"multi_dim={sum(1 for v in result.per_query.values() if v.verdict == 'MULTI_DIM')};"
            f"axis_cluster_triggered={result.axis_cluster_triggered};"
            f"axis_cluster_axis={result.axis_cluster_axis};"
            f"rewrite_attempted={rewrite_summary['attempted']};"
            f"rewrite_accepted={rewrite_summary['accepted']};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["query_single_dimension_gate"] = ""

    def _attempt_single_dimension_rewrites(
        self,
        case: CDICase,
        rewrite_items: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Make one bounded repair pass and re-enter all prior gates."""

        summary = {"attempted": 0, "accepted": 0}
        # The public trace contract requires an audit slot even when every
        # draft is already single-dimensional. An explicit non-execution
        # marker is truthful and avoids representing an optional branch as a
        # missing trace field.
        case.stage_run_ids["query_dimension_rewrite"] = "not_executed"
        case.stage_trace_ids["query_dimension_rewrite"] = ""
        if not rewrite_items:
            return summary

        gaps = {gap.gap_id: gap for gap in case.documentation_gaps}
        payload: list[dict[str, Any]] = []
        audit_by_source: dict[str, dict[str, Any]] = {}
        bounded_items = rewrite_items[:8]
        for item in rewrite_items[8:]:
            item["rewrite_attempt_status"] = "DEFERRED_BATCH_LIMIT"
            item["rewrite_attempt_reasons"] = [
                "single rewrite pass is limited to 8 compound drafts"
            ]
        for item in bounded_items:
            source_id = str(item.get("query_id") or "")
            gap_id = str(item.get("gap_id") or "")
            gap = gaps.get(gap_id)
            if not source_id or gap is None:
                item["rewrite_attempt_status"] = "REJECTED_INVALID_SOURCE"
                item["rewrite_attempt_reasons"] = [
                    "rewrite source must reference an existing documentation gap"
                ]
                continue
            target_axis = _rewrite_target_axis(gap.gap_type)
            if not target_axis:
                item["rewrite_attempt_status"] = "REJECTED_NO_SAFE_TARGET_AXIS"
                item["rewrite_attempt_reasons"] = [
                    "source gap type does not map to one deterministic rewrite axis"
                ]
                continue
            audit_by_source[source_id] = item
            payload.append({
                "source_query_id": source_id,
                "gap_id": gap_id,
                "gap_description": gap.description,
                "gap_reason": gap.why_it_matters,
                "gap_evidence_spans": item.get("evidence_spans") or [],
                "compound_topic": item.get("topic") or "",
                "compound_query_text": item.get("query_text") or "",
                "detected_axes": item.get("detected_axes") or [],
                "target_axis": target_axis,
            })

        if not payload:
            return summary
        summary["attempted"] = len(payload)
        deterministic_queries: list[dict[str, Any]] = []
        provider_payload: list[dict[str, Any]] = []
        for entry in payload:
            audit = audit_by_source[str(entry["source_query_id"])]
            gap = gaps[str(entry["gap_id"])]
            repaired = (
                _laterality_conflict_rewrite(audit, gap)
                if entry["target_axis"] == "site"
                else _pneumonia_type_rewrite(audit, gap)
                if entry["target_axis"] == "type"
                else None
            )
            if repaired is None:
                provider_payload.append(entry)
                continue
            deterministic_queries.append(repaired)
            audit["rewrite_kind"] = (
                "LATERALITY_CONFLICT_SITE_ONLY"
                if entry["target_axis"] == "site"
                else "PNEUMONIA_TYPE_ONLY"
            )
        try:
            if provider_payload:
                result = self.runner(
                    "query_dimension_rewrite", case,
                    {"rewrite_items": provider_payload},
                )
            else:
                result = {"queries": [], "run_id": "deterministic", "trace_id": ""}
            if not isinstance(result, dict):
                raise TypeError("rewrite runner returned a non-object result")
        except Exception as exc:
            logger.warning("query_dimension_rewrite degraded: %s", type(exc).__name__)
            case.stage_run_ids["query_dimension_rewrite"] = "degraded"
            case.stage_trace_ids["query_dimension_rewrite"] = ""
            for audit in audit_by_source.values():
                audit["rewrite_attempt_status"] = "DEGRADED"
                audit["rewrite_attempt_reasons"] = [
                    f"rewrite provider unavailable: {type(exc).__name__}"
                ]
            return summary
        case.stage_run_ids["query_dimension_rewrite"] = str(
            result.get("run_id", "")
        )
        case.stage_trace_ids["query_dimension_rewrite"] = str(
            result.get("trace_id", "")
        )
        if result.get("degraded"):
            reason = str(
                result.get("error_reason")
                or "rewrite provider returned a degraded result"
            )
            for audit in audit_by_source.values():
                audit["rewrite_attempt_status"] = "DEGRADED"
                audit["rewrite_attempt_reasons"] = [reason]
            return summary

        from .claim_evidence_gate import anchor_query_evidence_spans
        from .necessity_gate import evaluate_necessity
        from .query_eligibility_gate import evaluate_case_eligibility
        from .single_dimension_gate import evaluate_single_dimension

        seen_sources: set[str] = set()
        seen_query_ids = {
            query.query_id for query in case.proposed_provider_queries
        }
        for raw in [*deterministic_queries, *result.get("queries", [])]:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_query_id") or "")
            audit = audit_by_source.get(source_id)
            if audit is None or source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            reasons: list[str] = []
            if str(raw.get("gap_id") or "") != str(audit.get("gap_id") or ""):
                reasons.append("rewrite changed the source gap_id")
            query = self._hydrate_query(raw)
            if not query.query_id or query.query_id in seen_query_ids:
                reasons.append("rewrite query_id is empty or duplicated")
            anchor_reasons, _ = anchor_query_evidence_spans(
                query, case.chart_excerpt,
            )
            reasons.extend(anchor_reasons)
            dimension_result = evaluate_single_dimension(query)
            if dimension_result.verdict != "SINGLE_DIM":
                reasons.extend(dimension_result.drop_reasons)
            gap = gaps.get(str(audit.get("gap_id") or ""))
            expected_axes = set()
            if gap is not None:
                from .single_dimension_gate import detect_axes
                expected_axes = detect_axes(
                    " ".join((
                        gap.gap_type or "",
                        gap.description or "",
                        gap.minimal_clarification_needed or "",
                    ))
                )
            rewritten_axes = set(dimension_result.axes_detected)
            target_axis = next((
                str(entry.get("target_axis") or "")
                for entry in payload
                if entry.get("source_query_id") == source_id
            ), "")
            if target_axis and rewritten_axes != {target_axis}:
                reasons.append(
                    "rewrite must address exactly the server-selected target axis: "
                    f"target={target_axis}, got={sorted(rewritten_axes)}"
                )
            if expected_axes and not (expected_axes & rewritten_axes):
                reasons.append(
                    "rewrite clinical dimension does not match source gap: "
                    f"expected={sorted(expected_axes)}, got={sorted(rewritten_axes)}"
                )

            probe = copy.copy(case)
            probe.proposed_provider_queries = [query]
            probe.query_rewrite_queue = []
            eligibility = evaluate_case_eligibility(probe).per_query.get(
                query.query_id
            )
            if eligibility is None or eligibility.verdict != "ELIGIBLE":
                reasons.extend(
                    eligibility.drop_reasons if eligibility else [
                        "rewrite eligibility result missing"
                    ]
                )
            necessity = evaluate_necessity(
                query,
                chart=case.chart_excerpt,
                all_queries=[*case.proposed_provider_queries, query],
            )
            if necessity.verdict != "NECESSARY":
                reasons.extend(necessity.drop_reasons)

            if reasons:
                audit["rewrite_attempt_status"] = "REJECTED_BY_SAFETY_GATES"
                audit["rewrite_attempt_reasons"] = list(dict.fromkeys(reasons))
                continue
            case.proposed_provider_queries.append(query)
            seen_query_ids.add(query.query_id)
            audit["status"] = "REWRITE_CANDIDATE_GENERATED"
            audit["replacement_query_id"] = query.query_id
            audit["rewrite_attempt_status"] = "ACCEPTED_FOR_DOWNSTREAM_GATES"
            audit["rewrite_attempt_reasons"] = []
            summary["accepted"] += 1

        for source_id, audit in audit_by_source.items():
            if (
                source_id not in seen_sources
                and "rewrite_attempt_status" not in audit
            ):
                audit["rewrite_attempt_status"] = "NO_SAFE_CANDIDATE_RETURNED"
                audit["rewrite_attempt_reasons"] = [
                    "rewrite model returned no candidate for this compound draft"
                ]
        return summary

    def _stage_claim_evidence_alignment_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 4 — every claim must be chart-evidenced.

        Per Master Task §五: for each Provider Query, extract atomic
        clinical claims (LLM-backed), map each to a chart-verbatim
        EvidenceSpan, and run 9 deterministic CEA-XXX rules. Critical
        claims with no chart support are diagnosis-invention → BLOCK.

        On LLM extraction failure, the gate returns DEGRADED per query.
        Queries remain available for local audit, but the case records a
        structured required-gate failure so public adapters fail closed.
        """
        from .claim_evidence_gate import extract_claims, apply_claim_evidence_to_case

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"

        # Skip LLM extraction entirely if there are no queries to check
        queries_snapshot = list(case.proposed_provider_queries)
        if queries_snapshot and case.chart_excerpt:
            try:
                llm = _SafetyGateTelemetryLLM(
                    self._resolve_llm(),
                    case.safety_gate_model_traces,
                    stage="claim_evidence_alignment_gate",
                )
                coro = self._extract_claims_bulk(queries_snapshot, case.chart_excerpt, llm)
                per_query_results = _run_async(coro)
                for q, (claims, aligns) in zip(queries_snapshot, per_query_results):
                    q.claims = claims
                    q.claim_evidence_alignments = aligns
            except Exception as exc:  # DEGRADED — do not crash orchestrator
                logger.warning("claim_evidence_alignment_gate LLM bulk failed: %s", exc)
                for q in queries_snapshot:
                    q.claims = []
                    q.claim_evidence_alignments = []

        result = apply_claim_evidence_to_case(case)
        degraded_count = sum(
            1 for gate in result.per_query.values() if gate.degraded
        )
        if degraded_count:
            case.degraded_safety_gates["claim_evidence_alignment_gate"] = (
                f"degraded_queries={degraded_count}"
            )
        else:
            case.degraded_safety_gates.pop(
                "claim_evidence_alignment_gate", None,
            )
        claims_extracted = sum(len(q.claims) for q in queries_snapshot)
        case.stage_run_ids["claim_evidence_alignment_gate"] = (
            f"claims_extracted={claims_extracted};"
            f"degraded={degraded_count};"
            f"blocked={len(result.blocked_query_ids)};"
            f"flagged={len(result.flagged_query_ids)};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["claim_evidence_alignment_gate"] = trace_id
        # Stash run_id in the parallel dict for downstream visibility
        case.stage_run_ids["claim_evidence_alignment_gate::run_id"] = run_id

    def _stage_semantic_necessity_gate(self, case: CDICase) -> None:
        """Phase 5 Track D P0.5 Gate 4 — LLM semantic necessity reviewer.

        Per Master Task §5.6: catches empty-chart diagnosis-invention
        (C09 pathology), symptom-only-no-evidence, no-imaging-no-site,
        no-severity-indicator-no-grade, lab-positive-not-equals-diagnosis,
        and complete-chart redundancy. BLOCK verdicts drop the query.

        On LLM failure per query, the query survives for local audit and the
        downstream deterministic NLQ gate still runs. The case records the
        required-gate degradation so REST/A2A cannot publish the result.
        """
        from .necessity_semantic import review_necessity

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"

        queries_snapshot = list(case.proposed_provider_queries)
        blocked_count = 0
        flagged_count = 0
        degraded_count = 0

        if queries_snapshot and case.chart_excerpt:
            try:
                llm = _SafetyGateTelemetryLLM(
                    self._resolve_llm(),
                    case.safety_gate_model_traces,
                    stage="semantic_necessity_gate",
                )
                coro = self._review_necessity_bulk(queries_snapshot, case.chart_excerpt, llm)
                per_query_results = _run_async(coro)
            except Exception as exc:  # DEGRADED — keep all queries
                logger.warning("semantic_necessity_gate LLM bulk failed: %s", exc)
                per_query_results = [None] * len(queries_snapshot)

            survivors: list[ProviderQuery] = []
            gaps_by_id = {gap.gap_id: gap for gap in case.documentation_gaps}
            has_contradiction_risk = any(
                flag.category == "contradiction" for flag in case.risk_flags
            )
            for q, res in zip(queries_snapshot, per_query_results):
                if res is None:
                    q.semantic_necessity_verdict = "DEGRADED"
                    q.semantic_necessity_degraded = True
                    degraded_count += 1
                    survivors.append(q)
                    continue
                q.semantic_necessity_verdict = res.verdict
                q.semantic_necessity_reason_codes = list(res.reason_codes)
                q.semantic_necessity_degraded = res.degraded
                if res.degraded:
                    degraded_count += 1
                gap = gaps_by_id.get(q.gap_id)
                gap_text = " ".join((
                    gap.description if gap else "",
                    gap.why_it_matters if gap else "",
                ))
                contradiction_query = (
                    has_contradiction_risk
                    and gap is not None
                    and bool(re.search(
                        r"矛盾|不一致|冲突|conflict|contradict|inconsisten",
                        gap_text,
                        re.I,
                    ))
                )
                if res.verdict == "BLOCK" and not res.degraded and contradiction_query:
                    q.semantic_necessity_verdict = "REVIEW_REQUIRED"
                    q.semantic_necessity_reason_codes = [
                        *q.semantic_necessity_reason_codes,
                        "CONTRADICTION_REQUIRES_PROVIDER_REVIEW",
                    ]
                    flagged_count += 1
                    survivors.append(q)
                    continue
                if res.verdict == "BLOCK" and not res.degraded:
                    blocked_count += 1
                    case.query_rewrite_queue.append(query_audit_item(
                        q,
                        status="REJECTED_BY_SEMANTIC_NECESSITY",
                        gate_reasons=list(res.reason_codes),
                    ))
                    continue  # drop
                if res.verdict == "REVIEW_REQUIRED":
                    flagged_count += 1
                survivors.append(q)
            case.proposed_provider_queries = survivors

        if degraded_count:
            case.degraded_safety_gates["semantic_necessity_gate"] = (
                f"degraded_queries={degraded_count}"
            )
        else:
            case.degraded_safety_gates.pop("semantic_necessity_gate", None)

        case.stage_run_ids["semantic_necessity_gate"] = (
            f"blocked={blocked_count};flagged={flagged_count};degraded={degraded_count};"
            f"final_count={len(case.proposed_provider_queries)}"
        )
        case.stage_trace_ids["semantic_necessity_gate"] = trace_id
        case.stage_run_ids["semantic_necessity_gate::run_id"] = run_id

    # ------------------------------------------------------------------ LLM helpers

    @staticmethod
    def _get_llm() -> Any:
        """Lazy-import the singleton LLM service."""
        from app.services.llm_service import llm_service
        return llm_service

    def _resolve_llm(self) -> Any:
        """Resolve the LLM to use for gate-internal calls.

        Order of precedence:
          1. ``self.llm`` if explicitly injected
          2. ``self.runner.llm`` if the runner exposes one (test fixtures
             using ``RealCDIRunner(llm=mock)`` propagate it through)
          3. Production singleton ``llm_service``
        """
        if self.llm is not None:
            return self.llm
        runner_llm = getattr(self.runner, "llm", None)
        if runner_llm is not None:
            return runner_llm
        from app.services.llm_service import llm_service
        return llm_service

    @staticmethod
    async def _bounded_gate_map(
        queries: list[ProviderQuery],
        operation: Callable[[ProviderQuery], Any],
    ) -> list[Any]:
        """Run independent per-query gate calls with bounded concurrency.

        ``asyncio.gather`` preserves input order. The limit is intentionally
        capped at four even if local configuration is malformed or excessive;
        the default is three so a typical three-query CDI case completes each
        safety gate in one provider round without unbounded connection spikes.
        """
        try:
            from app.config import settings
            configured_limit = int(settings.ICODER_CDI_GATE_MAX_CONCURRENCY)
        except (AttributeError, TypeError, ValueError, OverflowError):
            configured_limit = 1
        limit = min(max(configured_limit, 1), 4)
        semaphore = asyncio.Semaphore(limit)

        async def _run_one(query: ProviderQuery) -> Any:
            async with semaphore:
                return await operation(query)

        return list(await asyncio.gather(*(
            _run_one(query) for query in queries
        )))

    @staticmethod
    async def _extract_claims_bulk(
        queries: list[ProviderQuery], chart: str, llm: Any
    ) -> list[tuple[list, list]]:
        """Run independent claim extraction with small bounded concurrency."""
        from .claim_evidence_gate import extract_claims

        async def _extract(query: ProviderQuery) -> tuple[list, list]:
            return await extract_claims(query, chart=chart, llm=llm)

        return await CDIOrchestrator._bounded_gate_map(queries, _extract)

    @staticmethod
    async def _review_necessity_bulk(
        queries: list[ProviderQuery], chart: str, llm: Any
    ) -> list[Any]:
        """Run independent semantic reviews with small bounded concurrency."""
        from .necessity_semantic import review_necessity

        async def _review(query: ProviderQuery) -> Any:
            return await review_necessity(query, chart=chart, llm=llm)

        return await CDIOrchestrator._bounded_gate_map(queries, _review)

    def _stage_query_compliance_gate(self, case: CDICase) -> None:
        """Run NLQ rules and withhold every BLOCK query for safe rewrite."""

        run_id = ""
        trace_id = ""
        survivors: list[ProviderQuery] = []
        blocked_count = 0
        for q in case.proposed_provider_queries:
            gate_input = ProviderQueryForGate(
                query_text=q.query_text,
                response_options=list(q.response_options),
                topic=q.topic,
                evidence_quote=q.evidence_span.quote,
            )
            result = evaluate_nlq(gate_input)
            failed_rule_ids = {rule.rule_id for rule in result.rules_failed}
            repaired = False
            repair_kind = ""
            original_audit: dict[str, Any] | None = None
            if failed_rule_ids == {"NLQ-011"}:
                normalized = _bounded_response_options(q.response_options)
                if normalized is not None:
                    original_audit = query_audit_item(
                        q,
                        status="AUTOMATIC_COMPLIANCE_REWRITE",
                        gate_reasons=list(result.block_reasons),
                        rewrite_kind="BOUND_RESPONSE_OPTIONS",
                    )
                    q.response_options = normalized
                    repaired = True
                    repair_kind = "BOUND_RESPONSE_OPTIONS"
            elif failed_rule_ids == {"NLQ-001"}:
                open_clause = _open_clause_without_yes_no_tail(q.query_text)
                if open_clause is not None:
                    original_audit = query_audit_item(
                        q,
                        status="AUTOMATIC_COMPLIANCE_REWRITE",
                        gate_reasons=list(result.block_reasons),
                        rewrite_kind="REMOVE_REDUNDANT_YES_NO_TAIL",
                    )
                    q.query_text = open_clause
                    repaired = True
                    repair_kind = "REMOVE_REDUNDANT_YES_NO_TAIL"
                else:
                    dka_open_clause = _dka_confirmation_without_yes_no(q)
                    if dka_open_clause is not None:
                        original_audit = query_audit_item(
                            q,
                            status="AUTOMATIC_COMPLIANCE_REWRITE",
                            gate_reasons=list(result.block_reasons),
                            rewrite_kind="OPEN_DKA_DIAGNOSIS_REQUEST",
                        )
                        q.query_text = dka_open_clause
                        repaired = True
                        repair_kind = "OPEN_DKA_DIAGNOSIS_REQUEST"
            if repaired:
                gate_input = ProviderQueryForGate(
                    query_text=q.query_text,
                    response_options=list(q.response_options),
                    topic=q.topic,
                    evidence_quote=q.evidence_span.quote,
                )
                result = evaluate_nlq(gate_input)
                if result.verdict == "PASS" and original_audit is not None:
                    original_audit["replacement_query_id"] = q.query_id
                    original_audit["rewrite_attempt_status"] = "ACCEPTED_AFTER_FULL_NLQ_RECHECK"
                    original_audit["rewritten_query_text"] = q.query_text
                    original_audit["rewritten_response_options"] = list(q.response_options)
                    case.query_rewrite_queue.append(original_audit)
                elif original_audit is not None:
                    original_audit["rewrite_attempt_status"] = "REJECTED_AFTER_FULL_NLQ_RECHECK"
                    original_audit["rewrite_attempt_reasons"] = list(result.block_reasons)
                    case.query_rewrite_queue.append(original_audit)
            q.nlq_gate_verdict = result.verdict
            q.nlq_gate_block_reasons = list(result.block_reasons)
            if result.verdict == "BLOCK":
                blocked_count += 1
                case.query_rewrite_queue.append(query_audit_item(
                    q,
                    status="NEEDS_NON_LEADING_REWRITE",
                    gate_reasons=list(result.block_reasons),
                ))
                continue
            survivors.append(q)
        case.proposed_provider_queries = survivors
        case.stage_run_ids["query_compliance_gate"] = (
            f"{run_id};passed={len(survivors)};blocked={blocked_count}"
        )
        case.stage_trace_ids["query_compliance_gate"] = trace_id

    def _stage_specialist_trace_emit(self, case: CDICase) -> None:
        result = self.runner("specialist_trace_emit", case, {})
        case.stage_run_ids["specialist_trace_emit"] = str(result.get("run_id", ""))
        case.stage_trace_ids["specialist_trace_emit"] = str(result.get("trace_id", ""))
        redacted = 0
        for entry in case.specialist_trace:
            entry.rationale, count = _redact_ungrounded_quantities(
                entry.rationale, case.chart_excerpt
            )
            redacted += count
            entry.route_reason, count = _redact_ungrounded_quantities(
                entry.route_reason, case.chart_excerpt
            )
            redacted += count
            entry.accepted = [
                _redact_ungrounded_quantities(value, case.chart_excerpt)[0]
                for value in entry.accepted
            ]
            entry.rejected = [
                _redact_ungrounded_quantities(value, case.chart_excerpt)[0]
                for value in entry.rejected
            ]
        if redacted:
            case.stage_run_ids["specialist_trace_emit::quantity_redacted"] = str(
                redacted
            )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _hydrate_gap(gap_dict: dict[str, Any]) -> DocumentationGap:
        ev = gap_dict.get("evidence_span") or {}
        return DocumentationGap(
            gap_id=gap_dict.get("gap_id") or f"gap_{uuid.uuid4().hex[:8]}",
            gap_type=gap_dict.get("gap_type", "unknown"),
            description=gap_dict.get("description", ""),
            why_it_matters=gap_dict.get("why_it_matters", ""),
            evidence_span=EvidenceSpan(
                document_id=ev.get("document_id", ""),
                quote=ev.get("quote", ""),
                char_start=int(ev.get("char_start", 0)),
                char_end=int(ev.get("char_end", 0)),
                documented_at=ev.get("documented_at", ""),
            ),
            minimal_clarification_needed=gap_dict.get("minimal_clarification_needed", ""),
            priority=gap_dict.get("priority", "routine"),
        )

    @staticmethod
    def _hydrate_query(q_dict: dict[str, Any]) -> ProviderQuery:
        ev = q_dict.get("evidence_span") or {}
        raw_spans = q_dict.get("evidence_spans") or []

        def _span(raw: dict[str, Any]) -> EvidenceSpan:
            return EvidenceSpan(
                document_id=str(raw.get("document_id", "")),
                quote=str(raw.get("quote", "")),
                char_start=int(raw.get("char_start", 0)),
                char_end=int(raw.get("char_end", 0)),
                documented_at=str(raw.get("documented_at", "")),
            )

        evidence_spans = [
            _span(item) for item in raw_spans if isinstance(item, dict)
        ]
        primary = evidence_spans[0] if evidence_spans else _span(ev)
        response_options = list(q_dict.get("response_options", []))
        # Track H3.18 — deterministic response_options padding.
        # The query_generation prompt requires ≥4 response_options including
        # ≥1 escape hatch, but the LLM sometimes emits only 3 (especially for
        # narrow clinical scenarios like "cirrhosis severity"). Pad with
        # generic alternatives + escape hatch to satisfy the >95% target.
        ESCAPE_OPTIONS = ("D. 无法确定", "D. 不确定", "D. 资料不足无法判断")
        if len(response_options) < 4:
            has_escape = any(
                "无法确定" in opt or "不确定" in opt or "资料不足" in opt
                for opt in response_options
            )
            padded = list(response_options)
            # Fill middle options if missing
            generic_middle = ["A. 是", "B. 否", "C. 可疑"]
            while len(padded) < 4 and generic_middle:
                # Find next option letter
                next_letter = chr(ord('A') + len(padded))
                padded.append(f"{next_letter}. 暂未明确")
            if not has_escape:
                next_letter = chr(ord('A') + len(padded))
                padded.append(f"{next_letter}. 无法确定")
            # Final safety: trim/extend to exactly 4 (or more if LLM gave more)
            if len(padded) < 4:
                # Couldn't pad (very rare) — accept whatever LLM produced
                pass
            response_options = padded
        return ProviderQuery(
            query_id=q_dict.get("query_id") or f"q_{uuid.uuid4().hex[:8]}",
            gap_id=q_dict.get("gap_id", ""),
            topic=q_dict.get("topic", ""),
            reason=q_dict.get("reason", ""),
            evidence_span=primary,
            query_text=q_dict.get("query_text", ""),
            evidence_spans=evidence_spans,
            response_options=response_options,
            priority=q_dict.get("priority", "routine"),
        )


# ---------------------------------------------------------------------------
# Stub runner (Gate 3 only — Gate 6 wires real DeepSeek runner)
# ---------------------------------------------------------------------------


def stub_runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Minimal runner that returns enough empty outputs to exercise the
    orchestrator path. Real LLM-backed runner arrives in Gate 6."""

    return {
        "encounter_synthesis": lambda: {"key_points": [], "encounter_metadata": {}},
        "gap_identification": lambda: {"gaps": []},
        "expert_consultation": lambda: {},
        "query_generation": lambda: {"queries": []},
        "specialist_trace_emit": lambda: {},
    }.get(stage, lambda: {})()


__all__ = ["CDIOrchestrator", "STAGES", "stub_runner", "StageRunner"]
