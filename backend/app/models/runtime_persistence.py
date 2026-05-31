# iCoDer - Runtime Persistence Models
#
# Formal persistence layer for the 5-layer safety framework:
# 1. RuntimeSession — persisted state machine instance
# 2. RuntimeTransition — immutable state change record
# 3. RuntimeAuditRecord — formal audit with content hash (immutable)
# 4. DUCDecision — Deny-Unless-Confirmed human decisions
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Float, JSON, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


def _content_hash(data: dict | list | str) -> str:
    """SHA-256 content hash for immutability verification."""
    if isinstance(data, (dict, list)):
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    else:
        raw = str(data)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# RuntimeSession — persisted state machine
# ============================================================================

class RuntimeSession(Base, TimestampMixin):
    """Persisted representation of a DeterministicRuntime instance.

    Maps 1:1 to a coding review pipeline execution.
    Survives server restart — loaded back into runtime_registry on startup.
    """

    __tablename__ = "runtime_sessions"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    runtime_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
        comment="Unique runtime identifier (matches pipeline_id / run_id)"
    )
    pipeline_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False,
        comment="Pipeline or Agent run identifier"
    )
    review_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
        comment="Linked CodingReview.review_id if applicable"
    )
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
        comment="Linked Agent.id if AgentRunner path"
    )

    # State machine
    current_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INGESTED", index=True,
        comment="Current CaseState value"
    )
    previous_state: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="Previous state before last transition"
    )
    state_entered_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow,
        comment="When current_state was entered (for timeout calculation)"
    )

    # Timeout tracking
    timeout_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="When the current state will timeout (derived from STATE_TIMEOUTS)"
    )
    escalated: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True if this runtime has been escalated to supervisor"
    )
    escalated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="When escalation occurred"
    )

    # Termination flags
    failed: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Metadata
    execution_path: Mapped[str] = mapped_column(
        String(32), default="orchestrator",
        comment="Which execution path: orchestrator | agent_runner | intelligent"
    )
    total_processing_ms: Mapped[Optional[int]] = mapped_column(default=None)
    error_count: Mapped[int] = mapped_column(default=0)

    # Content hash for the entire session record (immutability)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="SHA-256 hash of key fields for tamper detection"
    )

    def compute_hash(self) -> str:
        """Compute content hash over immutable fields."""
        payload = {
            "runtime_id": self.runtime_id,
            "pipeline_id": self.pipeline_id,
            "current_state": self.current_state,
            "escalated": self.escalated,
            "failed": self.failed,
            "archived": self.archived,
        }
        return _content_hash(payload)

    def seal(self):
        """Compute and store the content hash."""
        self.content_hash = self.compute_hash()

    def verify_integrity(self) -> bool:
        """Verify the stored hash matches recomputed hash."""
        if not self.content_hash:
            return False
        return self.content_hash == self.compute_hash()


# ============================================================================
# RuntimeTransition — immutable state change record
# ============================================================================

class RuntimeTransition(Base, TimestampMixin):
    """Immutable record of every state transition.

    Written once on transition, never updated.
    Content-hashed for tamper detection.
    """

    __tablename__ = "runtime_transitions"
    __allow_unmapped__ = True

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    runtime_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runtime_sessions.runtime_id"), nullable=False, index=True,
        comment="Parent RuntimeSession"
    )
    from_state: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    to_state: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    transition_type: Mapped[str] = mapped_column(
        String(32), default="normal",
        comment="normal | forced | timeout | recovery"
    )
    actor: Mapped[str] = mapped_column(
        String(128), default="system"
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="SHA-256 of payload for integrity verification"
    )

    def seal(self):
        """Hash the payload for immutability."""
        if self.payload:
            self.payload_hash = _content_hash(self.payload)

    def verify_integrity(self) -> bool:
        """Verify payload hasn't been tampered with."""
        if self.payload is None:
            return self.payload_hash is None
        return self.payload_hash == _content_hash(self.payload)


# ============================================================================
# RuntimeAuditRecord — formal audit with immutable hash
# ============================================================================

class RuntimeAuditRecord(Base, TimestampMixin):
    """Formal audit record — persistent, queryable, immutable.

    Every guard check, post_check, timeout, and human decision is recorded.
    Content-hashed for tamper detection.
    """

    __tablename__ = "runtime_audit_records"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    runtime_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runtime_sessions.runtime_id"), nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="state_transition | guard_check | post_guard | "
                "human_confirmation | timeout_escalation | "
                "illegal_transition_attempt | forced_transition"
    )
    action: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
        comment="The action being guarded/executed"
    )
    actor: Mapped[str] = mapped_column(String(128), default="system")
    current_state: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="Runtime state at time of event"
    )

    # Guard results
    guard_result: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        comment="ALLOW | REVIEW | DENY | DEFER"
    )
    post_check_result: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
        comment="ALLOW | REVIEW | DENY (for guard_post)"
    )

    # Payload
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Immutability
    immutable_hash: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="SHA-256 hash of (event_type + action + actor + payload) — "
                "proves this record has not been modified"
    )

    def compute_immutable_hash(self) -> str:
        """Hash the content that must never change."""
        content = {
            "event_type": self.event_type,
            "action": self.action,
            "actor": self.actor,
            "current_state": self.current_state,
            "guard_result": self.guard_result,
            "post_check_result": self.post_check_result,
            "payload": self.payload,
        }
        return _content_hash(content)

    def seal(self):
        """Compute and store the immutable hash."""
        self.immutable_hash = self.compute_immutable_hash()

    def verify_integrity(self) -> bool:
        """Verify this record hasn't been tampered with."""
        if not self.immutable_hash:
            return False
        return self.immutable_hash == self.compute_immutable_hash()


# ============================================================================
# DUCDecision — Deny-Unless-Confirmed human decision record
# ============================================================================

class DUCDecision(Base, TimestampMixin):
    """Persisted record of every human DUC decision.

    Each DUC action (finalize_principal_diagnosis, writeback_to_emr, etc.)
    that receives human confirmation is recorded here.
    """

    __tablename__ = "runtime_duc_decisions"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    runtime_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runtime_sessions.runtime_id"), nullable=False, index=True,
    )
    action: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
        comment="DUC action name (must be in DUC_ACTIONS set)"
    )
    reviewer: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Username or full name of the human reviewer"
    )
    decision: Mapped[str] = mapped_column(
        String(32), nullable=False, default="approved",
        comment="approved | rejected"
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Reviewer's rationale"
    )
    current_state: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="Runtime state when decision was made"
    )
    decision_hash: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
        comment="SHA-256 hash for immutability"
    )

    def compute_hash(self) -> str:
        content = {
            "runtime_id": self.runtime_id,
            "action": self.action,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "reason": self.reason,
        }
        return _content_hash(content)

    def seal(self):
        self.decision_hash = self.compute_hash()

    def verify_integrity(self) -> bool:
        if not self.decision_hash:
            return False
        return self.decision_hash == self.compute_hash()
