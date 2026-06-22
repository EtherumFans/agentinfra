"""RuleEngineAdapter — validates candidate coding results against local rules.

Independent of any LLM provider. Validates MedicalCodingOutputSchema against:
- R001-R012: Coding format and quality rules (implemented)
- DRG001-DRG002: DRG grouping signals (reserved, warning-only)
- DIP001: DIP scoring signals (reserved, warning-only)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from official_agents.medical_coding.schema import (
    CodingEngineAdapter, MedicalCodingOutputSchema, CodingIssue,
)

logger = logging.getLogger(__name__)

ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$")
ICD9_PROCEDURE_PATTERN = re.compile(r"^\d{2}\.\d{1,4}$")

# All rule definitions
RULES = {
    "R001": {"name": "主诊断不能为空", "severity": "critical", "category": "coding"},
    "R002": {"name": "诊断编码格式校验", "severity": "high", "category": "coding"},
    "R003": {"name": "诊断编码重复检测", "severity": "medium", "category": "coding"},
    "R004": {"name": "手术操作编码格式校验", "severity": "high", "category": "coding"},
    "R005": {"name": "手术操作编码重复检测", "severity": "medium", "category": "coding"},
    "R006": {"name": "置信度范围校验 (0-1)", "severity": "low", "category": "quality"},
    "R007": {"name": "低置信度编码触发人工复核", "severity": "high", "category": "quality"},
    "R008": {"name": "编码证据不能为空", "severity": "medium", "category": "quality"},
    "R009": {"name": "主诊断必须来自诊断列表", "severity": "critical", "category": "consistency"},
    "R010": {"name": "primary 角色只能有一个主诊断", "severity": "high", "category": "consistency"},
    "R011": {"name": "primary procedure 最多一个", "severity": "medium", "category": "consistency"},
    "R012": {"name": "critical/high 规则失败触发人工复核", "severity": "high", "category": "safety"},
    # DRG/DIP reserved (warning only, not scored)
    "DRG001": {"name": "主诊断变更可能影响 DRG 分组 (预留)", "severity": "low", "category": "drg_reserved"},
    "DRG002": {"name": "主手术/操作缺失可能影响 DRG 分组 (预留)", "severity": "low", "category": "drg_reserved"},
    "DIP001": {"name": "诊断编码不完整可能影响 DIP 分值 (预留)", "severity": "low", "category": "dip_reserved"},
}


@dataclass
class RuleValidationResult:
    """Result of rule engine validation."""
    passed: bool = True
    total_rules: int = 0
    rules_fired: list[str] = field(default_factory=list)
    issues: list[CodingIssue] = field(default_factory=list)
    quality_flags: dict[str, bool] = field(default_factory=dict)
    manual_review_required: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_rules": self.total_rules,
            "rules_fired": self.rules_fired,
            "issues": [i.to_dict() for i in self.issues],
            "quality_flags": self.quality_flags,
            "manual_review_required": self.manual_review_required,
        }


class RuleEngineAdapter(CodingEngineAdapter):
    """Validates MedicalCodingOutputSchema against local rules.

    Does NOT depend on any LLM provider — pure rule-based validation.
    Can be called standalone or as part of HybridCodingAdapter.
    """

    name = "rule_engine_adapter"

    def __init__(self):
        self._enabled_rules = set(RULES.keys())
        self._drg_reserved = {"DRG001", "DRG002", "DIP001"}

    @property
    def rules(self) -> list[dict]:
        """List all rules with metadata."""
        return [
            {"id": rid, "name": RULES[rid]["name"], "severity": RULES[rid]["severity"],
             "category": RULES[rid]["category"], "enabled": rid in self._enabled_rules}
            for rid in sorted(RULES.keys())
        ]

    @property
    def enabled_rules_count(self) -> int:
        return len(self._enabled_rules - self._drg_reserved)

    @property
    def rules_summary(self) -> dict:
        return {
            "total_rules": len(RULES),
            "enabled_rules": len(self._enabled_rules),
            "implemented_rules": self.enabled_rules_count,
            "reserved_rules": len(self._drg_reserved),
        }

    async def infer_async(
        self, messages=None, tools=None, response_schema=None, context=None,
    ) -> MedicalCodingOutputSchema:
        return MedicalCodingOutputSchema.mock_result()

    def validate(self, coding_output: MedicalCodingOutputSchema) -> RuleValidationResult:
        """Validate coding output against all enabled rules."""
        issues: list[CodingIssue] = []
        fired: list[str] = []
        quality: dict[str, bool] = {
            "invalid_code_format": False,
            "duplicate_codes": False,
            "low_confidence": False,
            "missing_evidence": False,
            "primary_diagnosis_missing": False,
        }

        all_dx = [coding_output.primary_diagnosis] + coding_output.secondary_diagnoses
        active_dx = [d for d in all_dx if d.code]

        # R001: Primary diagnosis required
        fired.append("R001")
        if not coding_output.primary_diagnosis.code:
            issues.append(CodingIssue(severity="critical", code="R001",
                message="主要诊断编码不能为空",
                suggestion="请为病历指定主要诊断 ICD-10 编码"))
            quality["primary_diagnosis_missing"] = True

        # R002: ICD-10 format
        fired.append("R002")
        for dx in all_dx:
            if dx.code and not ICD10_PATTERN.match(dx.code):
                issues.append(CodingIssue(severity="high", code="R002",
                    message=f"诊断编码格式无效: {dx.code}",
                    suggestion=f"{dx.code} 不符合 ICD-10 格式（字母+2位数字+可选.1-4位数字）"))
                quality["invalid_code_format"] = True

        # R003: Duplicate detection
        fired.append("R003")
        seen_codes: dict[str, list[str]] = {}
        for dx in all_dx:
            if dx.code:
                seen_codes.setdefault(dx.code, []).append(dx.description or dx.code)
        for code, descs in seen_codes.items():
            if len(descs) > 1:
                issues.append(CodingIssue(severity="medium", code="R003",
                    message=f"诊断编码重复: {code} 出现 {len(descs)} 次",
                    suggestion="请删除重复的编码条目，每个编码只保留最高置信度的诊断"))
                quality["duplicate_codes"] = True

        # R004: ICD-9-CM-3 procedure format
        fired.append("R004")
        for proc in coding_output.procedures:
            if proc.code and not ICD9_PROCEDURE_PATTERN.match(proc.code):
                issues.append(CodingIssue(severity="high", code="R004",
                    message=f"手术操作编码格式无效: {proc.code}",
                    suggestion=f"{proc.code} 不符合 ICD-9-CM-3 格式（2位数字+小数点+1-4位数字）"))

        # R005: Duplicate procedures
        fired.append("R005")
        seen_proc: dict[str, int] = {}
        for proc in coding_output.procedures:
            if proc.code:
                seen_proc[proc.code] = seen_proc.get(proc.code, 0) + 1
        for code, cnt in seen_proc.items():
            if cnt > 1:
                issues.append(CodingIssue(severity="medium", code="R005",
                    message=f"手术编码重复: {code} 出现 {cnt} 次",
                    suggestion="请删除重复的手术编码条目"))

        # R006: Confidence range
        fired.append("R006")
        for dx in all_dx:
            if dx.code and not (0 <= dx.confidence <= 1):
                issues.append(CodingIssue(severity="low", code="R006",
                    message=f"诊断 {dx.code} 置信度超出范围: {dx.confidence}",
                    suggestion="请输入0-1之间的置信度值"))

        # R007: Low confidence → manual review
        fired.append("R007")
        for dx in all_dx:
            if dx.code and dx.confidence < 0.7:
                quality["low_confidence"] = True
                issues.append(CodingIssue(severity="high", code="R007",
                    message=f"诊断 {dx.code} 置信度偏低 ({dx.confidence})，需要人工复核",
                    suggestion="请人工审核该编码是否正确，或补充病历证据以提高置信度"))
                break  # One flag is enough

        # R008: Evidence required
        fired.append("R008")
        for dx in all_dx:
            if dx.code and not dx.evidence:
                issues.append(CodingIssue(severity="medium", code="R008",
                    message=f"诊断 {dx.code} ({dx.description}) 缺少病历证据引用",
                    suggestion="请从病历原文中引用支持该编码的证据文本"))
                quality["missing_evidence"] = True

        # R009: Primary diagnosis must have a code that appears in diagnoses
        fired.append("R009")
        pd_code = coding_output.primary_diagnosis.code
        if pd_code:
            all_codes = {d.code for d in active_dx}
            if pd_code not in all_codes and len(active_dx) > 1:
                issues.append(CodingIssue(severity="critical", code="R009",
                    message=f"主诊断编码 {pd_code} 不在诊断列表中",
                    suggestion="请确保主要诊断编码包含在诊断编码列表中"))

        # R010: Only one primary diagnosis
        fired.append("R010")
        primary_count = sum(1 for d in all_dx if d.category == "principal" or d.category == "primary")
        if primary_count > 1:
            issues.append(CodingIssue(severity="high", code="R010",
                message=f"发现 {primary_count} 个主诊断，只能有一个",
                suggestion="请只保留一个主要诊断，其余改为次要诊断"))

        # R011: At most one primary procedure
        fired.append("R011")
        primary_proc = sum(1 for p in coding_output.procedures if p.category == "principal")
        if primary_proc > 1:
            issues.append(CodingIssue(severity="medium", code="R011",
                message=f"发现 {primary_proc} 个主要手术/操作，建议不超过一个",
                suggestion="请只保留一个主要手术/操作"))

        # R012: Critical/high → manual review
        fired.append("R012")
        has_critical = any(i.severity in ("critical", "high") for i in issues)
        if has_critical:
            quality["manual_review_required"] = True

        # DRG001-DRG002, DIP001: Reserved (warning-only)
        for rid in ("DRG001", "DRG002", "DIP001"):
            fired.append(rid)

        manual_review = (quality.get("primary_diagnosis_missing", False) or
                        quality.get("manual_review_required", False) or
                        quality.get("low_confidence", False))

        return RuleValidationResult(
            passed=not (quality.get("primary_diagnosis_missing") or quality.get("invalid_code_format")),
            total_rules=len(fired),
            rules_fired=fired,
            issues=issues,
            quality_flags=quality,
            manual_review_required=manual_review,
        )

    def health_check(self) -> dict:
        return {
            "engine": self.name,
            "status": "healthy",
            "rules_available": len(RULES),
            "rules_enabled": len(self._enabled_rules),
            "drg_dip_reserved": len(self._drg_reserved),
        }
