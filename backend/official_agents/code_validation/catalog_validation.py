"""Governed local catalog baseline for the Code Validation Agent.

This module validates only facts that the development environment can prove:

* exact membership in the pinned ICD-10-CN / ICD-9-CM-3 catalog files;
* whether an ICD-10 entry is a generated category rather than an assignable
  leaf; and
* duplicate submitted codes.

The catalog manifest deliberately marks both dictionaries as source-unverified
and licence-review-pending.  Consequently a catalog hit is never presented as
a billing-authoritative PASS: every successful local result remains WARNING
and requires a human coding review.  Cross-code semantics (Excludes,
sequencing, companion codes, diagnosis/documentation fit) are outside this
deterministic baseline.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
import uuid
from typing import Any, Iterable


ICD10_ASSET_ID = "cn.icd10cn.catalog"
ICD9_ASSET_ID = "cn.icd9cm3.catalog"
LOCAL_RUNTIME_MODE = "governed_local_catalog_baseline"

_ICD10_SYSTEM = "ICD-10-CN"
_ICD9_SYSTEM = "ICD-9-CM-3"

# Keep compound dagger/asterisk entries intact because the local catalog
# contains assignable rows such as ``E11.201+N08.3*``.
_ICD10_TEXT_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"([A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?"
    r"(?:\+[A-TV-Z]\d{2}(?:\.[A-Z0-9xX]{1,10})?\*?)?)"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)
_ICD9_TEXT_RE = re.compile(r"(?<![A-Z0-9])(\d{2}\.\d{2,4})(?![A-Z0-9])")


@dataclass(frozen=True)
class CodeRequest:
    code: str
    code_system: str
    role: str


def _normalize_code(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace(" ", "")
        .replace("．", ".")
    )


def _normalize_system(value: Any, *, role: str, code: str) -> str:
    text = str(value or "").strip().upper().replace("_", "-")
    if "ICD-9" in text or "ICD9" in text or role == "procedure":
        return _ICD9_SYSTEM
    if "ICD-10" in text or "ICD10" in text:
        return _ICD10_SYSTEM
    return _ICD10_SYSTEM if code[:1].isalpha() else _ICD9_SYSTEM


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


def _iter_code_values(value: Any) -> Iterable[tuple[Any, str]]:
    if isinstance(value, str):
        yield value, ""
    elif isinstance(value, dict):
        if "code" in value:
            yield value.get("code"), str(value.get("code_system") or "")
    elif isinstance(value, list):
        for item in value:
            yield from _iter_code_values(item)


def _extract_structured(payload: dict[str, Any]) -> list[CodeRequest]:
    requests: list[CodeRequest] = []
    default_system = str(payload.get("code_system") or "")

    def add(value: Any, role: str, explicit_system: str = "") -> None:
        for raw_code, item_system in _iter_code_values(value):
            code = _normalize_code(raw_code)
            if not code:
                continue
            requests.append(CodeRequest(
                code=code,
                code_system=_normalize_system(
                    item_system or explicit_system or default_system,
                    role=role,
                    code=code,
                ),
                role=role,
            ))

    coding_set = payload.get("coding_set")
    if isinstance(coding_set, dict):
        payload = {**payload, **coding_set}

    add(payload.get("primary_diagnosis"), "primary")
    add(payload.get("secondary_diagnoses"), "secondary")
    add(payload.get("procedures"), "procedure", _ICD9_SYSTEM)
    add(payload.get("codes"), "submitted")

    code_assignment = payload.get("code_assignment")
    if isinstance(code_assignment, dict):
        add(code_assignment.get("primary_diagnosis"), "primary")
        add(code_assignment.get("secondary_diagnoses"), "secondary")
        add(code_assignment.get("procedures"), "procedure", _ICD9_SYSTEM)
    return requests


def extract_code_requests(
    input_text: str,
    *,
    structured_input: dict[str, Any] | None = None,
) -> tuple[list[CodeRequest], list[CodeRequest]]:
    """Return unique requests plus duplicates, preserving submission order."""
    structured = dict(structured_input or {})
    parsed = _json_object(input_text)
    if parsed:
        structured = {**structured, **parsed}
    extracted = _extract_structured(structured) if structured else []

    if not extracted:
        for match in _ICD10_TEXT_RE.finditer(str(input_text or "")):
            code = _normalize_code(match.group(1))
            extracted.append(CodeRequest(code, _ICD10_SYSTEM, "submitted"))
        occupied = [match.span(1) for match in _ICD10_TEXT_RE.finditer(str(input_text or ""))]
        for match in _ICD9_TEXT_RE.finditer(str(input_text or "")):
            # Do not reinterpret a decimal substring inside an ICD-10 code.
            if any(start <= match.start(1) < end for start, end in occupied):
                continue
            code = _normalize_code(match.group(1))
            extracted.append(CodeRequest(code, _ICD9_SYSTEM, "procedure"))

    unique: list[CodeRequest] = []
    duplicates: list[CodeRequest] = []
    seen: set[tuple[str, str]] = set()
    for item in extracted:
        key = (item.code_system, item.code)
        if key in seen:
            duplicates.append(item)
            continue
        seen.add(key)
        unique.append(item)
    return unique, duplicates


def _governance_and_loader(code_system: str) -> tuple[dict[str, Any], Any]:
    from app.config import settings
    from app.services.clinical_asset_governance import (
        assert_asset_use_allowed,
        public_governance,
    )

    if code_system == _ICD9_SYSTEM:
        asset_id = ICD9_ASSET_ID
        from app.services.icd9cm3_loader import get_loader
    else:
        asset_id = ICD10_ASSET_ID
        from app.services.icd10cn_loader import get_loader

    asset = assert_asset_use_allowed(
        asset_id,
        deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
        usage="catalog_validation",
        verify_integrity=True,
    )
    return public_governance(asset), get_loader()


def verify_catalog_health() -> dict[str, Any]:
    """Verify both pinned dictionaries and return bounded audit evidence."""
    assets: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for system in (_ICD10_SYSTEM, _ICD9_SYSTEM):
        governance, loader = _governance_and_loader(system)
        assets.append(governance)
        stats = loader.stats()
        counts[system] = int(getattr(stats, "catalog_codes", 0))
    return {
        "integrity_verified": True,
        "assets": assets,
        "catalog_counts": counts,
    }


def _children_count(loader: Any, code: str) -> int:
    prefix = code.rstrip(".") + "."
    try:
        return sum(
            1
            for entry in loader.all_codes()
            if str(getattr(entry, "code", "") or "").startswith(prefix)
        )
    except Exception:
        return 0


def _validate_one(item: CodeRequest, loader: Any) -> dict[str, Any]:
    entry = loader.get(item.code)
    generated_category = bool(
        entry is not None
        and getattr(entry, "is_generated_category", False)
    )
    child_count = (
        _children_count(loader, item.code)
        if entry is None or generated_category
        else 0
    )
    in_catalog = entry is not None or child_count > 0
    assignable = bool(entry is not None and not generated_category)
    catalog_name = str(
        getattr(entry, "name_cn", "") or ""
    ) if entry is not None else ""

    if assignable:
        issue = (
            "命中固定哈希的本地开发目录并标记为可分配；目录来源与许可尚未独立核验，"
            "不可作为医保结算权威结论。"
        )
    elif in_catalog:
        issue = (
            f"该值是目录类别/前缀而非可分配叶子编码（检测到 {child_count} 个更具体条目）；"
            "不得自动选择替代编码。"
        )
    else:
        issue = "未命中固定哈希的本地开发目录；不得据格式推断其有效。"

    return {
        "code": item.code,
        "status": "valid" if assignable else "invalid",
        "in_catalog": in_catalog,
        "assignable": assignable,
        "catalog_name": catalog_name,
        "issue": issue,
        "suggested_replacement": "",
        "code_system": item.code_system,
        "role": item.role,
    }


def _governance_issue(assets: list[dict[str, Any]]) -> dict[str, Any]:
    versions = ", ".join(
        f"{asset['asset_id']}@{asset['version']}" for asset in assets
    )
    return {
        "code": versions,
        "issue": (
            "本次成员关系检查使用固定哈希开发目录；authority_status="
            "source_unverified、license_status=external_review_required。"
            "结果仅限开发验证，不能用于结算、支付或生产自动决策。"
        ),
        "severity": "warning",
        "manual_review_required": True,
    }


def _semantic_scope_issue(codes: list[str]) -> dict[str, Any]:
    return {
        "code": "/".join(codes),
        "issue": (
            "本地基线未判断 Excludes、排序、组合码、伴随编码、年龄/性别、时态或"
            "诊断与病历证据的一致性；这些语义项必须由编码员或受治理的语义增强复核。"
        ),
        "severity": "warning",
        "manual_review_required": True,
    }


def _markdown(
    *,
    conclusion: str,
    validated: list[dict[str, Any]],
    cross_issues: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> str:
    lines = [
        "# 编码校验报告 — 本地治理目录基线",
        "",
        f"## 结论\n\n{conclusion}",
        "",
        "## 逐码目录校验",
        "",
        "| 编码 | 体系 | 状态 | 目录名称 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for item in validated:
        lines.append(
            "| {code} | {system} | {status} | {name} | {issue} |".format(
                code=item["code"],
                system=item["code_system"],
                status=item["status"],
                name=item["catalog_name"] or "—",
                issue=item["issue"],
            )
        )
    if not validated:
        lines.append("| — | — | invalid | — | 未提取到待校验编码 |")
    lines.extend(["", "## 跨码与语义边界", ""])
    for issue in cross_issues:
        lines.append(f"- {issue['issue']}")
    lines.extend(["", "## 目录治理", ""])
    for asset in assets:
        lines.append(
            "- `{asset_id}@{version}`：authority=`{authority}`，"
            "license=`{license}`，billing_authoritative=`{billing}`，"
            "restriction=`{restriction}`。".format(
                asset_id=asset["asset_id"],
                version=asset["version"],
                authority=asset["authority_status"],
                license=asset["license_status"],
                billing=str(asset["billing_authoritative"]).lower(),
                restriction=asset.get("use_restriction") or "",
            )
        )
    lines.extend([
        "",
        "## 人工复核",
        "",
        "始终需要。不得自动写回 EMR/HIS，不得用于医保结算或支付决定。",
    ])
    return "\n".join(lines)


def _unavailable_response(run_id: str, error_type: str) -> dict[str, Any]:
    summary = "治理目录不可用或完整性/使用策略校验失败；编码校验已失败关闭。"
    return {
        "review_conclusion": "FAIL",
        "validated_codes": [],
        "cross_code_issues": [{
            "code": "catalog-governance",
            "issue": summary,
            "severity": "error",
            "manual_review_required": True,
        }],
        "manual_review_required": True,
        "summary": summary,
        "markdown": (
            "# 编码校验报告\n\n## 结论\n\nFAIL\n\n"
            "## 原因\n\n治理目录不可用；未发布任何编码有效性结论。\n\n"
            "## 人工复核\n\nRequired"
        ),
        "runtime_mode": "catalog_governance_unavailable",
        "catalog_governance": {
            "integrity_verified": False,
            "assets": [],
            "error_type": error_type,
        },
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/code-validation-agent@2.0.0",
            "catalog_integrity_verified": False,
        },
    }


async def run_governed_catalog_validation(
    input_text: str,
    *,
    run_id: str = "",
    structured_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the local catalog baseline and return the Agent's internal shape."""
    requests, duplicates = extract_code_requests(
        input_text,
        structured_input=structured_input,
    )
    if not requests:
        summary = "未提取到待校验编码；请提供结构化编码集或明确的 ICD 编码。"
        return {
            "review_conclusion": "FAIL",
            "validated_codes": [],
            "cross_code_issues": [{
                "code": "input",
                "issue": summary,
                "severity": "error",
                "manual_review_required": True,
            }],
            "manual_review_required": True,
            "summary": summary,
            "markdown": "# 编码校验报告\n\n## 结论\n\nFAIL\n\n" + summary,
            "runtime_mode": LOCAL_RUNTIME_MODE,
            "catalog_governance": {
                "integrity_verified": False,
                "assets": [],
                "reason": "no_codes",
            },
            "trace_refs": {
                "run_id": run_id or str(uuid.uuid4()),
                "agent_ref": "icoder/code-validation-agent@2.0.0",
                "catalog_integrity_verified": False,
            },
        }

    systems = list(dict.fromkeys(item.code_system for item in requests))
    governance_by_system: dict[str, dict[str, Any]] = {}
    loaders: dict[str, Any] = {}
    try:
        for system in systems:
            governance, loader = _governance_and_loader(system)
            governance_by_system[system] = governance
            loaders[system] = loader
    except Exception as exc:
        return _unavailable_response(run_id, type(exc).__name__)

    validated = [_validate_one(item, loaders[item.code_system]) for item in requests]
    assets = [governance_by_system[system] for system in systems]
    cross_issues: list[dict[str, Any]] = [_governance_issue(assets)]
    if duplicates:
        duplicate_counts = Counter(item.code for item in duplicates)
        for code, extra_count in sorted(duplicate_counts.items()):
            cross_issues.append({
                "code": code,
                "issue": f"输入中重复提交该编码 {extra_count + 1} 次；请核对是否重复编码。",
                "severity": "warning",
                "manual_review_required": True,
            })
    cross_issues.append(_semantic_scope_issue([item.code for item in requests]))

    invalid_count = sum(item["status"] == "invalid" for item in validated)
    conclusion = "FAIL" if invalid_count else "WARNING"
    versions = ", ".join(
        f"{asset['asset_id']}@{asset['version']}" for asset in assets
    )
    summary = (
        f"已按固定哈希开发目录校验 {len(validated)} 个编码："
        f"{len(validated) - invalid_count} 个目录可分配、{invalid_count} 个未通过。"
        f"目录版本：{versions}；来源与许可未独立核验，必须人工复核。"
    )
    return {
        "review_conclusion": conclusion,
        "validated_codes": validated,
        "cross_code_issues": cross_issues,
        "manual_review_required": True,
        "summary": summary,
        "markdown": _markdown(
            conclusion=conclusion,
            validated=validated,
            cross_issues=cross_issues,
            assets=assets,
        ),
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "catalog_governance": {
            "integrity_verified": True,
            "assets": assets,
        },
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/code-validation-agent@2.0.0",
            "catalog_integrity_verified": True,
            "catalog_asset_ids": [asset["asset_id"] for asset in assets],
            "catalog_asset_versions": [asset["version"] for asset in assets],
            "catalog_authority_statuses": [
                asset["authority_status"] for asset in assets
            ],
            "catalog_license_statuses": [
                asset["license_status"] for asset in assets
            ],
            "semantic_enhancement_used": False,
        },
    }


__all__ = [
    "CodeRequest",
    "ICD10_ASSET_ID",
    "ICD9_ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "extract_code_requests",
    "run_governed_catalog_validation",
    "verify_catalog_health",
]
