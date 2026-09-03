"""Catalog-grounded ICD-10-CN rule explanation.

The local development asset can prove only catalog membership, display name,
chapter/category hierarchy, generated-category status, and descendant rows.
It does not contain governed Includes/Excludes, Code First, Use Additional
Code, sequencing, reimbursement, or jurisdiction-specific rule content.
Those omissions are first-class output facts: this module never falls back to
the legacy inline guideline dictionary and never reconstructs rules from model
memory.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any


AGENT_REF = "icoder/rule-explainer@1.2.0"
ASSET_ID = "cn.icd10cn.catalog"
LOCAL_RUNTIME_MODE = "governed_local_catalog_rule_explanation"
OUTPUT_CONTRACT_REF = "icoder/RuleExplanationOutput/v4"
MAX_CHILDREN = 10

_ICD10_CODE_RE = re.compile(
    r"^[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?"
    r"(?:\+[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)?$",
    re.IGNORECASE,
)
_TEXT_CODE_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"([A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?"
    r"(?:\+[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)?)"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_PUBLIC_FIELDS = (
    "status",
    "code",
    "code_system",
    "catalog_status",
    "assignable",
    "catalog_name",
    "chapter",
    "hierarchy",
    "explanation_summary",
    "catalog_facts",
    "rule_content_status",
    "guideline_basis",
    "evidence_refs",
    "unsupported_scope",
    "limitations",
    "source_version",
    "manual_review_required",
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
        usage="catalog_rule_explanation",
        verify_integrity=True,
    )
    loader = get_loader()
    loader.ensure_loaded()
    return public_governance(asset), loader


def verify_rule_explainer_health() -> dict[str, Any]:
    governance, loader = _governance_and_loader()
    stats = loader.stats()
    return {
        "integrity_verified": True,
        "asset": governance,
        "catalog_count": int(stats.catalog_codes),
        "network_required": False,
        "llm_required": False,
        "governed_instructional_notes_available": False,
    }


def _bounded_text(value: Any) -> str:
    text = str(value or "")
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:2_000]


def _normalize_code(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("．", ".")
    )[:32]


def _json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_code(
    input_text: str,
    *,
    structured_input: dict[str, Any] | None = None,
) -> str:
    """Extract one explicitly submitted code without reading clinical meaning."""
    payload = dict(structured_input or {})
    parsed = _json_object(input_text)
    if parsed:
        payload = {**payload, **parsed}
    for key in ("code", "icd10_cn_code", "icd10_code"):
        candidate = _normalize_code(payload.get(key))
        if candidate:
            return candidate

    text = _bounded_text(payload.get("text") or input_text)
    match = _TEXT_CODE_RE.search(text)
    return _normalize_code(match.group(1)) if match else ""


def _children(loader: Any, code: str) -> tuple[list[dict[str, str]], int]:
    # Three-character categories use a dot before descendants (I50 -> I50.*),
    # while a submitted shortened decimal can be a raw prefix of a national
    # extension (I50.9 -> I50.900). Exact rows are excluded in both cases.
    prefix = code.rstrip(".") + ("" if "." in code else ".")
    rows = [
        {
            "code": str(entry.code),
            "display": (
                "" if bool(entry.is_generated_category) else str(entry.name_cn or "")
            ),
        }
        for entry in loader.all_codes()
        if str(entry.code or "").startswith(prefix) and str(entry.code) != code
    ]
    rows.sort(key=lambda item: item["code"])
    return rows[:MAX_CHILDREN], len(rows)


def _source_version(governance: dict[str, Any]) -> str:
    return (
        f"{governance['asset_id']}@{governance['version']}; "
        f"authority={governance['authority_status']}; "
        f"license={governance['license_status']}; "
        f"billing_authoritative={str(governance['billing_authoritative']).lower()}"
    )


def _base(code: str, *, status: str, catalog_status: str) -> dict[str, Any]:
    return {
        "status": status,
        "code": code,
        "code_system": "ICD-10-CN",
        "catalog_status": catalog_status,
        "assignable": False,
        "catalog_name": "",
        "chapter": "",
        "hierarchy": {
            "chapter_no": "",
            "category_code": "",
            "children": [],
            "children_truncated": False,
        },
        "explanation_summary": "",
        "catalog_facts": [],
        "rule_content_status": "UNAVAILABLE_IN_GOVERNED_ASSET",
        "guideline_basis": [
            "当前固定开发资产未收录可验证的 Includes/Excludes、Code First、"
            "Use Additional Code、Code Also、组合码或排序规则；未生成或猜测。"
        ],
        "evidence_refs": [],
        "unsupported_scope": [
            "Includes/Excludes1/Excludes2 与 instructional notes",
            "Code First/Use Additional Code/Code Also、组合码与排序规则",
            "CPT、ICD-10-CM、ICD-10-PCS 及中国医保、DRG/DIP、地方结算政策",
            "编码对具体病历或就诊的临床适用性",
        ],
        "limitations": [],
        "source_version": "未验证",
        "manual_review_required": True,
    }


def _input_required(run_id: str) -> dict[str, Any]:
    result = _base("", status="REQUIRES_REVIEW", catalog_status="INPUT_REQUIRED")
    result["explanation_summary"] = "未提取到一个明确的 ICD-10-CN 编码。"
    result["limitations"] = ["请提供一个待解释的 ICD-10-CN 编码；未执行目录查询。"]
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
            "catalog_facts_count": 0,
        },
    })
    return result


def _unavailable(code: str, run_id: str, error_type: str) -> dict[str, Any]:
    result = _base(
        code,
        status="REQUIRES_REVIEW",
        catalog_status="CATALOG_UNAVAILABLE",
    )
    result["explanation_summary"] = "治理目录不可用；规则解释已失败关闭。"
    result["limitations"] = ["目录完整性或使用策略校验失败；未发布任何编码事实。"]
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
            "catalog_facts_count": 0,
        },
    })
    return result


def explain_code(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain only governed catalog facts for one explicit ICD-10-CN code."""
    code = extract_code(input_text, structured_input=structured_input)
    if not code:
        return _input_required(run_id)
    if not _ICD10_CODE_RE.fullmatch(code):
        # A structured caller may submit a malformed token. Keep it visible as
        # an unverified input, but never let it reach the catalog as a claim.
        result = _base(code, status="REQUIRES_REVIEW", catalog_status="NOT_FOUND")
        result["explanation_summary"] = (
            f"编码 {code} 不符合本地 ICD-10-CN 查询格式；未据格式猜测有效性。"
        )
        result["limitations"] = ["输入格式未通过；未执行目录成员关系结论。"]
        result.update({
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "catalog_governance": {
                "integrity_verified": False,
                "asset": None,
                "reason": "invalid_code_format",
            },
            "trace_refs": {
                "run_id": run_id or str(uuid.uuid4()),
                "agent_ref": AGENT_REF,
                "catalog_integrity_verified": False,
                "catalog_facts_count": 0,
            },
        })
        return result

    try:
        governance, loader = _governance_and_loader()
    except Exception as exc:
        return _unavailable(code, run_id, type(exc).__name__)

    entry = loader.get(code)
    descendants, descendant_count = _children(loader, code)
    generated_category = bool(
        entry is not None and getattr(entry, "is_generated_category", False)
    )
    assignable = bool(entry is not None and not generated_category)
    in_catalog = entry is not None or bool(descendants)

    if assignable:
        catalog_status = "ASSIGNABLE"
        status = "WARNING"
        summary = (
            f"编码 {code} 精确命中固定开发目录，目录名称为“{entry.name_cn}”，"
            "且该条目不是生成类目；这仅证明目录叶子状态，不证明具体病历适用性。"
        )
    elif in_catalog:
        catalog_status = "CATEGORY_OR_PREFIX"
        status = "REQUIRES_REVIEW"
        summary = (
            f"编码 {code} 对应目录类目或前缀并存在更具体条目，"
            "因此据当前开发目录不可直接赋码，也未自动选择任何替代条目。"
        )
    else:
        catalog_status = "NOT_FOUND"
        status = "REQUIRES_REVIEW"
        summary = (
            f"编码 {code} 未命中固定开发目录且未发现更具体子条目；"
            "未据格式或模型记忆推断其有效。"
        )

    chapter_no = str(getattr(entry, "chapter_no", "") or "")
    category_code = str(getattr(entry, "category_code", "") or "")
    chapter = str(loader.chapter_for(code) or "") if entry is not None else ""
    if entry is None and descendants:
        first = loader.get(descendants[0]["code"])
        chapter_no = str(getattr(first, "chapter_no", "") or "")
        category_code = str(getattr(first, "category_code", "") or code)
        chapter = str(loader.chapter_for(descendants[0]["code"]) or "")

    facts = [
        f"catalog_membership={str(entry is not None).lower()}",
        f"catalog_status={catalog_status}",
        f"assignable_leaf={str(assignable).lower()}",
        f"descendant_rows_total={descendant_count}",
        f"descendant_rows_shown={len(descendants)}",
    ]
    if entry is not None:
        facts.extend([
            f"catalog_name={str(entry.name_cn or '')}",
            f"chapter={chapter}",
            f"category_code={category_code}",
        ])

    result = _base(code, status=status, catalog_status=catalog_status)
    result.update({
        "assignable": assignable,
        "catalog_name": str(getattr(entry, "name_cn", "") or ""),
        "chapter": chapter,
        "hierarchy": {
            "chapter_no": chapter_no,
            "category_code": category_code,
            "children": descendants,
            "children_truncated": descendant_count > len(descendants),
        },
        "explanation_summary": summary,
        "catalog_facts": facts,
        "evidence_refs": [
            f"{governance['asset_id']}@{governance['version']}:code={code}",
            f"catalog_integrity_sha256_verified=true; catalog_status={catalog_status}",
        ],
        "limitations": [
            "目录 authority_status=source_unverified、license_status=external_review_required；"
            "本结果不是结算权威。",
            "未调用 legacy get_guidelines 内嵌知识库，也未使用 LLM 或外部网络。",
            "只解释目录事实；所有规则内容与就诊适用性必须由具备授权来源的编码员复核。",
        ],
        "source_version": _source_version(governance),
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "catalog_governance": {
            "integrity_verified": True,
            "asset": governance,
        },
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": AGENT_REF,
            "catalog_integrity_verified": True,
            "catalog_asset_ids": [governance["asset_id"]],
            "catalog_asset_versions": [governance["version"]],
            "catalog_authority_statuses": [governance["authority_status"]],
            "catalog_license_statuses": [governance["license_status"]],
            "catalog_facts_count": len(facts),
            "instructional_notes_used": False,
            "llm_used": False,
        },
    })
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "explain_code",
    "extract_code",
    "to_pack_output",
    "verify_rule_explainer_health",
]
