"""GroupingExpert tests — the DRG/DIP grouping wedge in isolation.

Covers each per-dimension tool (MDC / ADRG / CC-MCC / DIP) and the top-level group():
severity tiers (none / CC / MCC, MCC wins), surgical vs medical ADRG, DIP score scaling,
and the ungrouped / no-primary fallbacks.
"""
from icoder.experts.grouping_expert import GroupingExpert
from icoder.runtime.types import CodeResult

G = GroupingExpert()


def _c(code: str, ctype: str = "diagnosis") -> CodeResult:
    return CodeResult(system="ICD-10-CN", code=code, display=code, code_type=ctype)


def test_mdc_by_icd_chapter():
    assert G.mdc_of("I50.900")[0] == "MDCF"   # 循环
    assert G.mdc_of("J18.900")[0] == "MDCE"   # 呼吸
    assert G.mdc_of("N18.900")[0] == "MDCL"   # 肾/泌尿
    assert G.mdc_of("E11.900")[0] == "MDCK"   # 内分泌
    assert G.mdc_of("M80.900")[0] == "MDCI"   # 肌肉骨骼
    assert G.mdc_of("Z51.102")[0] == "MDCR"   # Z51 longest-prefix wins (化疗)


def test_adrg_medical_vs_surgical():
    assert G.adrg_of("I50.900", surgical=False)[0] == "FT2"
    assert G.adrg_of("I48.x00", surgical=False)[0] == "FU2"
    # a confirmed endoscopy procedure pulls the case into a surgical ADRG
    assert G.adrg_of("I50.900", surgical=True, procedure_code="45.1600x001")[0] == "GK3"
    # surgical but unknown procedure -> generic operative group
    assert G.adrg_of("I50.900", surgical=True, procedure_code="99.9900")[0] == "GZ1"


def test_cc_level_classification():
    assert G.cc_level("N18.500") == "MCC"
    assert G.cc_level("N18.900") == "CC"
    assert G.cc_level("I50.900") is None


def test_dip_lookup():
    dip = G.dip_of("I50.900")
    assert dip["dip_code"] == "DIP-I50.900"
    assert dip["base_score"] == 285.0
    assert G.dip_of("I99.900") is None


def test_group_no_cc_is_tier_5():
    route = G.group(_c("I50.900", ), secondaries=[], procedures=[])
    assert route.adrg == "FT2"
    assert route.drg == "FT25"
    assert route.cc_mcc is None
    assert route.dip_score == 285.0          # factor 1.0
    assert route.rationale                    # derivation recorded


def test_group_cc_is_tier_3_and_scales_score():
    route = G.group(_c("I50.900"), secondaries=[_c("N18.900")], procedures=[])
    assert route.drg == "FT23"
    assert route.cc_mcc == "CC"
    assert route.dip_score == round(285.0 * 1.15, 1)   # base × CC factor, 1-dp


def test_group_mcc_is_tier_1_and_wins_over_cc():
    route = G.group(
        _c("I50.900"),
        secondaries=[_c("N18.900"), _c("N18.500")],  # CC + MCC -> MCC wins
        procedures=[],
    )
    assert route.drg == "FT21"
    assert route.cc_mcc == "MCC"
    assert route.dip_score == round(285.0 * 1.30, 1)   # base × MCC factor, 1-dp


def test_group_surgical_route():
    route = G.group(_c("I50.900"), secondaries=[], procedures=[_c("45.1600x001", "procedure")])
    assert route.surgical is True
    assert route.adrg == "GK3"
    assert route.drg == "GK35"


def test_group_primary_without_adrg_is_ungrouped_but_keeps_mdc():
    route = G.group(_c("I99.900"), secondaries=[], procedures=[])
    assert route.adrg is None
    assert route.drg is None
    assert route.mdc == "MDCF"               # MDC still derivable from the chapter
    assert "未命中" in route.note


def test_group_no_primary_does_not_group():
    route = G.group(None, secondaries=[], procedures=[])
    assert route.adrg is None
    assert route.drg is None
    assert "无主要诊断" in route.note
