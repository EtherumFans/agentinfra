"""Phase 7 Gate 3 — server-side Idempotency-Key dedup unit tests.

Covers Phase 7 §8.1-§8.3 semantics:

1. **concurrent INSERT race** (§8.3) — two asyncio.gather requests with the
   same key + same hash → exactly one wins (should_run=True), the other
   sees PENDING (in_progress=True). SELECT-then-INSERT is forbidden.
2. **hash mismatch 409** (§8.2) — same key + different request_hash →
   IdempotencyKeyReusedError (409).
3. **COMPLETED replay** (§8.2) — same key + same hash + COMPLETED +
   response_snapshot → returns the snapshot.
4. **IN_PROGRESS replay** (§8.2) — same key + same hash + PENDING /
   IN_PROGRESS → returns the run_id with in_progress=True.
5. **mark_completed / mark_in_progress / mark_failed** transition helpers
   write the expected columns.
6. **request_hash determinism** — same inputs → same hash; differing
   inputs → different hash.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_record import IdempotencyRecord
from app.services.idempotency_service import (
    DEFAULT_TTL_SECONDS,
    IdempotencyKeyReusedError,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    acquire_or_replay,
    compute_request_hash,
    mark_completed,
    mark_failed,
    mark_in_progress,
)


def _fresh_session() -> AsyncSession:
    """Get a clean AsyncSession bound to the test DB.

    ``AsyncSessionLocal`` is an async_sessionmaker — calling it returns
    an AsyncSession instance (not a coroutine), so the helper is a
    plain sync function and ``async with _fresh_session() as db:``
    works as expected.
    """
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal()


# ────────────────────────────────────────────────────────────────────
# §8.2 semantic — COMPLETED replay returns snapshot
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_completed_replay_returns_snapshot():
    """A second acquire_or_replay on a COMPLETED record returns the
    saved response_snapshot (the partner's first call's response)."""
    key = "test-replay-completed-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="hello", runtime_mode="default",
    )

    # First call — INSERTs PENDING.
    async with _fresh_session() as db1:
        r1 = await acquire_or_replay(
            db1, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        assert r1.should_run is True
        assert r1.in_progress is False
        assert r1.record.status == STATUS_PENDING
        # Promote to COMPLETED with a snapshot.
        await mark_in_progress(db1, r1.record, run_id="run-123")
        await mark_completed(
            db1, r1.record,
            response_snapshot={"agent_id": "test-agent", "run_id": "run-123", "summary": "ok"},
        )
        await db1.commit()

    # Second call — should replay.
    async with _fresh_session() as db2:
        r2 = await acquire_or_replay(
            db2, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        assert r2.should_run is False
        assert r2.in_progress is False
        assert r2.response_snapshot is not None
        assert r2.response_snapshot["run_id"] == "run-123"
        assert r2.response_snapshot["summary"] == "ok"


# ────────────────────────────────────────────────────────────────────
# §8.2 semantic — IN_PROGRESS replay returns run_id
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_progress_replay_returns_run_id():
    """A second acquire_or_replay on an IN_PROGRESS record returns
    in_progress=True (caller returns 200 with the existing run_id)."""
    key = "test-replay-in-progress-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="hello", runtime_mode="default",
    )

    async with _fresh_session() as db1:
        r1 = await acquire_or_replay(
            db1, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        await mark_in_progress(db1, r1.record, run_id="run-running")
        await db1.commit()

    async with _fresh_session() as db2:
        r2 = await acquire_or_replay(
            db2, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        assert r2.should_run is False
        assert r2.in_progress is True
        assert r2.response_snapshot is None
        assert r2.record.run_id == "run-running"


@pytest.mark.asyncio
async def test_pending_replay_returns_in_progress():
    """A second acquire_or_replay on a PENDING record (no run_id yet)
    also returns in_progress=True — the partner should poll/retry."""
    key = "test-replay-pending-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="hello", runtime_mode="default",
    )

    async with _fresh_session() as db1:
        r1 = await acquire_or_replay(
            db1, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        await db1.commit()

    async with _fresh_session() as db2:
        r2 = await acquire_or_replay(
            db2, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        assert r2.should_run is False
        assert r2.in_progress is True


# ────────────────────────────────────────────────────────────────────
# §8.2 semantic — hash mismatch raises 409
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hash_mismatch_raises_409():
    """Same Idempotency-Key + DIFFERENT request body → 409
    IdempotencyKeyReusedError. This is the contract that protects
    partners from accidentally reusing a key for a different request."""
    key = "test-mismatch-" + datetime.now(timezone.utc).isoformat()
    hash_a = compute_request_hash(
        agent_id="test-agent", input_text="AAA", runtime_mode="default",
    )
    hash_b = compute_request_hash(
        agent_id="test-agent", input_text="BBB", runtime_mode="default",
    )

    async with _fresh_session() as db1:
        await acquire_or_replay(
            db1, idempotency_key=key, request_hash=hash_a, agent_ref="test-agent", organization_id="org-test",
        )
        await db1.commit()

    async with _fresh_session() as db2:
        with pytest.raises(IdempotencyKeyReusedError) as exc_info:
            await acquire_or_replay(
                db2, idempotency_key=key, request_hash=hash_b, agent_ref="test-agent", organization_id="org-test",
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
        assert exc_info.value.detail["idempotency_key"] == key


# ────────────────────────────────────────────────────────────────────
# §8.3 concurrency — INSERT-then-SELECT race; exactly one winner
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_insert_exactly_one_winner():
    """Two concurrent asyncio.gather calls with the same key + hash:
    the UNIQUE constraint guarantees exactly one should_run=True.
    The other sees the winner's PENDING row and returns in_progress=True.

    This is the §8.3 "INSERT-with-UNIQUE is the dedup primitive"
    invariant. SELECT-then-INSERT would race here and produce two
    should_run=True responses.
    """
    key = "test-race-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="race", runtime_mode="default",
    )

    async def _attempt():
        async with _fresh_session() as db:
            result = await acquire_or_replay(
                db, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
            )
            await db.commit()
            return result

    r1, r2 = await asyncio.gather(_attempt(), _attempt())

    winners = [r for r in (r1, r2) if r.should_run]
    observers = [r for r in (r1, r2) if not r.should_run]
    assert len(winners) == 1, (
        f"Exactly one request should win; got {len(winners)}. "
        "UNIQUE constraint not enforcing §8.3 dedup."
    )
    assert len(observers) == 1
    assert observers[0].in_progress is True


# ────────────────────────────────────────────────────────────────────
# mark_failed transitions the record
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_transitions_status():
    """A FAILED record's status changes; future replays will re-attempt
    (the contract is "transient failures are retryable")."""
    key = "test-failed-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="will-fail", runtime_mode="default",
    )

    async with _fresh_session() as db:
        r = await acquire_or_replay(
            db, idempotency_key=key, request_hash=req_hash, agent_ref="test-agent", organization_id="org-test",
        )
        await mark_in_progress(db, r.record, run_id="run-failing")
        await mark_failed(db, r.record)
        await db.commit()
        assert r.record.status == STATUS_FAILED


@pytest.mark.asyncio
async def test_failed_replay_reacquires_for_retry():
    """A matching replay after FAILED gets a fresh execution attempt."""
    key = "test-failed-retry-" + datetime.now(timezone.utc).isoformat()
    req_hash = compute_request_hash(
        agent_id="test-agent", input_text="retryable", runtime_mode="default",
    )

    async with _fresh_session() as db1:
        first = await acquire_or_replay(
            db1,
            idempotency_key=key,
            request_hash=req_hash,
            agent_ref="test-agent",
            organization_id="org-test",
        )
        await mark_in_progress(db1, first.record, run_id="run-failed")
        await mark_failed(db1, first.record)
        await db1.commit()

    async with _fresh_session() as db2:
        retry = await acquire_or_replay(
            db2,
            idempotency_key=key,
            request_hash=req_hash,
            agent_ref="test-agent",
            organization_id="org-test",
        )
        assert retry.should_run is True
        assert retry.in_progress is False
        assert retry.record.status == STATUS_PENDING
        assert retry.record.run_id is None


@pytest.mark.asyncio
async def test_machine_replay_is_bound_to_delegated_subject_and_purpose():
    """A machine key must never replay across delegated authorization scope."""

    key = "test-delegated-scope-" + datetime.now(timezone.utc).isoformat()
    base_hash = compute_request_hash(
        agent_id="test-agent",
        input_text="same clinical request",
        runtime_mode="default",
    )

    async with _fresh_session() as db1:
        first = await acquire_or_replay(
            db1,
            idempotency_key=key,
            request_hash=base_hash,
            agent_ref="test-agent",
            organization_id="org-test",
            api_client_id="machine-client",
            delegated_subject_id="delegated-user-a",
            purpose_of_use="treatment",
        )
        assert first.should_run is True
        assert first.record.request_hash != base_hash
        assert not hasattr(first.record, "delegated_subject_id")
        await db1.commit()

    async with _fresh_session() as db2:
        replay = await acquire_or_replay(
            db2,
            idempotency_key=key,
            request_hash=base_hash,
            agent_ref="test-agent",
            organization_id="org-test",
            api_client_id="machine-client",
            delegated_subject_id="delegated-user-a",
            purpose_of_use="treatment",
        )
        assert replay.should_run is False
        assert replay.in_progress is True

    for subject, purpose in (
        ("delegated-user-b", "treatment"),
        ("delegated-user-a", "payment"),
    ):
        async with _fresh_session() as db:
            with pytest.raises(IdempotencyKeyReusedError):
                await acquire_or_replay(
                    db,
                    idempotency_key=key,
                    request_hash=base_hash,
                    agent_ref="test-agent",
                    organization_id="org-test",
                    api_client_id="machine-client",
                    delegated_subject_id=subject,
                    purpose_of_use=purpose,
                )


# ────────────────────────────────────────────────────────────────────
# request_hash determinism + divergence
# ────────────────────────────────────────────────────────────────────


def test_request_hash_is_stable_for_same_inputs():
    """Same normalized request → same hash (replayable)."""
    a = compute_request_hash(
        agent_id="medical-coding-agent",
        input_text="患者男性 60 岁",
        runtime_mode="corti_like_fast",
    )
    b = compute_request_hash(
        agent_id="medical-coding-agent",
        input_text="患者男性 60 岁",
        runtime_mode="corti_like_fast",
    )
    assert a == b


def test_request_hash_diverges_on_input_text():
    """Different input_text → different hash (would 409 on same key)."""
    a = compute_request_hash(
        agent_id="medical-coding-agent",
        input_text="患者男性 60 岁",
        runtime_mode="default",
    )
    b = compute_request_hash(
        agent_id="medical-coding-agent",
        input_text="患者女性 60 岁",
        runtime_mode="default",
    )
    assert a != b


def test_request_hash_normalizes_agent_id_case():
    """agent_id casing shouldn't matter — Medical-Coding-Agent and
    medical-coding-agent hash to the same value."""
    a = compute_request_hash(agent_id="Medical-Coding-Agent", input_text="x")
    b = compute_request_hash(agent_id="medical-coding-agent", input_text="x")
    assert a == b


def test_request_hash_normalizes_whitespace():
    """Trailing whitespace on input_text shouldn't trigger a false 409."""
    a = compute_request_hash(agent_id="a", input_text="hello world")
    b = compute_request_hash(agent_id="a", input_text="  hello world  ")
    assert a == b
