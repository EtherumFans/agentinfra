"""Medical Coding RuleSet — ICD-10/ICD-9-CM-3 coding compliance rules.

Implements the BaseRuleSet interface from compliance_services.rule_engine.
"""

import re
import logging
from compliance_services.rule_engine import BaseRuleSet, RuleValidationResult, RuleIssue

logger = logging.getLogger(__name__)

ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$")
ICD9_PROCEDURE_PATTERN = re.compile(r"^\d{2}\.\d{1,4}$")

MEDICAL_CODING_RULES = {
    "R001": {"name": "主诊断不能为空", "severity": "critical", "category": "coding"},
    "R002": {"name": "诊断编码格式校验", "severity": "high", "category": "coding"},
    "R003": {"name": "诊断编码重复检测", "severity": "medium", "category": "coding"},
    "R004": {"name": "手术操作编码格式校验", "severity": "high", "category": "coding"},
    "R005": {"name": "手术操作编码重复检测", "severity": "medium", "category": "coding"},
    "R006": {"name": "置信度范围校验 (0-1)", "severity": "low", "category": "quality"},
    "R007": {"name": "低置信度编码触发人工复核", "severity": "high", "category": "quality"},
    "R008": {"name": "每个编码必须有 evidence", "severity": "medium", "category": "quality"},
    "R009": {"name": "主诊断必须来自 diagnosis_codes", "severity": "critical", "category": "consistency"},
    "R010": {"name": "primary 角色只能有一个主诊断", "severity": "high", "category": "consistency"},
    "MC-R-M80-001": {"name": "骨质疏松骨折应优先评估 M80.x", "severity": "medium", "category": "coding_specific"},
    "MC-R-REPAIR-001": {"name": "Rule violations trigger RepairLoop", "severity": "high", "category": "repair"},
}


class MedicalCodingRuleSet(BaseRuleSet):
    """ICD-10/ICD-9-CM-3 medical coding validation rules."""

    name = "medical_coding"
    rules = MEDICAL_CODING_RULES

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        issues: list[RuleIssue] = []
        fired: list[str] = []
        quality: dict[str, bool] = {
            "invalid_code_format": False, "duplicate_codes": False,
            "low_confidence": False, "missing_evidence": False,
            "primary_diagnosis_missing": False,
        }

        pd = structured_output.get("primary_diagnosis", {})
        if isinstance(pd, dict):
            all_dx = [pd] + structured_output.get("secondary_diagnoses", [])
        else:
            all_dx = [{"code": ""}]
            pd = {"code": ""}

        # R001: Primary diagnosis required
        fired.append("R001")
        if not pd.get("code"):
            issues.append(RuleIssue(severity="critical", rule_id="R001",
                message="主要诊断编码不能为空", suggestion="请指定主要诊断 ICD-10 编码", category="coding"))
            quality["primary_diagnosis_missing"] = True

        # R002: ICD-10 format
        fired.append("R002")
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code") and not ICD10_PATTERN.match(str(dx["code"])):
                issues.append(RuleIssue(severity="high", rule_id="R002",
                    message=f"诊断编码格式无效: {dx['code']}", suggestion="应符合 ICD-10 格式", category="coding"))
                quality["invalid_code_format"] = True

        # R003: Duplicate detection
        fired.append("R003")
        seen: dict[str, int] = {}
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code"):
                seen[dx["code"]] = seen.get(dx["code"], 0) + 1
        for code, cnt in seen.items():
            if cnt > 1:
                issues.append(RuleIssue(severity="medium", rule_id="R003",
                    message=f"诊断编码重复: {code} 出现 {cnt} 次", suggestion="请删除重复编码", category="coding"))
                quality["duplicate_codes"] = True

        # R004: ICD-9-CM-3 procedure format
        fired.append("R004")
        for proc in structured_output.get("procedures", []):
            if isinstance(proc, dict) and proc.get("code") and not ICD9_PROCEDURE_PATTERN.match(str(proc["code"])):
                issues.append(RuleIssue(severity="high", rule_id="R004",
                    message=f"手术编码格式无效: {proc['code']}", suggestion="应符合 ICD-9-CM-3 格式", category="coding"))

        # R005: Duplicate procedures
        fired.append("R005")
        seen_p: dict[str, int] = {}
        for proc in structured_output.get("procedures", []):
            if isinstance(proc, dict) and proc.get("code"):
                seen_p[proc["code"]] = seen_p.get(proc["code"], 0) + 1
        for code, cnt in seen_p.items():
            if cnt > 1:
                issues.append(RuleIssue(severity="medium", rule_id="R005",
                    message=f"手术编码重复: {code}", suggestion="请删除重复编码", category="coding"))

        # R006: Confidence range
        fired.append("R006")
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code"):
                conf = dx.get("confidence", 1.0)
                if not (0 <= conf <= 1):
                    issues.append(RuleIssue(severity="low", rule_id="R006",
                        message=f"置信度超出范围: {conf}", suggestion="请输入0-1之间的值", category="quality"))

        # R007: Low confidence → manual review
        fired.append("R007")
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code") and dx.get("confidence", 1.0) < 0.7:
                quality["low_confidence"] = True
                issues.append(RuleIssue(severity="high", rule_id="R007",
                    message=f"诊断 {dx['code']} 置信度偏低 ({dx.get('confidence')})，需人工复核",
                    suggestion="请人工审核该编码或补充证据", category="quality"))
                break

        # R008: Evidence required
        fired.append("R008")
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code") and not dx.get("evidence"):
                issues.append(RuleIssue(severity="medium", rule_id="R008",
                    message=f"诊断 {dx.get('code')} 缺少证据引用",
                    suggestion="请从病历中引用证据文本", category="quality"))
                quality["missing_evidence"] = True

        # R009: Primary diagnosis must come from diagnosis list
        fired.append("R009")
        pd_code = pd.get("code", "")
        if pd_code and len(all_dx) > 1:
            all_codes = {d.get("code") for d in all_dx if isinstance(d, dict)}
            if pd_code not in all_codes:
                issues.append(RuleIssue(severity="critical", rule_id="R009",
                    message=f"主诊断 {pd_code} 不在诊断列表中",
                    suggestion="请确保主诊断包含在完整诊断列表中", category="consistency"))

        # R010: Only one primary diagnosis
        fired.append("R010")
        primary_count = sum(1 for d in all_dx if isinstance(d, dict) and d.get("category") in ("principal", "primary"))
        if primary_count > 1:
            issues.append(RuleIssue(severity="high", rule_id="R010",
                message=f"发现 {primary_count} 个主诊断，只能有一个",
                suggestion="请只保留一个主要诊断，其余改为次要诊断", category="consistency"))

        # MC-R-M80-001: Osteoporosis + vertebral fracture → check M80.x
        fired.append("MC-R-M80-001")
        encounter_text = context.get("encounter_text", "")
        if encounter_text:
            has_osteoporosis = any(kw in encounter_text for kw in ["骨质疏松", "骨量减少", "骨密度降低"])
            has_vertebral_fx = any(kw in encounter_text for kw in ["椎体压缩骨折", "椎体骨折", "病理性骨折", "压缩性骨折", "椎体新鲜压缩骨折"])
            # Age detection: "XX岁" where XX >= 50, or explicit keywords
            age_match = re.search(r'(\d{2,3})岁', encounter_text)
            is_elderly = (age_match and int(age_match.group(1)) >= 50) if age_match else False
            has_risk_keywords = any(kw in encounter_text for kw in ["老年", "轻微外伤", "无明显外伤", "低能量", "绝经", "骨质疏松症", "重度骨质疏松"])
            is_risk_profile = has_osteoporosis and has_vertebral_fx and (is_elderly or has_risk_keywords)
            if is_risk_profile:
                pd_code_check = pd.get("code", "")
                if pd_code_check and not pd_code_check.startswith("M80"):
                    issues.append(RuleIssue(
                        severity="medium", rule_id="MC-R-M80-001",
                        message=f"骨质疏松+椎体骨折+高龄风险组合：当前主诊断为 {pd_code_check}，建议优先评估 M80.x（骨质疏松伴病理性骨折）",
                        suggestion="患者同时存在骨质疏松和椎体压缩骨折，应优先考虑 M80.0 骨质疏松性病理性骨折，而非单纯按解剖部位编码（M48.x）",
                        category="coding_specific",
                    ))
                    quality["osteoporosis_coding_risk"] = True

        manual_review = quality.get("primary_diagnosis_missing") or quality.get("low_confidence")
        has_critical = any(i.severity in ("critical", "high") for i in issues)

        return RuleValidationResult(
            passed=not quality["primary_diagnosis_missing"] and not quality["invalid_code_format"],
            rule_set="medical_coding", total_rules=len(fired),
            rules_fired=fired, issues=issues, quality_flags=quality,
            manual_review_required=manual_review or has_critical,
        )
