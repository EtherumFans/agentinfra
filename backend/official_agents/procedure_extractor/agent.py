"""Conservative local procedure extraction backed by the pinned CN catalog.

The implementation intentionally separates two facts:

* an operation mention and its status are copied from an exact source span;
* an ICD-9-CM-3 code is emitted only when the submitted code is present in the
  pinned catalog or one tightly bounded lexical normalization has a unique
  catalog match.

It does not infer procedures, choose between ambiguous catalog entries, assess
clinical appropriateness, or authorize billing/write-back.  The development
catalog is source-unverified and licence-review-pending, so every result remains
subject to human coding review.
"""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Iterable


ASSET_ID = "cn.icd9cm3.catalog"
LOCAL_RUNTIME_MODE = "governed_local_explicit_procedure_baseline"
MAX_INPUT_CHARS = 20_000
MAX_MENTIONS = 100

_ICD9_RE = re.compile(r"(?<![A-Z0-9])(\d{2}\.\d{2,4})(?![A-Z0-9])")
_BOUNDARY = r"[^，,。；;！？!?\r\n]"
_MENTION_RE = re.compile(
    rf"(?P<marker>"
    r"既往(?:曾)?行|曾行|原拟行|拟行|计划(?:行|实施)?|准备(?:行|实施)?|"
    r"未施行|未实施|未行|已施行|已实施|已行|施行|实施|完成|行"
    rf")\s*(?P<value>{_BOUNDARY}{{2,96}}?(?:手术|操作术|术|操作))",
    flags=re.IGNORECASE,
)
_LABEL_RE = re.compile(
    rf"(?:手术名称|术式)\s*[:：]\s*(?P<value>{_BOUNDARY}{{2,96}})",
    flags=re.IGNORECASE,
)
_SPINE_LEVEL_RE = re.compile(r"(?<![A-Za-z0-9])([CTLS])\s*(1[0-2]|[1-9])(?!\d)", re.I)

_CANCELLED = ("取消", "拒绝手术", "拒绝实施", "放弃手术", "放弃治疗")
_NEGATED = ("未行", "未施行", "未实施", "无手术", "没有实施", "未接受")
_HISTORICAL = ("既往", "曾行", "既往史", "年前", "历史")
_PLANNED = ("拟行", "原拟行", "计划", "准备", "必要时", "待行")
_PERFORMED = ("已行", "已施行", "已实施", "施行", "实施", "完成", "手术顺利", "术后")
_GENERIC_NON_PROCEDURES = {
    "任何手术",
    "任何操作",
    "手术或操作",
    "手术",
    "操作",
}
_SPINE_REGION = {"C": "颈椎", "T": "胸椎", "L": "腰椎", "S": "骶椎"}


def _catalog_context() -> tuple[dict[str, Any], Any]:
    from app.config import settings
    from app.services.clinical_asset_governance import (
        assert_asset_use_allowed,
        public_governance,
    )
    from app.services.icd9cm3_loader import get_loader

    asset = assert_asset_use_allowed(
        ASSET_ID,
        deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
        usage="procedure_extraction",
        verify_integrity=True,
    )
    loader = get_loader()
    loader.ensure_loaded()
    return public_governance(asset), loader


def _normalize_term(value: str) -> str:
    text = re.sub(r"[\s　，,。；;：:（）()\[\]【】]", "", str(value or ""))
    # The observed catalog commonly writes 腹腔镜下X while records use
    # 腹腔镜X.  Removing this single grammatical particle is a lexical
    # normalization, not a medical synonym expansion.
    return text.replace("镜下", "镜")


@lru_cache(maxsize=1)
def _term_index() -> dict[str, tuple[str, ...]]:
    _governance, loader = _catalog_context()
    index: dict[str, list[str]] = {}
    for entry in loader.all_codes():
        names: Iterable[str] = (
            str(getattr(entry, "name_cn", "") or ""),
            *(str(item or "") for item in getattr(entry, "synonyms_cn", ()) or ()),
        )
        for name in names:
            normalized = _normalize_term(name)
            if len(normalized) < 4:
                continue
            codes = index.setdefault(normalized, [])
            code = str(getattr(entry, "code", "") or "")
            if code and code not in codes:
                codes.append(code)
    return {term: tuple(codes) for term, codes in index.items()}


def verify_procedure_extractor_health() -> dict[str, Any]:
    governance, loader = _catalog_context()
    stats = loader.stats()
    return {
        "integrity_verified": True,
        "asset": governance,
        "catalog_count": int(getattr(stats, "catalog_codes", 0)),
        "term_index_count": len(_term_index()),
        "network_required": False,
        "llm_required": False,
        "clinical_appropriateness_assessed": False,
    }


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(mark, 0, start) for mark in ("。", "！", "？", "\n"))
    right_candidates = [
        pos for mark in ("。", "！", "？", "\n")
        if (pos := text.find(mark, end)) >= 0
    ]
    return left + 1, min(right_candidates) if right_candidates else len(text)


def _classify_status(context: str, marker: str) -> str:
    combined = f"{marker}{context}"
    if any(token in marker for token in _HISTORICAL):
        return "historical"
    if any(token in marker for token in _NEGATED):
        return "negated"
    if any(token in combined for token in _CANCELLED):
        return "cancelled"
    if any(token in marker for token in _PLANNED):
        return "planned"
    if any(token in combined for token in _HISTORICAL):
        return "historical"
    if any(token in combined for token in _NEGATED):
        return "negated"
    if marker == "行" or any(token in combined for token in _PERFORMED):
        return "performed"
    return "unknown"


def _extract_mentions(text: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in _MENTION_RE.finditer(text):
        value = match.group("value").strip(" \t:：，,。；;")
        if value in _GENERIC_NON_PROCEDURES or value.endswith("任何手术"):
            continue
        start, end = match.span()
        sentence_start, sentence_end = _sentence_bounds(text, start, end)
        context = text[sentence_start:sentence_end]
        evidence = text[start:end]
        mentions.append({
            "text": value,
            "status": _classify_status(context, match.group("marker")),
            "evidence_text": evidence,
            "char_span": [start, end],
            "context": context,
        })
        occupied.append((start, end))
        if len(mentions) >= MAX_MENTIONS:
            return mentions

    for match in _LABEL_RE.finditer(text):
        start, end = match.span()
        if any(a <= start < b or a < end <= b for a, b in occupied):
            continue
        value = match.group("value").strip(" \t:：，,。；;")
        if not value or value in _GENERIC_NON_PROCEDURES:
            continue
        sentence_start, sentence_end = _sentence_bounds(text, start, end)
        context = text[sentence_start:sentence_end]
        mentions.append({
            "text": value,
            "status": _classify_status(context, ""),
            "evidence_text": text[start:end],
            "char_span": [start, end],
            "context": context,
        })
        if len(mentions) >= MAX_MENTIONS:
            break
    return sorted(mentions, key=lambda item: item["char_span"][0])


def _unique_entry(loader: Any, codes: Iterable[str]) -> Any | None:
    unique = list(dict.fromkeys(str(code) for code in codes if code))
    if len(unique) != 1:
        return None
    return loader.get(unique[0])


def _map_to_catalog(phrase: str, context: str, loader: Any) -> tuple[Any | None, str]:
    submitted = [match.group(1) for match in _ICD9_RE.finditer(context)]
    submitted_entries = [loader.get(code) for code in submitted]
    submitted_entries = [entry for entry in submitted_entries if entry is not None]
    if len({entry.code for entry in submitted_entries}) == 1:
        return submitted_entries[0], "submitted_catalog_code"

    normalized = _normalize_term(phrase)
    entry = _unique_entry(loader, _term_index().get(normalized, ()))
    if entry is not None:
        return entry, "unique_lexical_catalog_match"

    # Narrow anatomical normalization for an explicitly written spinal level.
    # No code is emitted unless the resulting exact catalog term is unique.
    level = _SPINE_LEVEL_RE.search(f"{phrase} {context}")
    if (
        level is not None
        and "骨折" in context
        and "切开复位内固定术" in phrase
    ):
        region = _SPINE_REGION.get(level.group(1).upper(), "")
        target = f"{region}骨折切开复位内固定术"
        entry = _unique_entry(loader, _term_index().get(_normalize_term(target), ()))
        if entry is not None:
            return entry, "explicit_spinal_level_catalog_normalization"
    return None, "no_unique_catalog_match"


def extract_procedures(text: str) -> dict[str, Any]:
    """Extract explicit procedure mentions with exact source evidence."""

    source = str(text or "")[:MAX_INPUT_CHARS]
    governance, loader = _catalog_context()
    mentions = _extract_mentions(source)
    procedures: list[dict[str, Any]] = []
    non_billable: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for mention in mentions:
        status = str(mention["status"])
        if status != "performed":
            non_billable.append({
                "text": str(mention["text"]),
                "status": status,
                "evidence_text": str(mention["evidence_text"]),
                "char_span": list(mention["char_span"]),
            })
            issues.append({
                "category": "non_performed_procedure_mention",
                "message": f"原文术式状态为 {status}，未进入已实施操作编码集合。",
                "severity": "warning",
                "suggestion": "由编码员结合完整手术记录确认实际实施状态。",
            })
            continue

        entry, basis = _map_to_catalog(
            str(mention["text"]), str(mention["context"]), loader
        )
        code = str(getattr(entry, "code", "") or "") if entry is not None else ""
        display = (
            str(getattr(entry, "name_cn", "") or "")
            if entry is not None else str(mention["text"])
        )
        warnings = [
            "本地 ICD-9-CM-3 目录 authority_status=source_unverified、"
            "license_status=external_review_required；不得用于自动结算或写回。"
        ]
        confidence = 1.0
        if basis == "explicit_spinal_level_catalog_normalization":
            confidence = 0.8
            warnings.append("编码来自明示脊柱节段的有界目录规范化，必须人工确认术式与解剖部位。")
        elif basis == "unique_lexical_catalog_match":
            confidence = 0.9
            warnings.append("编码来自唯一词法目录命中，不代表临床适用性或最终编码成立。")
        elif basis == "submitted_catalog_code":
            warnings.append("仅验证输入编码的目录成员关系，未验证病历支持或编码规则。")
        else:
            confidence = 0.0
            warnings.append("未能在固定目录中唯一映射；保留明示术式但不生成编码。")
            issues.append({
                "category": "procedure_code_unresolved",
                "message": f"明示已实施术式“{display}”未获得唯一目录编码。",
                "severity": "warning",
                "suggestion": "由编码员使用已获授权的 ICD-9-CM-3 目录人工检索确认。",
            })
        procedures.append({
            "code": code,
            "display": display,
            "evidence_text": str(mention["evidence_text"]),
            "char_span": list(mention["char_span"]),
            "confidence": confidence,
            "status": "performed",
            "warnings": warnings,
        })

    if source.strip() and not mentions:
        issues.append({
            "category": "no_explicit_procedure_mention",
            "message": "未定位到带实施状态的明示术式，不能生成手术操作编码。",
            "severity": "warning",
            "suggestion": "补充已脱敏的手术记录、操作名称和实施状态。",
        })
    elif not source.strip():
        issues.append({
            "category": "procedure_source_required",
            "message": "未提供手术或操作记录。",
            "severity": "warning",
            "suggestion": "提供已脱敏的病历原文后重试。",
        })

    # Governance is deliberately represented in every coded warning and in
    # the audit-only internal fields consumed by the Provider trace.
    return {
        "procedures": procedures,
        "non_billable_mentions": non_billable,
        "issues_found": issues,
        "manual_review_required": True,
        "total_count": len(procedures),
        "_catalog_governance": governance,
        "_runtime_mode": LOCAL_RUNTIME_MODE,
    }


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "procedures",
            "non_billable_mentions",
            "issues_found",
            "manual_review_required",
            "total_count",
        )
    }


__all__ = [
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "extract_procedures",
    "to_pack_output",
    "verify_procedure_extractor_health",
]
