"""End-to-end runtime tests — the 7-stage AgentRunner over the deterministic provider.

Asserts the load-bearing Corti-style invariants on the sample encounter:
PHI redaction, exact evidence char-spans, primary selection, codes-vs-candidates
separation (high-risk routes to candidates), compliance gate, and DRG routing.
"""
import pytest

from sample_data import SAMPLE_TEXT

from icoder.experts.coding_expert import CodingExpert
from icoder.runtime.gateway import DeterministicProvider, LLMGateway
from icoder.runtime.registry import default_registry
from icoder.runtime.runner import AgentRunner, RulesetMissing

AGENT_ID = "icoder/homepage-coding-review-agent"
DRG_AGENT_ID = "icoder/drg-grouping-review-agent"
REVENUE_AGENT_ID = "icoder/revenue-compliance-review-agent"


def _runner() -> AgentRunner:
    expert = CodingExpert()
    gateway = LLMGateway(DeterministicProvider(expert.lexicon()))
    return AgentRunner(gateway=gateway, agents=default_registry(), expert=expert)


def test_pipeline_has_seven_observed_stages():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    assert [s.stage for s in run.stages] == [
        "ingest", "extract", "retrieve", "verify", "sequence", "group", "compliance",
    ]
    for s in run.stages:
        assert s.tool_run_id
        assert s.duration_ms >= 0.0
    assert run.production_writeback_blocked is True


def test_phi_is_redacted_before_anything_renders():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    assert run.redaction["spans"] >= 3
    assert "张三" not in run.redaction["text"]
    assert "13800001111" not in run.redaction["text"]
    assert "ZY20260613" not in run.redaction["text"]


def test_every_evidence_span_is_exact():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    red = run.redaction["text"]
    spans_seen = 0
    for c in run.codes + run.candidates:
        for ev in c.evidences:
            assert red[ev.start:ev.end] == ev.text
            spans_seen += 1
    assert spans_seen >= 1


def test_primary_is_chf_and_codes_are_not_resorted():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    codes = [c.code for c in run.codes]
    assert codes[0] == "I50.900"
    assert run.codes[0].is_primary is True
    # exactly one primary
    assert sum(1 for c in run.codes if c.is_primary) == 1


def test_high_risk_codes_route_to_candidates_not_merged():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    code_set = {c.code for c in run.codes}
    cand_set = {c.code for c in run.candidates}
    assert "M80.900" in cand_set          # 易错: 骨质疏松伴病理性骨折
    assert "45.1600x001" in cand_set      # 易错: 胃镜活检 (procedure)
    assert code_set.isdisjoint(cand_set)  # never merged
    assert all(c.status == "code" for c in run.codes)
    assert all(c.status == "candidate" for c in run.candidates)


def test_compliance_gate_and_drg_route():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    assert run.compliance.passed is True               # no Critical
    assert run.compliance.human_review_required is True  # high-risk -> Moderate
    assert run.compliance.rule_set == "medical_coding"   # homepage agent: single ruleset
    drg = run.drg_route
    assert drg is not None
    assert drg.adrg == "FT2"
    assert drg.drg == "FT23"            # CC tier (secondaries are CC, none MCC)
    assert drg.mdc == "MDCF"            # I50 -> 循环系统
    assert drg.cc_mcc == "CC"
    assert drg.surgical is False        # only procedure (胃镜) is high-risk -> candidate
    assert drg.dip_code == "DIP-I50.900"
    assert drg.dip_score and drg.dip_score > 285.0  # base 285 scaled up by CC factor
    assert drg.rationale                # step-by-step derivation recorded


def test_second_agent_adds_drg_dip_ruleset():
    """The DRG/DIP agent reuses the same Experts + pipeline; only its rule_sets differ.
    This proves the agents×experts split scales to a second thin Agent."""
    run = _runner().run(DRG_AGENT_ID, SAMPLE_TEXT)
    assert run.agent_id == DRG_AGENT_ID
    assert run.codes[0].code == "I50.900"               # same sequencing as agent #1
    assert run.compliance.rule_set == "medical_coding+drg_dip"
    assert "drg_dip" in run.versions.ruleset_version
    rule_ids = {h.rule_id for h in run.compliance.hits}
    assert "DG-R004" in rule_ids                        # M80.900 (CC) in candidates -> 疑似低靠组
    assert run.drg_route.dip_code == "DIP-I50.900"


def test_homepage_agent_does_not_fire_drg_dip_rules():
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    rule_ids = {h.rule_id for h in run.compliance.hits}
    assert not any(r.startswith("DG-") or r.startswith("DIP-") for r in rule_ids)


def test_third_agent_folds_all_four_compliance_domains():
    """The capstone Agent stacks all four wired rule sets on the same Experts/pipeline —
    proving the RuleEngine folds an arbitrary number of compliance domains."""
    run = _runner().run(REVENUE_AGENT_ID, SAMPLE_TEXT)
    assert run.agent_id == REVENUE_AGENT_ID
    assert run.codes[0].code == "I50.900"          # same sequencing as agents #1/#2
    assert run.compliance.rule_set == \
        "medical_coding+drg_dip+insurance_audit+document_evidence"
    for dom in ("medical_coding", "drg_dip", "insurance_audit", "document_evidence"):
        assert dom in run.versions.ruleset_version
    rule_ids = {h.rule_id for h in run.compliance.hits}
    assert "IA-R002" in rule_ids                   # 结算: 候选胃镜活检 -> 结算路径变化
    assert "DG-R004" in rule_ids                   # 分组: M80.900(CC) 候选 -> 疑似低靠组
    assert run.compliance.passed is True           # no Critical
    assert run.compliance.human_review_required is True
    assert run.drg_route.dip_code == "DIP-I50.900"  # route unchanged by the extra domains


def test_homepage_agent_does_not_fire_new_domain_rules():
    """Adding domains to the runtime must NOT change the existing single-ruleset agents."""
    run = _runner().run(AGENT_ID, SAMPLE_TEXT)
    rule_ids = {h.rule_id for h in run.compliance.hits}
    assert not any(r.startswith("IA-") or r.startswith("DE-") for r in rule_ids)
    assert run.compliance.rule_set == "medical_coding"


def test_missing_ruleset_refuses_to_run():
    with pytest.raises(RulesetMissing):
        _runner().run(AGENT_ID, SAMPLE_TEXT, rule_set=None)


def test_unknown_agent_raises_keyerror():
    with pytest.raises(KeyError):
        _runner().run("icoder/does-not-exist", SAMPLE_TEXT)
