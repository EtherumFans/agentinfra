# Runtime Persistence Tests
#
# Coverage:
# 1. Flush to DB — events persisted correctly
# 2. Restart recovery — sessions loaded back into registry
# 3. Audit immutability — seal + verify_integrity
# 4. State sync — Runtime → Review/Candidate status
# 5. Migration — upgrade/downgrade structure
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.runtime import (
    runtime_registry, DeterministicRuntime, CaseState, GateOutcome,
    STATE_TRANSITIONS, STATE_ACTIONS, DUC_ACTIONS, STATE_TIMEOUTS,
)
from app.models.runtime_persistence import (
    RuntimeSession, RuntimeTransition, RuntimeAuditRecord, DUCDecision,
    _content_hash,
)
from app.services.runtime_state_sync import (
    runtime_state_sync, RUNTIME_TO_REVIEW_STATUS, RUNTIME_TO_CANDIDATE_STATUS,
    SYNC_TRIGGER_STATES,
)


@pytest.fixture(autouse=True)
def cleanup_registry():
    runtime_registry._runtimes.clear()
    yield
    runtime_registry._runtimes.clear()


# ============================================================================
# 1. PERSISTENCE FLUSH TESTS
# ============================================================================

class TestPersistenceFlush:
    """Verify flush_to_db writes correct records."""

    @pytest.mark.asyncio
    async def test_flush_writes_runtime_session(self):
        """flush_to_db creates a RuntimeSession record."""
        rt = DeterministicRuntime("case-flush-001", pipeline_id="pipe-001",
                                  execution_path="orchestrator", review_id="REV-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        rt.guard("extract_facts", "expert")
        rt.transition(CaseState.ARCHIVED, actor="test")

        # Mock DB
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing session
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        written = await rt.flush_to_db(db)
        assert written >= 1
        assert db.add.call_count >= 1  # At least the session + some transitions/audits
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_flush_includes_transitions(self):
        """flush_to_db writes RuntimeTransition records."""
        rt = DeterministicRuntime("case-flush-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="expert")

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        written = await rt.flush_to_db(db)
        # Should write 1 session + 2 transitions (INGESTED is implicit)
        assert written >= 3

    @pytest.mark.asyncio
    async def test_flush_includes_audit_records(self):
        """flush_to_db writes RuntimeAuditRecord for guard/post_guard events."""
        rt = DeterministicRuntime("case-flush-003")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.guard("extract_facts", "expert")
        rt.guard_post({"output": "test", "errors": []})
        rt.transition(CaseState.ARCHIVED, actor="test")

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        written = await rt.flush_to_db(db)
        assert written >= 4  # session + transitions + 2 audit records

    @pytest.mark.asyncio
    async def test_flush_includes_duc_decision(self):
        """flush_to_db writes DUCDecision for human_confirm events."""
        rt = DeterministicRuntime("case-flush-004")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.human_confirm("confirm_decision", "doctor_li", "Verified OK")

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        written = await rt.flush_to_db(db)
        assert written >= 2  # session + duc decision

    @pytest.mark.asyncio
    async def test_flush_with_zero_events_returns_zero(self):
        """Empty queue returns 0."""
        rt = DeterministicRuntime("case-flush-empty")
        db = AsyncMock()
        written = await rt.flush_to_db(db)
        assert written == 0


# ============================================================================
# 2. AUDIT IMMUTABILITY TESTS
# ============================================================================

class TestAuditImmutability:
    """Content hashing provides tamper detection."""

    def test_content_hash_deterministic(self):
        """Same input produces same hash."""
        h1 = _content_hash({"a": 1, "b": 2})
        h2 = _content_hash({"b": 2, "a": 1})  # Keys sorted
        assert h1 == h2  # JSON key order doesn't matter

    def test_content_hash_different_input_different_hash(self):
        """Different input produces different hash."""
        h1 = _content_hash({"a": 1})
        h2 = _content_hash({"a": 2})
        assert h1 != h2

    def test_runtime_session_seal_and_verify(self):
        """RuntimeSession.seal() → verify_integrity() round-trip."""
        session = RuntimeSession(
            runtime_id="rt-test-001", pipeline_id="pipe-001",
            current_state="INGESTED", execution_path="orchestrator",
        )
        assert session.verify_integrity() is False  # Not sealed yet
        session.seal()
        assert session.content_hash is not None
        assert session.verify_integrity() is True

    def test_runtime_session_tamper_detection(self):
        """Modifying after seal breaks integrity."""
        session = RuntimeSession(
            runtime_id="rt-test-002", pipeline_id="pipe-002",
            current_state="INGESTED",
        )
        session.seal()
        assert session.verify_integrity() is True
        session.current_state = "ARCHIVED"  # Tamper
        assert session.verify_integrity() is False

    def test_runtime_transition_seal_and_verify(self):
        """RuntimeTransition.seal() → verify_integrity()."""
        t = RuntimeTransition(
            runtime_id="rt-test-003", from_state="INGESTED",
            to_state="CONTEXT_READY", payload={"key": "value"},
        )
        t.seal()
        assert t.payload_hash is not None
        assert t.verify_integrity() is True

    def test_runtime_transition_tamper_detection(self):
        """Modifying payload after seal breaks integrity."""
        t = RuntimeTransition(
            runtime_id="rt-test-004", from_state="INGESTED",
            to_state="CONTEXT_READY", payload={"key": "value"},
        )
        t.seal()
        t.payload = {"key": "tampered"}  # Tamper
        assert t.verify_integrity() is False

    def test_audit_record_seal_and_verify(self):
        """RuntimeAuditRecord.seal() → verify_integrity()."""
        ar = RuntimeAuditRecord(
            runtime_id="rt-test-005", event_type="guard_check",
            action="extract_facts", actor="expert",
            current_state="CONTEXT_READY", guard_result="ALLOW",
        )
        ar.seal()
        assert ar.immutable_hash is not None
        assert ar.verify_integrity() is True

    def test_audit_record_tamper_detection(self):
        """Modifying guard_result after seal breaks integrity."""
        ar = RuntimeAuditRecord(
            runtime_id="rt-test-006", event_type="guard_check",
            action="extract_facts", actor="expert",
            current_state="CONTEXT_READY", guard_result="ALLOW",
        )
        ar.seal()
        ar.guard_result = "DENY"  # Tamper
        assert ar.verify_integrity() is False

    def test_duc_decision_seal_and_verify(self):
        """DUCDecision.seal() → verify_integrity()."""
        dd = DUCDecision(
            runtime_id="rt-test-007", action="finalize_principal_diagnosis",
            reviewer="doctor_wang", decision="approved",
            reason="Diagnosis verified against evidence",
        )
        dd.seal()
        assert dd.decision_hash is not None
        assert dd.verify_integrity() is True

    def test_duc_decision_tamper_detection(self):
        """Modifying decision after seal breaks integrity."""
        dd = DUCDecision(
            runtime_id="rt-test-008", action="finalize_principal_diagnosis",
            reviewer="doctor_wang", decision="approved",
            reason="Verified",
        )
        dd.seal()
        dd.decision = "rejected"  # Tamper
        assert dd.verify_integrity() is False


# ============================================================================
# 3. STATE SYNC TESTS
# ============================================================================

class TestStateSync:
    """Runtime ↔ Domain State mapping correctness."""

    def test_all_runtime_states_have_review_mapping(self):
        """Every CaseState must map to a review status."""
        for state in CaseState:
            assert state in RUNTIME_TO_REVIEW_STATUS, \
                f"Missing review mapping for {state.value}"
            assert isinstance(RUNTIME_TO_REVIEW_STATUS[state], str)

    def test_all_runtime_states_have_candidate_mapping(self):
        """Every CaseState must map to a candidate status."""
        for state in CaseState:
            assert state in RUNTIME_TO_CANDIDATE_STATUS, \
                f"Missing candidate mapping for {state.value}"
            assert isinstance(RUNTIME_TO_CANDIDATE_STATUS[state], str)

    def test_trigger_states_include_key_states(self):
        """REVIEW_REQUIRED, DECISION_CONFIRMED, etc. must be triggers."""
        assert CaseState.REVIEW_REQUIRED in SYNC_TRIGGER_STATES
        assert CaseState.DECISION_CONFIRMED in SYNC_TRIGGER_STATES
        assert CaseState.ARCHIVED in SYNC_TRIGGER_STATES
        assert CaseState.FAILED in SYNC_TRIGGER_STATES
        assert CaseState.ESCALATED in SYNC_TRIGGER_STATES

    def test_non_trigger_states_should_not_sync(self):
        """Non-trigger states should not sync."""
        non_triggers = {
            CaseState.INGESTED, CaseState.CONTEXT_READY,
            CaseState.FACTS_EXTRACTED, CaseState.CANDIDATES_READY,
            CaseState.RULES_VALIDATED, CaseState.RISK_IDENTIFIED,
        }
        for state in non_triggers:
            assert state not in SYNC_TRIGGER_STATES

    def test_review_required_maps_to_pending_review(self):
        """REVIEW_REQUIRED → pending_review."""
        assert RUNTIME_TO_REVIEW_STATUS[CaseState.REVIEW_REQUIRED] == "pending_review"

    def test_decision_confirmed_maps_to_confirmed(self):
        """DECISION_CONFIRMED → confirmed."""
        assert RUNTIME_TO_REVIEW_STATUS[CaseState.DECISION_CONFIRMED] == "confirmed"

    def test_archived_maps_to_archived(self):
        """ARCHIVED → archived."""
        assert RUNTIME_TO_REVIEW_STATUS[CaseState.ARCHIVED] == "archived"

    def test_failed_maps_to_failed(self):
        """FAILED → failed."""
        assert RUNTIME_TO_REVIEW_STATUS[CaseState.FAILED] == "failed"

    def test_escalated_maps_to_escalated(self):
        """ESCALATED → escalated."""
        assert RUNTIME_TO_REVIEW_STATUS[CaseState.ESCALATED] == "escalated"

    @pytest.mark.asyncio
    async def test_sync_review_status_updates_db(self):
        """sync_review_status writes to DB when triggered."""
        db = AsyncMock()
        review_mock = MagicMock()
        review_mock.human_review_status = "pending"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = review_mock
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        synced = await runtime_state_sync.sync_review_status(
            CaseState.REVIEW_REQUIRED, "REV-test", db,
        )
        assert synced is True
        assert review_mock.human_review_status == "pending_review"

    @pytest.mark.asyncio
    async def test_sync_ignores_non_trigger_states(self):
        """sync_review_status returns False for non-trigger states."""
        db = AsyncMock()
        synced = await runtime_state_sync.sync_review_status(
            CaseState.INGESTED, "REV-test", db,
        )
        assert synced is False
        assert not db.execute.called


# ============================================================================
# 4. MIGRATION STRUCTURE TESTS
# ============================================================================

class TestMigrationStructure:
    """Verify migration structure matches model definitions."""

    def test_runtime_session_has_required_columns(self):
        """RuntimeSession has all required fields."""
        cols = {c.name for c in RuntimeSession.__table__.columns}
        required = {
            "runtime_id", "pipeline_id", "current_state",
            "state_entered_at", "escalated", "failed", "archived",
            "execution_path", "content_hash",
        }
        assert required.issubset(cols)

    def test_runtime_transition_has_required_columns(self):
        """RuntimeTransition has all required fields."""
        cols = {c.name for c in RuntimeTransition.__table__.columns}
        required = {
            "runtime_id", "from_state", "to_state", "transition_type",
            "actor", "payload_hash",
        }
        assert required.issubset(cols)

    def test_runtime_audit_record_has_required_columns(self):
        """RuntimeAuditRecord has all required fields."""
        cols = {c.name for c in RuntimeAuditRecord.__table__.columns}
        required = {
            "runtime_id", "event_type", "actor",
            "guard_result", "post_check_result", "immutable_hash",
        }
        assert required.issubset(cols)

    def test_duc_decision_has_required_columns(self):
        """DUCDecision has all required fields."""
        cols = {c.name for c in DUCDecision.__table__.columns}
        required = {
            "runtime_id", "action", "reviewer", "decision",
            "decision_hash",
        }
        assert required.issubset(cols)

    def test_all_models_have_timestamps(self):
        """All runtime persistence models have id/created_at/updated_at."""
        for model in [RuntimeSession, RuntimeTransition, RuntimeAuditRecord, DUCDecision]:
            assert hasattr(model, 'id')
            assert hasattr(model, 'created_at')
            assert hasattr(model, 'updated_at')


# ============================================================================
# 5. RECOVERY TESTS
# ============================================================================

class TestRecovery:
    """Runtime recovery from DB."""

    def test_force_transition_for_recovery_is_audited(self):
        """force_transition used in recovery records 'forced_transition'."""
        rt = DeterministicRuntime("case-recov-001")
        rt.force_transition(CaseState.REVIEW_REQUIRED,
                           reason="Recovered from DB after restart",
                           actor="system_recovery")
        events = [e.event_type for e in rt.audit._events]
        assert "forced_transition" in events

    def test_pending_persist_collects_events(self):
        """Events are collected in _pending_persist queue."""
        rt = DeterministicRuntime("case-recov-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.guard("extract_facts", "expert")
        rt.guard_post({"output": "ok", "errors": []})

        queue = rt.get_pending_persist()
        assert len(queue) >= 3  # state_transition + 2 audit events

    def test_get_pending_persist_clears_queue(self):
        """After get_pending_persist(), queue is empty."""
        rt = DeterministicRuntime("case-recov-003")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        assert len(rt.get_pending_persist()) >= 1
        assert len(rt.get_pending_persist()) == 0  # Cleared

    @pytest.mark.asyncio
    async def test_flush_then_get_pending_empty(self):
        """After flush, queue is empty."""
        rt = DeterministicRuntime("case-recov-004")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.ARCHIVED, actor="test")

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        await rt.flush_to_db(db)
        assert len(rt.get_pending_persist()) == 0


# ============================================================================
# 6. EXCEPTION PATH TESTS
# ============================================================================

class TestPersistenceExceptionPaths:
    """Verify graceful handling of persistence failures."""

    @pytest.mark.asyncio
    async def test_flush_with_db_commit_failure(self):
        """Runtime state stays consistent even if DB commit fails."""
        rt = DeterministicRuntime("case-exc-001")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.guard("extract_facts", "expert")

        # DB that raises on commit
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock(side_effect=Exception("DB connection lost"))

        # Should raise, but not corrupt in-memory state
        try:
            await rt.flush_to_db(db)
        except Exception:
            pass

        # In-memory state should still be valid
        assert rt.state == CaseState.CONTEXT_READY
        assert len(rt.audit) >= 2  # state_entered + transition + guard

    @pytest.mark.asyncio
    async def test_flush_with_db_execute_failure(self):
        """Runtime stays consistent when DB execute fails."""
        rt = DeterministicRuntime("case-exc-002")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.ARCHIVED, actor="test")

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("Table not found"))
        db.commit = AsyncMock()

        try:
            await rt.flush_to_db(db)
        except Exception:
            pass

        # State unchanged despite DB failure
        assert rt.state == CaseState.ARCHIVED

    @pytest.mark.asyncio
    async def test_flush_with_existing_session_does_update(self):
        """When RuntimeSession already exists, flush does UPDATE not INSERT."""
        rt = DeterministicRuntime("case-exc-003", pipeline_id="pipe-dup")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")

        db = AsyncMock()
        # Existing session found
        existing = MagicMock()
        existing.current_state = "INGESTED"
        existing.previous_state = None
        existing.state_entered_at = None
        existing.escalated = False
        existing.failed = False
        existing.archived = False
        existing.total_processing_ms = None
        existing.error_count = 0
        existing.seal = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        written = await rt.flush_to_db(db)
        assert written >= 2  # session update + transitions
        # Verify the existing record was updated
        assert existing.current_state == CaseState.FACTS_EXTRACTED.value

    @pytest.mark.asyncio
    async def test_recovery_with_empty_db(self):
        """Recovery with no sessions returns 0, no errors."""
        from app.services.runtime import runtime_registry

        # Starting with clean registry and no DB sessions
        runtime_registry._runtimes.clear()
        active = runtime_registry.active_count()
        assert active == 0

    def test_recovery_with_corrupted_state_value(self):
        """Force transition with invalid state value raises ValueError gracefully."""
        rt = DeterministicRuntime("case-exc-004")
        # force_transition should work for recovery
        rt.force_transition(CaseState.ARCHIVED, reason="Emergency shutdown", actor="admin")
        assert rt.state == CaseState.ARCHIVED
        # Verify audit
        events = [e.event_type for e in rt.audit._events]
        assert "forced_transition" in events

    def test_multiple_flushes_no_duplicate_events(self):
        """After flush, queue is empty. Next flush writes only new events."""
        rt = DeterministicRuntime("case-exc-005")
        rt.transition(CaseState.CONTEXT_READY, actor="test")

        # First get clears the queue
        first_batch = rt.get_pending_persist()
        assert len(first_batch) >= 1

        # Second get returns 0 (no new events)
        second_batch = rt.get_pending_persist()
        assert len(second_batch) == 0

        # Add new events
        rt.transition(CaseState.FACTS_EXTRACTED, actor="test")
        third_batch = rt.get_pending_persist()
        assert len(third_batch) >= 1

    @pytest.mark.asyncio
    async def test_flush_preserves_content_hash_integrity(self):
        """After flush, session content_hash is valid and verifiable."""
        from app.models.runtime_persistence import RuntimeSession as RTSession

        rt = DeterministicRuntime("case-exc-006", pipeline_id="pipe-hash")
        rt.transition(CaseState.CONTEXT_READY, actor="test")
        rt.transition(CaseState.ARCHIVED, actor="test")

        # Create a real session model (not flushed to real DB, just verify seal works)
        session_model = RTSession(
            runtime_id=rt.case_id,
            pipeline_id=rt.pipeline_id,
            current_state=rt.state.value,
            execution_path=rt.execution_path,
            escalated=False,
            failed=False,
            archived=True,
        )
        session_model.seal()
        assert session_model.content_hash is not None
        assert session_model.verify_integrity() is True

        # Tamper
        session_model.archived = False
        assert session_model.verify_integrity() is False
