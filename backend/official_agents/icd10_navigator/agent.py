"""Governed local ICD-10-CN index navigation.

The default path uses only the hash-pinned local ICD-10-CN catalog and term
index.  It surfaces unverified candidates and one-level hierarchy context; it
does not validate, assign, recommend, or infer codes for an encounter.  The
asset manifest deliberately marks the catalog as source-unverified and
licence-review-pending, so every result requires a human coding review.
"""

from __future__ import annotations

from collections import defaultdict
import json
import re
import uuid
from typing import Any


AGENT_REF = "icoder/icd10-navigator@1.1.0"
ASSET_ID = "cn.icd10cn.catalog"
LOCAL_RUNTIME_MODE = "governed_local_index_navigation"
OUTPUT_CONTRACT_REF = "icoder/Icd10NavigatorOutput/v4"

_CODE_RE = re.compile(
    r"^[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?"
    r"(?:\+[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)?$",
    re.IGNORECASE,
)
_LABELED_TERM_RE = re.compile(
    r"(?:诊断表述|临床术语|检索词|查询词|术语)\s*(?:只有|为)?\s*[：:]?\s*"
    r"[‘'\"“]?([^’'\"”，,。；;\n]+)",
)
_SPLIT_RE = re.compile(r"\s*(?:伴有?|合并|并发|以及|及|和|、|，|,|/|；|;)\s*")
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_PUBLIC_FIELDS = (
    "search_status",
    "query_interpretation",
    "query_used",
    "rephrasing_attempted",
    "rephrased_query",
    "index_terms",
    "candidate_codes",
    "hierarchy_notes",
    "inclusion_exclusion_notes",
    "source_version",
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
        usage="catalog_navigation",
        verify_integrity=True,
    )
    return public_governance(asset), get_loader()


def verify_navigator_health() -> dict[str, Any]:
    """Verify the governed catalog and term index without exposing paths."""
    governance, loader = _governance_and_loader()
    stats = loader.stats()
    return {
        "integrity_verified": True,
        "asset": governance,
        "catalog_count": int(stats.catalog_codes),
        "term_index_count": int(stats.term_index_size),
    }


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _bounded_input_text(value: Any) -> str:
    text = str(value or "").strip()
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:500].strip()


def extract_query(
    input_text: str,
    *,
    structured_input: dict[str, Any] | None = None,
) -> str:
    """Extract one explicit lookup term without interpreting a clinical note."""
    payload = dict(structured_input or {})
    parsed = _json_object(input_text)
    if parsed:
        payload = {**payload, **parsed}
    for key in ("term", "query", "clinical_term", "index_term"):
        value = _bounded_input_text(payload.get(key))
        if value:
            return value.strip(" ‘'\"”。，；;")[:200]

    text = _bounded_input_text(payload.get("text") or input_text)
    match = _LABELED_TERM_RE.search(text)
    if match:
        return match.group(1).strip(" ‘'\"”。，；;")[:200]
    first_sentence = re.split(r"[。；;\n]", text, maxsplit=1)[0]
    return first_sentence.strip(" ‘'\"”。，；;")[:200]


def _normalize_term(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _split_terms(query: str) -> list[str]:
    parts = [
        item.strip(" ‘'\"”()（）[]【】")
        for item in _SPLIT_RE.split(query)
        if item.strip(" ‘'\"”()（）[]【】")
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for item in parts:
        normalized = _normalize_term(item)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item[:80])
    return unique[:6]


def _search_term(
    loader: Any,
    term: str,
    *,
    allow_lexical: bool = True,
) -> list[tuple[Any, str, float, str]]:
    """Return catalog-backed candidates; never manufacture a code."""
    normalized = _normalize_term(term)
    if not normalized:
        return []

    if _CODE_RE.fullmatch(term.strip().upper()):
        code = term.strip().upper().replace(" ", "")
        exact = loader.get(code)
        if exact is not None:
            return [(exact, "exact_code", 1.0, exact.name_cn or exact.code)]
        prefix = code.rstrip(".") + "."
        matches = [
            entry for entry in loader.all_codes()
            if entry.code.startswith(prefix)
        ]
        return [
            (entry, "prefix_code", 0.95, entry.name_cn or entry.code)
            for entry in matches[:20]
        ]

    indexed_codes = loader.codes_for_term(term)
    if indexed_codes:
        rows: list[tuple[Any, str, float, str]] = []
        indexed_entries = loader.codes_for_codes(indexed_codes)
        indexed_entries.sort(key=lambda entry: bool(entry.is_generated_category))
        for entry in indexed_entries:
            rows.append((entry, "term_index", 1.0, term))
        return rows

    if not allow_lexical:
        return []

    lexical: list[tuple[float, Any, str]] = []
    for entry in loader.all_codes():
        best_name = ""
        best_score = 0.0
        for name in entry.all_names:
            candidate = _normalize_term(name)
            if not candidate:
                continue
            if normalized in candidate or candidate in normalized:
                ratio = min(len(normalized), len(candidate)) / max(
                    len(normalized), len(candidate)
                )
                score = round(0.7 + min(ratio, 1.0) * 0.2, 4)
                if score > best_score:
                    best_score = score
                    best_name = name
        if best_score:
            lexical.append((best_score, entry, best_name))
    lexical.sort(key=lambda row: (-row[0], row[1].code))
    return [
        (entry, "lexical_name", score, matched_name)
        for score, entry, matched_name in lexical[:20]
    ]


def _candidate_order(
    matches_by_term: list[tuple[str, list[tuple[Any, str, float, str]]]],
    *,
    maximum: int = 3,
) -> list[tuple[str, Any, str, float, str]]:
    """Round-robin terms so one broad term cannot hide another explicit term."""
    selected: list[tuple[str, Any, str, float, str]] = []
    seen_codes: set[str] = set()
    depth = 0
    while len(selected) < maximum:
        added = False
        for term, matches in matches_by_term:
            if depth >= len(matches):
                continue
            entry, match_type, score, matched_term = matches[depth]
            if entry.code in seen_codes:
                continue
            seen_codes.add(entry.code)
            selected.append((term, entry, match_type, score, matched_term))
            added = True
            if len(selected) >= maximum:
                break
        if not added:
            break
        depth += 1
    return selected


def _code_summary(entry: Any) -> dict[str, str]:
    return {
        "code": str(entry.code),
        "display": (
            "" if bool(entry.is_generated_category) else str(entry.name_cn or "")
        ),
    }


def _catalog_groups(loader: Any) -> dict[str, list[Any]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for entry in loader.all_codes():
        groups[str(entry.category_code or entry.code)].append(entry)
    for entries in groups.values():
        entries.sort(key=lambda item: item.code)
    return groups


def _candidate_payload(
    *,
    entry: Any,
    matched_term: str,
    match_type: str,
    score: float,
    governance: dict[str, Any],
    groups: dict[str, list[Any]],
) -> dict[str, Any]:
    category = str(entry.category_code or "")
    parent = loader_parent = None
    if category and category != entry.code:
        # The generated category is present in the same group when available.
        parent = next(
            (item for item in groups.get(category, []) if item.code == category),
            None,
        )
        loader_parent = parent

    siblings = [
        item
        for item in groups.get(category or entry.code, [])
        if item.code != entry.code and not bool(item.is_generated_category)
    ]
    if bool(entry.is_generated_category):
        children = siblings
        siblings = []
    else:
        children = [
            item for item in siblings
            if item.code.startswith(entry.code.rstrip("."))
        ]

    related_count = len(groups.get(category or entry.code, [])) - 1
    assignable = not bool(entry.is_generated_category)
    rationale = {
        "exact_code": "输入代码精确命中固定目录；仅作为导航条目，尚未验证临床适用性。",
        "prefix_code": "输入代码前缀命中更具体目录条目；未选择或推荐其中任何编码。",
        "term_index": "固定术语反向索引命中；候选尚未经过 Verify/Guidelines 校验。",
        "lexical_name": "固定目录名称/同义词包含匹配；相关性较弱，必须人工复核。",
    }[match_type]
    return {
        "code": str(entry.code),
        "display": (
            "" if bool(entry.is_generated_category) else str(entry.name_cn or "")
        ),
        "description": str(entry.name_en or ""),
        "index_term": str(matched_term or entry.name_cn or ""),
        "rationale": rationale,
        "match_type": match_type,
        "match_score": float(score),
        "assignable": assignable,
        "parent": _code_summary(loader_parent) if loader_parent else {
            "code": "",
            "display": "",
        },
        "siblings": [_code_summary(item) for item in siblings[:10]],
        "children": [_code_summary(item) for item in children[:10]],
        "related_codes_count": max(related_count, 0),
        "instructional_notes_available": False,
        "source_asset_id": str(governance["asset_id"]),
        "source_version": str(governance["version"]),
    }


def _markdown(result: dict[str, Any], governance: dict[str, Any] | None) -> str:
    lines = [
        "# ICD-10-CN 索引导航",
        "",
        f"**状态：** {result['search_status']}",
        "",
        f"**检索词：** {result['query_used'] or '未形成可验证检索词'}",
        "",
        "## 候选与一层目录遍历",
        "",
    ]
    candidates = result.get("candidate_codes") or []
    if not candidates:
        lines.append("未从固定目录索引返回候选；没有猜测或构造编码。")
    for index, item in enumerate(candidates, start=1):
        lines.extend([
            f"{index}. **{item['code']} — {item['display']}**",
            "",
            f"   - 匹配：`{item['match_type']}` / {item['match_score']:.4f}",
            f"   - 可分配目录叶子：`{str(item['assignable']).lower()}`",
            f"   - 父类目：{item['parent']['code'] or '未返回'} "
            f"{item['parent']['display']}",
            f"   - 同层候选：{len(item['siblings'])}（仅展示最多 10 条）",
            f"   - 子条目：{len(item['children'])}（仅展示最多 10 条）",
            "",
        ])
    lines.extend([
        "## 包括/不包括说明",
        "",
        "当前固定资产不包含可验证 instructional notes；本 Agent 不生成或猜测该信息。",
        "",
        "## 目录治理",
        "",
    ])
    if governance:
        lines.append(
            "`{asset}@{version}`：authority=`{authority}`，license=`{license}`，"
            "billing_authoritative=`{billing}`。".format(
                asset=governance["asset_id"],
                version=governance["version"],
                authority=governance["authority_status"],
                license=governance["license_status"],
                billing=str(governance["billing_authoritative"]).lower(),
            )
        )
    else:
        lines.append("目录治理不可用；没有发布候选事实。")
    lines.extend([
        "",
        "## 下一步",
        "",
        "所有候选均未验证。分配或提交前必须进入 Code Validation，并由编码员人工审核。",
    ])
    return "\n".join(lines)


def _base_response(*, status: str, summary: str) -> dict[str, Any]:
    return {
        "search_status": status,
        "query_interpretation": summary,
        "query_used": "",
        "rephrasing_attempted": False,
        "rephrased_query": "",
        "index_terms": [],
        "candidate_codes": [],
        "hierarchy_notes": [],
        "inclusion_exclusion_notes": [
            "当前固定资产不包含可验证的包括/不包括 instructional notes；未生成或猜测。"
        ],
        "source_version": "未验证",
        "manual_review_required": True,
        "summary": summary,
        "markdown": "",
    }


def _unavailable_response(run_id: str, error_type: str) -> dict[str, Any]:
    result = _base_response(
        status="CATALOG_UNAVAILABLE",
        summary="治理目录或术语索引不可用；索引导航已失败关闭。",
    )
    result["markdown"] = _markdown(result, None)
    result.update({
        "runtime_mode": "catalog_governance_unavailable",
        "catalog_governance": {
            "integrity_verified": False,
            "asset": None,
            "error_type": error_type,
        },
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "catalog_integrity_verified": False,
            "candidate_codes_count": 0,
            "query_terms_count": 0,
            "rephrasing_attempted": False,
        },
    })
    return result


async def run(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic Search + one-level Explore against governed assets."""
    query = extract_query(input_text, structured_input=structured_input)
    if not query:
        result = _base_response(
            status="INPUT_REQUIRED",
            summary="未提供可用于目录检索的明确临床术语或 ICD-10-CN 编码。",
        )
        result["markdown"] = _markdown(result, None)
        result.update({
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "catalog_governance": {
                "integrity_verified": False,
                "asset": None,
                "reason": "input_required",
            },
            "trace_refs": {
                "run_id": run_id or str(uuid.uuid4()),
                "agent_ref": AGENT_REF,
                "catalog_integrity_verified": False,
                "candidate_codes_count": 0,
                "query_terms_count": 0,
                "rephrasing_attempted": False,
            },
        })
        return result

    try:
        governance, loader = _governance_and_loader()
        split_terms = _split_terms(query)
        exact_matches = _search_term(
            loader,
            query,
            allow_lexical=len(split_terms) <= 1,
        )
        rephrasing_attempted = False
        matches_by_term: list[tuple[str, list[tuple[Any, str, float, str]]]] = []
        if exact_matches:
            matches_by_term = [(query, exact_matches)]
        else:
            if split_terms and split_terms != [query]:
                rephrasing_attempted = True
                matches_by_term = [
                    (term, matches)
                    for term in split_terms
                    if (matches := _search_term(loader, term))
                ]
            if not matches_by_term:
                matches_by_term = [(query, [])]

        selected = _candidate_order(matches_by_term)
        groups = _catalog_groups(loader)
        candidates = [
            _candidate_payload(
                entry=entry,
                matched_term=matched_term,
                match_type=match_type,
                score=score,
                governance=governance,
                groups=groups,
            )
            for _term, entry, match_type, score, matched_term in selected
        ]
        safe_terms = list(dict.fromkeys(
            str(matched_term or entry.name_cn or entry.code)
            for _term, entry, _match_type, _score, matched_term in selected
        ))
        status = "CANDIDATES_FOUND" if candidates else "NO_CANDIDATES"
        summary = (
            f"固定目录索引返回 {len(candidates)} 个未验证候选；仅完成导航和一层层级浏览。"
            if candidates
            else "固定目录索引未返回候选；未猜测或构造编码。"
        )
        result = _base_response(status=status, summary=summary)
        result.update({
            "query_interpretation": (
                "只按输入中的明确术语执行目录索引检索；未解释病历、未判断候选适用性。"
            ),
            "query_used": "；".join(safe_terms),
            "rephrasing_attempted": rephrasing_attempted,
            "rephrased_query": "；".join(safe_terms) if rephrasing_attempted else "",
            "index_terms": safe_terms,
            "candidate_codes": candidates,
            "hierarchy_notes": [
                (
                    f"{item['code']}：父类目 {item['parent']['code'] or '未返回'}；"
                    f"同层候选 {len(item['siblings'])} 条；子条目 {len(item['children'])} 条；"
                    f"相关目录条目总数 {item['related_codes_count']}。"
                )
                for item in candidates
            ],
            "source_version": (
                f"{governance['asset_id']}@{governance['version']}; "
                f"authority={governance['authority_status']}; "
                f"license={governance['license_status']}"
            ),
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "catalog_governance": {
                "integrity_verified": True,
                "asset": governance,
            },
        })
        result["markdown"] = _markdown(result, governance)
        result["trace_refs"] = {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "catalog_integrity_verified": True,
            "catalog_asset_ids": [governance["asset_id"]],
            "catalog_asset_versions": [governance["version"]],
            "catalog_authority_statuses": [governance["authority_status"]],
            "catalog_license_statuses": [governance["license_status"]],
            "candidate_codes_count": len(candidates),
            "query_terms_count": len(safe_terms),
            "rephrasing_attempted": rephrasing_attempted,
        }
        return result
    except Exception as exc:
        return _unavailable_response(run_id, type(exc).__name__)


def to_current_pack_candidate(result: dict[str, Any]) -> dict[str, Any]:
    """Project internal audit fields into the immutable public Pack contract."""
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "extract_query",
    "run",
    "to_current_pack_candidate",
    "verify_navigator_health",
]
