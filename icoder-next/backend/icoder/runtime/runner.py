"""AgentRunner — executes a thin Agent by orchestrating its Experts into a staged run.

Stages (thin but real; each recorded with tool_run_id + duration_ms):
  1 ingest      — PHI redaction (report renders the de-identified text only)
  2 extract     — LLMGateway provider (deterministic local, or DeepSeek seam)
  3 retrieve    — coding-expert.search per extracted entity -> candidate codes + evidence offsets
  4 verify      — coding-expert.verify/guidelines/alternatives per code
  5 sequence    — split codes vs candidates, pick primary; clinically-meaningful order (NOT re-sorted)
  6 group       — grouping-expert derives the CHS-DRG / DIP route from the confirmed codes
  7 compliance  — RuleEngine folds the agent's rule sets into one gate. Four domains are
                  wired (medical_coding, drg_dip, insurance_audit, document_evidence); an
                  Agent declares which subset runs via ``agent.rule_sets``.

The single pipeline is agent-configurable: which Experts and which rule sets run is driven by
the thin Agent definition (``agent.experts`` / ``agent.rule_sets``), not by the runner. Grouping
runs before compliance so the drg_dip rules can inspect the route (low-靠组 / 未入组 detection).

codes vs candidates: confident & not-high-risk go to ``codes`` (billable); high-risk/易错 codes
(or evidence-less) go to ``candidates`` — pending human review before billing. The two are
never merged and ``codes`` is never re-sorted after sequencing.
"""
from __future__ import annotations

import re
import time
from contextlib import contextmanager

from ..experts.catalog import CATALOG, CATALOG_VERSION, HIGH_RISK
from ..experts.coding_expert import CodingExpert
from ..experts.compliance import (
    DocumentEvidenceRuleSet,
    DrgDipRuleSet,
    InsuranceAuditRuleSet,
    MedicalCodingRuleSet,
    RuleContext,
    RuleEngine,
)
from ..experts.grouping_expert import GroupingExpert
from .gateway import LLMGateway
from .registry import AgentRegistry
from .types import (
    CodeResult,
    RunResult,
    StageObservation,
    Versions,
    new_id,
)

RUNTIME_VERSION = "icoder-next-runtime@0.1.0"


class RulesetMissing(RuntimeError):
    """Raised when no compliance ruleset is injected — the runtime refuses to run."""


class PHIRedactor:
    """Minimal PHI redactor. Production binds app/services/phi_redactor.py; this slice
    masks the obvious identifiers so the report/embed never render raw PHI."""

    _patterns = [
        (re.compile(r"\b\d{17}[\dXx]\b"), "[身份证]"),
        (re.compile(r"\b1[3-9]\d{9}\b"), "[手机]"),
        (re.compile(r"住院号[:：]?\s*[A-Za-z0-9]+"), "住院号：[已脱敏]"),
        (re.compile(r"姓名[:：]?\s*[一-龥]{2,4}"), "姓名：[已脱敏]"),
    ]

    def redact(self, text: str) -> tuple[str, int]:
        count = 0
        for pat, repl in self._patterns:
            text, n = pat.subn(repl, text)
            count += n
        return text, count


@contextmanager
def _timed(stages: list[StageObservation], stage: str, tool: str):
    obs = StageObservation(stage=stage, tool=tool, tool_run_id=new_id("tr"), duration_ms=0.0)
    t0 = time.perf_counter()
    try:
        yield obs
    finally:
        obs.duration_ms = round((time.perf_counter() - t0) * 1000, 3)
        stages.append(obs)


def _first_start(c: CodeResult) -> int:
    return min((e.start for e in c.evidences), default=10**9)


class AgentRunner:
    def __init__(self, gateway: LLMGateway, agents: AgentRegistry,
                 expert: CodingExpert | None = None,
                 grouper: GroupingExpert | None = None,
                 rulesets: dict | None = None,
                 redactor: PHIRedactor | None = None):
        self.gateway = gateway
        self.agents = agents
        self.expert = expert or CodingExpert()
        self.grouper = grouper or GroupingExpert()
        # name -> RuleSet; the running agent selects a subset via agent.rule_sets
        self.rulesets = rulesets or {
            "medical_coding": MedicalCodingRuleSet(),
            "drg_dip": DrgDipRuleSet(self.grouper),
            "insurance_audit": InsuranceAuditRuleSet(),
            "document_evidence": DocumentEvidenceRuleSet(),
        }
        self.redactor = redactor or PHIRedactor()

    def run(self, agent_id: str, text: str, coding_system: str = "ICD-10-CN",
            rule_set: str | None = "medical_coding") -> RunResult:
        if rule_set is None:
            raise RulesetMissing("COMPLIANCE_RULESET 未注入，按合规要求拒绝执行")
        agent = self.agents.get(agent_id)
        if agent is None:
            raise KeyError(agent_id)

        # Resolve the agent's declared rule sets against what the runtime knows.
        selected = [self.rulesets[n] for n in agent.rule_sets if n in self.rulesets]
        if not selected:
            raise RulesetMissing(f"Agent {agent.id} 声明的规则集均未注册，拒绝执行")

        stages: list[StageObservation] = []
        tool_calls = 0
        llm_calls = 0

        # Stage 1 — ingest + PHI redaction
        with _timed(stages, "ingest", "phi-redactor") as obs:
            red_text, n_spans = self.redactor.redact(text)
            obs.summary = f"脱敏 {n_spans} 处 PHI"

        # Stage 2 — extraction (LLM provider, or deterministic local)
        with _timed(stages, "extract", f"llm:{self.gateway.provider.name}") as obs:
            extractions = self.gateway.extract(red_text)
            llm_calls += 1
            obs.summary = f"抽取 {len(extractions)} 个临床实体"

        # Stage 3 — retrieve candidate codes + evidence offsets
        chosen: dict[str, CodeResult] = {}
        with _timed(stages, "retrieve", "coding-expert.search") as obs:
            for ex in extractions:
                hits = self.expert.search(ex.term)
                tool_calls += 1
                if not hits:
                    continue
                top = hits[0]
                code = top["code"]
                cr = chosen.get(code)
                if cr is None:
                    cr = CodeResult(
                        system=top["system"], code=code, display=top["display"],
                        code_type=CATALOG[code]["code_type"], status="code",
                        confidence=round(top["score"], 3), high_risk=code in HIGH_RISK,
                    )
                    chosen[code] = cr
                seen = {e.start for e in cr.evidences}
                for ev in self.expert.find_evidences(red_text, ex.evidence_text):
                    if ev.start not in seen:
                        cr.evidences.append(ev)
                        seen.add(ev.start)
            obs.summary = f"检索得到 {len(chosen)} 个候选码"

        # Stage 4 — verify + guidelines + differentiation per code
        with _timed(stages, "verify", "coding-expert.verify") as obs:
            for code, cr in chosen.items():
                v = self.expert.verify(code)
                tool_calls += 1
                if v:
                    cr.notes = v["notes"]
                self.expert.guidelines(code)
                tool_calls += 1
                cr.alternatives = self.expert.alternatives(code)
                tool_calls += 1
            obs.summary = f"校验 {len(chosen)} 个码（指令注释/指南/鉴别）"

        # Stage 5 — split codes vs candidates + sequencing
        def is_candidate(c: CodeResult) -> bool:
            return (not c.evidences) or c.high_risk

        with _timed(stages, "sequence", "coding-expert.explore") as obs:
            code_set = [c for c in chosen.values() if not is_candidate(c)]
            cand_set = [c for c in chosen.values() if is_candidate(c)]
            primary: CodeResult | None = None
            for c in sorted(
                (c for c in code_set if c.code_type == "diagnosis"),
                key=lambda x: (-x.confidence, _first_start(x)),
            ):
                primary = c
                primary.is_primary = True
                break
            obs.summary = f"主要诊断: {primary.code if primary else '未定'}"

        code_diag = [c for c in code_set if c.code_type == "diagnosis"]
        code_proc = [c for c in code_set if c.code_type == "procedure"]
        codes = (
            ([primary] if primary else [])
            + [c for c in code_diag if c is not primary]
            + code_proc
        )
        candidates = cand_set
        for c in codes:
            c.status = "code"
        for c in candidates:
            c.status = "candidate"

        # Stage 6 — DRG/DIP grouping (grouping-expert) on the confirmed codes only.
        # Runs before compliance so the drg_dip rule set can inspect the route.
        with _timed(stages, "group", "grouping-expert.group") as obs:
            secondaries = [c for c in code_diag if c is not primary]
            drg = self.grouper.group(primary, secondaries, code_proc)
            tool_calls += 1
            obs.summary = (drg.drg or drg.note or "未分组")

        # Stage 7 — compliance gate: fold the agent's rule sets into one ComplianceGate.
        rs_label = "+".join(rs.rule_set for rs in selected)
        with _timed(stages, "compliance", f"ruleset:{rs_label}") as obs:
            ctx = RuleContext(codes=codes, candidates=candidates,
                              primary=primary, grouping=drg)
            gate = RuleEngine(selected).evaluate(ctx)
            obs.summary = f"门禁{'通过' if gate.passed else '拦截'}；需复核={gate.human_review_required}"

        versions = Versions(
            runtime_version=RUNTIME_VERSION,
            agent_version=agent.version,
            ruleset_version="+".join(rs.version for rs in selected),
            catalog_version=CATALOG_VERSION,
            model_version=self.gateway.provider.name,
        )
        return RunResult(
            run_id=new_id("run"),
            agent_id=agent.id,
            agent_version=agent.version,
            coding_system=coding_system,
            created_at=time.time(),
            redaction={"redacted": True, "spans": n_spans, "text": red_text},
            codes=codes,
            candidates=candidates,
            compliance=gate,
            drg_route=drg,
            stages=stages,
            usage={
                "tool_calls": tool_calls,
                "llm_calls": llm_calls,
                "provider": self.gateway.provider.name,
                "stages_observed": len(stages),
            },
            versions=versions,
            production_writeback_blocked=True,
        )
