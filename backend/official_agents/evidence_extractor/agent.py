"""Governed exact-mention evidence locator for submitted ICD-10-CN codes.

The local baseline locates only exact catalog terms or exact code literals in
the supplied text.  A mention is documentation evidence, not proof that the
condition is clinically true or that the code is valid for the encounter.
"""

from __future__ import annotations

import re
from typing import Any


AGENT_REF = "icoder/evidence-extractor@1.1.0"
ASSET_ID = "cn.icd10cn.catalog"
PROVIDER_ID = "icoder.governed-evidence-extractor.v1"
OUTPUT_CONTRACT_REF = "icoder/CodedEvidence/v11"
LOCAL_RUNTIME_MODE = "governed_local_exact_mention_extraction"
MATCH_BASIS = "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"

_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)"
    r"(?![A-Za-z0-9])",
    re.I,
)
_LABELED_CODES_RE = re.compile(
    r"(?:待核查编码|候选编码|编码集|已有编码|codes?)\s*(?:为|是)?\s*[：:=]?\s*"
    r"([^。；;\n]+)",
    re.I,
)
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_PUBLIC_FIELDS = (
    "extraction_status",
    "input_codes",
    "input_code_count",
    "match_basis",
    "located_mentions",
    "code_results",
    "unmatched_codes",
    "uncoded_findings",
    "source_version",
    "limitations",
    "manual_review_required",
    "summary",
    "markdown",
)


def _governance_and_loader() -> tuple[dict[str, Any], Any]:
    from app.config import settings
    from app.services.clinical_asset_governance import (
        assert_asset_use_allowed,
        public_governance,
    )
    from app.services.icd10cn_loader import get_loader

    asset = assert_asset_use_allowed(
        ASSET_ID,
        deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
        usage="exact_evidence_mention_extraction",
        verify_integrity=True,
    )
    return public_governance(asset), get_loader()


def verify_extractor_health() -> dict[str, Any]:
    governance, loader = _governance_and_loader()
    stats = loader.stats()
    return {
        "integrity_verified": True,
        "asset": governance,
        "catalog_count": int(stats.catalog_codes),
        "term_index_count": int(stats.term_index_size),
        "clinical_support_assessed": False,
    }


def _bounded_text(value: Any, maximum: int) -> str:
    text = str(value or "").strip()
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:maximum]


def _input_codes(payload: dict[str, Any], text: str) -> list[str]:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    raw = (
        payload.get("codes")
        or payload.get("candidate_codes")
        or extra.get("codes")
        or extra.get("candidate_codes")
    )
    codes: list[str] = []
    if isinstance(raw, list):
        for value in raw[:20]:
            code = _bounded_text(value, 32).strip()
            if code:
                codes.append(code)
        if codes:
            return codes
    if isinstance(raw, str):
        codes = [match.group(1) for match in _CODE_RE.finditer(raw)][:20]
        if codes:
            return codes

    match = _LABELED_CODES_RE.search(text)
    if match:
        codes = [item.group(1) for item in _CODE_RE.finditer(match.group(1))]
    return codes[:20]


def _mask_code_declarations(text: str) -> str:
    """Hide submitted-code labels while preserving all character offsets."""
    chars = list(text)
    for match in _LABELED_CODES_RE.finditer(text):
        for index in range(match.start(), match.end()):
            chars[index] = "\n" if chars[index] == "\n" else " "
    return "".join(chars)


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(mark, 0, start) for mark in ("。", "！", "？", "\n", ";", "；"))
    right_candidates = [
        position for mark in ("。", "！", "？", "\n", ";", "；")
        if (position := text.find(mark, end)) >= 0
    ]
    return left + 1, (min(right_candidates) + 1 if right_candidates else len(text))


def _context_status(text: str, start: int, end: int) -> tuple[str, str]:
    sentence_start, sentence_end = _sentence_bounds(text, start, end)
    sentence = text[sentence_start:sentence_end]
    prefix = text[max(sentence_start, start - 30):start]
    if re.search(r"(?:家族史|父亲|母亲|兄弟|姐妹|家人)", sentence):
        return "family_history", "explicit_family_context"
    if re.search(r"(?:否认|排除|未见|未发现|无)(?:[^。；，,\n]{0,12})$", prefix):
        return "negated", "explicit_negation_before_mention"
    if re.search(r"(?:既往|曾患|病史|史\s*\d+\s*年)", prefix):
        return "historical", "explicit_history_before_mention"
    if re.search(r"(?:疑似|待排|考虑|不排除|可能)(?:[^。；，,\n]{0,12})$", prefix):
        return "suspected", "explicit_uncertainty_before_mention"
    return "current_mention", "no_explicit_context_modifier_detected"


def _literal_spans(text: str, needle: str, *, ascii_boundary: bool) -> list[tuple[int, int]]:
    if not needle:
        return []
    flags = re.I if any(character.isascii() and character.isalpha() for character in needle) else 0
    pattern = re.escape(needle)
    if ascii_boundary:
        pattern = rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"
    return [(match.start(), match.end()) for match in re.finditer(pattern, text, flags)][:20]


def _mentions_for_code(
    *,
    original_code: str,
    input_index: int,
    entry: Any | None,
    text: str,
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, int, str, str]] = []
    normalized_code = original_code.strip().upper()
    for start, end in _literal_spans(text, normalized_code, ascii_boundary=True):
        candidates.append((start, end, text[start:end], "exact_code_literal"))
    if entry is not None:
        terms = sorted(
            {
                str(term).strip()
                for term in entry.all_names
                if 2 <= len(str(term).strip()) <= 200
            },
            key=lambda value: (-len(value), value.casefold()),
        )[:50]
        for term in terms:
            ascii_boundary = all(character.isascii() for character in term)
            for start, end in _literal_spans(text, term, ascii_boundary=ascii_boundary):
                candidates.append((start, end, text[start:end], "exact_catalog_term"))

    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[3]))
    selected: list[tuple[int, int, str, str]] = []
    for candidate in candidates:
        start, end, _, _ = candidate
        if any(not (end <= old_start or start >= old_end) for old_start, old_end, _, _ in selected):
            continue
        selected.append(candidate)
        if len(selected) >= 5:
            break

    mentions: list[dict[str, Any]] = []
    for start, end, matched, match_type in sorted(selected):
        context_status, context_rule = _context_status(text, start, end)
        mentions.append({
            "input_index": input_index,
            "code": original_code,
            "evidence_text": matched,
            "char_span": [start, end],
            "matched_term": matched,
            "match_type": match_type,
            "context_status": context_status,
            "context_rule": context_rule,
            "clinical_support_assessed": False,
        })
    return mentions


def _governance_source(governance: dict[str, Any] | None) -> str:
    if not governance:
        return ""
    return (
        f"{governance['asset_id']}@{governance['version']}; "
        f"authority={governance['authority_status']}; "
        f"license={governance['license_status']}"
    )


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 编码候选精确证据提及定位",
        "",
        f"**状态：** {result['extraction_status']}",
        "",
        f"**输入编码数：** {result['input_code_count']}",
        "",
        "> 仅定位代码字面量或固定目录术语的精确 span；不判断临床支持度或编码有效性。",
        "",
        "## 逐码结果",
        "",
    ]
    if not result["code_results"]:
        lines.append("未提供可处理的候选编码。")
    for item in result["code_results"]:
        lines.extend([
            f"- **{item['code']}**：`{item['result_status']}`，精确提及 {item['mention_count']} 处",
            f"  - 目录状态：`{item['catalog_status']}`；目录可分配叶子：`{str(item['assignable_catalog_entry']).lower()}`",
            f"  - 复核：{item['manual_review_prompt']}",
        ])
    lines.extend([
        "",
        "## 边界",
        "",
        "当前结果不能证明诊断成立、操作已实施或候选编码适用于本次就诊，必须人工复核。",
    ])
    return "\n".join(lines)[:20_000]


async def run(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(structured_input or {})
    text = _bounded_text(payload.get("text") or input_text, 50_000)
    codes = _input_codes(payload, text)
    searchable = _mask_code_declarations(text)

    governance: dict[str, Any] | None = None
    loader: Any | None = None
    catalog_error = ""
    if codes:
        try:
            governance, loader = _governance_and_loader()
        except Exception as exc:
            catalog_error = f"catalog_governance_unavailable:{type(exc).__name__}"

    located: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for index, code in enumerate(codes):
        if loader is None:
            results.append({
                "input_index": index,
                "code": code,
                "catalog_status": "unavailable",
                "catalog_display": "",
                "assignable_catalog_entry": False,
                "mention_count": 0,
                "result_status": "CATALOG_UNAVAILABLE",
                "clinical_support_assessed": False,
                "manual_review_prompt": "目录治理不可用，未执行提及定位；请勿据此判断编码。",
            })
            unmatched.append(code)
            continue
        entry = loader.get(code.strip().upper())
        mentions = _mentions_for_code(
            original_code=code,
            input_index=index,
            entry=entry,
            text=searchable,
        )
        located.extend(mentions)
        if entry is None:
            catalog_status = "not_found"
            display = ""
            assignable = False
        else:
            catalog_status = "found"
            display = "" if bool(entry.is_generated_category) else str(entry.name_cn or "")
            assignable = not bool(entry.is_generated_category)
        if mentions:
            result_status = "EXACT_MENTION_FOUND"
            prompt = (
                "已定位精确提及；这不证明临床支持或编码有效性，需结合完整病历和编码规则人工复核。"
            )
        elif entry is None:
            result_status = "CODE_NOT_IN_CATALOG"
            prompt = "编码未在固定 ICD-10-CN 目录命中，且未定位精确提及；不得猜测替代码。"
            unmatched.append(code)
        else:
            result_status = "NO_EXACT_MENTION"
            prompt = "未定位代码字面量或固定目录术语的精确提及；不等于临床无证据。"
            unmatched.append(code)
        results.append({
            "input_index": index,
            "code": code,
            "catalog_status": catalog_status,
            "catalog_display": display,
            "assignable_catalog_entry": assignable,
            "mention_count": len(mentions),
            "result_status": result_status,
            "clinical_support_assessed": False,
            "manual_review_prompt": prompt,
        })

    extraction_status = (
        "INPUT_REQUIRED" if not codes
        else "CATALOG_UNAVAILABLE" if catalog_error
        else "COMPLETED"
    )
    limitations = [
        "只定位精确代码字面量或固定目录术语，不执行同义医学推理、缩写扩展或隐含证据判断。",
        "current_mention 仅表示未检测到显式否定/既往/家族史/疑似修饰，不代表当前诊断成立。",
        "目录命中和 assignable_catalog_entry 只描述来源未核验目录结构，不代表本次就诊可编码或可结算。",
        "不扫描或生成新编码；uncoded_findings 固定为空。",
    ]
    result = {
        "extraction_status": extraction_status,
        "input_codes": codes,
        "input_code_count": len(codes),
        "match_basis": MATCH_BASIS,
        "located_mentions": located,
        "code_results": results,
        "unmatched_codes": unmatched,
        "uncoded_findings": [],
        "source_version": _governance_source(governance),
        "limitations": limitations,
        "manual_review_required": True,
        "summary": (
            "需要显式提供最多 20 个待核查编码。"
            if not codes
            else "目录治理不可用，未执行任何证据提及定位。"
            if catalog_error
            else f"处理 {len(codes)} 个输入编码，定位 {len(located)} 个精确原文提及，{len(unmatched)} 个编码无精确提及或目录未命中。"
        ),
        "markdown": "",
        "trace_refs": {
            "run_id": run_id,
            "catalog_asset_ids": [str(governance["asset_id"])] if governance else [],
            "catalog_asset_versions": [str(governance["version"])] if governance else [],
            "catalog_authority_statuses": [str(governance["authority_status"])] if governance else [],
            "catalog_license_statuses": [str(governance["license_status"])] if governance else [],
            "catalog_integrity_verified": bool(governance),
            "evidence_input_codes_count": len(codes),
            "evidence_located_mentions_count": len(located),
            "evidence_unmatched_codes_count": len(unmatched),
            "catalog_error": catalog_error,
        },
    }
    result["markdown"] = _markdown(result)
    return result


def to_current_pack_candidate(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "MATCH_BASIS",
    "OUTPUT_CONTRACT_REF",
    "PROVIDER_ID",
    "run",
    "to_current_pack_candidate",
    "verify_extractor_health",
]
