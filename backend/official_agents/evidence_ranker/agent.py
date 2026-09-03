"""Governed deterministic documentation-grounding ranker.

This local baseline ranks only explicitly supplied evidence fragments by
traceability and documentation quality.  It does not infer clinical support,
validate a diagnosis/code, or replace a reviewer.  In particular, source type
is never treated as proof that the content supports the candidate code.
"""

from __future__ import annotations

import json
import re
from typing import Any


AGENT_REF = "icoder/evidence-ranker@1.1.0"
PROVIDER_ID = "icoder.governed-evidence-ranker.v1"
POLICY_ID = "icoder.documentation-grounding-ranking"
POLICY_VERSION = "1.0.0"
OUTPUT_CONTRACT_REF = "icoder/EvidenceRankerOutput/v4"
LOCAL_RUNTIME_MODE = "governed_local_documentation_grounding"

_CODE_RE = re.compile(r"\b([A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)\b", re.I)
_EVIDENCE_RE = re.compile(
    r"证据\s*([A-Za-z0-9_-]{1,32})\s*"
    r"(?:[（(]([^）)\r\n]{1,200})[）)])?\s*[：:]\s*"
    r"(.*?)"
    r"(?=(?:[；;]\s*)?证据\s*[A-Za-z0-9_-]{1,32}\s*(?:[（(]|[：:])|"
    r"(?:[。；;]\s*(?:请|要求|输出))|$)",
    re.S,
)
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_CERTAINTIES = frozenset({"confirmed", "suspected", "probable", "ruled_out", "unknown"})
_PUBLIC_FIELDS = (
    "ranking_status",
    "candidate_code",
    "ranking_basis",
    "ranked_evidence",
    "conflicts",
    "unsupported_claims",
    "confidence_calibration",
    "source_coverage",
    "limitations",
    "manual_review_required",
    "summary",
    "markdown",
)


def verify_ranker_health() -> dict[str, Any]:
    """Return bounded policy evidence; no filesystem or model dependency."""
    return {
        "provider_id": PROVIDER_ID,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "network_required": False,
        "llm_required": False,
        "deterministic": True,
        "clinical_support_assessed": False,
    }


def _bounded_text(value: Any, maximum: int) -> str:
    text = str(value or "").strip()
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:maximum].strip()


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = _bounded_text(text, 100_000)
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if 0 <= number <= 10_000_000 else None


def _source_documents(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("source_documents") or payload.get("documents") or {}
    documents: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in list(raw.items())[:50]:
            doc_id = _bounded_text(key, 64)
            text = _bounded_text(value, 50_000)
            if doc_id and text:
                documents[doc_id] = text
    elif isinstance(raw, list):
        for item in raw[:50]:
            if not isinstance(item, dict):
                continue
            doc_id = _bounded_text(item.get("doc_id") or item.get("id"), 64)
            text = _bounded_text(item.get("text") or item.get("content"), 50_000)
            if doc_id and text:
                documents[doc_id] = text
    return documents


def _structured_evidence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("evidence_items") or payload.get("evidences") or payload.get("evidence") or []
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:50]):
        if not isinstance(item, dict):
            continue
        certainty = _bounded_text(item.get("certainty"), 32).casefold() or "unknown"
        if certainty not in _CERTAINTIES:
            certainty = "unknown"
        rows.append({
            "evidence_id": _bounded_text(
                item.get("evidence_id") or item.get("id") or f"EV-{index + 1:03d}", 64
            ),
            "source": _bounded_text(
                item.get("source") or item.get("source_document") or item.get("doc_type"), 200
            ),
            "content": _bounded_text(
                item.get("content") or item.get("evidence_text") or item.get("text"), 1000
            ),
            "doc_id": _bounded_text(item.get("doc_id"), 64),
            "char_start": _safe_int(item.get("char_start")),
            "char_end": _safe_int(item.get("char_end")),
            "certainty": certainty,
            "explicit_negation": bool(item.get("negation") or item.get("negated")),
            "input_index": index,
        })
    return rows


def _free_text_evidence(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(_EVIDENCE_RE.finditer(_bounded_text(text, 20_000))):
        rows.append({
            "evidence_id": _bounded_text(match.group(1), 64),
            "source": _bounded_text(match.group(2), 200),
            "content": _bounded_text(match.group(3).strip(" ；;。"), 1000),
            "doc_id": "",
            "char_start": None,
            "char_end": None,
            "certainty": "unknown",
            "explicit_negation": False,
            "input_index": index,
        })
    return rows[:50]


def _candidate_code(payload: dict[str, Any], text: str) -> str:
    explicit = _bounded_text(payload.get("candidate_code") or payload.get("code"), 32)
    if explicit:
        return explicit.upper()
    match = _CODE_RE.search(_bounded_text(text, 20_000))
    return match.group(1).upper() if match else ""


def _span_status(item: dict[str, Any], documents: dict[str, str]) -> str:
    doc_id = item["doc_id"]
    start, end = item["char_start"], item["char_end"]
    if start is None or end is None:
        return "missing_coordinates"
    if not doc_id or doc_id not in documents:
        return "source_unavailable"
    source = documents[doc_id]
    if start > end or end > len(source):
        return "mismatch"
    return "valid" if source[start:end] == item["content"] else "mismatch"


def _score_item(
    item: dict[str, Any],
    *,
    candidate_code: str,
    span_status: str,
) -> tuple[float, list[str], bool]:
    """Score traceability only; never claim clinical relevance."""
    score = 0.0
    components: list[str] = []
    if item["content"]:
        score += 0.35
        components.append("content_present:+0.35")
    if item["source"]:
        score += 0.20
        components.append("source_label_present:+0.20")
    if item["evidence_id"]:
        score += 0.10
        components.append("evidence_id_present:+0.10")
    if span_status == "valid":
        score += 0.25
        components.append("source_span_exact:+0.25")
    lexical_code_mention = bool(
        candidate_code and candidate_code.casefold() in item["content"].casefold()
    )
    if lexical_code_mention:
        score += 0.10
        components.append("candidate_code_literal_present:+0.10")
    certainty = item["certainty"]
    if certainty == "suspected":
        score -= 0.10
        components.append("explicit_suspected:-0.10")
    elif certainty == "probable":
        score -= 0.05
        components.append("explicit_probable:-0.05")
    elif certainty == "ruled_out":
        score -= 0.20
        components.append("explicit_ruled_out:-0.20")
    if item["explicit_negation"]:
        score -= 0.20
        components.append("explicit_negation:-0.20")
    return round(max(0.0, min(1.0, score)), 4), components, lexical_code_mention


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 编码证据文档可追溯性排序",
        "",
        f"**状态：** {result['ranking_status']}",
        "",
        f"**候选编码：** {result['candidate_code'] or '未提供'}",
        "",
        "> 分数仅反映显式来源、span、否定/不确定标记和词面信息，不代表临床支持度或编码置信度。",
        "",
        "## 排序结果",
        "",
    ]
    if not result["ranked_evidence"]:
        lines.append("没有可排序的显式证据项。")
    for item in result["ranked_evidence"]:
        lines.extend([
            f"{item['rank']}. **{item['evidence_id']}** — `{item['documentation_grounding_score']:.4f}`",
            f"   - 来源：{item['source'] or '未提供'}",
            f"   - span：`{item['span_status']}`；候选码词面出现：`{str(item['lexical_code_mention']).lower()}`",
            f"   - 说明：{item['rationale']}",
        ])
    lines.extend([
        "",
        "## 人工复核",
        "",
        "本结果不验证诊断、操作或编码。任何编码、结算或临床用途都必须人工复核。",
    ])
    return "\n".join(lines)[:20_000]


async def run(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(structured_input or {})
    parsed = _json_object(input_text)
    if parsed:
        payload = {**payload, **parsed}
    text = _bounded_text(payload.get("text") or input_text, 20_000)
    items = _structured_evidence(payload) or _free_text_evidence(text)
    documents = _source_documents(payload)
    candidate_code = _candidate_code(payload, text)

    duplicate_ids: dict[str, list[dict[str, Any]]] = {}
    unique_items: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        evidence_id = item["evidence_id"]
        if evidence_id in seen:
            duplicate_ids.setdefault(evidence_id, [seen[evidence_id]]).append(item)
            continue
        seen[evidence_id] = item
        unique_items.append(item)

    conflicts: list[dict[str, Any]] = []
    for evidence_id, duplicates in duplicate_ids.items():
        distinct = {(row["source"], row["content"]) for row in duplicates}
        conflicts.append({
            "conflict_type": "duplicate_evidence_id",
            "evidence_ids": [evidence_id],
            "description": (
                "同一 evidence_id 对应多个不同来源或内容，已仅保留首次出现项。"
                if len(distinct) > 1
                else "同一 evidence_id 重复出现，已仅保留首次出现项。"
            ),
        })

    unsupported: list[dict[str, str]] = []
    ranked: list[dict[str, Any]] = []
    valid_spans = 0
    invalid_spans = 0
    sourced = 0
    for item in unique_items:
        if item["source"]:
            sourced += 1
        status = _span_status(item, documents)
        if status == "valid":
            valid_spans += 1
        elif status in {"mismatch", "source_unavailable"}:
            invalid_spans += 1
        if not item["content"]:
            unsupported.append({
                "evidence_id": item["evidence_id"],
                "claim": "",
                "reason_code": "empty_content",
                "reason": "证据项没有可排序内容。",
            })
            continue
        if not item["source"]:
            unsupported.append({
                "evidence_id": item["evidence_id"],
                "claim": item["content"][:200],
                "reason_code": "missing_source_label",
                "reason": "证据项没有显式来源标签，不能视为可追溯证据。",
            })
        if status in {"mismatch", "source_unavailable"}:
            unsupported.append({
                "evidence_id": item["evidence_id"],
                "claim": item["content"][:200],
                "reason_code": "span_mismatch" if status == "mismatch" else "source_unavailable",
                "reason": (
                    "证据文本与声明的来源字符区间不一致。"
                    if status == "mismatch"
                    else "提供了字符区间，但对应 source document 不可用。"
                ),
            })
        score, components, lexical = _score_item(
            item, candidate_code=candidate_code, span_status=status
        )
        ranked.append({
            "evidence_id": item["evidence_id"],
            "source": item["source"],
            "content": item["content"],
            "rank": 0,
            "documentation_grounding_score": score,
            "span_status": status,
            "certainty": item["certainty"],
            "explicit_negation": item["explicit_negation"],
            "lexical_code_mention": lexical,
            "score_components": components,
            "rationale": "；".join(components) if components else "未形成可验证文档排序分量。",
        })
    ranked.sort(key=lambda row: (-row["documentation_grounding_score"], items.index(seen[row["evidence_id"]])))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index

    total = len(unique_items)
    source_ratio = round(sourced / total, 4) if total else 0.0
    if not ranked:
        confidence = "not_assessed"
    elif unsupported or conflicts or invalid_spans:
        confidence = "low"
    elif valid_spans == len(ranked):
        confidence = "high"
    else:
        confidence = "moderate"
    missing_sources = [row["evidence_id"] for row in unique_items if not row["source"]]
    covered_sources = sorted({row["source"] for row in unique_items if row["source"]})[:50]
    ranking_status = (
        "INPUT_REQUIRED" if not ranked
        else "RANKED_WITH_GAPS" if unsupported or conflicts
        else "RANKED"
    )
    limitations = [
        "documentation_grounding_score 不是临床证据强度、诊断概率或编码置信度。",
        "来源文档类型不被当作临床真实性或编码适用性的证明。",
        "本地基线不执行医学语义推理、代码验证、指南检索或结算规则判断。",
    ]
    if candidate_code and not any(row["lexical_code_mention"] for row in ranked):
        limitations.append("候选编码未在任何证据文本中词面出现；这不等于临床不支持。")
    if ranked and valid_spans == 0:
        limitations.append("没有证据项通过 source document 字符区间精确校验。")

    result = {
        "ranking_status": ranking_status,
        "candidate_code": candidate_code,
        "ranking_basis": "DOCUMENTATION_GROUNDING_ONLY",
        "ranked_evidence": ranked,
        "conflicts": conflicts,
        "unsupported_claims": unsupported,
        "confidence_calibration": {
            "overall_confidence": confidence,
            "rationale": "置信度只描述输入来源和 span 的可审计完整性，不描述临床正确性。",
        },
        "source_coverage": {
            "evidence_count": total,
            "sourced_count": sourced,
            "valid_span_count": valid_spans,
            "invalid_span_count": invalid_spans,
            "source_coverage_ratio": source_ratio,
            "covered_sources": covered_sources,
            "missing_sources": missing_sources,
            "coverage_assessment": (
                "无可排序证据" if not ranked
                else "来源或 span 存在缺口" if unsupported or conflicts
                else "显式来源已覆盖；未提供 span 的项目仍需人工核对"
                if valid_spans < len(ranked)
                else "全部排序证据均通过显式来源 span 校验"
            ),
        },
        "limitations": limitations,
        "manual_review_required": True,
        "summary": (
            "需要提供至少一个包含内容的显式证据项。"
            if not ranked
            else f"按文档可追溯性排序 {len(ranked)} 项证据；发现 {len(unsupported)} 个来源/span 缺口和 {len(conflicts)} 个结构冲突。"
        ),
        "markdown": "",
        "trace_refs": {
            "run_id": run_id,
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "evidence_items_count": len(ranked),
            "valid_evidence_spans_count": valid_spans,
            "invalid_evidence_spans_count": invalid_spans,
            "evidence_source_coverage_ratio": source_ratio,
        },
    }
    result["markdown"] = _markdown(result)
    return result


def to_current_pack_candidate(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "POLICY_ID",
    "POLICY_VERSION",
    "PROVIDER_ID",
    "run",
    "to_current_pack_candidate",
    "verify_ranker_health",
]
