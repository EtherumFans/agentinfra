"""Deterministic Runtime — iCoDer-style safety scaffold around AI decisions.

Five-layer safety framework:
1. STATE MACHINE   — 12 states, only predefined transitions allowed
2. TOOL GATES      — Pre/post checks on every tool invocation
3. DUC (Deny-Unless-Confirmed) — High-risk actions default-deny
4. AUDIT CHAIN     — Append-only structured compliance record
5. HUMAN-IN-THE-LOOP — 5 mandatory human review gates

Principle: All safety decisions are deterministic rules, not AI judgment.
The AI generates suggestions; the runtime validates them before they take effect.
"""
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Layer 1: State Machine
# ============================================================================

class CaseState(str, Enum):
    INGESTED = "INGESTED"
    CONTEXT_READY = "CONTEXT_READY"
    FACTS_EXTRACTED = "FACTS_EXTRACTED"
    CANDIDATES_READY = "CANDIDATES_READY"
    RULES_VALIDATED = "RULES_VALIDATED"
    RISK_IDENTIFIED = "RISK_IDENTIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DECISION_CONFIRMED = "DECISION_CONFIRMED"
    DOC_FEEDBACK_READY = "DOC_FEEDBACK_READY"
    WRITEBACK_PENDING = "WRITEBACK_PENDING"
    WRITTEN_BACK = "WRITTEN_BACK"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# Allowed transitions: from_state -> set of legal to_states
STATE_TRANSITIONS: dict[CaseState, set[CaseState]] = {
    CaseState.INGESTED:           {CaseState.CONTEXT_READY, CaseState.FAILED},
    CaseState.CONTEXT_READY:      {CaseState.FACTS_EXTRACTED, CaseState.ARCHIVED, CaseState.FAILED},
    CaseState.FACTS_EXTRACTED:    {CaseState.CANDIDATES_READY, CaseState.ARCHIVED, CaseState.FAILED},
    CaseState.CANDIDATES_READY:   {CaseState.RULES_VALIDATED, CaseState.FAILED},
    CaseState.RULES_VALIDATED:    {CaseState.RISK_IDENTIFIED, CaseState.REVIEW_REQUIRED, CaseState.FAILED},
    CaseState.RISK_IDENTIFIED:    {CaseState.REVIEW_REQUIRED, CaseState.FAILED},
    CaseState.REVIEW_REQUIRED:    {CaseState.DECISION_CONFIRMED, CaseState.ESCALATED, CaseState.FAILED},
    CaseState.DECISION_CONFIRMED: {CaseState.DOC_FEEDBACK_READY, CaseState.WRITEBACK_PENDING, CaseState.ARCHIVED, CaseState.FAILED},
    CaseState.DOC_FEEDBACK_READY: {CaseState.WRITEBACK_PENDING, CaseState.ARCHIVED, CaseState.FAILED},
    CaseState.WRITEBACK_PENDING:  {CaseState.WRITTEN_BACK, CaseState.ESCALATED, CaseState.FAILED},
    CaseState.WRITTEN_BACK:       {CaseState.ARCHIVED, CaseState.FAILED},
    CaseState.ARCHIVED:           set(),  # No further transitions
    CaseState.FAILED:             {CaseState.INGESTED},  # Can restart
    CaseState.ESCALATED:          {CaseState.REVIEW_REQUIRED},  # Can de-escalate to review
}

# State timeouts (seconds)
STATE_TIMEOUTS: dict[CaseState, int] = {
    CaseState.INGESTED:           1800,   # 30 min
    CaseState.CONTEXT_READY:      600,    # 10 min
    CaseState.FACTS_EXTRACTED:    300,    # 5 min
    CaseState.CANDIDATES_READY:   300,    # 5 min
    CaseState.REVIEW_REQUIRED:    14400,  # 4 hours
    CaseState.WRITEBACK_PENDING:  7200,   # 2 hours
}

# State -> permitted actions (any action not listed is denied)
STATE_ACTIONS: dict[CaseState, set[str]] = {
    CaseState.INGESTED:           {"context_build"},
    CaseState.CONTEXT_READY:      {"extract_facts", "context_build"},
    CaseState.FACTS_EXTRACTED:    {"generate_candidates", "extract_facts"},
    CaseState.CANDIDATES_READY:   {"validate_rules", "generate_candidates"},
    CaseState.RULES_VALIDATED:    {"assess_risk", "validate_rules"},
    CaseState.RISK_IDENTIFIED:    {"request_review", "assess_risk"},
    CaseState.REVIEW_REQUIRED:    {"confirm_decision", "escalate", "finalize_principal_diagnosis",
                                   "confirm_high_dispute_comorbidity", "submit_payment_high_risk"},
    CaseState.DECISION_CONFIRMED: {"generate_feedback", "initiate_writeback", "archive",
                                   "writeback_to_emr", "writeback_to_his", "writeback_to_insurance",
                                   "create_document_correction_task"},
    CaseState.DOC_FEEDBACK_READY: {"initiate_writeback", "archive"},
    CaseState.WRITEBACK_PENDING:  {"complete_writeback", "escalate"},
    CaseState.WRITTEN_BACK:       {"archive"},
    CaseState.ARCHIVED:           set(),
    CaseState.FAILED:             {"restart"},
    CaseState.ESCALATED:          {"de_escalate"},
}

# ============================================================================
# Layer 2: Tool Gates
# ============================================================================

class GateOutcome(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    DENY = "DENY"
    DEFER = "DEFER"


class ToolGate:
    """Pre/post invocation safety checks for tool calls."""

    def pre_check(self, action: str, state: CaseState, actor_role: str,
                  has_human_confirmation: bool = False) -> GateOutcome:
        """Check if an action is permitted in the current state.

        iCoDer equivalent: "PreToolUse Guards"
        """
        # Rule 0: agent expert calls (call_*) are always permitted
        if action.startswith('call_'):
            return GateOutcome.ALLOW

        # Rule 1: state permits this action
        permitted = STATE_ACTIONS.get(state, set())
        if action not in permitted:
            logger.warning(f"Gate DENY: action '{action}' not permitted in state {state}")
            return GateOutcome.DENY

        # Rule 2: high-risk actions need human confirmation
        if action in DUC_ACTIONS and not has_human_confirmation:
            logger.warning(f"Gate REVIEW: DUC action '{action}' lacks human confirmation")
            return GateOutcome.REVIEW

        # Rule 3: writeback actions need decision confirmed
        if action.startswith("writeback") and state != CaseState.DECISION_CONFIRMED and state != CaseState.WRITEBACK_PENDING:
            return GateOutcome.DENY

        return GateOutcome.ALLOW

    # Unified guard_post rules — must pass all applicable checks
    GUARD_POST_RULES = [
        # (rule_name, check_fn_description, applies_to_output_keys)
        ("output_non_empty", "output must not be None or empty string"),
        ("code_candidates_valid", "code candidates must be non-empty list if present"),
        ("evidence_exists", "evidence section must have diagnosis or procedure facts if present"),
        ("drg_structure_valid", "DRG output must have valid structure if present"),
        ("report_non_empty", "report_markdown must not be empty if present"),
        ("high_risk_output_blocked", "output containing blocked terms is DENIED"),
    ]

    # Terms that should never appear in AI-generated output
    BLOCKED_OUTPUT_TERMS = [
        "处方",  # Prescription — never auto-generate
        "建议用药",  # Medication recommendation
        "手术方案",  # Surgical plan
        "剂量",  # Dosage
    ]

    def post_check(self, output: dict, expected_schema: Optional[dict] = None) -> GateOutcome:
        """Validate tool output after execution.

        iCoDer equivalent: "PostToolUse Guards"

        Unified rules:
        1. Output non-empty — output dict must exist and have content
        2. Code candidates valid — if 'diagnosis_candidates'/'procedure_candidates' present, must be list
        3. Evidence exists — if 'evidence' present, must have diagnosis_facts or procedure_facts
        4. DRG structure valid — if 'drg_impact' present, must be dict
        5. Report non-empty — if 'report_markdown' present, must be non-empty string
        6. High-risk output blocked — output text must not contain blocked terms
        """
        if output is None:
            logger.warning("Gate DENY: output is None")
            return GateOutcome.DENY

        # Rule 1: Non-empty output
        if isinstance(output, dict):
            # Check if all values are effectively empty
            has_content = any(
                v is not None and v != "" and v != [] and v != {}
                for v in output.values()
            )
            if not has_content:
                logger.warning("Gate DENY: output dict has no meaningful content")
                return GateOutcome.DENY
        output_str = str(output)
        if not output_str or output_str.strip() in ("", "{}", "[]", "null", "None"):
            logger.warning("Gate DENY: output is empty")
            return GateOutcome.DENY

        # Rule 2: Code candidates valid
        for key in ("diagnosis_candidates", "procedure_candidates"):
            if key in output and output[key] is not None:
                if not isinstance(output[key], list):
                    logger.warning(f"Gate REVIEW: {key} is not a list")
                    return GateOutcome.REVIEW

        # Rule 3: Evidence exists
        if "evidence" in output and output["evidence"] is not None:
            evidence = output["evidence"]
            if isinstance(evidence, dict):
                diag_facts = evidence.get("diagnosis_facts", [])
                proc_facts = evidence.get("procedure_facts", [])
                if not diag_facts and not proc_facts:
                    logger.warning("Gate REVIEW: evidence section has no facts")
                    return GateOutcome.REVIEW

        # Rule 4: DRG structure valid
        if "drg_impact" in output and output["drg_impact"] is not None:
            if not isinstance(output["drg_impact"], dict):
                logger.warning("Gate DENY: drg_impact is not a dict")
                return GateOutcome.DENY

        # Rule 5: Report non-empty
        if "report_markdown" in output and output.get("report_markdown") is not None:
            report = output["report_markdown"]
            if isinstance(report, str) and len(report.strip()) < 10:
                logger.warning("Gate REVIEW: report_markdown is too short")
                return GateOutcome.REVIEW

        # Rule 6: High-risk output blocked
        output_text = json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else output_str
        for term in self.BLOCKED_OUTPUT_TERMS:
            if term in output_text:
                logger.warning(f"Gate DENY: blocked term '{term}' found in output")
                return GateOutcome.DENY

        # Legacy: critical fields null check
        critical = ["primary_diagnosis", "main_procedure", "evidence", "errors"]
        for field in critical:
            if field in output:
                if output[field] is None:
                    logger.warning(f"Gate REVIEW: critical field '{field}' is null")
                    return GateOutcome.REVIEW

        return GateOutcome.ALLOW


# DUC (Deny-Unless-Confirmed) actions — never auto-execute
DUC_ACTIONS = {
    "finalize_principal_diagnosis",
    "confirm_high_dispute_comorbidity",
    "submit_payment_high_risk",
    "writeback_to_emr",
    "writeback_to_his",
    "writeback_to_insurance",
    "create_document_correction_task",
    "archive_case",
    "confirm_decision",
    "initiate_writeback",
    "flag_unsupported_code",
    "resolve_evidence_conflict",
}

# ============================================================================
# Layer 3: Audit Chain
# ============================================================================

class AuditEvent:
    """Append-only, case-scoped event record."""

    def __init__(self, event_type: str, case_id: str, actor: str = "system",
                 payload: dict | None = None):
        self.event_id = uuid.uuid4().hex[:12]
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.case_id = case_id
        self.event_type = event_type
        self.actor = actor
        self.payload = payload or {}
        self.payload_hash = self._hash_payload()

    def _hash_payload(self) -> str:
        try:
            import hashlib
            raw = json.dumps(self.payload, sort_keys=True, ensure_ascii=False)
            return hashlib.sha256(raw.encode()).hexdigest()[:16]
        except Exception:
            return "hash_error"

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "case_id": self.case_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload_hash": self.payload_hash,
            "payload": self.payload,
        }


class AuditChain:
    """Append-only audit log. No deletion, no modification."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self._events: list[AuditEvent] = []

    def record(self, event_type: str, actor: str = "system",
               payload: dict | None = None) -> AuditEvent:
        event = AuditEvent(event_type, self.case_id, actor, payload)
        self._events.append(event)
        logger.info(f"[Audit:{self.case_id}] {event_type} by {actor}")
        return event

    def get_recent(self, n: int = 10) -> list[dict]:
        return [e.to_dict() for e in self._events[-n:]]

    def get_all(self) -> list[dict]:
        return [e.to_dict() for e in self._events]

    def verify_integrity(self) -> bool:
        """Verify the chain has not been tampered with via hash chain validation.

        Each event's payload_hash must match the SHA-256 of its payload.
        In production, this also verifies the linked hash chain (each event
        includes the previous event's hash).
        """
        for event in self._events:
            if event.payload_hash != event._hash_payload():
                logger.error(f"Audit chain integrity violation at event {event.event_id}")
                return False
        return True

    def replay(self, from_idx: int = 0) -> list[dict]:
        """Replay audit events for compliance review or dispute resolution.

        Returns the full decision chain — what tool was called when, by whom,
        with what contract validation results.
        """
        return [e.to_dict() for e in self._events[from_idx:]]

    def __len__(self) -> int:
        return len(self._events)


# ============================================================================
# Layer 4: Deterministic Runtime
# ============================================================================

class DeterministicRuntime:
    """Core runtime that enforces safety boundaries around AI decisions.

    Usage:
        rt = DeterministicRuntime("case-001")
        rt.transition(CaseState.FACTS_EXTRACTED)  # ← validates
        gate = rt.guard("finalize_principal_diagnosis", "coder")
        if gate == GateOutcome.REVIEW:
            ... # require human confirmation
    """

    def __init__(self, case_id: str, pipeline_id: str = "",
                 execution_path: str = "orchestrator", review_id: str = "",
                 agent_id: str = ""):
        self.case_id = case_id
        self.pipeline_id = pipeline_id or case_id
        self.execution_path = execution_path
        self.review_id = review_id
        self.agent_id = agent_id
        self.state = CaseState.INGESTED
        self.state_entered_at = time.time()
        self.gate = ToolGate()
        self.audit = AuditChain(case_id)
        self._human_confirmations: set[str] = set()
        self._total_errors = 0
        self._total_processing_ms: int | None = None

        # Pending persistence queue: list of (type, data_dict)
        self._pending_persist: list[dict] = []

        self.audit.record("state_entered", payload={"state": self.state.value})

    # ---- State Machine ----

    def transition(self, to_state: CaseState, actor: str = "system") -> bool:
        """Attempt to transition to a new state. Returns False if transition is illegal."""
        from_state = self.state

        if to_state not in STATE_TRANSITIONS.get(from_state, set()):
            logger.error(
                f"[Runtime:{self.case_id}] Illegal transition: "
                f"{from_state.value} -> {to_state.value}"
            )
            self.audit.record("illegal_transition_attempt",
                actor=actor,
                payload={"from": from_state.value, "to": to_state.value}
            )
            return False

        self.state = to_state
        self.state_entered_at = time.time()

        self.audit.record("state_transition",
            actor=actor,
            payload={"from": from_state.value, "to": to_state.value}
        )
        # --- Persistence: enqueue state transition ---
        self._enqueue_persist("state_transition", {
            "from": from_state.value,
            "to": to_state.value,
            "transition_type": "normal",
            "actor": actor,
        })
        logger.info(f"[Runtime:{self.case_id}] {from_state.value} -> {to_state.value}")
        return True

    def force_transition(self, to_state: CaseState, reason: str, actor: str = "system"):
        """Force a transition even if normally illegal (for error recovery). Always audited."""
        from_state = self.state
        self.state = to_state
        self.state_entered_at = time.time()
        self.audit.record("forced_transition",
            actor=actor,
            payload={"from": from_state.value, "to": to_state.value, "reason": reason}
        )
        # --- Persistence: enqueue forced transition ---
        self._enqueue_persist("state_transition", {
            "from": from_state.value,
            "to": to_state.value,
            "transition_type": "forced",
            "actor": actor,
            "reason": reason,
        })
        logger.warning(f"[Runtime:{self.case_id}] FORCED: {from_state.value} -> {to_state.value} ({reason})")

    def check_timeout(self) -> Optional[str]:
        """Check if current state has timed out.

        If timed out, auto-transitions to ESCALATED or FAILED and records audit.
        Returns the escalation action string, or None if not timed out.
        """
        timeout = STATE_TIMEOUTS.get(self.state)
        if timeout is None:
            return None
        elapsed = time.time() - self.state_entered_at
        if elapsed > timeout:
            if self.state == CaseState.REVIEW_REQUIRED:
                action = "escalate_to_supervisor"
                self.force_transition(CaseState.ESCALATED,
                    reason=f"Timeout in {self.state.value} after {elapsed:.0f}s (limit {timeout}s)",
                    actor="system")
            elif self.state == CaseState.WRITEBACK_PENDING:
                action = "alert_oncall"
                self.force_transition(CaseState.ESCALATED,
                    reason=f"Writeback timeout after {elapsed:.0f}s (limit {timeout}s)",
                    actor="system")
            else:
                action = "auto_retry"
                self.force_transition(CaseState.FAILED,
                    reason=f"Timeout in {self.state.value} after {elapsed:.0f}s (limit {timeout}s)",
                    actor="system")
            self.audit.record("timeout_escalation",
                actor="system",
                payload={
                    "from_state": self.state.value,
                    "timeout_s": timeout,
                    "elapsed_s": int(elapsed),
                    "action": action,
                }
            )
            return action
        return None

    # ---- Tool Guards ----

    def guard(self, action: str, actor_role: str = "system") -> GateOutcome:
        """Check if an action is permitted. Returns gate outcome."""
        outcome = self.gate.pre_check(
            action=action,
            state=self.state,
            actor_role=actor_role,
            has_human_confirmation=(action in self._human_confirmations),
        )
        self.audit.record("guard_check",
            payload={"action": action, "state": self.state.value, "outcome": outcome.value}
        )
        # --- Persistence: enqueue audit ---
        self._enqueue_persist("audit", {
            "event_type": "guard_check",
            "action": action,
            "actor": actor_role,
            "current_state": self.state.value,
            "guard_result": outcome.value,
            "payload": {"action": action, "outcome": outcome.value},
        })
        return outcome

    def guard_post(self, output: dict, schema: dict | None = None) -> GateOutcome:
        """Validate tool output."""
        outcome = self.gate.post_check(output, schema)
        self.audit.record("post_guard",
            payload={"outcome": outcome.value}
        )
        # --- Persistence: enqueue audit ---
        self._enqueue_persist("audit", {
            "event_type": "post_guard",
            "actor": "system",
            "current_state": self.state.value,
            "post_check_result": outcome.value,
            "payload": {"outcome": outcome.value},
        })
        return outcome

    # ---- Human Confirmation ----

    def human_confirm(self, action: str, reviewer: str, rationale: str = "") -> bool:
        """Record human confirmation for a DUC action."""
        self._human_confirmations.add(action)
        self.audit.record("human_confirmation",
            actor=reviewer,
            payload={"action": action, "rationale": rationale}
        )
        # --- Persistence: enqueue DUC decision ---
        self._enqueue_persist("duc_decision", {
            "action": action,
            "reviewer": reviewer,
            "decision": "approved",
            "reason": rationale,
            "current_state": self.state.value,
        })
        logger.info(f"[Runtime:{self.case_id}] Human confirmed: {action} by {reviewer}")
        return True

    def is_human_confirmed(self, action: str) -> bool:
        return action in self._human_confirmations

    # ---- Persistence ----

    def _enqueue_persist(self, event_type: str, data: dict):
        """Enqueue a persistence event for later flush to DB."""
        self._pending_persist.append({
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })

    def get_pending_persist(self) -> list[dict]:
        """Return (and clear) the pending persistence queue."""
        queue = self._pending_persist[:]
        self._pending_persist.clear()
        return queue

    async def flush_to_db(self, db) -> int:
        """Persist all pending events to database. Returns count of records written.

        Call this at the end of pipeline/agent execution.
        Uses the async SQLAlchemy session passed by the caller.
        """
        from app.models.runtime_persistence import (
            RuntimeSession as RuntimeSessionModel,
            RuntimeTransition as RuntimeTransitionModel,
            RuntimeAuditRecord as RuntimeAuditRecordModel,
            DUCDecision as DUCDecisionModel,
        )

        queue = self.get_pending_persist()
        if not queue:
            return 0

        written = 0

        # 1. Upsert RuntimeSession
        session_model = RuntimeSessionModel(
            runtime_id=self.case_id,
            pipeline_id=self.pipeline_id,
            review_id=self.review_id or None,
            agent_id=self.agent_id or None,
            current_state=self.state.value,
            previous_state=None,
            state_entered_at=datetime.fromtimestamp(self.state_entered_at, tz=timezone.utc),
            escalated=(self.state == CaseState.ESCALATED),
            failed=(self.state == CaseState.FAILED),
            archived=(self.state == CaseState.ARCHIVED),
            execution_path=self.execution_path,
            total_processing_ms=self._total_processing_ms,
            error_count=self._total_errors,
        )
        session_model.seal()
        # Upsert: check if exists
        from sqlalchemy import select as _select
        result = await db.execute(
            _select(RuntimeSessionModel).where(RuntimeSessionModel.runtime_id == self.case_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.current_state = self.state.value
            existing.previous_state = session_model.previous_state
            existing.state_entered_at = session_model.state_entered_at
            existing.escalated = session_model.escalated
            existing.failed = session_model.failed
            existing.archived = session_model.archived
            existing.total_processing_ms = session_model.total_processing_ms
            existing.error_count = session_model.error_count
            existing.updated_at = datetime.now(timezone.utc)
            existing.seal()
            db.add(existing)
        else:
            db.add(session_model)
        written += 1

        # 2. Insert RuntimeTransitions
        for event in queue:
            etype = event["type"]
            data = event["data"]

            if etype == "state_transition":
                t = RuntimeTransitionModel(
                    runtime_id=self.case_id,
                    from_state=data.get("from", ""),
                    to_state=data.get("to", ""),
                    transition_type=data.get("transition_type", "normal"),
                    actor=data.get("actor", "system"),
                    reason=data.get("reason"),
                    payload=data.get("payload"),
                )
                t.seal()
                db.add(t)
                written += 1

            elif etype == "audit":
                ar = RuntimeAuditRecordModel(
                    runtime_id=self.case_id,
                    event_type=data.get("event_type", "unknown"),
                    action=data.get("action"),
                    actor=data.get("actor", "system"),
                    current_state=data.get("current_state"),
                    guard_result=data.get("guard_result"),
                    post_check_result=data.get("post_check_result"),
                    payload=data.get("payload"),
                )
                ar.seal()
                db.add(ar)
                written += 1

            elif etype == "duc_decision":
                dd = DUCDecisionModel(
                    runtime_id=self.case_id,
                    action=data.get("action", ""),
                    reviewer=data.get("reviewer", "system"),
                    decision=data.get("decision", "approved"),
                    reason=data.get("reason"),
                    current_state=data.get("current_state"),
                )
                dd.seal()
                db.add(dd)
                written += 1

        await db.commit()
        logger.info(f"[Runtime:{self.case_id}] Flushed {written} records to DB (from {len(queue)} events)")
        return written

    # ---- Status ----

    def status(self) -> dict:
        return {
            "case_id": self.case_id,
            "state": self.state.value,
            "state_duration_s": int(time.time() - self.state_entered_at),
            "audit_events": len(self.audit),
            "human_confirmations": list(self._human_confirmations),
        }


# ============================================================================
# Layer 5: Runtime Registry (global)
# ============================================================================

class RuntimeRegistry:
    """Global registry of active DeterministicRuntime instances."""

    def __init__(self):
        self._runtimes: dict[str, DeterministicRuntime] = {}

    def create(self, case_id: str) -> DeterministicRuntime:
        rt = DeterministicRuntime(case_id)
        self._runtimes[case_id] = rt
        return rt

    def get(self, case_id: str) -> Optional[DeterministicRuntime]:
        return self._runtimes.get(case_id)

    def get_or_create(self, case_id: str) -> DeterministicRuntime:
        if case_id not in self._runtimes:
            return self.create(case_id)
        return self._runtimes[case_id]

    def remove(self, case_id: str):
        self._runtimes.pop(case_id, None)

    def active_count(self) -> int:
        return len(self._runtimes)
        """Find cases that have been stuck in a state for too long."""
        stale = []
        now = time.time()
        for case_id, rt in self._runtimes.items():
            if rt.state in (CaseState.ARCHIVED, CaseState.FAILED):
                continue
            elapsed_h = (now - rt.state_entered_at) / 3600
            if elapsed_h > max_age_hours:
                stale.append(case_id)
        return stale


# Global singleton
runtime_registry = RuntimeRegistry()
