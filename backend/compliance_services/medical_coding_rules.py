"""Medical Coding RuleSet — ICD-10/ICD-9-CM-3 coding compliance rules.

Implements the BaseRuleSet interface from compliance_services.rule_engine.

Phase 5 Track C Gate 2 §7.2 (2026-07-11): R002 split per code-system.
"""

import re
import logging
from compliance_services.rule_engine import BaseRuleSet, RuleValidationResult, RuleIssue

logger = logging.getLogger(__name__)

# ── Per-code-system patterns (Phase 5 Track C Gate 2 §7.2) ──────────────
# China hospital code systems. Each must be validated separately — no
# single regex can validate all of them.

# WHO ICD-10 (international, 3-5 chars): A00, I21, I21.9, I21.19
# Allows 0-2 decimals (China's mandatory 3-decimal form is captured
# separately as ICD10_CN_6DIGIT_PATTERN).
ICD10_WHO_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,2})?$")

# ICD-10-CN 6-digit (China national clinical, e.g. J15.900, I21.100, S22.000)
# Mandatory exactly 3 digits after the dot (zero-padded to 3).
ICD10_CN_6DIGIT_PATTERN = re.compile(r"^[A-Z]\d{2}\.\d{3}$")

# ICD-10 with x-placeholder (e.g. I21.x00, M80.x01) — used in some
# national clinical versions before subdivision is filled in.
ICD10_X_PLACEHOLDER_PATTERN = re.compile(r"^[A-Z]\d{2}\.x\d{0,3}$", re.IGNORECASE)

# ICD-9-CM-3 procedure (China national 4-digit, e.g. 81.0100, 84.5100)
ICD9_CM3_PATTERN = re.compile(r"^\d{2}\.\d{4}$")

# National clinical version extension (long-form codes with >3 decimals
# or alphanumeric suffixes).
ICD10_CN_CLINICAL_EXT_PATTERN = re.compile(r"^[A-Z]\d{2}\.\d{4,}[A-Za-z0-9]{0,2}$")

# Legacy fallback — kept for backwards compatibility with non-China callers.
ICD10_PATTERN = ICD10_WHO_PATTERN
ICD9_PROCEDURE_PATTERN = ICD9_CM3_PATTERN


def classify_code_system(code: str) -> str:
    """Identify which code-system a code belongs to.

    Returns one of:
      - ``icd10_who``           — WHO ICD-10 (international)
      - ``icd10_cn_6digit``     — China national clinical 6-digit
      - ``icd10_cn_x``          — China x-placeholder (pre-subdivision)
      - ``icd10_cn_clinical_ext`` — China national clinical extension
      - ``icd9_cm3``            — ICD-9-CM-3 procedure
      - ``unknown``             — doesn't match any known system
    """
    if not code:
        return "unknown"
    code = str(code).strip()
    if ICD9_CM3_PATTERN.match(code):
        return "icd9_cm3"
    if ICD10_CN_6DIGIT_PATTERN.match(code):
        return "icd10_cn_6digit"
    if ICD10_X_PLACEHOLDER_PATTERN.match(code):
        return "icd10_cn_x"
    if ICD10_CN_CLINICAL_EXT_PATTERN.match(code):
        return "icd10_cn_clinical_ext"
    if ICD10_WHO_PATTERN.match(code):
        return "icd10_who"
    return "unknown"


def normalize_code(code: str, target_system: str = "icd10_cn_6digit") -> str:
    """Best-effort normalization to a canonical form.

    For icd10_cn_6digit target, pads the decimal part to 3 digits:
      I21.9 → I21.900
      I21.19 → I21.190
      J15.900 → J15.900 (already 3)
    """
    if not code:
        return ""
    code = str(code).strip()
    if target_system == "icd10_cn_6digit":
        m = re.match(r"^([A-Z]\d{2})\.(\d+)$", code)
        if m:
            prefix, decimal = m.group(1), m.group(2)
            return f"{prefix}.{decimal.ljust(3, '0')[:3]}"
    return code


def validate_code_per_system(code: str) -> dict:
    """Phase 5 Track C Gate 2 §7.2 structured code validation.

    Returns:
        {
            "code": str,
            "code_system": str,
            "normalized_code": str,
            "format_valid": bool,
            "catalog_valid": bool | None,  # requires catalog lookup
            "assignable": bool,            # True iff format_valid AND not x-placeholder
        }
    """
    if not code:
        return {
            "code": "",
            "code_system": "unknown",
            "normalized_code": "",
            "format_valid": False,
            "catalog_valid": None,
            "assignable": False,
        }
    code = str(code).strip()
    system = classify_code_system(code)
    format_valid = system != "unknown"
    # x-placeholder is format-valid but NOT assignable (incomplete code).
    assignable = format_valid and system != "icd10_cn_x"
    normalized = normalize_code(code) if system.startswith("icd10") else code
    return {
        "code": code,
        "code_system": system,
        "normalized_code": normalized,
        "format_valid": format_valid,
        "catalog_valid": None,  # set later by catalog-aware caller
        "assignable": assignable,
    }

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

        # R002: ICD-10 per-code-system format (Phase 5 Track C Gate 2 §7.2)
        fired.append("R002")
        for dx in all_dx:
            if isinstance(dx, dict) and dx.get("code"):
                validation = validate_code_per_system(str(dx["code"]))
                # Skip ICD-9-CM-3 here (handled by R004 for procedures).
                if validation["code_system"] == "icd9_cm3":
                    continue
                if not validation["format_valid"]:
                    issues.append(RuleIssue(severity="high", rule_id="R002",
                        message=f"诊断编码格式无效: {dx['code']} (无法识别编码体系)",
                        suggestion="应符合 ICD-10 (WHO/CN-6位/x占位/临床版扩展) 之一",
                        category="coding"))
                    quality["invalid_code_format"] = True
                elif not validation["assignable"]:
                    issues.append(RuleIssue(severity="medium", rule_id="R002",
                        message=f"诊断编码不完整: {dx['code']} (x占位码不可作为最终编码)",
                        suggestion="请补全为 ICD-10-CN 6位码 (例: I21.x00 → I21.100)",
                        category="coding"))
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

        # R004: ICD-9-CM-3 procedure per-code-system format (Phase 5 Track C Gate 2 §7.2)
        fired.append("R004")
        for proc in structured_output.get("procedures", []):
            if isinstance(proc, dict) and proc.get("code"):
                validation = validate_code_per_system(str(proc["code"]))
                # Must be icd9_cm3 specifically (not icd10_*, not unknown).
                if validation["code_system"] != "icd9_cm3":
                    issues.append(RuleIssue(severity="high", rule_id="R004",
                        message=f"手术编码格式无效: {proc['code']} (体系={validation['code_system']})",
                        suggestion="应符合 ICD-9-CM-3 格式 (例: 81.0100)",
                        category="coding"))

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
