"""DRG/DIP Compliance RuleSet — placeholder rules for DRG grouping and DIP scoring validation.

These are BASIC placeholder rules. Real DRG/DIP grouping requires integration
with the national DRG grouper or DIP scoring service.
"""

import logging
from compliance_services.rule_engine import BaseRuleSet, RuleValidationResult, RuleIssue

logger = logging.getLogger(__name__)

DRG_DIP_RULES = {
    "DRG001": {"name": "主诊断变更可能影响 DRG 分组", "severity": "low", "category": "drg"},
    "DRG002": {"name": "主手术/操作缺失可能影响 DRG 分组", "severity": "low", "category": "drg"},
    "DRG003": {"name": "CC/MCC 诊断编码完整性", "severity": "medium", "category": "drg"},
    "DRG004": {"name": "性别与 DRG 分组一致性", "severity": "low", "category": "drg"},
    "DIP001": {"name": "诊断编码不完整可能影响 DIP 分值", "severity": "low", "category": "dip"},
    "DIP002": {"name": "手术操作编码缺失可能影响 DIP 分值", "severity": "medium", "category": "dip"},
    "DIP003": {"name": "主要诊断与主要手术一致性", "severity": "high", "category": "dip"},
}


class DRGDIPRuleSet(BaseRuleSet):
    """DRG/DIP grouping and scoring placeholder rules.

    MVP: Returns warning-level issues only. Does NOT perform real DRG grouping.
    Reserved for integration with national DRG grouper (CN-DRG) or DIP service.
    """

    name = "drg_dip"
    rules = DRG_DIP_RULES

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        issues: list[RuleIssue] = []
        fired: list[str] = []

        pd = structured_output.get("primary_diagnosis", {})
        if isinstance(pd, dict):
            pd_code = pd.get("code", "")
        else:
            pd_code = ""

        procedures = structured_output.get("procedures", [])

        # DRG001: Primary diagnosis present (needed for DRG grouping)
        fired.append("DRG001")
        if pd_code:
            issues.append(RuleIssue(
                severity="low", rule_id="DRG001",
                message=f"主诊断 {pd_code} 将用于 DRG 分组。注意：主诊断编码变更可能影响 DRG 分组结果。",
                suggestion="如需调整主诊断，请确认 DRG 分组变化。", category="drg",
            ))

        # DRG002: Primary procedure for surgical DRG
        fired.append("DRG002")
        has_surgery = any(isinstance(p, dict) and p.get("code") for p in procedures)
        if not has_surgery and pd_code:
            issues.append(RuleIssue(
                severity="low", rule_id="DRG002",
                message="未检测到手术操作编码。如为内科病例，DRG 分组将归入内科组。",
                suggestion="如有手术操作，请补充 ICD-9-CM-3 编码以确保正确 DRG 分组。", category="drg",
            ))

        # DRG003: CC/MCC completeness
        fired.append("DRG003")
        secondary = structured_output.get("secondary_diagnoses", [])
        if isinstance(secondary, list) and len(secondary) == 0 and pd_code:
            issues.append(RuleIssue(
                severity="medium", rule_id="DRG003",
                message="无次要诊断编码。CC/MCC（合并症/并发症）编码缺失将影响 DRG 权重计算。",
                suggestion="请检查病历是否有合并症或并发症需要编码。", category="drg",
            ))

        # DRG004: Gender consistency (placeholder)
        fired.append("DRG004")

        # DIP001: Diagnosis completeness for DIP
        fired.append("DIP001")
        if pd_code:
            issues.append(RuleIssue(
                severity="low", rule_id="DIP001",
                message="诊断编码完整性将影响 DIP 分值计算。",
                suggestion="请确保所有相关诊断均已编码。", category="dip",
            ))

        # DIP002: Procedure for DIP scoring
        fired.append("DIP002")

        # DIP003: Primary dx-procedure consistency
        fired.append("DIP003")

        return RuleValidationResult(
            passed=True, rule_set="drg_dip", total_rules=len(fired),
            rules_fired=fired, issues=issues, quality_flags={},
            manual_review_required=False,
        )
