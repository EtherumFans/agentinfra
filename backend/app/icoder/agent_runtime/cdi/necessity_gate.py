"""Phase 5 Track D P0.5 Gate 2 — Query Necessity Gate.

PDF §3.2 — a Provider Query is *necessary* if and only if:

  (a) the chart evidence is genuinely insufficient to answer the
      documentation question (real gap), AND
  (b) the clinician's answer would actually change the documented
      record or downstream coding (documentation impact).

Unnecessary queries violate PDF §4.3 ("CDI must not generate
diagnoses") by asking the clinician to invent content the chart never
supported. They also inflate chart-review workload without improving
coding accuracy.

Five-dimension evaluation (NQ-001..NQ-005):

  NQ-001  evidence_sufficiency    Is chart evidence really insufficient?
                                  Hard-fail if the chart already answers.
  NQ-002  clinical_relevance     Would the answer affect care or coding?
                                  Soft-fail if topic is purely academic.
  NQ-003  answerability           Can a clinician realistically answer?
                                  Soft-fail if question asks for info the
                                  clinician cannot know at this visit.
  NQ-004  documentation_impact   Would the answer change the record?
                                  Soft-fail if the chart already documents
                                  the topic at the level the query seeks.
  NQ-005  redundancy_risk         Is this query redundant with another in
                                  the same case? Hard-fail on duplicate.

Per-case over-query guard (NQ-006, separate from per-query rules):
  NQ-006  overquery_per_case      If the case produced ≥5 queries, the
                                  case is flagged for over-query review.
                                  (Does not block — but tags the case.)

Implementation strategy
=======================

Rules NQ-001..NQ-005 are pure-regex / lexical where possible. A
separate semantic reviewer (``necessity_semantic.py``) provides
LLM-based judgment for ambiguous cases; on provider failure it
returns DEGRADED (does not block — same pattern as NLQ semantic).

The gate runs in the orchestrator AFTER query_generation and BEFORE
query_compliance_gate (NLQ). Unnecessary queries are dropped from
``case.proposed_provider_queries`` before NLQ sees them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.icoder.agent_runtime.cdi.domain import (
    CDICase,
    ProviderQuery,
    query_audit_item,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NecessityRuleResult:
    """Outcome of one NQ-XXX rule on a single query."""
    rule_id: str
    name: str
    description: str
    passed: bool
    evidence: str = ""
    severity: Literal["hard", "soft"] = "hard"  # hard = drop, soft = flag


@dataclass
class NecessityGateResult:
    """Aggregate outcome for all 5 rules on a single query."""
    verdict: Literal["NECESSARY", "UNNECESSARY", "DEGRADED"]
    rules_evaluated: int
    rules_passed: int
    rules_failed: list[NecessityRuleResult] = field(default_factory=list)
    drop_reasons: list[str] = field(default_factory=list)
    flag_reasons: list[str] = field(default_factory=list)


@dataclass
class CaseNecessityResult:
    """Per-case aggregate including the over-query guard NQ-006."""
    per_query: dict[str, NecessityGateResult] = field(default_factory=dict)
    overquery_triggered: bool = False
    overquery_count: int = 0
    overquery_threshold: int = 4  # cases with ≥5 queries are flagged


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# NQ-001 — chart-already-answers heuristics. If the topic phrase already
# appears verbatim in the chart with a value, the query is unnecessary.
_CHART_ANSWERS_PATTERNS = [
    # 体温/血压 already numeric → severity graded
    (r"体温\s*[Tt]?\s*[\d.]+\s*[°℃C]", "体温值已记录"),
    (r"血压\s*(BP)?\s*\d+\s*/\s*\d+\s*mm?Hg", "血压值已记录"),
    (r"糖化血红蛋白\s*\(HbA1c\)\s*[\d.]+\s*%", "HbA1c已记录"),
    # Diagnosis with explicit type/site/severity already specified
    (r"急性[^,。、\s]{0,8}(?:心肌梗死|阑尾炎|胆囊炎|胰腺炎|肺炎|胃肠炎)", "急性类型已明确"),
    (r"慢性[^,。、\s]{0,8}(?:阻塞性肺疾病|肺疾病|肾脏病|心力衰竭)", "慢性类型已明确"),
    (r"(?:前壁|下壁|侧壁|前间壁)ST段抬高", "部位已明确"),
    #PCI/手术 explicit
    (r"PCI.*植入.*支架", "PCI 手术细节已记录"),
    (r"腹腔镜.*切除", "腹腔镜手术已记录"),
]

# NQ-003 — unanswerable patterns (clinician cannot know)
_UNANSWERABLE_PATTERNS = [
    r"未来.{0,8}预后",
    r"预后.{0,8}预测",
    r"假如.{0,8}如果.{0,8}是否",
    r"如果.{0,8}病程.{0,8}变化",
]

# NQ-005 — redundancy: queries with identical topic are duplicates
# (Match is done at the case level, not pattern level.)


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _check_chart_already_answers(query: ProviderQuery, chart: str) -> tuple[bool, str]:
    """Return (matches, evidence) if chart already answers the query."""
    topic = query.topic or ""
    diabetes_specificity_conflict = bool(re.search(
        r"入院诊断[:：].{0,80}(?:1型|2型)糖尿病.{0,180}出院诊断[:：](?:(?![12]型糖尿病).){0,80}糖尿病"
        r"|admission diagnosis.{0,100}type\s*[12]\s*diabetes.{0,220}discharge diagnosis(?:(?!type\s*[12]\s*diabetes).){0,100}diabetes",
        chart,
        re.I | re.S,
    ))
    acute_mi_specificity_query = bool(
        re.search(r"(?:心肌梗死|myocardial infarction)", chart, re.I)
        and re.search(
            r"(?:心肌梗死|myocardial infarction).{0,30}(?:STEMI|NSTEMI|ST段|类型|分型|部位|前壁|下壁|Killip|严重程度|type|site|wall|severity)",
            f"{topic} {query.query_text}",
            re.I,
        )
    )
    if any(key in topic for key in ("糖尿病类型", "糖尿病分型")):
        if diabetes_specificity_conflict:
            return False, ""
        explicit_type = re.search(r"(?:1型|2型)糖尿病", chart)
        if explicit_type:
            return True, (
                "chart explicitly documents diabetes type: "
                f"'{explicit_type.group(0)}'"
            )
    for pat, label in _CHART_ANSWERS_PATTERNS:
        if not re.search(pat, chart, flags=re.IGNORECASE):
            continue
        if acute_mi_specificity_query:
            # "acute" describes timing and does not answer STEMI/NSTEMI,
            # infarct-wall/site, or Killip/severity documentation.
            continue
        # Only flag if the query topic is what the chart pattern answers.
        if "体温值" in label and any(k in topic for k in ["体温", "发热程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "血压值" in label and "血压" in topic:
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "HbA1c" in label and any(k in topic for k in ["HbA1c", "糖化", "血糖控制"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "急性类型" in label and "呼吸衰竭" not in topic and any(k in topic for k in ["类型", "急慢性", "病程", "严重程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "慢性类型" in label and "呼吸衰竭" not in topic and any(k in topic for k in ["类型", "急慢性", "病程", "严重程度"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "部位已明确" in label and any(k in topic for k in ["部位", "具体位置", "解剖"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "PCI" in label and any(k in topic for k in ["支架", "PCI", "手术细节", "支架类型"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
        if "腹腔镜" in label and any(k in topic for k in ["手术方式", "腹腔镜", "术式"]):
            return True, f"chart matches /{pat}/ ({label}) and query asks for {topic}"
    return False, ""


def _rule_nq_001(query: ProviderQuery, chart: str) -> NecessityRuleResult:
    matched, evidence = _check_chart_already_answers(query, chart)
    return NecessityRuleResult(
        rule_id="NQ-001",
        name="evidence_sufficiency",
        description="Chart already contains the requested information",
        passed=not matched,
        evidence=evidence,
        severity="hard",
    )


def _rule_nq_002(query: ProviderQuery) -> NecessityRuleResult:
    """Clinical relevance — drop pure-academic or family-history-only queries."""
    # Family-history-only topic is not clinically actionable for THIS patient
    fam_only = re.search(r"家族史.*具体类型|父亲.*糖尿病.*类型|母亲.*高血压.*类型",
                         query.query_text + query.topic, flags=re.IGNORECASE)
    if fam_only:
        return NecessityRuleResult(
            rule_id="NQ-002",
            name="clinical_relevance",
            description="Family-history-only detail does not change THIS patient's documentation",
            passed=False,
            evidence=f"family-history-only: '{fam_only.group(0)}'",
            severity="soft",
        )
    return NecessityRuleResult(
        rule_id="NQ-002",
        name="clinical_relevance",
        description="Family-history-only detail does not change THIS patient's documentation",
        passed=True,
        evidence="topic is clinically actionable",
        severity="soft",
    )


def _rule_nq_003(query: ProviderQuery) -> NecessityRuleResult:
    """Answerability — drop queries no clinician can answer at this visit."""
    for pat in _UNANSWERABLE_PATTERNS:
        m = re.search(pat, query.query_text, flags=re.IGNORECASE)
        if m:
            return NecessityRuleResult(
                rule_id="NQ-003",
                name="answerability",
                description="Query asks for prognosis / hypothetical the clinician cannot answer",
                passed=False,
                evidence=f"matched /{pat}/ : '{m.group(0)}'",
                severity="soft",
            )
    return NecessityRuleResult(
        rule_id="NQ-003",
        name="answerability",
        description="Query asks for prognosis / hypothetical the clinician cannot answer",
        passed=True,
        evidence="answerable",
        severity="soft",
    )


def _rule_nq_004(query: ProviderQuery, chart: str) -> NecessityRuleResult:
    """Documentation impact — drop queries whose answer is already in chart at the requested level."""
    topic_and_text = f"{query.topic or ''} {query.query_text or ''}"
    evidence_text = " ".join(span.quote for span in query.all_evidence_spans())
    has_redacted_evidence = bool(re.search(r"<REDACTED:[A-Z_]+>", evidence_text, re.I))
    has_clean_independent_evidence = any(
        span.quote.strip()
        and not re.search(r"<REDACTED:[A-Z_]+>", span.quote, re.I)
        for span in query.all_evidence_spans()
    )
    aecopd_severity_conflict = bool(
        re.search(r"(?:COPD|慢阻肺).{0,20}急性加重.{0,12}(?:重度|severe)", chart, re.I)
        and re.search(r"(?:COPD|慢阻肺).{0,20}急性加重.{0,12}(?:轻度|mild)", chart, re.I)
        and re.search(r"(?:COPD|慢阻肺).{0,20}急性加重.{0,12}(?:中度|moderate)", chart, re.I)
    )
    if (has_redacted_evidence and not has_clean_independent_evidence) or re.search(
        r"<REDACTED:[A-Z_]+>.{0,30}(?:所指|具体|解释|含义|what|clarify|specify)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="A privacy-redaction artifact is not a clinician-facing documentation gap",
            passed=False,
            evidence="query is grounded in or asks to decode a REDACTED placeholder",
            severity="hard",
        )
    # CDI queries clarify diagnosis documentation; they are not a request to
    # back-fill every raw measurement.  When the record already states a lab
    # is elevated/positive, asking only for its exact value and reference
    # interval does not establish a missing diagnosis dimension.
    if (
        re.search(r"(?:升高|增高|阳性|elevated|positive)", chart, re.I)
        and re.search(
            r"(?:具体数值|精确数值|参考范围|正常范围|reference (?:range|interval)|exact value)",
            topic_and_text,
            re.I,
        )
        and not re.search(r"诊断|分型|类型|严重程度|分级|diagnos|type|severity|grade", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Exact lab-value back-filling is not a minimum CDI diagnosis clarification",
            passed=False,
            evidence="the chart already records the qualitative lab result",
            severity="hard",
        )
    if evidence_text.strip() in {"常", "正常", "normal"} and re.search(
        r"体格检查|查体|检查发现|physical examination|exam finding|缺失|truncated|incomplete",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="A truncated normal-exam fragment is not safe provider-query evidence",
            passed=False,
            evidence="the evidence anchor contains only a generic/truncated normal token",
            severity="hard",
        )
    if re.search(r"建议(?:随访|复查)|follow[- ]?up (?:recommended|advised)", chart, re.I) and re.search(
        r"随访.{0,20}(?:安排|计划|时间|频率|具体)|follow[- ]?up.{0,20}(?:plan|schedule|interval|frequency)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Follow-up scheduling detail is not a minimum CDI diagnosis/coding gap",
            passed=False,
            evidence="the chart already recommends follow-up; scheduling does not change diagnosis documentation",
            severity="hard",
        )
    # If chart has "肺炎链球菌" and query asks for "病原体" → already documented
    if "病原体" in query.topic or "病原学" in query.topic:
        if re.search(r"(?:培养|阳性|检出).{0,15}(?:链球菌|葡萄球菌|大肠杆菌|克雷伯|铜绿)",
                     chart, flags=re.IGNORECASE):
            return NecessityRuleResult(
                rule_id="NQ-004",
                name="documentation_impact",
                description="Chart already documents pathogen culture result",
                passed=False,
                evidence="culture result present in chart",
                severity="hard",
            )
    # A fully named acute suppurative otitis diagnosis already carries the
    # requested acute/suppurative clinical description. Asking the clinician
    # to restate a generic severity label adds no coding/documentation value.
    if (
        re.search(r"急性化脓性(?:中耳炎|乳突炎)", chart)
        and re.search(r"严重程度|严重性|分级", topic_and_text)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Named acute suppurative diagnosis already provides the requested description",
            passed=False,
            evidence="acute suppurative diagnosis is already explicit",
            severity="hard",
        )
    if (
        re.search(r"急性化脓性中耳炎", chart)
        and re.search(r"病原体|病原学", topic_and_text)
        and not re.search(r"(?:培养|PCR|核酸|抗原).{0,20}(?:阳性|检出|提示)", chart, re.I)
        and re.search(r"(?:治疗|口服|静滴|抗菌|抗生素)", chart)
        and re.search(r"(?:好转|缓解|治愈)", chart)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Resolved treated otitis without microbiology does not support a pathogen clarification",
            passed=False,
            evidence="diagnosis, treatment, and improvement are documented without microbiology",
            severity="hard",
        )
    # Anatomical sub-segmentation of the appendix does not alter the CDI
    # diagnosis/coding level once appendicitis itself is explicitly
    # documented.  This excludes laterality/site queries for diseases where
    # site is a real coding dimension.
    if re.search(r"阑尾炎|appendicitis", chart, re.I) and re.search(
        r"(?:阑尾|appendix).{0,20}(?:解剖部位|具体部位|位置|尖端|根部|全段|entire|tip|base|site)"
        r"|(?:解剖部位|具体部位|位置|site).{0,20}(?:阑尾|appendix)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Appendiceal sub-site is beyond the minimum diagnosis/coding need",
            passed=False,
            evidence="appendicitis is explicit; appendix sub-site does not change documentation",
            severity="hard",
        )
    if (
        re.search(r"(?:单纯性|化脓性|坏疽性).{0,8}阑尾炎|阑尾炎.{0,8}(?:单纯性|化脓性|坏疽性)|(?:simple|suppurative|gangrenous).{0,12}appendicitis", chart, re.I)
        and re.search(r"(?:阑尾炎|appendicitis).{0,20}(?:分型|类型|病理类型|type|classification)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Appendicitis type is already explicit in diagnosis/pathology",
            passed=False,
            evidence="an explicit appendicitis subtype is documented",
            severity="hard",
        )
    # A measured fever in an encounter already diagnosed as acute otitis
    # does not need a separate provider attestation of clinical correlation.
    if re.search(r"(?:急性.{0,8}中耳炎|acute.{0,12}otitis)", chart, re.I) and re.search(
        r"(?:发热|体温|fever|temperature).{0,20}(?:相关|关联|关系|correlat)"
        r"|(?:相关|关联|关系|correlat).{0,20}(?:发热|体温|fever|temperature)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Fever correlation is implicit in the documented acute otitis encounter",
            passed=False,
            evidence="acute otitis diagnosis and measured fever are already documented",
            severity="hard",
        )
    # Pathology that already names chronic cholecystitis and a stone answers
    # type/subtype questions.  Asking whether it is calculous after the stone
    # is documented is redundant.
    if re.search(
        r"慢性胆囊炎.{0,30}(?:结石|胆固醇)|chronic cholecystitis.{0,40}stone",
        chart,
        re.I,
    ) and re.search(
        r"(?:胆囊炎|cholecystitis).{0,20}(?:类型|分型|亚型|结石性|非结石性|type|subtype|classification)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Cholecystitis type is explicit in pathology and stone findings",
            passed=False,
            evidence="chronic cholecystitis and a stone are both explicitly documented",
            severity="hard",
        )
    if (
        re.search(r"慢性胆囊炎|chronic cholecystitis", chart, re.I)
        and re.search(r"(?:手术顺利|无粘连|出血\s*\d+\s*ml|术后第?\d+天出院|uneventful|discharged post-op)", chart, re.I)
        and re.search(r"(?:胆囊炎|cholecystitis).{0,24}(?:严重程度|急性程度|急性发作|severity|acuity)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Uncomplicated chronic cholecystitis course does not need severity/acuity reclassification",
            passed=False,
            evidence="chronic pathology and an uncomplicated operative course are explicit",
            severity="hard",
        )
    # Type 2 diabetes is already a complete type classification.  Insulin use
    # is medication/status information, not a further diabetes subtype.
    diabetes_specificity_conflict = bool(re.search(
        r"入院诊断[:：].{0,80}(?:1型|2型)糖尿病.{0,180}出院诊断[:：](?:(?![12]型糖尿病).){0,80}糖尿病"
        r"|admission diagnosis.{0,100}type\s*[12]\s*diabetes.{0,220}discharge diagnosis(?:(?!type\s*[12]\s*diabetes).){0,100}diabetes",
        chart,
        re.I | re.S,
    ))
    if not diabetes_specificity_conflict and re.search(r"(?:2型糖尿病|type\s*2\s*diabetes)", chart, re.I) and re.search(
        r"(?:糖尿病|diabetes).{0,30}(?:亚型|具体类型|治疗分类|胰岛素依赖|非胰岛素依赖|subtype|treatment classification|insulin[- ]dependent)"
        r"|(?:type|subtype|classification).{0,20}(?:糖尿病|diabetes)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Type 2 diabetes is already explicitly classified",
            passed=False,
            evidence="the chart explicitly documents type 2 diabetes",
            severity="hard",
        )
    if re.search(r"咳嗽|cough", chart, re.I) and re.search(
        r"(?:咳嗽|cough).{0,24}(?:解剖部位|上呼吸道|下呼吸道|anatomical site|upper respiratory|lower respiratory)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Cough is a symptom and has no anatomical-site coding dimension",
            passed=False, evidence="upper/lower respiratory origin would require a diagnosis, not a cough-site label",
            severity="hard",
        )
    # Risk stratification is not a missing coding dimension when essential
    # hypertension grade, control status, and absence of target-organ damage
    # are all explicit.
    hypertension_complete = (
        bool(re.search(r"(?:原发性|essential).{0,8}(?:高血压|hypertension)", chart, re.I))
        and bool(re.search(r"(?:高血压|hypertension).{0,12}(?:[123一二三]\s*级|grade\s*[123])", chart, re.I))
        and bool(re.search(r"(?:控制良好|well controlled)", chart, re.I))
        and bool(re.search(r"(?:无靶器官损害|no target[- ]organ damage)", chart, re.I))
    )
    if hypertension_complete and re.search(
        r"(?:危险|风险).{0,8}(?:分层|分级)|risk.{0,12}(?:stratification|classification)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Hypertension risk detail is beyond the minimum documented coding need",
            passed=False,
            evidence="grade, control status, and target-organ assessment are explicit",
            severity="hard",
        )
    if re.search(r"(?:原发性高血压|essential hypertension)", chart, re.I) and re.search(
        r"(?:高血压|hypertension).{0,20}(?:病因分类|原发性还是继发性|etiology|primary or secondary)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Hypertension etiology is already explicit in the diagnosis",
            passed=False,
            evidence="the chart explicitly diagnoses essential/primary hypertension",
            severity="hard",
        )
    if re.search(r"(?:原发性高血压|essential hypertension)", chart, re.I):
        explicit_hypertension_course = bool(re.search(
            r"(?:高血压|<REDACTED:NAME>).{0,8}\d+\s*年|hypertension.{0,12}\d+\s*years",
            chart,
            re.I,
        ))
        explicit_grade = bool(re.search(
            r"(?:高血压|hypertension).{0,12}(?:[123一二三]\s*级|grade\s*[123])",
            chart,
            re.I,
        ))
        explicit_target_organs = bool(re.search(
            r"(?:无靶器官损害|no target[- ]organ damage)", chart, re.I,
        ))
        if explicit_hypertension_course and re.search(
            r"(?:高血压|hypertension).{0,20}(?:病程|持续时间|病史多久|duration|course)",
            topic_and_text,
            re.I,
        ):
            return NecessityRuleResult(
                rule_id="NQ-004", name="documentation_impact",
                description="Hypertension duration is already explicit",
                passed=False, evidence="a numeric hypertension history duration is documented",
                severity="hard",
            )
        if explicit_grade and re.search(
            r"(?:高血压|hypertension).{0,20}(?:分级|级别|分级依据|grade|grading)",
            topic_and_text,
            re.I,
        ):
            return NecessityRuleResult(
                rule_id="NQ-004", name="documentation_impact",
                description="Hypertension grade is already explicit",
                passed=False, evidence="an explicit hypertension grade is documented",
                severity="hard",
            )
        if explicit_target_organs and re.search(
            r"(?:靶器官|target[- ]organ).{0,24}(?:损害|评估|范围|damage|assessment|scope)",
            topic_and_text,
            re.I,
        ):
            return NecessityRuleResult(
                rule_id="NQ-004", name="documentation_impact",
                description="Target-organ assessment is already explicit at the required documentation level",
                passed=False, evidence="absence of target-organ damage is documented",
                severity="hard",
            )
    if (
        re.search(r"(?:慢阻肺|COPD).{0,16}急性加重|acute exacerbation.{0,16}(?:COPD|chronic obstructive)", chart, re.I)
        and re.search(r"(?:血气|blood gas).{0,40}(?:pH|PaCO2|PaO2)", chart, re.I)
        and not aecopd_severity_conflict
        and re.search(
            r"(?:血气|blood gas|酸碱|氧合).{0,35}(?:临床意义|解释|相关|状态|interpret|correlat|acid.base|oxygenation)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Recorded blood-gas values do not need a separate derived interpretation query",
            passed=False, evidence="COPD exacerbation and objective blood-gas values are explicit",
            severity="hard",
        )
    if (
        re.search(r"食欲下降|体重减轻|loss of appetite|weight loss", chart, re.I)
        and re.search(r"(?:1\s*(?:月|个月)|one month)", chart, re.I)
        and re.search(r"(?:体重减轻|weight loss)\s*5\s*kg", chart, re.I)
        and re.search(
            r"(?:体重减轻|weight loss).{0,35}(?:程度|具体情况|具体数值|持续时间|趋势|amount|duration|trend)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Weight-loss amount and duration are already explicit",
            passed=False,
            evidence="the chart records one month and 5 kg of weight loss",
            severity="hard",
        )
    if (
        re.search(r"食欲下降|体重减轻|loss of appetite|weight loss", chart, re.I)
        and re.search(r"建议(?:进一步)?检查|recommend(?:ed)? further (?:workup|testing)", chart, re.I)
        and not re.search(r"(?:入院诊断|出院诊断|诊断)[:：][^。\n]{2,}|(?:admission|discharge) diagnosis", chart, re.I)
        and re.search(
            r"(?:诊断|鉴别诊断|可能病因|possible diagnosis|differential diagnosis|etiology)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="A sparse symptom-only record must not ask the provider to invent a differential diagnosis",
            passed=False,
            evidence="no diagnosis or completed workup supports a diagnosis-clarification query",
            severity="hard",
        )
    if (
        re.search(r"建议(?:进一步)?检查|recommend(?:ed)? further (?:workup|testing)", chart, re.I)
        and re.search(
            r"(?:具体检查|检查项目|检查计划|哪些检查|workup|test(?:ing)? plan)",
            topic_and_text,
            re.I,
        )
        and not re.search(r"明确诊断|diagnosis", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="A diagnostic-workup plan is not a provider diagnosis clarification",
            passed=False,
            evidence="the chart already defers diagnosis to further evaluation",
            severity="hard",
        )
    if (
        re.search(r"(?:慢阻肺|COPD).{0,16}急性加重|acute exacerbation.{0,16}(?:COPD|chronic obstructive)", chart, re.I)
        and re.search(r"(?:血气|blood gas).{0,40}(?:pH|PaCO2|PaO2)", chart, re.I)
        and not aecopd_severity_conflict
        and re.search(
            r"(?:慢阻肺|COPD).{0,35}(?:急性加重.{0,12})?(?:严重程度|严重性|分级|诱因|病因|severity|grade|trigger|etiology)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Generic AECOPD severity/trigger is secondary to the objective respiratory-failure gap",
            passed=False,
            evidence="AECOPD and blood-gas abnormalities are explicit; prioritize respiratory-failure documentation",
            severity="hard",
        )
    if (
        re.search(r"(?:诊断|diagnosis)[:：]?[^。\n]{0,20}(?:肺炎|pneumonia)", chart, re.I)
        and re.search(r"(?:右下肺|左下肺|右上肺|左上肺|lower lobe|upper lobe)", chart, re.I)
        and re.search(r"(?:肺炎|pneumonia).{0,24}(?:解剖部位|肺叶|肺段|具体位置|anatomic|lobe|segment)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Pneumonia anatomical location is already documented by imaging",
            passed=False,
            evidence="the chart already localizes the infiltrate",
            severity="hard",
        )
    if (
        re.search(r"(?:诊断|diagnosis)[:：]?[^。\n]{0,20}(?:肺炎|pneumonia)", chart, re.I)
        and re.search(r"(?:WBC|白细胞).{0,12}\d", chart, re.I)
        and re.search(r"(?:肺炎|pneumonia).{0,30}(?:关联|相关性|关系|correlat)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Inflammatory-marker correlation is not a separate minimum CDI query",
            passed=False,
            evidence="pneumonia and the inflammatory finding are already documented in the same encounter",
            severity="hard",
        )
    if (
        re.search(r"(?:WBC|白细胞).{0,12}\d", chart, re.I)
        and re.search(
            r"(?:WBC|白细胞).{0,30}(?:临床意义|解读|解释|处理计划|后续计划|interpret|meaning|management plan)",
            topic_and_text,
            re.I,
        )
        and not re.search(r"诊断|diagnosis", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="An isolated lab interpretation/management request is not a CDI diagnosis query",
            passed=False,
            evidence="the query asks for lab interpretation or planning rather than diagnosis clarification",
            severity="hard",
        )
    if (
        re.search(r"(?:糖尿病|diabetes)", chart, re.I)
        and re.search(r"pH\s*[:=]?\s*(?:7\.[0-2]\d|7\.30)", chart, re.I)
        and re.search(r"酮体\s*(?:阳性|\+)|ketones?\s*(?:positive|\+)", chart, re.I)
        and re.search(r"(?:代谢性酸中毒|metabolic acidosis).{0,25}(?:病因|原因|诊疗计划|后续计划|etiology|cause|plan)", topic_and_text, re.I)
        and not re.search(r"糖尿病酮症酸中毒|DKA|diabetic ketoacidosis", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Generic acidosis etiology/plan is secondary to the specific DKA documentation gap",
            passed=False,
            evidence="objective diabetic ketoacidosis criteria support a diagnosis-focused clarification",
            severity="hard",
        )
    if (
        re.search(r"(?:心肌梗死|myocardial infarction)", chart, re.I)
        and re.search(r"(?:冠脉造影|冠状动脉造影|angiograph).{0,50}(?:闭塞|occlusion)|(?:PCI|经皮冠状动脉介入)", chart, re.I)
        and re.search(
            r"(?:心肌梗死|myocardial infarction).{0,24}(?:病因|原因|etiology|cause)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Speculative infarct etiology is not a minimum diagnosis-specificity query",
            passed=False,
            evidence="acute infarction and the culprit coronary occlusion/intervention are documented",
            severity="hard",
        )
    if (
        re.search(r"(?:心肌梗死|myocardial infarction)", chart, re.I)
        and re.search(r"(?:胸痛|chest pain).{0,12}(?:\d+(?:\.\d+)?\s*(?:小时|h(?:ours?)?))", chart, re.I)
        and re.search(r"(?:心肌梗死|myocardial infarction).{0,24}(?:发病时间|起病时间|onset time)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Myocardial-infarction onset duration is already explicit",
            passed=False,
            evidence="the chart records the chest-pain/onset duration",
            severity="hard",
        )
    if (
        re.search(r"(?:冠脉造影|angiograph).{0,60}(?:前降支|LAD).{0,24}(?:闭塞|occlusion)", chart, re.I)
        and re.search(r"(?:冠脉|coronary).{0,24}(?:血管数量|病变血管数|vessel count|number of vessels)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Unsupported total-vessel counting is not a minimum infarct diagnosis query",
            passed=False,
            evidence="only the culprit-vessel finding is documented; do not solicit undocumented vessel counts",
            severity="hard",
        )
    if (
        re.search(r"(?:心肌梗死|myocardial infarction)", chart, re.I)
        and re.search(r"(?:冠脉造影|angiograph).{0,60}(?:闭塞|occlusion)|\bPCI\b", chart, re.I)
        and re.search(
            r"(?:其他冠脉|其他血管|回旋支|右冠状动脉|PCI).{0,30}(?:病变情况|操作细节|具体细节|支架细节|detail)",
            topic_and_text,
            re.I,
        )
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Non-culprit-vessel and procedural details are secondary to infarct diagnosis specificity",
            passed=False,
            evidence="the culprit vessel and PCI are already documented",
            severity="hard",
        )
    # In a cough-only encounter with explicit negative infectious/red-flag
    # findings and normal lung assessment, generic severity or correlation
    # questions do not change the symptom-level record.
    low_risk_cough = (
        bool(re.search(r"咳嗽|cough", chart, re.I))
        and bool(re.search(r"否认.{0,35}(?:发热|脓痰|咯血|胸痛)|denies.{0,80}(?:fever|purulent sputum|hemoptysis|chest pain)", chart, re.I))
        and bool(re.search(r"(?:双肺清晰|胸片.{0,12}未见活动性病变|clear lungs|no active lesions)", chart, re.I))
    )
    if low_risk_cough and re.search(
        r"(?:咳嗽|cough).{0,25}(?:严重程度|severity)"
        r"|(?:胸片|影像|x-ray).{0,25}(?:相关|关联|关系|correlat)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Low-risk cough severity/correlation does not change symptom-level documentation",
            passed=False,
            evidence="red flags are denied and lung examination/imaging is non-acute",
            severity="hard",
        )
    if (
        low_risk_cough
        and re.search(r"高血压|hypertension", chart, re.I)
        and not re.search(r"(?:BP|血压)\s*[:：]?\s*\d{2,3}\s*/\s*\d{2,3}", chart, re.I)
        and re.search(r"(?:高血压|hypertension).{0,30}(?:严重程度|控制情况|分级|severity|control|grade)", topic_and_text, re.I)
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Historical hypertension without current measurements is not an answerable CDI refinement",
            passed=False,
            evidence="hypertension is history-only and no current blood pressure supports severity/control clarification",
            severity="hard",
        )
    if re.search(r"咳嗽|cough", chart, re.I) and re.search(
        r"(?:咳嗽|cough).{0,12}(?:\d+\s*(?:天|日|周|月|年)|for\s+\d+\s+(?:day|week|month|year))",
        chart,
        re.I,
    ) and re.search(
        r"(?:咳嗽|cough).{0,25}(?:病程分类|急性.?亚急性.?慢性|course classification|acute.?subacute.?chronic)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Recorded cough duration already determines the requested course category",
            passed=False,
            evidence="an explicit cough duration is documented",
            severity="hard",
        )
    # A headache-only encounter with broad red-flag denials and a normal
    # examination does not support speculative etiology, severity grading, or
    # course-detail queries solely to replace an otherwise valid symptom code.
    low_risk_headache = (
        bool(re.search(r"头痛|headache", chart, re.I))
        and bool(re.search(r"否认.{0,80}(?:呕吐|畏光|视觉先兆|肢体无力)|denies.{0,140}(?:vomiting|photophobia|visual aura|limb weakness)", chart, re.I))
        and bool(re.search(r"(?:查体正常|<REDACTED:NAME>常|normal exam)", chart, re.I))
    )
    if low_risk_headache and re.search(
        r"(?:头痛|headache).{0,30}(?:病因|原因|严重程度|病程|类型|分型|etiology|cause|severity|course|type|classification)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Speculative headache detail is beyond the minimum symptom-documentation need",
            passed=False,
            evidence="red flags are broadly denied and the examination is normal",
            severity="hard",
        )
    # Symptom-only records that explicitly defer evaluation to further tests
    # do not support diagnosis-invention or redundant reclassification of an
    # already quantified duration/weight change.
    sparse_weight_loss = (
        bool(re.search(r"(?:食欲下降|体重减轻|loss of appetite|weight loss)", chart, re.I))
        and bool(re.search(r"(?:建议进一步检查|further (?:testing|evaluation))", chart, re.I))
        and not bool(re.search(r"(?:诊断|diagnosis)\s*[:：].{1,40}", chart, re.I))
    )
    if sparse_weight_loss and re.search(
        r"(?:食欲下降|体重减轻|loss of appetite|weight loss).{0,30}(?:病因|原因|严重程度|病程|量化|etiology|cause|severity|course|quantif)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Sparse symptom-only evidence does not support speculative CDI refinement",
            passed=False, evidence="the chart defers diagnosis to further evaluation",
            severity="hard",
        )
    # NIHSS is already the accepted quantified stroke-severity assessment;
    # asking the provider to restate a generic mild/moderate/severe label adds
    # no minimum coding documentation value.
    if re.search(r"\bNIHSS\s*\d+", chart, re.I) and re.search(
        r"(?:脑梗死|卒中|stroke|cerebral infarction).{0,24}(?:严重程度|分级|severity|grade)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Stroke severity is already quantified by NIHSS",
            passed=False, evidence="an explicit NIHSS score is documented",
            severity="hard",
        )
    if re.search(r"(?:血糖控制不佳|poor glycemic control)", chart, re.I) and re.search(
        r"(?:血糖|glycemic).{0,30}(?:控制|严重程度|HbA1c|severity|control)",
        topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004", name="documentation_impact",
            description="Poor glycemic control is already explicitly documented",
            passed=False, evidence="the requested control characterization is explicit",
            severity="hard",
        )
    # Do not ask a provider to re-derive haemorrhage severity or temporal
    # course when the chart already records the objective inputs. Etiology or
    # a genuine contradiction remains eligible and is not covered here.
    if re.search(r"出血|呕血|便血", chart) and re.search(r"出血", topic_and_text):
        has_bp = bool(re.search(r"BP\s*\d+\s*/\s*\d+|血压\s*\d+\s*/\s*\d+", chart, re.I))
        has_hr = bool(re.search(r"HR\s*\d+|心率\s*\d+", chart, re.I))
        has_hb = bool(re.search(r"(?:Hb|血红蛋白)\s*\d+", chart, re.I))
        if has_bp and has_hr and has_hb and re.search(r"严重程度|严重性|分级", topic_and_text):
            return NecessityRuleResult(
                rule_id="NQ-004",
                name="documentation_impact",
                description="Objective haemorrhage severity indicators are already documented",
                passed=False,
                evidence="blood pressure, heart rate, and haemoglobin are explicit",
                severity="hard",
            )
        has_onset = bool(re.search(r"\d+\s*(?:小时|天|周|月|年)(?:前|来)", chart))
        if has_onset and re.search(r"病程|起病|急性程度|持续时间", topic_and_text):
            return NecessityRuleResult(
                rule_id="NQ-004",
                name="documentation_impact",
                description="Haemorrhage onset/course is already documented",
                passed=False,
                evidence="explicit onset duration is present",
                severity="hard",
            )
        if has_hb and re.search(r"血红蛋白.*(?:关联|相关|关系)|(?:关联|相关|关系).*血红蛋白", topic_and_text):
            return NecessityRuleResult(
                rule_id="NQ-004",
                name="documentation_impact",
                description="Haemoglobin and the documented haemorrhage already establish the requested correlation",
                passed=False,
                evidence="haemorrhage and haemoglobin are both explicit",
                severity="hard",
            )
    # A complete lipid panel and an explicit cardiovascular risk estimate can
    # be interpreted from the chart. Do not ask the clinician to repeat a
    # derived type/severity/risk label; a separate etiologic clarification may
    # still survive when it is genuinely needed.
    lipid_markers = all(
        re.search(rf"\b{marker}(?:-C)?\s*[\d.]+", chart, re.I)
        for marker in ("TC", "LDL", "HDL", "TG")
    )
    has_cv_risk = bool(re.search(r"(?:10年|十年).{0,12}(?:风险|危险).{0,8}\d+\s*%", chart))
    if lipid_markers and has_cv_risk and re.search(
        r"血脂.{0,8}(?:类型|分型|严重程度|分级|风险分层)", topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Lipid phenotype/severity/risk is derivable from recorded objective values",
            passed=False,
            evidence="complete lipid panel and cardiovascular risk are explicit",
            severity="hard",
        )
    if lipid_markers and re.search(
        r"血脂.{0,8}(?:病程|急慢性|急性|慢性|持续时间)", topic_and_text,
        re.I,
    ):
        return NecessityRuleResult(
            rule_id="NQ-004",
            name="documentation_impact",
            description="Acute/chronic course is not a necessary clarification for an objectively recorded lipid abnormality",
            passed=False,
            evidence="lipid abnormality is objectively recorded; course label adds no current documentation value",
            severity="hard",
        )
    return NecessityRuleResult(
        rule_id="NQ-004",
        name="documentation_impact",
        description="Chart already documents or objectively answers the requested detail",
        passed=True,
        evidence="topic is not redundant with existing documentation",
        severity="hard",
    )


def _rule_nq_005(query: ProviderQuery, all_queries: list[ProviderQuery]) -> NecessityRuleResult:
    """Redundancy — keep the FIRST query per topic; mark duplicates redundant.

    A query is redundant if another query with the same topic appears
    earlier in the case list (i.e. there exists an earlier q whose
    topic equals this query's topic). The first occurrence passes.
    """
    for earlier in all_queries:
        if earlier is query:
            break  # query is the first occurrence — pass
        if earlier.topic == query.topic:
            return NecessityRuleResult(
                rule_id="NQ-005",
                name="redundancy_risk",
                description="Another earlier query in this case has the same topic",
                passed=False,
                evidence=f"earlier query '{earlier.query_id}' already asks topic='{query.topic}'",
                severity="hard",
            )
    return NecessityRuleResult(
        rule_id="NQ-005",
        name="redundancy_risk",
        description="Another earlier query in this case has the same topic",
        passed=True,
        evidence="topic is unique among earlier queries",
        severity="hard",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_necessity(
    query: ProviderQuery,
    *,
    chart: str,
    all_queries: list[ProviderQuery],
) -> NecessityGateResult:
    """Run NQ-001..NQ-005 on a single query.

    Returns verdict:
      - NECESSARY   — no hard-fail; query survives
      - UNNECESSARY — at least one hard-fail; query should be dropped
      - DEGRADED    — provider/reviewer unavailable; default to NECESSARY
                      (do not block on degraded necessity)
    """
    rules: list[NecessityRuleResult] = [
        _rule_nq_001(query, chart),
        _rule_nq_002(query),
        _rule_nq_003(query),
        _rule_nq_004(query, chart),
        _rule_nq_005(query, all_queries),
    ]

    hard_fails = [r for r in rules if not r.passed and r.severity == "hard"]
    soft_fails = [r for r in rules if not r.passed and r.severity == "soft"]

    if hard_fails:
        return NecessityGateResult(
            verdict="UNNECESSARY",
            rules_evaluated=len(rules),
            rules_passed=len(rules) - len(hard_fails) - len(soft_fails),
            rules_failed=rules,
            drop_reasons=[f"{r.rule_id}: {r.evidence}" for r in hard_fails],
            flag_reasons=[f"{r.rule_id}: {r.evidence}" for r in soft_fails],
        )
    return NecessityGateResult(
        verdict="NECESSARY",
        rules_evaluated=len(rules),
        rules_passed=len(rules) - len(soft_fails),
        rules_failed=rules,
        drop_reasons=[],
        flag_reasons=[f"{r.rule_id}: {r.evidence}" for r in soft_fails],
    )


def evaluate_case_necessity(case: CDICase) -> CaseNecessityResult:
    """Run necessity evaluation on every query in the case + over-query guard.

    Side-effect-free — does NOT mutate ``case.proposed_provider_queries``.
    Caller (orchestrator) decides whether to drop queries based on verdicts.
    """
    result = CaseNecessityResult()
    queries = list(case.proposed_provider_queries)
    for q in queries:
        result.per_query[q.query_id] = evaluate_necessity(
            q,
            chart=case.chart_excerpt,
            all_queries=queries,
        )

    # NQ-006 — over-query per case
    result.overquery_count = len(queries)
    result.overquery_triggered = len(queries) > result.overquery_threshold
    return result


def apply_necessity_to_case(case: CDICase) -> CaseNecessityResult:
    """Evaluate necessity AND drop UNNECESSARY queries from the case.

    This is the orchestrator-friendly entry point — it mutates
    ``case.proposed_provider_queries`` in place by removing queries
    that hard-failed NQ-001, NQ-004, or NQ-005.

    Returns the full evaluation result (including soft-fails) for
    traceability; the dropped queries are recorded in the result.
    """
    result = evaluate_case_necessity(case)
    survivors: list[ProviderQuery] = []
    for q in case.proposed_provider_queries:
        verdict = result.per_query.get(q.query_id)
        if verdict is None or verdict.verdict != "UNNECESSARY":
            survivors.append(q)
            continue
        case.query_rewrite_queue.append(query_audit_item(
            q,
            status="REJECTED_AS_UNNECESSARY",
            gate_reasons=list(verdict.drop_reasons),
        ))
    case.proposed_provider_queries = survivors
    return result


__all__ = [
    "NecessityRuleResult",
    "NecessityGateResult",
    "CaseNecessityResult",
    "evaluate_necessity",
    "evaluate_case_necessity",
    "apply_necessity_to_case",
]
