"""CodingComplianceOrchestrator — 7-stage coding compliance mainline (§9).

Stage order (per PDF §9.2):
  1. discharge-summary-structuring  — structure raw discharge text
  2. medical-coding-agent           — extract ICD-10 / ICD-9-CM-3 codes
  3. principal-diagnosis-review     — pick + validate primary dx
  4. evidence-extractor             — tier codes into supported/uncertain/rejected
  5. compliance-guardrail           — run R001-R010 + China business rules
  6. note-completeness              — 8 required sections check
  7. drg-analyzer                   — DRG/DIP risk points + reservations

After stage 7, the orchestrator runs the Human Review Gate (§9.4):
  - AUTO_PASS: clean run, ship to EMR
  - REVIEW_RECOMMENDED: warnings only, surface in workbench
  - REVIEW_REQUIRED: critical violations / primary-dx conflict
  - BLOCKED_*: hard blockers (missing discharge, no codes, etc.)

The orchestrator is pure logic — it accepts a callable
``agent_runner(agent_id, input_text, context) -> dict`` and threads a
CaseState through. Production wiring (HTTP fetch / AgentRunner / async
fanout) is the caller's job. Tests use a deterministic stub.

Per §9.5 the orchestrator must be idempotent: rerunning with the same
input_text + case_id yields the same CaseState (modulo LLM nondeterminism
in the agent calls themselves, which is out-of-scope).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .completion_controller import (
    CompletionController,
    CompletionDecision,
)
from .conflict_resolver import (
    ConflictResolution,
    ConflictResolver,
)
from .result_normalizer import (
    NormalizedExpertResult,
    normalize_expert_result,
)

logger = logging.getLogger(__name__)


# ── Stage order ─────────────────────────────────────────────────────────

STAGE_DISCHARGE = "discharge-summary-structuring"
STAGE_MEDICAL_CODING = "medical-coding-agent"
STAGE_PRINCIPAL_DX = "principal-diagnosis-review"
STAGE_EVIDENCE = "evidence-extractor"
STAGE_COMPLIANCE = "compliance-guardrail"
STAGE_NOTE_COMPLETENESS = "note-completeness"
STAGE_DRG = "drg-analyzer"

STAGE_ORDER: tuple[str, ...] = (
    STAGE_DISCHARGE,
    STAGE_MEDICAL_CODING,
    STAGE_PRINCIPAL_DX,
    STAGE_EVIDENCE,
    STAGE_COMPLIANCE,
    STAGE_NOTE_COMPLETENESS,
    STAGE_DRG,
)


# ── Human Review Gate states (§9.4) ─────────────────────────────────────

REVIEW_AUTO_PASS = "AUTO_PASS"
REVIEW_REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
REVIEW_REVIEW_REQUIRED = "REVIEW_REQUIRED"
REVIEW_BLOCKED = "BLOCKED"

# Specific blockers
BLOCKED_MISSING_DISCHARGE = "BLOCKED_MISSING_DISCHARGE"
BLOCKED_NO_CODES_EXTRACTED = "BLOCKED_NO_CODES_EXTRACTED"
BLOCKED_PRIMARY_DX_CONFLICT = "BLOCKED_PRIMARY_DX_CONFLICT"
BLOCKED_CRITICAL_RULE_VIOLATION = "BLOCKED_CRITICAL_RULE_VIOLATION"
BLOCKED_NOTE_SEVERELY_INCOMPLETE = "BLOCKED_NOTE_SEVERELY_INCOMPLETE"


# ── Agent runner contract ───────────────────────────────────────────────


class AgentRunner(Protocol):
    """Callable contract for invoking an agent by id."""

    def __call__(
        self,
        agent_id: str,
        input_text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


# ── CaseState accumulator ───────────────────────────────────────────────


@dataclass
class CaseState:
    """Per-case accumulator threaded through all 7 stages."""

    case_id: str
    input_text: str
    agent_id: str = "coding-compliance-mainline"

    # Per-stage raw outputs (the agent's structured result dict).
    stage_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Per-stage errors ("" means success).
    stage_errors: dict[str, str] = field(default_factory=dict)
    # Per-stage latency in ms.
    stage_latencies_ms: dict[str, int] = field(default_factory=dict)

    # Normalized views (filled in by _post_process).
    normalized: dict[str, NormalizedExpertResult] = field(default_factory=dict)

    # Conflict resolutions (across stages).
    conflicts: list[ConflictResolution] = field(default_factory=list)

    # Completion decision (final).
    completion: CompletionDecision | None = None

    # Human Review Gate decision.
    review_gate_status: str = REVIEW_AUTO_PASS
    review_gate_reasons: list[str] = field(default_factory=list)
    review_gate_blocker: str = ""


# ── Config ──────────────────────────────────────────────────────────────


@dataclass
class CodingComplianceConfig:
    """Per-stage tunables."""

    # If True, missing discharge-summary output blocks the case.
    block_on_missing_discharge: bool = True
    # If True, zero codes extracted blocks the case.
    block_on_no_codes: bool = True
    # If True, primary-dx coding_draft_consistent=false blocks the case.
    block_on_primary_dx_conflict: bool = True
    # If True, critical R001/R004/R009/R010 violations block the case.
    block_on_critical_rule: bool = True
    # If True, note completeness score < threshold blocks the case.
    block_on_note_score_below: float | None = 0.30
    # Critical rule IDs (must match compliance_services.medical_coding_rules).
    critical_rule_ids: tuple[str, ...] = (
        "R001", "R002", "R004", "R009", "R010",
    )


# ── Orchestrator ────────────────────────────────────────────────────────


class CodingComplianceOrchestrator:
    """7-stage coding compliance mainline.

    Construct once, call ``.run(input_text=...)`` per case. Idempotent
    per case_id: same case_id + same input → same CaseState (modulo
    agent nondeterminism).
    """

    def __init__(
        self,
        agent_runner: AgentRunner,
        *,
        conflict_resolver: ConflictResolver | None = None,
        completion_controller: CompletionController | None = None,
        config: CodingComplianceConfig | None = None,
        case_id_factory=None,
    ) -> None:
        self._runner = agent_runner
        self._conflict_resolver = conflict_resolver or ConflictResolver()
        self._completion = completion_controller or CompletionController()
        self._config = config or CodingComplianceConfig()
        self._case_id_factory = case_id_factory or (lambda: str(uuid.uuid4()))

    def run(
        self,
        *,
        input_text: str,
        case_id: str | None = None,
        agent_id: str = "coding-compliance-mainline",
    ) -> CaseState:
        """Execute all 7 stages + Human Review Gate. Returns final CaseState."""
        if not input_text or not input_text.strip():
            raise ValueError("input_text must be non-empty")

        case = CaseState(
            case_id=case_id or self._case_id_factory(),
            input_text=input_text,
            agent_id=agent_id,
        )

        # ── Run each stage in order ──────────────────────────────────
        # Stage 1 uses raw input_text. Each subsequent stage uses the
        # accumulated case state to build its input.
        for stage in STAGE_ORDER:
            self._run_stage(stage, case)

        # ── Normalize outputs ────────────────────────────────────────
        for stage, raw in case.stage_outputs.items():
            err = case.stage_errors.get(stage, "")
            case.normalized[stage] = normalize_expert_result(
                stage, raw, error=err or None
            )

        # ── Conflict resolution across stages ────────────────────────
        cross_stage_conflicts = self._detect_cross_stage_conflicts(case)
        case.conflicts = self._conflict_resolver.resolve(cross_stage_conflicts)

        # ── Completion decision ──────────────────────────────────────
        case.completion = self._completion.evaluate(
            normalized=list(case.normalized.values()),
            conflicts=case.conflicts,
            critical_expert_failed=any(
                e and stage in STAGE_ORDER[:5]  # only first 5 stages are "critical"
                for stage, e in case.stage_errors.items()
            ),
        )

        # ── Human Review Gate ────────────────────────────────────────
        self._evaluate_review_gate(case)

        return case

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def _run_stage(self, stage: str, case: CaseState) -> None:
        """Invoke one stage's agent and record its output."""
        runner_input = self._build_stage_input(stage, case)
        if runner_input is None:
            case.stage_errors[stage] = "skipped:upstream_failure"
            case.stage_outputs[stage] = {}
            return

        try:
            import time as _time
            t0 = _time.monotonic()
            ctx = {
                "case_id": case.case_id,
                "stage": stage,
                "prior_stages": {
                    s: case.stage_outputs.get(s, {})
                    for s in STAGE_ORDER[:STAGE_ORDER.index(stage)]
                },
            }
            result = self._runner(stage, runner_input, ctx) or {}
            case.stage_outputs[stage] = result
            case.stage_latencies_ms[stage] = int((_time.monotonic() - t0) * 1000)
            case.stage_errors[stage] = ""
        except Exception as e:
            logger.warning(
                "coding_compliance.stage_failed case=%s stage=%s error=%s",
                case.case_id, stage, e,
            )
            case.stage_outputs[stage] = {}
            case.stage_errors[stage] = f"{type(e).__name__}: {e}"
            case.stage_latencies_ms[stage] = 0

    def _build_stage_input(self, stage: str, case: CaseState) -> str | None:
        """Build the input text for a given stage.

        Returns None if the stage should be skipped due to upstream failure.
        """
        # Check for upstream failures (only in critical-path stages 1-5).
        if stage != STAGE_DISCHARGE:
            idx = STAGE_ORDER.index(stage)
            upstream = STAGE_ORDER[:idx]
            for up in upstream:
                if case.stage_errors.get(up):
                    return None

        if stage == STAGE_DISCHARGE:
            return case.input_text
        if stage == STAGE_MEDICAL_CODING:
            # Use structured discharge text if stage 1 produced it, else raw.
            sd = case.stage_outputs.get(STAGE_DISCHARGE, {})
            structured_text = self._extract_structured_discharge_text(sd)
            return structured_text or case.input_text
        if stage == STAGE_PRINCIPAL_DX:
            mc = case.stage_outputs.get(STAGE_MEDICAL_CODING, {})
            codes = self._extract_codes_for_principal(mc)
            return self._format_principal_dx_prompt(case.input_text, codes)
        if stage == STAGE_EVIDENCE:
            mc = case.stage_outputs.get(STAGE_MEDICAL_CODING, {})
            return self._format_evidence_prompt(case.input_text, mc)
        if stage == STAGE_COMPLIANCE:
            mc = case.stage_outputs.get(STAGE_MEDICAL_CODING, {})
            return self._format_compliance_prompt(mc)
        if stage == STAGE_NOTE_COMPLETENESS:
            return case.input_text
        if stage == STAGE_DRG:
            mc = case.stage_outputs.get(STAGE_MEDICAL_CODING, {})
            pd = case.stage_outputs.get(STAGE_PRINCIPAL_DX, {})
            return self._format_drg_prompt(mc, pd)
        return case.input_text

    # ------------------------------------------------------------------
    # Cross-stage conflict detection
    # ------------------------------------------------------------------

    def _detect_cross_stage_conflicts(self, case: CaseState) -> dict[str, list[dict]]:
        """Find conflicts between medical-coding and principal-dx outputs."""
        conflicts: dict[str, list[dict]] = {}
        mc = case.stage_outputs.get(STAGE_MEDICAL_CODING, {})
        pd = case.stage_outputs.get(STAGE_PRINCIPAL_DX, {})

        mc_primary = self._extract_primary_dx_code(mc)
        pd_recommended = self._extract_recommended_dx_code(pd)
        if mc_primary and pd_recommended and mc_primary != pd_recommended:
            conflicts["primary_diagnosis.code"] = [
                {"expert_id": STAGE_MEDICAL_CODING, "value": mc_primary},
                {"expert_id": STAGE_PRINCIPAL_DX, "value": pd_recommended},
            ]
        return conflicts

    # ------------------------------------------------------------------
    # Human Review Gate evaluation (§9.4)
    # ------------------------------------------------------------------

    def _evaluate_review_gate(self, case: CaseState) -> None:
        """Decide AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED / BLOCKED_*."""
        reasons: list[str] = []
        blocker: str = ""

        # BLOCKED: missing discharge output
        if self._config.block_on_missing_discharge:
            ds = case.stage_outputs.get(STAGE_DISCHARGE, {})
            if not ds:
                blocker = BLOCKED_MISSING_DISCHARGE
                reasons.append(f"stage:{STAGE_DISCHARGE}:no_output")

        # BLOCKED: no codes extracted
        if self._config.block_on_no_codes and not blocker:
            mc = case.normalized.get(STAGE_MEDICAL_CODING)
            if mc and not mc.codes_emitted:
                blocker = BLOCKED_NO_CODES_EXTRACTED
                reasons.append("medical_coding:no_codes")

        # BLOCKED: primary dx conflict
        if self._config.block_on_primary_dx_conflict and not blocker:
            for c in case.conflicts:
                if c.field_path == "primary_diagnosis.code" and c.deferred_to_human:
                    blocker = BLOCKED_PRIMARY_DX_CONFLICT
                    reasons.append(f"conflict:{c.field_path}")

        # BLOCKED: critical rule violation
        if self._config.block_on_critical_rule and not blocker:
            cg = case.normalized.get(STAGE_COMPLIANCE, NormalizedExpertResult(expert_id=STAGE_COMPLIANCE))
            for issue in cg.issues:
                rid = str(issue.get("rule_id") or "")
                sev = str(issue.get("severity") or "").lower()
                if rid in self._config.critical_rule_ids and sev in ("critical", "high"):
                    blocker = BLOCKED_CRITICAL_RULE_VIOLATION
                    reasons.append(f"critical_rule:{rid}")
                    break

        # BLOCKED: note severely incomplete
        if self._config.block_on_note_score_below is not None and not blocker:
            nc = case.stage_outputs.get(STAGE_NOTE_COMPLETENESS, {})
            score = nc.get("completeness_score")
            if isinstance(score, (int, float)) and score < self._config.block_on_note_score_below:
                blocker = BLOCKED_NOTE_SEVERELY_INCOMPLETE
                reasons.append(f"note_completeness:score={score:.2f}")

        if blocker:
            case.review_gate_status = REVIEW_BLOCKED
            case.review_gate_blocker = blocker
            case.review_gate_reasons = reasons
            return

        # Not blocked. Decide AUTO_PASS vs REVIEW_*.
        if case.completion:
            if case.completion.status == "COMPLETED":
                case.review_gate_status = REVIEW_AUTO_PASS
            elif case.completion.status == "COMPLETED_WITH_WARNINGS":
                case.review_gate_status = REVIEW_REVIEW_RECOMMENDED
            else:  # NEEDS_HUMAN_REVIEW or INCOMPLETE
                case.review_gate_status = REVIEW_REVIEW_REQUIRED
            case.review_gate_reasons = case.completion.reasons or []
        else:
            case.review_gate_status = REVIEW_AUTO_PASS

    # ------------------------------------------------------------------
    # Output extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_structured_discharge_text(sd: dict) -> str:
        """Pull a usable text blob from discharge-summary-structuring output."""
        if not isinstance(sd, dict):
            return ""
        sections = sd.get("structured_sections") or {}
        if isinstance(sections, dict):
            parts: list[str] = []
            for v in sections.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            t = item.get("text") or item.get("display") or ""
                            if t:
                                parts.append(str(t))
            if parts:
                return "\n".join(parts)
        return ""

    @staticmethod
    def _extract_codes_for_principal(mc: dict) -> list[str]:
        """Pull candidate ICD-10 codes from medical-coding output.

        Handles two shapes:
          - Synthetic/tests: ``extracted_diagnoses: [{final_code|code, is_primary}]``
          - Real agent:      ``codes: [{code, type: "primary_diagnosis"|"secondary_diagnosis"}]``
            (may be nested under ``result.codes`` for the v2 medical-coding agent)
        """
        if not isinstance(mc, dict):
            return []
        # Normalize: if wrapped under "result", unwrap.
        if isinstance(mc.get("result"), dict):
            mc = mc["result"]
        codes: list[str] = []
        diagnoses = (
            mc.get("extracted_diagnoses")
            or mc.get("diagnoses")
            or mc.get("codes")
            or []
        )
        for dx in diagnoses:
            if isinstance(dx, dict):
                c = dx.get("final_code") or dx.get("code")
                if isinstance(c, str) and c:
                    codes.append(c)
        return codes

    @staticmethod
    def _extract_primary_dx_code(mc: dict) -> str:
        """Pull the primary diagnosis code from medical-coding output."""
        if not isinstance(mc, dict):
            return ""
        if isinstance(mc.get("result"), dict):
            mc = mc["result"]
        diagnoses = (
            mc.get("extracted_diagnoses")
            or mc.get("diagnoses")
            or mc.get("codes")
            or []
        )
        for dx in diagnoses:
            if not isinstance(dx, dict):
                continue
            is_primary = (
                dx.get("is_primary")
                or str(dx.get("type", "")).lower() == "primary_diagnosis"
                or str(dx.get("type", "")).lower() == "primary"
            )
            if is_primary:
                c = dx.get("final_code") or dx.get("code")
                if isinstance(c, str):
                    return c
        return ""

    @staticmethod
    def _extract_recommended_dx_code(pd: dict) -> str:
        """Pull recommended primary dx from principal-diagnosis-review output."""
        if not isinstance(pd, dict):
            return ""
        rec = pd.get("recommended")
        if isinstance(rec, dict):
            c = rec.get("code")
            if isinstance(c, str):
                return c
        rp = pd.get("principal_dx") or pd.get("principal_diagnosis")
        if isinstance(rp, str):
            return rp
        return ""

    def _format_principal_dx_prompt(self, raw_text: str, codes: list[str]) -> str:
        codes_block = ", ".join(codes) if codes else "(none extracted)"
        return (
            f"病历文本:\n{raw_text}\n\n"
            f"medical-coding 阶段抽出的候选诊断编码: {codes_block}\n\n"
            "请基于上述信息选出最合适的主诊断 (返回 JSON, 含 coding_draft_consistent 字段)。"
        )

    def _format_evidence_prompt(self, raw_text: str, mc: dict) -> str:
        return (
            f"病历文本:\n{raw_text}\n\n"
            f"medical-coding 阶段提取的诊断 (JSON):\n{self._safe_json(mc)}\n\n"
            "请按 supported / uncertain / rejected 三档对每个诊断编码给出证据强度。"
        )

    def _format_compliance_prompt(self, mc: dict) -> str:
        return (
            "请对以下编码结果做合规审查 (R001-R010):\n"
            f"{self._safe_json(mc)}"
        )

    def _format_drg_prompt(self, mc: dict, pd: dict) -> str:
        return (
            "请基于以下编码 + 主诊断复核结果给出 DRG/DIP 风险点:\n"
            f"medical-coding: {self._safe_json(mc)}\n\n"
            f"principal-dx-review: {self._safe_json(pd)}"
        )

    @staticmethod
    def _safe_json(obj: Any) -> str:
        import json as _j
        try:
            return _j.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return repr(obj)[:4000]


__all__ = [
    "AgentRunner",
    "BLOCKED_CRITICAL_RULE_VIOLATION",
    "BLOCKED_MISSING_DISCHARGE",
    "BLOCKED_NO_CODES_EXTRACTED",
    "BLOCKED_NOTE_SEVERELY_INCOMPLETE",
    "BLOCKED_PRIMARY_DX_CONFLICT",
    "CaseState",
    "CodingComplianceConfig",
    "CodingComplianceOrchestrator",
    "REVIEW_AUTO_PASS",
    "REVIEW_BLOCKED",
    "REVIEW_REVIEW_RECOMMENDED",
    "REVIEW_REVIEW_REQUIRED",
    "STAGE_COMPLIANCE",
    "STAGE_DISCHARGE",
    "STAGE_DRG",
    "STAGE_EVIDENCE",
    "STAGE_MEDICAL_CODING",
    "STAGE_NOTE_COMPLETENESS",
    "STAGE_ORDER",
    "STAGE_PRINCIPAL_DX",
]
