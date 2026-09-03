"""Development-only DRG/DIP risk-review heuristics.

Wires the local candidate heuristic into deterministic validation.  The rule
pack is not an official grouper or payment engine.  It always requires human
review and is barred from billing/settlement use by asset-governance policy.

Rules:
  DRG001  Primary diagnosis present (required for DRG grouping)
  DRG002  Primary procedure present (for surgical DRG cases)
  DRG003  CC/MCC completeness from secondary diagnoses
  DRG004  Diagnosis/gender consistency risk (development heuristic)
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
        "description": "主诊断缺失会阻止候选分组风险复核；最终分组须由获授权引擎完成。",
    },
    "DRG002": {
        "name": "主手术/操作编码缺失",
        "severity": "high",
        "category": "drg",
        "description": "如为外科病例，主手术缺失会影响候选一致性复核；不得据此推断结算权重。",
    },
    "DRG003": {
        "name": "CC/MCC 诊断编码完整性",
        "severity": "medium",
        "category": "drg",
        "description": "次要诊断缺失可能影响候选 CC/MCC 风险提示；仅可依据病历证据补充编码。",
    },
    "DRG004": {
        "name": "性别与诊断编码一致性",
        "severity": "critical",
        "category": "drg",
        "description": "非权威开发规则提示主要诊断与患者性别可能不一致，需人工核实。",
    },
    "DIP001": {
        "name": "诊断编码完整性",
        "severity": "low",
        "category": "dip",
        "description": "诊断完整性会影响 DIP 风险复核；本规则包不计算官方 DIP 分值。",
    },
    "DIP002": {
        "name": "手术操作编码缺失",
        "severity": "medium",
        "category": "dip",
        "description": "手术缺失会影响 DIP 组合风险复核；本规则包不计算支付结果。",
    },
    "DIP003": {
        "name": "主诊断与主手术一致性",
        "severity": "high",
        "category": "dip",
        "description": "主诊与主操组合异常需人工复核；最终判断须使用获授权的地区规则。",
    },
}


class DRGDIPRuleSet(BaseRuleSet):
    """Non-authoritative DRG/DIP risk-review rules."""

    name = "drg_dip"
    rules = DRG_DIP_RULES

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        issues: list[RuleIssue] = []
        fired: list[str] = []
        # The bundled rule pack is explicitly unverified.  A clean heuristic
        # result must never be promoted to an authoritative automatic pass.
        manual_review_required = True

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

        # ── Run development candidate heuristic (if available) ──
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
                message=f"主诊断 {pd_code} 的开发期候选组为 {grouper_result.get('drg', 'N/A')} ({grouper_result.get('drg_name', 'N/A')})，该结果非结算依据。",
                suggestion="请使用获授权的本地区/医院分组器复核；不得为改变分组而调整缺乏病历证据的编码。",
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
                suggestion=f"请仅依据病历证据核实主诊断 {pd_code} 是否遗漏合并症/并发症编码，不得为提高权重补码。",
                category="drg",
            ))
        elif grouper_result.get("cc_level") == "不伴合并症/并发症" and _cc_likely(pd_code):
            issues.append(RuleIssue(
                severity="low", rule_id="DRG003",
                message="当前 DRG 分组为「不伴合并症/并发症」,但该主诊断常合并 CC/MCC。",
                suggestion="请仅依据病历证据核实是否遗漏合并症/并发症编码；不得据此追求分组收益。",
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
                        suggestion="请核实患者性别和主诊断编码；此提示来自非权威开发规则。",
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
                suggestion="如病历证据支持，请选择更特异的编码；不得为分值目的推断未记录事实。" if specificity < 4 else "编码特异性通过开发期格式检查，仍需人工复核。",
                category="dip",
            ))

        # ── DIP002: Procedure completeness ──
        fired.append("DIP002")
        if not main_proc_code and pd_code:
            issues.append(RuleIssue(
                severity="medium", rule_id="DIP002",
                message="未检测到主手术/操作编码。",
                suggestion="如病历确有手术/操作，请依据原始记录补充编码；不得为分值目的补码。",
                category="dip",
            ))

        # ── DIP003: Primary dx-procedure consistency ──
        fired.append("DIP003")
        if pd_code and main_proc_code and grouper_result.get("coverage"):
            grp_method = grouper_result.get("grouping_method", "")
            if grp_method == "surgical":
                issues.append(RuleIssue(
                    severity="info", rule_id="DIP003",
                    message=f"主诊 {pd_code} + 主操 {main_proc_code} 通过开发期启发式匹配，候选组: {grouper_result.get('drg', '')}；并非官方验证。",
                    suggestion="请交由获授权的地区/医院引擎复核，不得使用本结果计算 DIP 分值。",
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
                suggestion="请先由人工及获授权的地区/医院引擎确认编码组合与分组。",
                category="dip",
            ))

        # ── Quality flags ──
        governance = grouper_result.get("governance", {})
        issues.append(RuleIssue(
            severity="info",
            rule_id="DRG_GOVERNANCE",
            message="当前 DRG/DIP 规则包为未验证的开发期风险启发式，不能用于支付或结算。",
            suggestion="必须人工复核，并使用获授权的本地区/医院规则包完成最终分组。",
            category="governance",
        ))
        quality_flags = {
            "grouper_coverage": grouper_result.get("coverage", False),
            "grouper_method": grouper_result.get("grouping_method", ""),
            "predicted_drg": grouper_result.get("drg", ""),
            "candidate_only": True,
            "billing_authoritative": False,
            "cc_level": grouper_result.get("cc_level", ""),
            "rule_pack_id": governance.get("asset_id", ""),
            "rule_pack_version": governance.get("version", ""),
            "authority_status": governance.get("authority_status", "unknown"),
        }

        return RuleValidationResult(
            passed=False,
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
