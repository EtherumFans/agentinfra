"""Conservative explicit-diagnosis extraction using the pinned ICD-10-CN asset.

This local baseline recognizes only diagnoses inside explicit diagnosis labels
or mentions carrying explicit suspected/negated/history/family-history
modifiers.  It never infers a disease from medication, tests, procedures, or
general narrative.  A current diagnosis is emitted only when its exact term
has one uniquely assignable entry in the governed development catalog.
"""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Iterable


ASSET_ID = "cn.icd10cn.catalog"
LOCAL_RUNTIME_MODE = "governed_local_explicit_diagnosis_baseline"
MAX_INPUT_CHARS = 20_000
MAX_ITEMS = 100

_BOUNDARY = r"[^，,。；;！？!?\r\n]"
_LABEL_RE = re.compile(
    rf"(?:出院诊断|入院诊断|主要诊断|初步诊断|明确诊断|诊断)"
    rf"\s*(?:为|是)?\s*[:：]\s*(?P<value>{_BOUNDARY}{{2,512}})",
    re.I,
)
_SUSPECTED_RE = re.compile(
    rf"(?P<full>(?:考虑|疑似|待排|不排除|可能(?:为)?)"
    rf"\s*(?P<value>{_BOUNDARY}{{2,80}}))",
    re.I,
)
_NEGATED_RE = re.compile(
    rf"(?P<full>(?:已排除|排除|否认|未见|未发现|无)"
    rf"\s*(?P<value>{_BOUNDARY}{{2,80}}?)(?:史)?)"
    rf"(?=[，,。；;！？!?\r\n]|$)",
    re.I,
)
_HISTORY_RE = re.compile(
    rf"(?P<full>(?:既往(?:有|患)?|曾患)\s*"
    rf"(?P<value>{_BOUNDARY}{{2,80}}?)(?:病史|史))",
    re.I,
)
_FAMILY_RE = re.compile(
    rf"(?P<full>(?:家族史\s*[:：]?|父亲|母亲|兄弟|姐妹|家人)"
    rf"(?:有|患)?\s*(?P<value>{_BOUNDARY}{{2,80}}))",
    re.I,
)
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
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
        usage="explicit_diagnosis_extraction",
        verify_integrity=True,
    )
    loader = get_loader()
    loader.ensure_loaded()
    return public_governance(asset), loader


@lru_cache(maxsize=1)
def _catalog_terms() -> tuple[str, ...]:
    _governance, loader = _governance_and_loader()
    terms = {
        str(term).strip()
        for term in loader.term_index()
        if 3 <= len(str(term).strip()) <= 80
        and any("\u4e00" <= char <= "\u9fff" for char in str(term))
    }
    return tuple(sorted(terms, key=lambda item: (-len(item), item)))


def verify_diagnosis_extractor_health() -> dict[str, Any]:
    governance, loader = _governance_and_loader()
    stats = loader.stats()
    return {
        "integrity_verified": True,
        "asset": governance,
        "catalog_count": int(stats.catalog_codes),
        "term_index_count": int(stats.term_index_size),
        "scannable_term_count": len(_catalog_terms()),
        "network_required": False,
        "llm_required": False,
        "clinical_diagnosis_assessed": False,
    }


def _bounded_text(value: Any) -> str:
    text = str(value or "")
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:MAX_INPUT_CHARS]


def _overlaps(span: tuple[int, int], others: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(not (end <= old_start or start >= old_end) for old_start, old_end in others)


def _terms_in_region(
    region: str,
    *,
    base_offset: int,
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, int, str]] = []
    for term in _catalog_terms():
        if term not in region:
            continue
        for match in re.finditer(re.escape(term), region):
            candidates.append((
                base_offset + match.start(),
                base_offset + match.end(),
                match.group(0),
            ))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    selected: list[tuple[int, int, str]] = []
    for candidate in candidates:
        if _overlaps((candidate[0], candidate[1]), ((a, b) for a, b, _ in selected)):
            continue
        selected.append(candidate)
        if len(selected) >= MAX_ITEMS:
            break
    return [
        {"text": term, "char_span": [start, end]}
        for start, end, term in selected
    ]


def _unique_assignable_entry(loader: Any, term: str) -> tuple[Any | None, str]:
    entries = [
        loader.get(code)
        for code in loader.codes_for_term(term)
    ]
    entries = [entry for entry in entries if entry is not None]
    exact = [
        entry for entry in entries
        if str(entry.name_cn or "") == term and not bool(entry.is_generated_category)
    ]
    exact_codes = {str(entry.code) for entry in exact}
    if len(exact_codes) == 1:
        return exact[0], "exact_catalog_name_unique"
    assignable = [entry for entry in entries if not bool(entry.is_generated_category)]
    assignable_codes = {str(entry.code) for entry in assignable}
    if len(assignable_codes) == 1:
        return assignable[0], "exact_index_term_unique"
    return None, "no_unique_assignable_catalog_entry"


def _modifier_mentions(text: str, loader: Any) -> tuple[list[dict[str, Any]], list[tuple[int, int]]]:
    mentions: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    specs = (
        (_FAMILY_RE, "family_history", "家族史提及，不作为本次就诊当前诊断编码"),
        (_NEGATED_RE, "negated", "否定或已排除提及，不作为当前诊断编码"),
        (_HISTORY_RE, "history_of", "既往史提及，不作为本次就诊当前诊断编码"),
        (_SUSPECTED_RE, "suspected", "疑似、待排或可能提及，不作为已确诊诊断编码"),
    )
    for pattern, status, reason in specs:
        for match in pattern.finditer(text):
            full_start, full_end = match.span("full")
            if _overlaps((full_start, full_end), occupied):
                continue
            value_start, _value_end = match.span("value")
            value = match.group("value").strip()
            terms = _terms_in_region(value, base_offset=value_start)
            mention_text = terms[0]["text"] if terms else value.strip("病史 ")
            if not mention_text:
                continue
            # Merely touching the catalog does not validate the assertion or
            # code; this lookup only avoids returning label/connector noise.
            _entry, _basis = _unique_assignable_entry(loader, mention_text)
            mentions.append({
                "mention_text": mention_text,
                "evidence_text": text[full_start:full_end],
                "char_span": [full_start, full_end],
                "assertion_status": status,
                "reason": reason,
            })
            occupied.append((full_start, full_end))
            if len(mentions) >= MAX_ITEMS:
                return mentions, occupied
    mentions.sort(key=lambda item: item["char_span"][0])
    occupied.sort()
    return mentions, occupied


def extract_diagnoses(text: str, *, run_id: str = "") -> dict[str, Any]:
    source = _bounded_text(text)
    governance, loader = _governance_and_loader()
    non_codable, modifier_spans = _modifier_mentions(source, loader)
    diagnoses: list[dict[str, Any]] = []
    issues: list[str] = []
    seen_spans: set[tuple[int, int]] = set()

    for label in _LABEL_RE.finditer(source):
        value_start, _value_end = label.span("value")
        label_mentions = _terms_in_region(
            label.group("value"),
            base_offset=value_start,
        )
        for mention in label_mentions:
            span = tuple(mention["char_span"])
            if span in seen_spans or _overlaps(span, modifier_spans):
                continue
            seen_spans.add(span)
            entry, basis = _unique_assignable_entry(loader, str(mention["text"]))
            if entry is None:
                non_codable.append({
                    "mention_text": str(mention["text"]),
                    "evidence_text": source[span[0]:span[1]],
                    "char_span": [span[0], span[1]],
                    "assertion_status": "unresolved",
                    "reason": (
                        "明示当前诊断未获得唯一可分配目录条目；"
                        "保留原文供编码员复核，不猜测编码"
                    ),
                })
                issues.append(
                    f"明示当前诊断“{mention['text']}”未获得唯一可分配目录条目；未生成编码。"
                )
                continue
            diagnoses.append({
                "diagnosis_text": str(mention["text"]),
                "evidence_text": source[span[0]:span[1]],
                "char_span": [span[0], span[1]],
                "assertion_status": "present",
                "icd10_cn_code": str(entry.code),
                "icd10_cn_name": str(entry.name_cn or ""),
                "confidence": "high" if basis == "exact_catalog_name_unique" else "medium",
                "verification": (
                    f"{basis}; authority={governance['authority_status']}; "
                    f"license={governance['license_status']}; "
                    "clinical_support_not_assessed"
                ),
            })
            if len(diagnoses) >= MAX_ITEMS:
                break

        # Preserve an explicit diagnosis label even when the development
        # catalog contains no recognizable term.  This is deliberately an
        # unresolved, review-only mention: it must never be upgraded into a
        # guessed clinical diagnosis or code.
        if not label_mentions:
            raw_value = label.group("value").strip()
            raw_start = value_start + len(label.group("value")) - len(
                label.group("value").lstrip()
            )
            raw_end = raw_start + len(raw_value)
            if raw_value and not _overlaps((raw_start, raw_end), modifier_spans):
                non_codable.append({
                    "mention_text": raw_value,
                    "evidence_text": source[raw_start:raw_end],
                    "char_span": [raw_start, raw_end],
                    "assertion_status": "unresolved",
                    "reason": (
                        "明示当前诊断未在固定目录中定位；"
                        "保留原文供编码员复核，不猜测编码"
                    ),
                })
                issues.append(
                    f"明示当前诊断“{raw_value}”未在固定目录中定位；未生成编码。"
                )

    non_codable.sort(key=lambda item: item["char_span"][0])

    issues.extend(
        f"{item['mention_text']}：{item['reason']}"
        for item in non_codable
    )
    issues.append(
        "本地 ICD-10-CN 目录 authority_status=source_unverified、"
        "license_status=external_review_required；目录候选不具有结算权威。"
    )
    if source.strip() and not diagnoses and not non_codable:
        issues.insert(0, "未在明确诊断标签或明确状态修饰中定位到可处理的诊断实体。")
    if not source.strip():
        issues.insert(0, "未提供已脱敏病历文本。")

    return {
        "status": "WARNING" if diagnoses else "REQUIRES_REVIEW",
        "diagnoses": diagnoses,
        "non_codable_mentions": non_codable,
        "issues_found": issues[:MAX_ITEMS],
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id,
            "provider_trace_refs": [
                f"{run_id}:governed-diagnosis-extraction"
            ] if run_id else [],
        },
        "_catalog_governance": governance,
        "_runtime_mode": LOCAL_RUNTIME_MODE,
    }


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "status",
            "diagnoses",
            "non_codable_mentions",
            "issues_found",
            "manual_review_required",
            "trace_refs",
        )
    }


__all__ = [
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "extract_diagnoses",
    "to_pack_output",
    "verify_diagnosis_extractor_health",
]
