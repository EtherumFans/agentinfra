"""Compliance Services — domain rule sets + a small multi-ruleset RuleEngine.

A RuleSet inspects a RuleContext and emits RuleHits (it does NOT decide pass/fail).
The RuleEngine runs one or more RuleSets and folds their hits into a single
ComplianceGate (passed := no Critical; human_review_required := any Critical or Moderate).

  medical_coding   — evidence-grounded / catalog membership / high-risk review / primary required
  drg_dip          — grouping compliance: groupability, CC/MCC undercoding, DIP catalog
  insurance_audit  — settlement/医保 payment: surgical-procedure authorization, settlement-path change
  document_evidence — 病历 substantiation: primary anchored, procedures backed by operative notes

This mirrors iCoDer's reserved compliance domains (medical_coding, drg_dip,
insurance_audit, charge_compliance, document_evidence) — four are wired here; the
RuleEngine folds any subset an Agent declares via ``agent.rule_sets``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..runtime.types import CodeResult, ComplianceGate, DrgRoute, RuleHit
from .catalog import CATALOG, HIGH_RISK
from .grouping_expert import GroupingExpert

RULESET_VERSION = "medical_coding@1.0.0"


@dataclass
class RuleContext:
    """Everything a rule set may need to inspect, assembled once by the runner."""
    codes: list[CodeResult] = field(default_factory=list)
    candidates: list[CodeResult] = field(default_factory=list)
    primary: CodeResult | None = None
    grouping: DrgRoute | None = None


class MedicalCodingRuleSet:
    rule_set = "medical_coding"
    version = RULESET_VERSION

    def check(self, ctx: RuleContext) -> list[RuleHit]:
        hits: list[RuleHit] = []

        # R001 — every billable code must be evidence-grounded
        for c in ctx.codes:
            if not c.evidences:
                hits.append(RuleHit(rule_id="R001", severity="Critical",
                                    message=f"码 {c.code} 缺少证据支撑（不可计费）", code=c.code))

        # R003 — catalog membership (hallucination guard)
        for c in ctx.codes + ctx.candidates:
            if c.code not in CATALOG:
                hits.append(RuleHit(rule_id="R003", severity="Critical",
                                    message=f"码 {c.code} 不在 ICD-10-CN/ICD-9-CM-3 目录内", code=c.code))

        # R002 / MC-R-M80-001 — high-risk 易错码强制人工复核 (high-risk codes route to candidates)
        for c in ctx.codes + ctx.candidates:
            if c.code in HIGH_RISK:
                rid = "MC-R-M80-001" if c.code.startswith("M80") else "MC-R-HR-001"
                hits.append(RuleHit(rule_id=rid, severity="Moderate",
                                    message=f"高风险易错码 {c.code} 需人工复核", code=c.code))

        # R004 — at least one primary diagnosis
        if ctx.codes and not any(c.is_primary for c in ctx.codes):
            hits.append(RuleHit(rule_id="R004", severity="Moderate", message="未确定主要诊断"))

        return hits

    def evaluate(self, codes: list[CodeResult], candidates: list[CodeResult]) -> ComplianceGate:
        """Standalone gate (single ruleset) — kept for direct use + back-compat."""
        return RuleEngine([self]).evaluate(
            RuleContext(codes=codes, candidates=candidates,
                        primary=next((c for c in codes if c.is_primary), None))
        )


class DrgDipRuleSet:
    """Grouping-compliance rules — the iCoDer wedge Corti has no analog for."""
    rule_set = "drg_dip"
    version = "drg_dip@1.0.0"

    def __init__(self, grouper: GroupingExpert | None = None):
        self._g = grouper or GroupingExpert()

    def check(self, ctx: RuleContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        g = ctx.grouping

        # DG-R001 — coded but no primary -> cannot be grouped
        if ctx.codes and ctx.primary is None:
            hits.append(RuleHit(rule_id="DG-R001", severity="Moderate",
                                message="无主要诊断，病例无法入组 DRG/DIP"))

        # DG-R005 — primary present but did not hit a concrete ADRG (ambiguous / ungrouped)
        if g is not None and ctx.primary is not None and not g.drg:
            hits.append(RuleHit(rule_id="DG-R005", severity="Informational",
                                message=f"主诊断 {ctx.primary.code} 未命中具体 ADRG，落入歧义/未入组",
                                code=ctx.primary.code))

        # DG-R004 — a CC/MCC sitting unconfirmed in candidates would lift the DRG severity
        # tier once confirmed (suspected undercoding / 低靠组)
        for c in ctx.candidates:
            lvl = self._g.cc_level(c.code)
            if lvl:
                hits.append(RuleHit(rule_id="DG-R004", severity="Moderate",
                                    message=f"合并症/并发症 {c.code}（{lvl}）待人工确认；"
                                            f"确认后将上调 DRG 严重度（疑似低靠组）", code=c.code))

        # DIP-R001 — primary not in the local DIP catalog
        if g is not None and ctx.primary is not None and not g.dip_code:
            hits.append(RuleHit(rule_id="DIP-R001", severity="Informational",
                                message=f"主诊断 {ctx.primary.code} 未在示例 DIP 目录", code=ctx.primary.code))

        return hits


# Operative-context terms — a *confirmed* procedure code should be substantiated by
# operative-note-like evidence, not merely a passing mention in the chart.
_OPERATIVE_TERMS = ("手术", "术", "操作", "镜", "活检", "切除", "置入", "引流", "穿刺", "缝合", "造影", "插管")


class DocumentEvidenceRuleSet:
    """病历合规 — does the medical record substantiate each billable code?

    Distinct angle from medical_coding R001 (which blocks any evidence-less billable
    code as Critical): this domain checks substantiation *quality* — the primary must be
    anchored in the chart, and a confirmed procedure must be backed by an operative note —
    surfacing 病历缺口 for the coder to complete rather than blocking billing outright.
    """
    rule_set = "document_evidence"
    version = "document_evidence@1.0.0"

    def check(self, ctx: RuleContext) -> list[RuleHit]:
        hits: list[RuleHit] = []

        # DE-R001 — the primary diagnosis must be anchored in the de-identified chart
        if ctx.primary is not None and not ctx.primary.evidences:
            hits.append(RuleHit(rule_id="DE-R001", severity="Moderate",
                                message=f"主要诊断 {ctx.primary.code} 缺少病历证据锚点，病历未充分支撑",
                                code=ctx.primary.code))

        # DE-R002 — a confirmed procedure must be backed by operative-note-like evidence
        for c in ctx.codes:
            if c.code_type != "procedure":
                continue
            ev_text = " ".join(e.text for e in c.evidences)
            if not any(term in ev_text for term in _OPERATIVE_TERMS):
                hits.append(RuleHit(rule_id="DE-R002", severity="Moderate",
                                    message=f"手术/操作码 {c.code} 缺少手术记录类证据，病历不足以支撑计费",
                                    code=c.code))

        return hits


class InsuranceAuditRuleSet:
    """结算合规 — settlement / 医保 payment risk on top of the grouped route.

    The revenue-closest domain (and a China wedge Corti's cloud has no analog for):
    a *confirmed* surgical procedure needs payment authorization before settlement;
    a *candidate* procedure would change the settlement path (内科组 → 外科组) and the
    payable amount once confirmed. It reads the DRG/DIP route the grouper already derived.
    """
    rule_set = "insurance_audit"
    version = "insurance_audit@1.0.0"

    def check(self, ctx: RuleContext) -> list[RuleHit]:
        hits: list[RuleHit] = []
        g = ctx.grouping

        # IA-R001 — a confirmed procedure routed into a surgical DRG must clear medical-
        # insurance payment eligibility / pre-authorization before settlement
        if g is not None and g.surgical:
            for c in ctx.codes:
                if c.code_type == "procedure":
                    hits.append(RuleHit(rule_id="IA-R001", severity="Moderate",
                                        message=f"确认手术 {c.code} 进入外科组 {g.drg or '-'}，"
                                                f"结算前须核验医保支付资质与术前授权", code=c.code))

        # IA-R002 — an unconfirmed (candidate) procedure would shift the settlement path
        # (内科组 → 外科组) and the payable amount once confirmed; review before settling
        for c in ctx.candidates:
            if c.code_type == "procedure":
                hits.append(RuleHit(rule_id="IA-R002", severity="Moderate",
                                    message=f"候选手术 {c.code} 未确认；确认后将改变结算路径"
                                            f"（内科组→外科组）与支付金额，结算前须复核", code=c.code))

        return hits


class RuleEngine:
    """Runs a list of rule sets and folds their hits into one ComplianceGate."""

    def __init__(self, rulesets: list):
        if not rulesets:
            raise ValueError("RuleEngine requires at least one rule set")
        self.rulesets = rulesets

    def evaluate(self, ctx: RuleContext) -> ComplianceGate:
        hits: list[RuleHit] = []
        for rs in self.rulesets:
            hits.extend(rs.check(ctx))
        critical = any(h.severity == "Critical" for h in hits)
        needs_review = any(h.severity in ("Critical", "Moderate") for h in hits)
        return ComplianceGate(
            rule_set="+".join(rs.rule_set for rs in self.rulesets),
            passed=not critical,
            human_review_required=needs_review,
            hits=hits,
        )
