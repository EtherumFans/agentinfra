"""MedicalCodingRuleSet tests — the domain compliance gate in isolation.

R001 evidence-grounded (Critical), R003 catalog membership (Critical),
R002/MC-R-M80-001 high-risk human review (Moderate), R004 primary required (Moderate).
passed := no Critical;  human_review_required := any Critical or Moderate.
"""
from icoder.experts.compliance import (
    DocumentEvidenceRuleSet,
    DrgDipRuleSet,
    InsuranceAuditRuleSet,
    MedicalCodingRuleSet,
    RuleContext,
    RuleEngine,
)
from icoder.experts.grouping_expert import GroupingExpert
from icoder.runtime.types import CodeResult, Evidence

RS = MedicalCodingRuleSet()
G = GroupingExpert()
DRG_RS = DrgDipRuleSet(G)
INS_RS = InsuranceAuditRuleSet()
DOC_RS = DocumentEvidenceRuleSet()


def _c(code: str, ev: bool = True, primary: bool = False, hr: bool = False,
       ctype: str = "diagnosis", system: str = "ICD-10-CN") -> CodeResult:
    return CodeResult(
        system=system, code=code, display=code, code_type=ctype,
        confidence=0.9, is_primary=primary, high_risk=hr,
        evidences=[Evidence(start=0, end=2, text="证据")] if ev else [],
    )


def _rule_ids(gate) -> set[str]:
    return {h.rule_id for h in gate.hits}


def test_clean_case_passes_without_review():
    gate = RS.evaluate([_c("I50.900", primary=True)], [])
    assert gate.passed is True
    assert gate.human_review_required is False
    assert gate.hits == []


def test_high_risk_candidate_forces_review_but_still_passes():
    gate = RS.evaluate([_c("I50.900", primary=True)], [_c("M80.900", hr=True)])
    assert gate.passed is True                  # Moderate does not block
    assert gate.human_review_required is True
    assert "MC-R-M80-001" in _rule_ids(gate)    # M80 prefix -> specific rule id


def test_non_m80_high_risk_uses_generic_rule_id():
    gate = RS.evaluate([_c("I50.900", primary=True)], [_c("45.1600x001", hr=True, ctype="procedure", system="ICD-9-CM-3")])
    assert gate.human_review_required is True
    assert "MC-R-HR-001" in _rule_ids(gate)


def test_missing_evidence_is_critical_and_blocks():
    gate = RS.evaluate([_c("I50.900", ev=False, primary=True)], [])
    assert gate.passed is False
    hit = next(h for h in gate.hits if h.rule_id == "R001")
    assert hit.severity == "Critical"


def test_non_catalog_code_is_critical():
    gate = RS.evaluate([_c("ZZZ.000", primary=True)], [])
    assert gate.passed is False
    assert "R003" in _rule_ids(gate)


def test_no_primary_is_moderate():
    gate = RS.evaluate([_c("I50.900", primary=False)], [])
    assert gate.passed is True
    assert gate.human_review_required is True
    assert "R004" in _rule_ids(gate)


# ---- drg_dip rule set (the grouping-compliance wedge) ----

def _route(primary, secondaries=(), procedures=()):
    return G.group(primary, list(secondaries), list(procedures))


def _drg_ids(ctx) -> set[str]:
    return {h.rule_id for h in DRG_RS.check(ctx)}


def test_drg_no_primary_cannot_be_grouped():
    ctx = RuleContext(codes=[_c("N18.900")], candidates=[], primary=None, grouping=None)
    assert "DG-R001" in _drg_ids(ctx)


def test_drg_cc_sitting_in_candidates_flags_undercoding():
    primary = _c("I50.900", primary=True)
    ctx = RuleContext(codes=[primary], candidates=[_c("M80.900", hr=True)],
                      primary=primary, grouping=_route(primary))
    assert "DG-R004" in _drg_ids(ctx)   # M80.900 is a CC -> 确认后上调严重度 (疑似低靠组)


def test_drg_primary_without_adrg_is_ambiguous():
    primary = _c("I99.900", primary=True)   # not in the ADRG table
    route = _route(primary)
    assert route.drg is None
    ctx = RuleContext(codes=[primary], candidates=[], primary=primary, grouping=route)
    assert "DG-R005" in _drg_ids(ctx)


def test_dip_primary_not_in_local_catalog():
    primary = _c("I66.901", primary=True)   # has ADRG (BR2) but no DIP entry
    route = _route(primary)
    assert route.drg is not None
    assert route.dip_code is None
    ctx = RuleContext(codes=[primary], candidates=[], primary=primary, grouping=route)
    assert "DIP-R001" in _drg_ids(ctx)


def test_rule_engine_folds_medical_coding_and_drg_dip():
    primary = _c("I50.900", primary=True)
    secondary = _c("N18.900")
    ctx = RuleContext(
        codes=[primary, secondary],
        candidates=[_c("M80.900", hr=True)],
        primary=primary,
        grouping=_route(primary, secondaries=[secondary]),
    )
    gate = RuleEngine([MedicalCodingRuleSet(), DrgDipRuleSet(G)]).evaluate(ctx)
    assert gate.rule_set == "medical_coding+drg_dip"
    ids = {h.rule_id for h in gate.hits}
    assert "MC-R-M80-001" in ids   # medical_coding: high-risk M80 in candidates
    assert "DG-R004" in ids        # drg_dip: M80 is a CC -> 疑似低靠组
    assert gate.passed is True                  # no Critical
    assert gate.human_review_required is True   # Moderate hits present


# ---- document_evidence rule set (病历合规：病历是否支撑计费) ----

def _doc_ids(ctx) -> set[str]:
    return {h.rule_id for h in DOC_RS.check(ctx)}


def test_doc_primary_without_evidence_flags_de_r001():
    primary = _c("I50.900", ev=False, primary=True)
    ctx = RuleContext(codes=[primary], primary=primary)
    assert "DE-R001" in _doc_ids(ctx)   # 主诊断缺病历证据锚点


def test_doc_procedure_without_operative_evidence_flags_de_r002():
    proc = CodeResult(system="ICD-9-CM-3", code="45.1600x001", display="胃镜活检",
                      code_type="procedure", confidence=0.9,
                      evidences=[Evidence(start=0, end=5, text="患者诉腹痛")])  # 无手术记录类证据
    ctx = RuleContext(codes=[proc])
    assert "DE-R002" in _doc_ids(ctx)


def test_doc_procedure_with_operative_evidence_is_clean():
    proc = CodeResult(system="ICD-9-CM-3", code="45.1600x001", display="胃镜活检",
                      code_type="procedure", confidence=0.9,
                      evidences=[Evidence(start=0, end=7, text="胃镜检查及活检")])  # 镜/活检 -> 手术记录类
    ctx = RuleContext(codes=[proc])
    assert "DE-R002" not in _doc_ids(ctx)


def test_doc_anchored_primary_no_procedure_is_clean():
    primary = _c("I50.900", primary=True)   # 有证据
    ctx = RuleContext(codes=[primary], primary=primary)
    assert _doc_ids(ctx) == set()


# ---- insurance_audit rule set (结算合规：医保支付/结算路径) ----

def _ins_ids(ctx) -> set[str]:
    return {h.rule_id for h in INS_RS.check(ctx)}


def test_ins_confirmed_surgical_procedure_needs_authorization_ia_r001():
    primary = _c("I50.900", primary=True)
    proc = _c("45.1600x001", ctype="procedure", system="ICD-9-CM-3")   # 已确认手术 -> 外科组
    route = _route(primary, procedures=[proc])
    assert route.surgical is True
    ctx = RuleContext(codes=[primary, proc], primary=primary, grouping=route)
    ids = _ins_ids(ctx)
    assert "IA-R001" in ids        # 须核验医保支付资质/术前授权
    assert "IA-R002" not in ids    # candidates 为空


def test_ins_candidate_procedure_changes_settlement_path_ia_r002():
    primary = _c("I50.900", primary=True)
    route = _route(primary)        # 无确认手术 -> 内科组
    assert route.surgical is False
    cand = _c("45.1600x001", hr=True, ctype="procedure", system="ICD-9-CM-3")
    ctx = RuleContext(codes=[primary], candidates=[cand], primary=primary, grouping=route)
    ids = _ins_ids(ctx)
    assert "IA-R002" in ids        # 确认后内科组→外科组，改变支付
    assert "IA-R001" not in ids    # 无确认手术


def test_rule_engine_folds_all_four_domains():
    """The capstone composition: RuleEngine folds 4 rule sets into one gate + label."""
    primary = _c("I50.900", primary=True)
    cand_proc = _c("45.1600x001", hr=True, ctype="procedure", system="ICD-9-CM-3")
    ctx = RuleContext(codes=[primary], candidates=[cand_proc],
                      primary=primary, grouping=_route(primary))
    gate = RuleEngine([MedicalCodingRuleSet(), DrgDipRuleSet(G),
                       InsuranceAuditRuleSet(), DocumentEvidenceRuleSet()]).evaluate(ctx)
    assert gate.rule_set == "medical_coding+drg_dip+insurance_audit+document_evidence"
    ids = {h.rule_id for h in gate.hits}
    assert "MC-R-HR-001" in ids    # medical_coding domain (high-risk candidate)
    assert "IA-R002" in ids        # insurance_audit domain (candidate procedure)
    assert gate.passed is True                  # no Critical
    assert gate.human_review_required is True   # Moderate hits present


def test_rule_engine_requires_at_least_one_ruleset():
    import pytest
    with pytest.raises(ValueError):
        RuleEngine([])
