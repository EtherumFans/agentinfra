"""DRG/DIP Compliance RuleSet — production rules with real grouper integration.

Wires `app.services.drg_grouper.group_drg()` into rule validation. Each rule
contributes actionable issues when coding affects DRG grouping or DIP scoring.

Rules:
  DRG001  Primary diagnosis present (required for DRG grouping)
  DRG002  Primary procedure present (for surgical DRG cases)
  DRG003  CC/MCC completeness from secondary diagnoses
  DRG004  Gender consistency (CHS-DRG 1.1 error group YA1)
  DIP001  Diagnosis completeness for DIP scoring
  DIP002  Procedure completeness for DIP scoring
  DIP003  Primary diagnosis-procedure consistency for DIP
"""
from __future__ import annotations

import logging
from compliance_services.rule_engine import BaseRuleSet, RuleValidationResult, RuleIssue

logger = logging.getLogger(__name__)

DRG_DIP_RULES = {
    "DRG001": {
        "name": "主诊断编码缺失",
        "severity": "critical",
        "category": "drg",
        "description": "主诊断是 DRG 分组的入口，缺失将导致无法分组或归入错误组。",
    },
    "DRG002": {
        "name": "主手术/操作编码缺失",
        "severity": "high",
        "category": "drg",
        "description": "如为外科病例，主手术缺失将导致分组至内科组，权重显著降低。",
    },
    "DRG003": {
        "name": "CC/MCC 诊断编码完整性",
        "severity": "medium",
        "category": "drg",
        "description": "次要诊断(合并症/并发症)缺失将影响 DRG 权重计算与 CC/MCC 加成。",
    },
    "DRG004": {
        "name": "性别与诊断编码一致性",
        "severity": "critical",
        "category": "drg",
        "description": "CHS-DRG 1.1 错误组 YA1：主要诊断与患者性别不符将导致入组错误。",
    },
    "DIP001": {
        "name": "诊断编码完整性",
        "severity": "low",
        "category": "dip",
        "description": "DIP 分值计算依赖主要诊断与其他诊断的完整编码。",
    },
    "DIP002": {
        "name": "手术操作编码缺失",
        "severity": "medium",
        "category": "dip",
        "description": "DIP 以「主要诊断 + 主要手术」为分值计算基础，手术缺失直接降低分值。",
    },
    "DIP003": {
        "name": "主诊断与主手术一致性",
        "severity": "high",
        "category": "dip",
        "description": "DIP 分值对照表按主诊+主操组合计算，组合异常（如未编码）将归入低分值组。",
    },
}


class DRGDIPRuleSet(BaseRuleSet):
    """DRG/DIP grouping and scoring rules with real grouper integration."""

    name = "drg_dip"
    rules = DRG_DIP_RULES

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        issues: list[RuleIssue] = []
        fired: list[str] = []
        manual_review_required = False

        # ── Extract input ──
        pd = structured_output.get("primary_diagnosis", {})
        pd_code = pd.get("code", "") if isinstance(pd, dict) else ""
        pd_confidence = pd.get("confidence", 1.0) if isinstance(pd, dict) else 1.0

        secondary = structured_output.get("secondary_diagnoses", [])
        secondary_codes = [s.get("code", "") for s in secondary if isinstance(s, dict)]

        procedures = structured_output.get("procedures", [])
        main_proc = procedures[0] if procedures else None
        main_proc_code = main_proc.get("code", "") if isinstance(main_proc, dict) else ""

        patient_gender = context.get("patient_gender", "") or context.get("gender", "")
        patient_age = context.get("patient_age") or context.get("age")

        # ── Run real grouper (if available) ──
        grouper_result: dict = {}
        try:
            from app.services.drg_grouper import group_drg
            grouper_result = group_drg(
                [pd_code] + secondary_codes if pd_code else [],
                procedure_code=main_proc_code or None,
            )
        except Exception as e:
            logger.debug("DRG grouper unavailable: %s", e)

        # ── DRG001: Primary diagnosis present ──
        fired.append("DRG001")
        if not pd_code:
            issues.append(RuleIssue(
                severity="critical", rule_id="DRG001",
                message="主诊断编码缺失,无法进行 DRG 分组。",
                suggestion="请从病历中提取主要诊断并编码到 ICD-10。",
                category="drg",
            ))
            manual_review_required = True
        else:
            issues.append(RuleIssue(
                severity="info", rule_id="DRG001",
                message=f"主诊断 {pd_code} 将用于 DRG 分组,预测入组 {grouper_result.get('drg', 'N/A')} ({grouper_result.get('drg_name', 'N/A')})。",
                suggestion="如需调整主诊断,请确认 DRG 分组变化。",
                category="drg",
            ))

        # ── DRG002: Surgical case procedure ──
        fired.append("DRG002")
        if not main_proc_code and pd_code and not pd_code.startswith("Z"):
            issues.append(RuleIssue(
                severity="medium", rule_id="DRG002",
                message="未检测到主手术/操作编码。",
                suggestion="如有手术操作(尤其外科病例),请补充 ICD-9-CM-3 编码以避免分组至内科组。",
                category="drg",
            ))
            manual_review_required = True
        elif main_proc_code:
            grp_method = grouper_result.get("grouping_method", "")
            if grp_method == "medical" and not _is_likely_medical_case(pd_code):
                issues.append(RuleIssue(
                    severity="high", rule_id="DRG002",
                    message=f"主手术 {main_proc_code} 未匹配外科 DRG 组,病例按内科分组。",
                    suggestion="请核实手术编码是否正确,或确认是否为非手术病例。",
                    category="drg",
                ))

        # ── DRG003: CC/MCC completeness ──
        fired.append("DRG003")
        if not secondary_codes and pd_code and _cc_likely(pd_code):
            issues.append(RuleIssue(
                severity="medium", rule_id="DRG003",
                message="无次要诊断编码。",
                suggestion=f"主诊断 {pd_code} 常见合并症/并发症(如高血压、糖尿病、心衰等),请检查病历是否遗漏 CC/MCC 编码。",
                category="drg",
            ))
        elif grouper_result.get("cc_level") == "不伴合并症/并发症" and _cc_likely(pd_code):
            issues.append(RuleIssue(
                severity="low", rule_id="DRG003",
                message="当前 DRG 分组为「不伴合并症/并发症」,但该主诊断常合并 CC/MCC。",
                suggestion="请核实是否遗漏了合并症/并发症编码,完善可提升 DRG 权重。",
                category="drg",
            ))

        # ── DRG004: Gender consistency ──
        fired.append("DRG004")
        if pd_code and patient_gender:
            try:
                from app.services.drg_grouper import check_gender_consistency
                gender_check = check_gender_consistency(pd_code, patient_gender)
                if not gender_check.get("consistent"):
                    issues.append(RuleIssue(
                        severity="critical", rule_id="DRG004",
                        message=gender_check.get("message", "性别与诊断不一致"),
                        suggestion="CHS-DRG 1.1 错误组 YA1:请核实患者性别或修正主诊断编码。",
                        category="drg",
                    ))
                    manual_review_required = True
            except Exception as e:
                logger.debug("Gender check unavailable: %s", e)

        # ── DIP001: Diagnosis completeness ──
        fired.append("DIP001")
        if pd_code:
            specificity = _code_specificity(pd_code)
            issues.append(RuleIssue(
                severity="low" if specificity >= 4 else "medium",
                rule_id="DIP001",
                message=f"主诊断 {pd_code} 特异性 {specificity} 位字符。",
                suggestion="DIP 倾向于更特异的编码(≥4 位),如使用 .9 未特指编码会显著降低分值。" if specificity < 4 else "诊断编码特异性良好。",
                category="dip",
            ))

        # ── DIP002: Procedure completeness ──
        fired.append("DIP002")
        if not main_proc_code and pd_code:
            issues.append(RuleIssue(
                severity="medium", rule_id="DIP002",
                message="未检测到主手术/操作编码。",
                suggestion="DIP 以「主要诊断 + 主要手术」为分值计算基础,补充手术编码可显著提升分值。",
                category="dip",
            ))

        # ── DIP003: Primary dx-procedure consistency ──
        fired.append("DIP003")
        if pd_code and main_proc_code and grouper_result.get("coverage"):
            grp_method = grouper_result.get("grouping_method", "")
            if grp_method == "surgical":
                issues.append(RuleIssue(
                    severity="info", rule_id="DIP003",
                    message=f"主诊 {pd_code} + 主操 {main_proc_code} 一致性已通过 grouper 验证,DRG: {grouper_result.get('drg', '')}。",
                    suggestion="DIP 分值计算可基于此 DRG 组合进一步精算。",
                    category="dip",
                ))
            else:
                # medical grouping - no surgery, but main_proc exists: mismatch
                issues.append(RuleIssue(
                    severity="high", rule_id="DIP003",
                    message=f"主手术 {main_proc_code} 与主诊断 {pd_code} 在 grouper 中未形成外科组合。",
                    suggestion="DIP003 警告:主诊+主操组合可能异常,请核实诊断或手术编码。",
                    category="dip",
                ))
                manual_review_required = True
        elif pd_code and main_proc_code and not grouper_result.get("coverage"):
            issues.append(RuleIssue(
                severity="medium", rule_id="DIP003",
                message=f"主诊 {pd_code} + 主操 {main_proc_code} 未在 grouper 中匹配。",
                suggestion="DIP 分值计算前需先确认 DRG 分组,可能编码有误。",
                category="dip",
            ))

        # ── Quality flags ──
        quality_flags = {
            "grouper_coverage": grouper_result.get("coverage", False),
            "grouper_method": grouper_result.get("grouping_method", ""),
            "predicted_drg": grouper_result.get("drg", ""),
            "cc_level": grouper_result.get("cc_level", ""),
        }

        return RuleValidationResult(
            passed=not manual_review_required,
            rule_set="drg_dip",
            total_rules=len(fired),
            rules_fired=fired,
            issues=issues,
            quality_flags=quality_flags,
            manual_review_required=manual_review_required,
        )


# ── Helpers ──


def _is_likely_medical_case(primary_diag: str) -> bool:
    """Heuristic: check if a primary diagnosis typically goes to medical ADRG."""
    if not primary_diag:
        return False
    code = primary_diag.upper()
    # Surgical-prone chapters/prefixes
    surgical_prefixes = ("C", "S", "T",  # neoplasm, injury
                         "K80", "K81", "K82", "K83", "K84", "K85",  # cholecystitis etc.
                         "M16", "M17", "M23", "M75",  # joint issues
                         "I20", "I21", "I25",  # ischemic heart (often PCI)
                         )
    return not any(code.startswith(p) for p in surgical_prefixes)


def _cc_likely(primary_diag: str) -> bool:
    """Heuristic: which primary diagnoses typically have CC/MCC secondary codes."""
    if not primary_diag:
        return False
    code = primary_diag.upper()
    return any(code.startswith(p) for p in (
        "I20", "I21", "I25",  # ischemic heart
        "I50",  # heart failure
        "J18", "J44", "J96",  # pneumonia, COPD, resp failure
        "E11",  # diabetes
        "I63", "I64",  # stroke
        "N17", "N18",  # renal failure
        "A41",  # sepsis
        "K74", "K72",  # liver
    ))


def _code_specificity(code: str) -> int:
    """Return ICD-10 code specificity (total chars including digits, excluding dot).

    - I21 → 3 (category)
    - I21.0 → 4 (subcategory, .9 unspecific is lowest)
    - I50.22 → 6 (subclassification)
    """
    if not code:
        return 0
    return len(code.replace(".", ""))
