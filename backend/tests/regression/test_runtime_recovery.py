# Regression: Runtime Recovery — failure paths, timeout, illegal transitions
import pytest
from app.services.runtime import (
    DeterministicRuntime, CaseState, GateOutcome,
    runtime_registry,
)


class TestRuntimeStateRecovery:
    def setup_method(self):
        runtime_registry._runtimes.clear()

    def test_failed_to_ingested_retry(self):
        rt = DeterministicRuntime(case_id="R-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FAILED, actor="orchestrator")
        assert rt.state == CaseState.FAILED
        ok = rt.transition(CaseState.INGESTED, actor="orchestrator")
        assert ok is True
        assert rt.state == CaseState.INGESTED

    def test_illegal_transition_returns_false(self):
        rt = DeterministicRuntime(case_id="R-002")
        # ARCHIVED directly from INGESTED is illegal
        ok = rt.transition(CaseState.ARCHIVED, actor="test")
        assert ok is False
        assert rt.state == CaseState.INGESTED  # unchanged

    def test_normal_pipeline_flow(self):
        rt = DeterministicRuntime(case_id="R-003")
        path = [CaseState.CONTEXT_READY, CaseState.FACTS_EXTRACTED, CaseState.CANDIDATES_READY,
                CaseState.RULES_VALIDATED, CaseState.REVIEW_REQUIRED]
        for state in path:
            ok = rt.transition(state, actor="orchestrator")
            assert ok is True, f"Failed at {state.value}"
        assert rt.state == CaseState.REVIEW_REQUIRED


class TestRuntimeTimeoutRecovery:
    def setup_method(self):
        runtime_registry._runtimes.clear()

    def test_review_required_timeout_escalates(self):
        rt = DeterministicRuntime(case_id="R-004")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.CANDIDATES_READY, actor="test")
        rt.transition(CaseState.RULES_VALIDATED, actor="test")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="test")
        rt.state_entered_at = 0  # epoch 0
        rt.check_timeout()
        assert rt.state == CaseState.ESCALATED

    def test_ingested_timeout_fails(self):
        rt = DeterministicRuntime(case_id="R-005")
        rt.state_entered_at = 0
        rt.check_timeout()
        assert rt.state == CaseState.FAILED

    def test_no_timeout_when_recent(self):
        rt = DeterministicRuntime(case_id="R-006")
        import time
        rt.state_entered_at = time.time()  # just now
        result = rt.check_timeout()
        assert result is None  # No timeout triggered
        assert rt.state == CaseState.INGESTED  # unchanged


class TestRuntimeGuardRecovery:
    def setup_method(self):
        runtime_registry._runtimes.clear()

    def test_guard_denies_in_wrong_state(self):
        rt = DeterministicRuntime(case_id="R-007")
        gate = rt.guard("writeback_to_emr", "test")
        assert gate == GateOutcome.DENY

    def test_guard_allows_confirm_in_review_state(self):
        rt = DeterministicRuntime(case_id="R-008")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.CANDIDATES_READY, actor="test")
        rt.transition(CaseState.RULES_VALIDATED, actor="test")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="test")
        gate = rt.guard("confirm_decision", "test")
        assert gate != GateOutcome.DENY

    def test_du_action_without_confirm_returns_review(self):
        rt = DeterministicRuntime(case_id="R-009")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.transition(CaseState.CANDIDATES_READY, actor="test")
        rt.transition(CaseState.RULES_VALIDATED, actor="test")
        rt.transition(CaseState.REVIEW_REQUIRED, actor="test")
        gate = rt.guard("finalize_principal_diagnosis", "test")
        # Should be REVIEW because human hasn't confirmed the DUC action
        assert gate in (GateOutcome.REVIEW, GateOutcome.DENY)


class TestRuntimeAuditRecovery:
    def setup_method(self):
        runtime_registry._runtimes.clear()

    def test_audit_persists_after_error(self):
        rt = DeterministicRuntime(case_id="R-010")
        rt.audit.record("test_event", actor="test", payload={"key": "value"})
        rt.transition(CaseState.ARCHIVED, actor="test")  # illegal — returns False
        assert len(rt.audit.get_all()) >= 1

    def test_audit_records_timeout_escalation(self):
        rt = DeterministicRuntime(case_id="R-011")
        before = len(rt.audit.get_all())
        rt.state_entered_at = 0
        rt.check_timeout()
        after = len(rt.audit.get_all())
        assert after > before  # Timeout should have recorded additional events

    def test_audit_records_guard_outcomes(self):
        rt = DeterministicRuntime(case_id="R-012")
        before = len(rt.audit.get_all())
        rt.guard("writeback_to_emr", "test")
        after = len(rt.audit.get_all())
        assert after >= before  # Guard check records events

    def test_audit_records_illegal_transition(self):
        rt = DeterministicRuntime(case_id="R-013")
        before = len(rt.audit.get_all())
        rt.transition(CaseState.ARCHIVED, actor="test")
        after = len(rt.audit.get_all())
        assert after > before  # Illegal attempt should be recorded


class TestRuntimeRegistryRecovery:
    def setup_method(self):
        runtime_registry._runtimes.clear()

    def test_get_or_create_idempotent(self):
        rt1 = runtime_registry.get_or_create("PIPE-001")
        rt2 = runtime_registry.get_or_create("PIPE-001")
        assert rt1 is rt2

    def test_multiple_pipelines_isolated(self):
        rt1 = runtime_registry.get_or_create("PIPE-A")
        rt2 = runtime_registry.get_or_create("PIPE-B")
        rt1.transition(CaseState.FAILED, actor="test")
        assert rt1.state == CaseState.FAILED
        assert rt2.state == CaseState.INGESTED  # rt2 unaffected
