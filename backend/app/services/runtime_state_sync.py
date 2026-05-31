# iCoDer - Runtime ↔ Domain State Unified Mapping
#
# Maps Runtime states to business domain states (Review, Candidate, etc.)
# Ensures automatic synchronization when Runtime transitions occur.
#
# Mapping table:
#
#   Runtime State        → Review.human_review_status  → Candidate.status
#   ──────────────────────────────────────────────────────────────────
#   INGESTED             → pending                     → pending
#   CONTEXT_READY        → pending                     → pending
#   FACTS_EXTRACTED      → pending                     → pending
#   CANDIDATES_READY     → pending                     → pending
#   RULES_VALIDATED      → in_review                   → pending
#   RISK_IDENTIFIED       → in_review                   → needs_review
#   REVIEW_REQUIRED       → pending_review              → needs_review
#   DECISION_CONFIRMED    → confirmed                   → confirmed
#   DOC_FEEDBACK_READY    → confirmed                   → confirmed
#   WRITEBACK_PENDING     → confirmed                   → confirmed
#   WRITTEN_BACK          → completed                   → confirmed
#   ARCHIVED              → archived                    → supported/confirmed
#   FAILED                → failed                      → (unchanged)
#   ESCALATED             → escalated                   → needs_review
#
# Auto-sync rules:
# 1. REVIEW_REQUIRED → review.human_review_status = "pending_review"
# 2. DECISION_CONFIRMED → review.human_review_status = "confirmed"
# 3. ARCHIVED → review.human_review_status = "archived" (if review complete)
# 4. FAILED → review.human_review_status = "failed"
# 5. ESCALATED → review.human_review_status = "escalated"
import logging
from app.services.runtime import CaseState

logger = logging.getLogger(__name__)

# ============================================================================
# Mapping Tables
# ============================================================================

RUNTIME_TO_REVIEW_STATUS: dict[CaseState, str] = {
    CaseState.INGESTED:           "pending",
    CaseState.CONTEXT_READY:      "pending",
    CaseState.FACTS_EXTRACTED:    "pending",
    CaseState.CANDIDATES_READY:   "pending",
    CaseState.RULES_VALIDATED:    "in_review",
    CaseState.RISK_IDENTIFIED:    "in_review",
    CaseState.REVIEW_REQUIRED:    "pending_review",
    CaseState.DECISION_CONFIRMED: "confirmed",
    CaseState.DOC_FEEDBACK_READY: "confirmed",
    CaseState.WRITEBACK_PENDING:  "confirmed",
    CaseState.WRITTEN_BACK:       "completed",
    CaseState.ARCHIVED:           "archived",
    CaseState.FAILED:             "failed",
    CaseState.ESCALATED:          "escalated",
}

RUNTIME_TO_CANDIDATE_STATUS: dict[CaseState, str] = {
    CaseState.INGESTED:           "pending",
    CaseState.CONTEXT_READY:      "pending",
    CaseState.FACTS_EXTRACTED:    "pending",
    CaseState.CANDIDATES_READY:   "pending",
    CaseState.RULES_VALIDATED:    "pending",
    CaseState.RISK_IDENTIFIED:    "needs_review",
    CaseState.REVIEW_REQUIRED:    "needs_review",
    CaseState.DECISION_CONFIRMED: "confirmed",
    CaseState.DOC_FEEDBACK_READY: "confirmed",
    CaseState.WRITEBACK_PENDING:  "confirmed",
    CaseState.WRITTEN_BACK:       "confirmed",
    CaseState.ARCHIVED:           "supported",
    CaseState.FAILED:             "pending",
    CaseState.ESCALATED:          "needs_review",
}

# States that trigger a review status sync
SYNC_TRIGGER_STATES: set[CaseState] = {
    CaseState.REVIEW_REQUIRED,
    CaseState.DECISION_CONFIRMED,
    CaseState.ARCHIVED,
    CaseState.FAILED,
    CaseState.ESCALATED,
}


class RuntimeStateSync:
    """Synchronizes Runtime state changes with business domain models.

    When a Runtime transitions to a trigger state, this service updates:
    - CodingReview.human_review_status
    - CodeCandidate.status (for all candidates in the review)
    """

    async def sync_review_status(
        self,
        rt_state: CaseState,
        review_id: str,
        db,  # AsyncSession
    ) -> bool:
        """Sync Runtime state → CodingReview.human_review_status.

        Only triggers for SYNC_TRIGGER_STATES.
        Returns True if sync was performed, False if no sync needed.
        """
        if rt_state not in SYNC_TRIGGER_STATES:
            return False

        new_status = RUNTIME_TO_REVIEW_STATUS.get(rt_state)
        if not new_status:
            return False

        from sqlalchemy import select as _select
        from app.models.review import CodingReview

        # Find review by review_id
        result = await db.execute(
            _select(CodingReview).where(
                (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
            )
        )
        review = result.scalar_one_or_none()
        if not review:
            logger.debug(f"StateSync: no review found for {review_id}")
            return False

        old_status = review.human_review_status
        review.human_review_status = new_status
        db.add(review)
        await db.commit()

        logger.info(f"StateSync: review {review_id} status {old_status} → {new_status} "
                    f"(Runtime: {rt_state.value})")
        return True

    async def sync_candidate_statuses(
        self,
        rt_state: CaseState,
        review_id: str,
        db,  # AsyncSession
    ) -> int:
        """Sync Runtime state → all CodeCandidate.status in a review.

        Only updates candidates that are in 'pending' or 'needs_review' state.
        Returns count of updated candidates.
        """
        new_status = RUNTIME_TO_CANDIDATE_STATUS.get(rt_state)
        if not new_status:
            return 0

        from sqlalchemy import select as _select
        from app.models.review import CodingReview
        from app.models.code_candidate import CodeCandidate

        result = await db.execute(
            _select(CodingReview).where(
                (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
            )
        )
        review = result.scalar_one_or_none()
        if not review:
            return 0

        result = await db.execute(
            _select(CodeCandidate).where(CodeCandidate.review_id == review.id)
        )
        candidates = result.scalars().all()

        count = 0
        for c in candidates:
            if c.status in ("pending", "needs_review"):
                c.status = new_status
                db.add(c)
                count += 1

        if count > 0:
            await db.commit()
            logger.info(f"StateSync: updated {count} candidate(s) to '{new_status}' "
                        f"(review {review_id}, Runtime: {rt_state.value})")

        return count

    async def sync_all(
        self,
        rt_state: CaseState,
        review_id: str,
        db,  # AsyncSession
    ) -> dict:
        """Full sync: review status + candidate statuses.

        Returns summary dict.
        """
        review_synced = await self.sync_review_status(rt_state, review_id, db)
        candidate_count = await self.sync_candidate_statuses(rt_state, review_id, db)
        return {
            "review_synced": review_synced,
            "candidates_updated": candidate_count,
            "runtime_state": rt_state.value,
            "review_status": RUNTIME_TO_REVIEW_STATUS.get(rt_state),
            "candidate_status": RUNTIME_TO_CANDIDATE_STATUS.get(rt_state),
        }


runtime_state_sync = RuntimeStateSync()
