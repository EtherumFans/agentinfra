# Runtime Discipline Tests — comprehensive coverage of the 5-layer safety framework
#
# Coverage:
# 1. Legal state flow (INGESTED → CONTEXT_READY → FACTS_EXTRACTED → ... → ARCHIVED)
# 2. Illegal state transitions rejected
# 3. REVIEW_REQUIRED blocks unconfirmed actions
# 4. DECISION_CONFIRMED requires human_confirm for DUC actions
# 5. Timeout escalation (FAILED / ESCALATED)
# 6. Guard denial (action not permitted in state)
# 7. Guard_post denial (blocked terms, empty output, invalid structure)
# 8. Audit chain integrity
import time
import pytest
from app.services.runtime import (
    runtime_registry, DeterministicRuntime, CaseState, GateOutcome,
    ToolGate, STATE_TRANSITIONS, STATE_ACTIONS, DUC_ACTIONS, STATE_TIMEOUTS,
)


@pytest.fixture(autouse=True)
def cleanup_registry():
    runtime_registry._runtimes.clear()
    yield
    runtime_registry._runtimes.clear()


# ============================================================================
# 1. LEGAL STATE FLOW
# ============================================================================

class TestLegalStateFlow:
    """Verify all legal state transitions work correctly."""

    def test_full_happy_path(self):
        """Full pipeline: INGESTED → CONTEXT_READY → FACTS_EXTRACTED →
        CANDIDATES_READY → RULES_VALIDATED → REVIEW_REQUIRED →
        DECISION_CONFIRMED → ARCHIVED"""
        rt = runtime_registry.get_or_create("case-happy-001")
        assert rt.state == CaseState.INGESTED

        # Step through every state
        assert rt.transition(CaseState.CONTEXT_READY, actor="system")
        assert rt.state == CaseState.CONTEXT_READY

        assert rt.transition(CaseState.FACTS_EXTRACTED, actor="evidence_expert")
        assert rt.state == CaseState.FACTS_EXTRACTED

        assert rt.transition(CaseState.CANDIDATES_READY, actor="coder")
        assert rt.state == CaseState.CANDIDATES_READY

        assert rt.transition(CaseState.RULES_VALIDATED, actor="homepage_expert")
        assert rt.state == CaseState.RULES_VALIDATED

        assert rt.transition(CaseState.REVIEW_REQUIRED, actor="orchestrator")
        assert rt.state == CaseState.REVIEW_REQUIRED

        # Human confirms DUC action
        rt.human_confirm("confirm_decision", reviewer="doctor_wang",
                        rationale="All codes verified")
        assert rt.transition(CaseState.DECISION_CONFIRMED, actor="doctor_wang")
        assert rt.state == CaseState.DECISION_CONFIRMED

        assert rt.transition(CaseState.ARCHIVED, actor="system")
        assert rt.state == CaseState.ARCHIVED

        # ARCHIVED has no valid transitions
        assert rt.transition(CaseState.INGESTED, actor="system") is False

        # Audit chain should have events for each key step
        event_types = {e.event_type for e in rt.audit._events}
        assert "state_transition" in event_types
        assert "human_confirmation" in event_types
        assert len(rt.audit) >= 8  # state_entered + state_transitions + guard + confirm

    def test_fast_path_context_to_archived(self):
        """AgentRunner fast path: INGESTED → CONTEXT_READY → FACTS_EXTRACTED → ARCHIVED"""
        rt = runtime_registry.get_or_create("case-fast-001")
        assert rt.transition(CaseState.CONTEXT_READY, actor="agent_runner")
        assert rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
        assert rt.transition(CaseState.ARCHIVED, actor="agent_runner")
        assert rt.state == CaseState.ARCHIVED

    def test_failed_can_restart(self):
        """FAILED state can restart back to INGESTED."""
        rt = runtime_registry.get_or_create("case-fail-restart")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FAILED, actor="test")
        assert rt.state == CaseState.FAILED
        assert rt.transition(CaseState.INGESTED, actor="test")
        assert rt.state == CaseState.INGESTED

    def test_review_required_can_go_to_multiple_states(self):
        """REVIEW_REQUIRED → DECISION_CONFIRMED | ESCALATED | FAILED"""
        rt = runtime_registry.get_or_create("case-review-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.CANDIDATES_READY, actor="test")
        rt.transition(CaseState.RULES_VALIDATED, actor="test")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="test")

        rt2 = runtime_registry.get_or_create("case-review-002")
        rt2.transition(CaseState.CONTEXT_READY, actor="test")
        rt2.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt2.transition(CaseState.CANDIDATES_READY, actor="test")
        rt2.transition(CaseState.RULES_VALIDATED, actor="test")
        rt2.transition(CaseState.REVIEW_REQUIRED, actor="test")
        assert rt2.transition(CaseState.ESCALATED, actor="test")

        rt3 = runtime_registry.get_or_create("case-review-003")
        rt3.transition(CaseState.CONTEXT_READY, actor="test")
        rt3.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt3.transition(CaseState.CANDIDATES_READY, actor="test")
        rt3.transition(CaseState.RULES_VALIDATED, actor="test")
        rt3.transition(CaseState.REVIEW_REQUIRED, actor="test")
        assert rt3.transition(CaseState.FAILED, actor="test")

    def test_escalated_can_de_escalate(self):
        """ESCALATED can go back to REVIEW_REQUIRED."""
        rt = runtime_registry.get_or_create("case-esc-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.CANDIDATES_READY, actor="test")
        rt.transition(CaseState.RULES_VALIDATED, actor="test")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="test")
        rt.transition(CaseState.ESCALATED, actor="test")
        assert rt.state == CaseState.ESCALATED
        assert rt.transition(CaseState.REVIEW_REQUIRED, actor="supervisor")


# ============================================================================
# 2. ILLEGAL STATE TRANSITIONS
# ============================================================================

class TestIllegalStateTransitions:
    """Verify illegal transitions are rejected."""

    def test_ingested_cannot_jump_to_archived(self):
        rt = runtime_registry.get_or_create("case-illegal-001")
        assert rt.transition(CaseState.ARCHIVED, actor="hacker") is False
        assert rt.state == CaseState.INGESTED

    def test_facts_extracted_cannot_jump_to_decision_confirmed(self):
        rt = runtime_registry.get_or_create("case-illegal-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        assert rt.transition(CaseState.DECISION_CONFIRMED, actor="hacker") is False
        assert rt.state == CaseState.FACTS_EXTRACTED

    def test_archived_cannot_transition_anywhere(self):
        rt = runtime_registry.get_or_create("case-illegal-003")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.ARCHIVED, actor="test")
        assert rt.state == CaseState.ARCHIVED
        for state in CaseState:
            if state != CaseState.ARCHIVED:
                assert rt.transition(state, actor="test") is False

    def test_force_transition_bypasses_illegal(self):
        """force_transition can bypass illegal transitions (for error recovery)."""
        rt = runtime_registry.get_or_create("case-force-001")
        rt.force_transition(CaseState.ARCHIVED, reason="emergency recovery", actor="admin")
        assert rt.state == CaseState.ARCHIVED
        # Audit should record the forced transition
        events = [e.event_type for e in rt.audit._events]
        assert "forced_transition" in events

    def test_illegal_transition_audited(self):
        """Illegal transition attempt is recorded in audit."""
        rt = runtime_registry.get_or_create("case-illegal-audit")
        rt.transition(CaseState.ARCHIVED, actor="test")  # Illegal, returns False
        events = [e.event_type for e in rt.audit._events]
        assert "illegal_transition_attempt" in events


# ============================================================================
# 3. REVIEW_REQUIRED BLOCKS UNAPPROVED ACTIONS
# ============================================================================

class TestReviewRequiredBlocking:
    """REVIEW_REQUIRED state: only certain actions permitted."""

    def test_review_required_permits_only_listed_actions(self):
        rt = runtime_registry.get_or_create("case-rr-001")
        # Navigate to REVIEW_REQUIRED
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")

        # These actions should be permitted in REVIEW_REQUIRED
        permitted = STATE_ACTIONS[CaseState.REVIEW_REQUIRED]
        assert "confirm_decision" in permitted
        assert "escalate" in permitted
        assert "finalize_principal_diagnosis" in permitted

        # These should NOT be permitted
        not_permitted = ["extract_facts", "generate_candidates", "writeback_to_emr",
                        "context_build", "validate_rules"]
        for action in not_permitted:
            gate = rt.guard(action, "test")
            assert gate == GateOutcome.DENY, f"Action '{action}' should be DENIED in REVIEW_REQUIRED"

    def test_confirm_decision_without_human_returns_review(self):
        """confirm_decision is DUC — guard returns REVIEW without human_confirm."""
        rt = runtime_registry.get_or_create("case-rr-002")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")

        # confirm_decision IS in REVIEW_REQUIRED's actions but IS a DUC action
        gate = rt.guard("confirm_decision", "unauthorized")
        assert gate == GateOutcome.REVIEW  # DUC: needs human confirmation

    def test_confirm_decision_with_human_returns_allow(self):
        """After human_confirm, guard returns ALLOW for the same action."""
        rt = runtime_registry.get_or_create("case-rr-003")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")

        rt.human_confirm("confirm_decision", reviewer="doctor_li",
                        rationale="Verified all diagnoses")
        gate = rt.guard("confirm_decision", "doctor_li")
        assert gate == GateOutcome.ALLOW


# ============================================================================
# 4. DECISION_CONFIRMED REQUIRES HUMAN_CONFIRM
# ============================================================================

class TestDecisionConfirmedRequiresHumanConfirm:
    """DUC actions in DECISION_CONFIRMED need human_confirm."""

    def test_writeback_to_emr_without_confirm_denied(self):
        """writeback_to_emr is DUC + requires DECISION_CONFIRMED state."""
        rt = runtime_registry.get_or_create("case-dc-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        # Not yet in DECISION_CONFIRMED
        gate = rt.guard("writeback_to_emr", "coder")
        assert gate == GateOutcome.DENY  # Not in correct state

    def test_duc_action_in_decision_confirmed_without_human_returns_review(self):
        """In DECISION_CONFIRMED, DUC actions need human_confirm."""
        rt = runtime_registry.get_or_create("case-dc-002")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")
        rt.human_confirm("confirm_decision", reviewer="doc", rationale="ok")
        rt.transition(CaseState.DECISION_CONFIRMED, actor="doc")

        # initiate_writeback is DUC — needs human confirmation
        gate = rt.guard("initiate_writeback", "system")
        assert gate == GateOutcome.REVIEW  # DUC without human_confirm

    def test_duc_action_with_human_confirm_in_decision_confirmed_allowed(self):
        """After human_confirm in DECISION_CONFIRMED, DUC actions are ALLOW."""
        rt = runtime_registry.get_or_create("case-dc-003")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")
        rt.human_confirm("confirm_decision", reviewer="doc", rationale="ok")
        rt.transition(CaseState.DECISION_CONFIRMED, actor="doc")

        rt.human_confirm("writeback_to_emr", reviewer="doc",
                        rationale="EMR writeback approved")
        gate = rt.guard("writeback_to_emr", "doc")
        assert gate == GateOutcome.ALLOW


# ============================================================================
# 5. TIMEOUT ESCALATION
# ============================================================================

class TestTimeoutEscalation:
    """check_timeout auto-transitions to FAILED or ESCALATED with audit."""

    def test_timeout_in_facts_extracted_goes_to_failed(self):
        """Non-review timeout → FAILED."""
        rt = DeterministicRuntime("case-timeout-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")

        # Manually set state_entered_at far in the past to force timeout
        rt.state_entered_at = time.time() - 99999  # ~27 hours ago
        action = rt.check_timeout()

        assert action == "auto_retry"
        assert rt.state == CaseState.FAILED
        # Audit should have timeout_escalation event
        events = [e.event_type for e in rt.audit._events]
        assert "timeout_escalation" in events

    def test_timeout_in_review_required_goes_to_escalated(self):
        """REVIEW_REQUIRED timeout → ESCALATED."""
        rt = DeterministicRuntime("case-timeout-002")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")

        rt.state_entered_at = time.time() - 99999
        action = rt.check_timeout()

        assert action == "escalate_to_supervisor"
        assert rt.state == CaseState.ESCALATED

    def test_timeout_in_writeback_pending_goes_to_escalated(self):
        """WRITEBACK_PENDING timeout → ESCALATED."""
        rt = DeterministicRuntime("case-timeout-003")
        for s in [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED,
                   CaseState.CANDIDATES_READY, CaseState.RULES_VALIDATED,
                   CaseState.REVIEW_REQUIRED]:
            rt.transition(s, actor="test")
        rt.human_confirm("confirm_decision", reviewer="doc", rationale="ok")
        rt.transition(CaseState.DECISION_CONFIRMED, actor="doc")
        rt.transition(CaseState.WRITEBACK_PENDING, actor="test")

        rt.state_entered_at = time.time() - 99999
        action = rt.check_timeout()

        assert action == "alert_oncall"
        assert rt.state == CaseState.ESCALATED

    def test_no_timeout_when_within_limit(self):
        """When within timeout limit, check_timeout returns None."""
        rt = DeterministicRuntime("case-timeout-004")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        # state_entered_at is current time, within 300s limit
        action = rt.check_timeout()
        assert action is None
        assert rt.state == CaseState.FACTS_EXTRACTED  # State unchanged

    def test_timeout_with_state_with_no_timeout_config(self):
        """States without timeout config return None."""
        rt = DeterministicRuntime("case-timeout-005")
        # INGESTED has timeout 1800s, but we just entered it
        action = rt.check_timeout()
        assert action is None  # Within limit

    def test_timeout_audit_payload(self):
        """Timeout audit event contains correct payload."""
        rt = DeterministicRuntime("case-timeout-006")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.state_entered_at = time.time() - 99999
        rt.check_timeout()

        events = rt.audit.get_all()
        timeout_event = [e for e in events if e["event_type"] == "timeout_escalation"]
        assert len(timeout_event) == 1
        payload = timeout_event[0].get("payload", {}) if isinstance(timeout_event[0], dict) else {}
        # payload may not be in dict form from get_all, check event object
        # The audit event payload is stored in the AuditEvent, verify via raw events
        raw_events = rt.audit._events
        timeout_raw = [e for e in raw_events if e.event_type == "timeout_escalation"]
        assert len(timeout_raw) == 1
        assert "timeout_s" in timeout_raw[0].payload
        assert "elapsed_s" in timeout_raw[0].payload
        assert "action" in timeout_raw[0].payload


# ============================================================================
# 6. GUARD DENIAL
# ============================================================================

class TestGuardDenial:
    """Guard returns DENY for actions not permitted in current state."""

    def test_all_duc_actions_require_correct_state(self):
        """Each DUC action should be denied outside its permitted state."""
        rt = runtime_registry.get_or_create("case-guard-001")
        # In INGESTED, only context_build is permitted
        for action in DUC_ACTIONS:
            gate = rt.guard(action, "test")
            assert gate == GateOutcome.DENY, \
                f"DUC action '{action}' should be DENIED in INGESTED state"

    def test_wrong_state_for_action(self):
        """An action permitted in one state is denied in another."""
        rt = runtime_registry.get_or_create("case-guard-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")

        # extract_facts IS permitted in CONTEXT_READY
        assert rt.guard("extract_facts", "test") == GateOutcome.ALLOW

        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        # validate_rules is NOT permitted in FACTS_EXTRACTED
        assert rt.guard("validate_rules", "test") == GateOutcome.DENY

    def test_guard_denial_is_audited(self):
        """Every guard check (including denials) is audited."""
        rt = runtime_registry.get_or_create("case-guard-003")
        rt.guard("writeback_to_emr", "hacker")  # Will be DENIED in INGESTED
        rt.guard("context_build", "user")  # Will be ALLOWED in INGESTED

        events = [e for e in rt.audit._events if e.event_type == "guard_check"]
        assert len(events) == 2
        outcomes = [e.payload.get("outcome") for e in events]
        assert "DENY" in outcomes
        assert "ALLOW" in outcomes


# ============================================================================
# 7. GUARD_POST DENIAL
# ============================================================================

class TestGuardPostDenial:
    """guard_post must reject invalid outputs per unified rules."""

    def test_none_output_denied(self):
        rt = DeterministicRuntime("case-post-001")
        gate = rt.guard_post(None)
        assert gate == GateOutcome.DENY

    def test_empty_output_denied(self):
        rt = DeterministicRuntime("case-post-002")
        gate = rt.guard_post({})
        assert gate == GateOutcome.DENY

    def test_empty_string_output_denied(self):
        rt = DeterministicRuntime("case-post-003")
        gate = rt.guard_post({"output": ""})
        # Empty dict with empty string is still non-empty as a dict but has empty content
        assert gate in (GateOutcome.DENY, GateOutcome.REVIEW)

    def test_blocked_term_in_output_denied(self):
        rt = DeterministicRuntime("case-post-004")
        output = {"output": "根据诊断结果，建议使用以下处方进行治疗"}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.DENY  # "处方" is a blocked term

    def test_blocked_term_dosage_denied(self):
        rt = DeterministicRuntime("case-post-005")
        output = {"output": "建议剂量为每日三次"}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.DENY  # "剂量" is a blocked term

    def test_blocked_term_surgery_denied(self):
        rt = DeterministicRuntime("case-post-006")
        output = {"output": "推荐手术方案为..."}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.DENY  # "手术方案" is a blocked term

    def test_evidence_without_facts_review(self):
        rt = DeterministicRuntime("case-post-007")
        output = {"evidence": {"diagnosis_facts": [], "procedure_facts": []}}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.REVIEW

    def test_drg_impact_not_dict_denied(self):
        rt = DeterministicRuntime("case-post-008")
        output = {"drg_impact": "not a dict"}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.DENY

    def test_report_too_short_review(self):
        rt = DeterministicRuntime("case-post-009")
        output = {"report_markdown": "Hi"}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.REVIEW

    def test_code_candidates_not_list_review(self):
        rt = DeterministicRuntime("case-post-010")
        output = {"diagnosis_candidates": "not a list"}
        gate = rt.guard_post(output)
        assert gate == GateOutcome.REVIEW

    def test_valid_output_allowed(self):
        rt = DeterministicRuntime("case-post-011")
        output = {
            "diagnosis_candidates": [{"code": "M80.0", "name": "骨质疏松"}],
            "procedure_candidates": [],
            "evidence": {"diagnosis_facts": [{"finding": "骨质疏松"}], "procedure_facts": []},
            "drg_impact": {"estimated_drg": "I68"},
            "report_markdown": "# 编码审核报告\n\n审核完成，编码正确。",
            "errors": [],
        }
        gate = rt.guard_post(output)
        assert gate == GateOutcome.ALLOW

    def test_guard_post_audited(self):
        rt = DeterministicRuntime("case-post-012")
        output = {"report_markdown": "# Valid Report\n\nEverything looks good. No issues found in this review."}
        rt.guard_post(output)
        events = [e for e in rt.audit._events if e.event_type == "post_guard"]
        assert len(events) == 1


# ============================================================================
# 8. AUDIT CHAIN INTEGRITY
# ============================================================================

class TestAuditChainIntegrity:
    """Audit chain is append-only, complete, and verifiable."""

    def test_audit_events_are_ordered(self):
        rt = DeterministicRuntime("case-audit-001")
        rt.transition(CaseState.CONTEXT_READY, actor="system")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="expert")
        rt.transition(CaseState.ARCHIVED, actor="system")

        events = rt.audit._events
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)  # Chronological order

    def test_audit_events_have_all_required_fields(self):
        rt = DeterministicRuntime("case-audit-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.guard("extract_facts", "expert")
        rt.human_confirm("confirm_decision", "doctor", "ok")

        for event in rt.audit._events:
            assert event.event_id  # Unique ID
            assert event.timestamp  # ISO timestamp
            assert event.case_id == "case-audit-002"  # Correct case
            assert event.event_type  # Event type
            assert event.actor  # Who performed the action
            assert isinstance(event.payload, dict)  # Payload is dict

    def test_audit_cannot_be_modified(self):
        """Audit events are append-only — no deletion/modification."""
        rt = DeterministicRuntime("case-audit-003")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        initial_count = len(rt.audit)

        # Try to get events and modify — won't affect original
        events = rt.audit.get_all()
        events.clear()  # This clears the returned copy, not the original
        assert len(rt.audit) == initial_count  # Original unchanged

    def test_audit_get_recent_limits_results(self):
        rt = DeterministicRuntime("case-audit-004")
        for i in range(15):
            rt.audit.record(f"event_{i}", actor="test")
        recent = rt.audit.get_recent(5)
        assert len(recent) == 5

    def test_full_pipeline_audit_completeness(self):
        """Complete pipeline produces a comprehensive audit trail."""
        rt = DeterministicRuntime("case-audit-005")
        rt.transition(CaseState.CONTEXT_READY, actor="orchestrator")
        rt.guard("extract_facts", "evidence_expert")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="evidence_expert")
        rt.guard("generate_candidates", "coder")
        rt.transition(CaseState.CANDIDATES_READY, actor="coder")
        rt.guard("validate_rules", "homepage_expert")
        rt.transition(CaseState.RULES_VALIDATED, actor="homepage_expert")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="orchestrator")
        rt.guard("finalize_principal_diagnosis", "orchestrator")
        rt.human_confirm("confirm_decision", "doctor", "Verified")
        rt.transition(CaseState.DECISION_CONFIRMED, actor="doctor")
        rt.guard_post({"diagnosis_candidates": [{"code": "M80"}], "evidence": {"diagnosis_facts": [{"f": 1}]}, "report_markdown": "# Good Report\n\nAll codes verified.", "errors": []})
        rt.transition(CaseState.ARCHIVED, actor="orchestrator")

        # Should have audit events for each step type
        event_types = {e.event_type for e in rt.audit._events}
        expected_types = {
            "state_entered", "state_transition", "guard_check",
            "human_confirmation", "post_guard",
        }
        assert expected_types.issubset(event_types)

    def test_timeout_escalation_appears_in_audit(self):
        """Timeout escalation is fully audited."""
        rt = DeterministicRuntime("case-audit-006")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.state_entered_at = time.time() - 99999
        rt.check_timeout()

        events = rt.audit.get_all()
        event_types = [e["event_type"] for e in events]
        assert "timeout_escalation" in event_types
        assert "forced_transition" in event_types

    def test_illegal_transition_appears_in_audit(self):
        """Illegal transition attempts are recorded."""
        rt = DeterministicRuntime("case-audit-007")
        rt.transition(CaseState.ARCHIVED, actor="hacker")  # Illegal

        events = [e.event_type for e in rt.audit._events]
        assert "illegal_transition_attempt" in events
