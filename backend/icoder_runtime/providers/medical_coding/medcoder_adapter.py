"""MedCodER pipeline adapter — 5-stage medical coding per NAACL 2025.

Stage 1: Extraction (LLM) — extract diseases + supporting evidence + initial ICD guess
Stage 2: Retrieval (BGE-M3 + FAISS) — top-20 ICD candidates per disease
Stage 3: Merge — union of LLM codes + retrieved codes (cap 30)
Stage 4: Re-rank (LLM, RankGPT) — pick top-5 with per-diagnosis confidence
Stage 5: Compliance + Calibration — MedCodERRetrievalRuleSet, MedCodERConsistencyRuleSet

This module contains the pipeline logic; HybridCodingAdapter routes to
``_medcoder_pipeline()`` when mode="medcoder".
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Stage 1: Extraction prompt ──


EXTRACTION_SYSTEM_PROMPT = (
    "你是一名资深中国医院编码审核员，专长 ICD-10 中文版与 ICD-9-CM-3 手术编码。"
    "从以下病历文本中抽取所有疾病诊断 + 所有手术/操作，每个诊断或手术：\n\n"
    "【疾病诊断】每个疾病给出：\n"
    "1) 规范化疾病名 (disease_text)\n"
    "2) 摘录支持证据的原文句子 (supporting_evidence，必须是病历中实际出现的文本片段)\n"
    "3) 给出你的初始 ICD-10 编码猜测 (llm_initial_code)\n\n"
    "【手术/操作】列出所有手术与操作名称（procedure_mentions），"
    "如 \"腹腔镜胆囊切除术\"、\"结肠镜检查\"、\"气管插管\"。"
    "只列名称，不要猜测编码。\n\n"
    "严格按 JSON 对象输出，schema:\n"
    "{\n"
    '  "diseases": [\n'
    '    {"disease_text": "...", "supporting_evidence": "原文片段", "llm_initial_code": "I50.900"}\n'
    '  ],\n'
    '  "procedure_mentions": ["手术或操作名称1", "手术或操作名称2"]\n'
    "}"
)


def build_extraction_messages(emr_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": emr_text},
    ]


# ── Stage 1: Extraction result (E1.4) ───────────────────────────────


@dataclass
class ExtractionResult:
    """Stage 1 LLM extraction result. E1.4 adds ``procedure_mentions``.

    Backward-compatible with the legacy "list of diseases" shape: the
    dataclass is iterable as ``diseases`` so existing code that does
    ``for dx in extraction: ...`` keeps working. Direct attribute access
    uses ``.diseases`` and ``.procedure_mentions``.
    """
    diseases: list[dict] = field(default_factory=list)
    procedure_mentions: list[str] = field(default_factory=list)

    def __iter__(self):
        return iter(self.diseases)

    def __len__(self):
        return len(self.diseases)

    def __getitem__(self, idx):
        return self.diseases[idx]

    def __bool__(self):
        return bool(self.diseases or self.procedure_mentions)

    def to_dict(self) -> dict:
        return {
            "diseases": list(self.diseases),
            "procedure_mentions": list(self.procedure_mentions),
        }


# ── Stage 4: Re-rank prompt ──


RERANK_SYSTEM_PROMPT = (
    "你是一名资深编码审核员。下面有一个已抽取的疾病诊断、其支持证据，"
    "以及候选 ICD-10 编码列表（来自 LLM 初始猜测 + BGE-M3 语义检索）。\n"
    "请从候选列表中选出最准确的 top-5 编码，按相关度降序排列。\n"
    "对每个最终选择：\n"
    "- final_code: ICD-10 编码\n"
    "- final_name: 编码对应中文名\n"
    "- final_confidence: 0-1 之间的置信度\n"
    "- rationale: 一句话说明选择理由（30字内）\n\n"
    "严格按 JSON 输出，schema:\n"
    '{"ranked": [{"final_code": "I50.900", "final_name": "心力衰竭", '
    '"final_confidence": 0.95, "rationale": "..."}]}'
)


def build_rerank_messages(
    disease_text: str,
    supporting_evidence: str,
    candidates: list[dict],
    differentiation_hints: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build the Stage 4 re-rank prompt for one disease."""
    # Build candidate list with code, name, score, source
    cand_lines = []
    for i, c in enumerate(candidates, start=1):
        cand_lines.append(
            f"{i}. {c.get('code', '?')} {c.get('name', '')} "
            f"(score={c.get('score', 0):.3f}, source={c.get('source', '?')})"
        )
    cand_block = "\n".join(cand_lines) if cand_lines else "(无候选)"

    hints_block = ""
    if differentiation_hints:
        hints_block = "\n\n# 编码区分提示 (P0/P1 rules):\n" + "\n".join(differentiation_hints[:3])

    user_content = (
        f"# 疾病: {disease_text}\n"
        f"# 支持证据: {supporting_evidence}\n"
        f"# 候选编码 (top-{len(candidates)}):\n{cand_block}"
        f"{hints_block}\n\n"
        f"请输出 top-5 编码 + 置信度。"
    )
    return [
        {"role": "system", "content": RERANK_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ── JSON parsing helpers ──


def parse_extraction_response(content: str) -> "ExtractionResult":
    """Parse the Stage 1 LLM JSON response into :class:`ExtractionResult`.

    Tolerant to:
      - code-fenced JSON ```json ... ```
      - trailing commas
      - leading/trailing prose around the JSON
      - legacy array shape ``[{disease}, ...]`` (E1.4 back-compat)

    E1.4: returns :class:`ExtractionResult` (diseases + procedure_mentions)
    instead of a raw ``list[dict]``. Legacy array responses are mapped
    to ``ExtractionResult(diseases=...)`` with empty procedure_mentions.

    Shape detection: the first non-whitespace, non-fence character
    decides which branch to take (``[`` → legacy array, ``{`` → new
    object). This avoids the regex-greediness bug where a dict literal
    inside an array was matched as the top-level object.
    """
    if not content:
        return ExtractionResult()
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content.strip())
    content = content.strip()

    # Decide shape by the first structural character.
    head_idx = 0
    while head_idx < len(content) and content[head_idx] in " \t\r\n":
        head_idx += 1
    if head_idx >= len(content):
        return ExtractionResult()
    head = content[head_idx]

    if head == "{":
        return _parse_object_response(content)
    if head == "[":
        return _parse_array_response(content)

    # Fallback (content starts with prose like "Here is the result:"):
    # find the first structural char and dispatch on that.
    first_open = -1
    for i, ch in enumerate(content):
        if ch == "[":
            first_open = i
            shape = "array"
            break
        if ch == "{":
            first_open = i
            shape = "object"
            break
    if first_open < 0:
        return ExtractionResult()
    if shape == "array":
        arr = _try_match_and_load(content[first_open:], r"\[.*\]", flags=re.DOTALL)
        if isinstance(arr, list):
            return ExtractionResult(diseases=_normalize_disease_list(arr))
    else:
        obj = _try_match_and_load(content[first_open:], r"\{.*\}", flags=re.DOTALL)
        if isinstance(obj, dict):
            return _extraction_from_object(obj)
    return ExtractionResult()


def _parse_object_response(content: str) -> "ExtractionResult":
    """Parse a content string whose top-level JSON is an object."""
    obj = _try_match_and_load(content, r"\{.*\}", flags=re.DOTALL)
    if isinstance(obj, dict):
        return _extraction_from_object(obj)
    return ExtractionResult()


def _parse_array_response(content: str) -> "ExtractionResult":
    """Parse a content string whose top-level JSON is an array (legacy)."""
    arr = _try_match_and_load(content, r"\[.*\]", flags=re.DOTALL)
    if isinstance(arr, list):
        return ExtractionResult(diseases=_normalize_disease_list(arr))
    return ExtractionResult()


def _try_match_and_load(content: str, pattern: str, **flags):
    """Find the first match of ``pattern`` in ``content`` and try to JSON-load it.

    Returns the parsed value on success, ``None`` on failure.
    """
    match = re.search(pattern, content, **flags)
    if not match:
        return None
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return _try_relaxed_json_loads(raw)


def _try_relaxed_json_loads(raw: str):
    """Best-effort tolerant JSON parse: strips trailing commas, retries."""
    try:
        relaxed = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(relaxed)
    except json.JSONDecodeError:
        return None


def _extraction_from_object(obj: dict) -> "ExtractionResult":
    """Map a parsed object response to :class:`ExtractionResult`."""
    raw_diseases = obj.get("diseases", []) or []
    raw_mentions = obj.get("procedure_mentions", []) or []
    diseases = _normalize_disease_list(raw_diseases) if isinstance(raw_diseases, list) else []
    mentions: list[str] = []
    if isinstance(raw_mentions, list):
        for m in raw_mentions:
            if isinstance(m, str):
                m_clean = m.strip()
                if m_clean:
                    mentions.append(m_clean)
            elif isinstance(m, dict):
                # Permissive: accept {"name": "..."} or {"mention": "..."} shape
                for k in ("name", "mention", "procedure_text", "text"):
                    if m.get(k):
                        mentions.append(str(m[k]).strip())
                        break
    return ExtractionResult(diseases=diseases, procedure_mentions=mentions)


def _normalize_disease_list(items: list) -> list[dict]:
    """Normalize each disease dict to the expected 3-key shape."""
    norm: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            norm.append({
                "disease_text": str(item.get("disease_text", "")).strip(),
                "supporting_evidence": str(item.get("supporting_evidence", "")).strip(),
                "llm_initial_code": str(item.get("llm_initial_code", "")).strip(),
            })
    return norm


def parse_rerank_response(content: str) -> list[dict]:
    """Parse the Stage 4 LLM JSON response into list[ranked-dict]."""
    if not content:
        return []
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content.strip())
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        return []
    raw = match.group(0)
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            out = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(out, dict):
        return []
    ranked = out.get("ranked") or []
    if not isinstance(ranked, list):
        return []
    norm: list[dict] = []
    for item in ranked:
        if isinstance(item, dict):
            try:
                conf = float(item.get("final_confidence", 0))
            except (TypeError, ValueError):
                conf = 0.0
            norm.append({
                "code": str(item.get("final_code", "")).strip(),
                "name": str(item.get("final_name", "")).strip(),
                "confidence": max(0.0, min(1.0, conf)),
                "rationale": str(item.get("rationale", "")).strip(),
            })
    return norm


# ── Fuzzy evidence → EvidenceSpan ──


def fuzzy_evidence_to_span(
    evidence_text: str,
    source_text: str,
    threshold: float = 0.85,
) -> dict | None:
    """Find the best matching span of ``evidence_text`` in ``source_text``.

    Uses rapidfuzz's partial_ratio; returns a dict with char_start/char_end
    snapped to the nearest sentence boundary (。/；) for clean UI rendering.
    Returns None if no match exceeds the threshold.
    """
    if not evidence_text or not source_text:
        return None

    try:
        from rapidfuzz import fuzz  # type: ignore
    except ImportError:
        return None

    # Quick check: case-insensitive substring
    if evidence_text in source_text:
        start = source_text.index(evidence_text)
        return {
            "text": evidence_text,
            "char_start": start,
            "char_end": start + len(evidence_text),
        }

    # Sliding window: compare each window of len(evidence_text)
    n = len(evidence_text)
    best_score = 0
    best_start = -1
    # Limit window scan to avoid quadratic blowup on long texts
    if len(source_text) > 20000:
        source_text = source_text[:20000]
    for i in range(0, max(1, len(source_text) - n + 1), max(1, n // 4)):
        window = source_text[i:i + n]
        score = fuzz.partial_ratio(evidence_text, window) / 100.0
        if score > best_score:
            best_score = score
            best_start = i
            if score >= 0.99:
                break

    if best_score < threshold or best_start < 0:
        return None

    char_end = best_start + n
    # Snap to nearest sentence boundary
    char_start, char_end = _snap_to_sentence(source_text, best_start, char_end)
    return {
        "text": source_text[char_start:char_end],
        "char_start": char_start,
        "char_end": char_end,
    }


def _snap_to_sentence(text: str, start: int, end: int) -> tuple[int, int]:
    """Snap (start, end) to the nearest 。；\\n boundary within ±30 chars."""
    BOUNDARIES = "。；\n.!?;"

    def _search(lo: int, hi: int, direction: int) -> int:
        i = lo + direction
        while 0 <= i < len(text) and abs(i - lo) <= 30:
            if text[i] in BOUNDARIES:
                return i + 1 if direction > 0 else i
            i += direction
        return lo

    snapped_start = _search(start, 0, -1)
    snapped_end = _search(end, 0, +1)
    # If snapping collapsed the range, return original
    if snapped_end <= snapped_start:
        return start, end
    return snapped_start, snapped_end


# ── Differentiation KB hints (lightweight) ──


def get_differentiation_hints(disease_text: str, max_hints: int = 3) -> list[str]:
    """Pull a few P0/P1 differentiation hints from the iCoDerA KB.

    Best-effort: returns empty list if the KB is unavailable or doesn't
    match the disease. The hints are injected into the Stage 4 prompt.
    """
    try:
        import os
        asset = os.environ.get("ICODER_DATA_ASSET_DIR", r"E:\iCoDerA\DataAsset")
        path = os.path.join(asset, "coding_differentiation_kb.json")
        if not os.path.isfile(path):
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            kb = json.load(f)
    except Exception:
        return []

    # KB is a list of differentiation rules; match by disease name
    rules = kb.get("rules") if isinstance(kb, dict) else kb
    if not isinstance(rules, list):
        return []
    out: list[str] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get("priority") not in ("P0", "P1"):
            continue
        text = r.get("text") or r.get("hint") or r.get("description") or ""
        if disease_text and disease_text in str(r):
            out.append(str(text)[:200])
        if len(out) >= max_hints:
            break
    return out
