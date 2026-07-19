"""RunTrace — Corti-style Agent execution trace store.

Phase 3-D1 Task 4 (2026-07-06): introduced the 9-step timeline
(user_message_received / planner_selected_experts / tools_list /
auth_resolved / scope_checked / tools_call / expert_response /
output_generated / completion) with an in-memory store.

Phase 3-D2 Task 1 (2026-07-06): promoted the store to a DB-backed
implementation (``DbRunTraceStore``) so traces survive process
restarts, are visible across workers, and can be org-scoped for
audit. The in-memory store remains as a test/dev fallback
(``settings.RUNTRACE_STORE == "memory"``).

Design:

  - ``RunTraceEvent`` carries ``step``, ``status``, ``duration_ms``,
    ``ts``, and ``safe_metadata`` (dict). The ``safe_metadata`` is
    ALREADY redacted at the emit site — it must not contain raw
    tokens / client_secrets / Authorization headers. The Auth step
    surfaces only ``redacted_view``.
  - ``RunTraceStore`` is an abstract base — ``InMemoryRunTraceStore``
    is the process-local dict; ``DbRunTraceStore`` persists to the
    ``run_trace_events`` table via a sync SQLAlchemy engine.
  - ``emit_trace_event`` is the public emit helper. The dispatcher
    (mcp/server.py) and orchestrator hooks call it at each step.

The frontend RunTracePage reads via ``GET /api/runtime/runs/{run_id}/trace``
(see app/api/run_trace.py).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── 9-step timeline ───────────────────────────────────────────────────────


class RunTraceStep:
    """The 9 Corti-style timeline steps.

    Use string literals (not Enum) so JSON serialization is trivial
    and downstream consumers (frontend, external API) don't need to
    import this class.
    """
    USER_MESSAGE_RECEIVED = "user_message_received"
    PLANNER_SELECTED_EXPERTS = "planner_selected_experts"
    TOOLS_LIST = "tools_list"
    AUTH_RESOLVED = "auth_resolved"
    SCOPE_CHECKED = "scope_checked"
    TOOLS_CALL = "tools_call"
    EXPERT_RESPONSE = "expert_response"
    OUTPUT_GENERATED = "output_generated"
    COMPLETION = "completion"          # status="ok" or "failed"


class RunTraceStatus:
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Event dataclass ───────────────────────────────────────────────────────


@dataclass
class RunTraceEvent:
    """One timeline entry.

    ``safe_metadata`` is a flat dict of display-safe fields only.
    The emit site is responsible for scrubbing — the store trusts
    whatever it receives. For Auth steps, ``safe_metadata`` carries
    ``{"redacted_view": "Bearer ••••1234", "required_scopes": [...],
    "granted_scopes": [...]}`` — NEVER the raw token.
    """
    run_id: str
    step: str
    status: str
    ts: float  # epoch seconds
    duration_ms: float = 0.0
    safe_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Redaction defensive scan ─────────────────────────────────────────────


# Known-secret keys that must NEVER appear in safe_metadata.
_KNOWN_SECRET_KEYS: frozenset[str] = frozenset({
    "token", "secret", "client_secret", "authorization",
    "password", "refresh_token", "access_token", "api_key",
    "bearer_token", "raw_token",
})

# Keys that are display-safe by contract — even if their value looks like a
# token blob (e.g. ``redacted_view = "Bearer ••••12"``), they are the canonical
# redacted form, NOT a raw credential. Skip the token-blob scan for these.
_SAFE_KEYS: frozenset[str] = frozenset({
    "redacted_view", "auth_type", "granted_scopes", "required_scopes",
    "tool_name", "tool_count", "tool_names", "handler_ref", "error",
    "error_code", "mcp_error_code", "is_error", "agent_id", "input_parts",
    "input_len", "review_conclusion", "issues_count", "experts",
    "expert_id", "reason", "stage",
    # ── Phase 4-A (2026-07-07): Agent Backend Provider metadata ──
    # These keys are emitted by AgentBackendProvider.invoke() into the
    # TOOLS_CALL / EXPERT_RESPONSE / OUTPUT_GENERATED safe_metadata so
    # RunTracePage can render a "Backend Provider" summary panel.
    "backend_provider", "backend_type", "provider_latency_ms",
    "provider_status", "provider_deterministic",
    "supports_tool_calling", "fallback_used", "output_contract",
    "tool_rounds",
})


def _is_token_blob(value: Any) -> bool:
    """Heuristic: does this string value look like a raw token?"""
    if not isinstance(value, str):
        return False
    if value.startswith("Bearer "):
        return True
    # JWT shape: three base64 segments separated by dots
    if value.startswith("eyJ") and value.count(".") == 2:
        return True
    # Long opaque credential (>=40 chars, hex/base64 only)
    if len(value) >= 40 and all(c.isalnum() or c in "-_" for c in value):
        return True
    return False


def _redact_safe_metadata(safe_metadata: dict[str, Any]) -> dict[str, Any]:
    """Defensive last-mile redaction before DB persist.

    The emit sites are supposed to write only display-safe fields,
    but if a future caller accidentally writes a raw token, this
    scan blanks the offending field + logs a warning.

    Skips the token-blob scan for keys in ``_SAFE_KEYS`` (e.g.
    ``redacted_view`` is allowed to be ``"Bearer ••••12"`` — that's
    the canonical redacted form, not a raw credential).

    Does NOT mutate the input dict; returns a scrubbed copy.
    """
    if not safe_metadata:
        return {}
    scrubbed: dict[str, Any] = {}
    for key, value in safe_metadata.items():
        key_lower = key.lower()
        if any(secret in key_lower for secret in _KNOWN_SECRET_KEYS):
            logger.warning(
                "run_trace redaction: blanking secret key %r in safe_metadata",
                key,
            )
            scrubbed[key] = "[REDACTED]"
            continue
        if key not in _SAFE_KEYS and _is_token_blob(value):
            logger.warning(
                "run_trace redaction: blanking token-blob value for key %r",
                key,
            )
            scrubbed[key] = "[REDACTED]"
            continue
        scrubbed[key] = value
    return scrubbed


# ── Store interface ──────────────────────────────────────────────────────


class RunTraceStore:
    """Process-wide in-memory store.

    Not thread-safe (Python GIL makes dict append atomic enough for
    the test/single-server use case). For multi-worker production,
    use ``DbRunTraceStore`` (set ``settings.RUNTRACE_STORE = "db"``).

    The interface (``append`` / ``get_run`` / ``get_run_scoped`` /
    ``clear``) is the contract — ``DbRunTraceStore`` implements the
    same shape, so callers can swap without touching emit sites.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[RunTraceEvent]] = {}

    def append(self, event: RunTraceEvent) -> None:
        self._events.setdefault(event.run_id, []).append(event)
        # Phase A1A Gate 3.3 §3 — record FALLBACK_MEMORY on run_history
        # so audits can distinguish "events in DB" from "events only in
        # process RAM" (which vanish on restart). In cloud mode this is
        # a fail-closed signal: the row should never have been written
        # with memory store to begin with (see Settings validation).
        #
        # Phase A1A Gate 3R.3 — use the canonical state name from
        # TraceCaptureState. The literal value is unchanged
        # ("FALLBACK_MEMORY"); the import is for single-source-of-truth.
        try:
            from app.services.trace_capture_state import TraceCaptureState
            _mark_trace_capture_status(event.run_id, TraceCaptureState.FALLBACK_MEMORY)
        except Exception as mark_err:  # pragma: no cover — defensive
            logger.debug(
                "run_trace FALLBACK_MEMORY mark skipped: %s (run_id=%s)",
                mark_err, event.run_id,
            )

    def get_run(self, run_id: str) -> list[RunTraceEvent]:
        return list(self._events.get(run_id, []))

    def get_run_scoped(self, run_id: str, organization_id: Optional[str]) -> list[RunTraceEvent]:
        # In-memory store doesn't track org; treat as dev mode — return all.
        return self.get_run(run_id)

    def clear(self) -> None:
        """Test hook — wipe all events."""
        self._events.clear()


class DbRunTraceStore:
    """DB-backed store. Uses a sync SQLAlchemy engine so emit_trace_event
    can be called from sync contexts (InboundHandler / _SimpleAgentDispatchHandler
    are sync).

    Writes go through a defensive redaction scan (``_redact_safe_metadata``)
    before insert — the last-mile safety net against an emit-site mistake.

    Reads via ``get_run`` / ``get_run_scoped`` use the same sync engine.
    The API endpoint wraps these in ``run_in_executor`` so the async event
    loop isn't blocked.
    """

    def __init__(self) -> None:
        # Lazy-init the sync engine — avoid creating on import (tests that
        # never touch DB shouldn't pay the cost).
        self._sync_engine = None
        self._sync_session_factory = None

    def _ensure_engine(self):
        if self._sync_engine is not None:
            return
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Strip async driver from URL: sqlite+aiosqlite://... → sqlite://...
        #                                postgresql+asyncpg://... → postgresql://...
        url = settings.DATABASE_URL
        for async_driver in ("+aiosqlite", "+asyncpg", "+psycopg"):
            url = url.replace(async_driver, "")
        # SQLite needs check_same_thread=False for cross-thread usage.
        connect_args = {"check_same_thread": False} if "sqlite" in url else {}
        self._sync_engine = create_engine(url, connect_args=connect_args, echo=False)
        self._sync_session_factory = sessionmaker(bind=self._sync_engine, expire_on_commit=False)

    def append(self, event: RunTraceEvent) -> None:
        self._ensure_engine()
        from app.models.run_trace import RunTraceEventModel

        scrubbed = _redact_safe_metadata(event.safe_metadata)
        # Extract org/project/user context from safe_metadata if present
        # (emit sites that have it stash it there); fall back to None.
        org_id = scrubbed.pop("_organization_id", None)
        project_id = scrubbed.pop("_project_id", None)
        user_id = scrubbed.pop("_user_id", None)
        actor_id = scrubbed.pop("_actor_id", None)
        agent_id = scrubbed.get("agent_id")
        # Phase A1A Gate 3R.4 — propagate trace_id from safe_metadata
        # if the emit site stashed it there. Fall back to None.
        trace_id = scrubbed.pop("_trace_id", None)

        # Phase A1A Gate 3R.4 — stable event identity.
        # event_id is a UUID v4 string. sequence_number is per-trace
        # monotonic ordering (1-indexed within trace_id).
        event_id, sequence_number = _assign_event_identity(
            event.run_id, trace_id
        )

        record = RunTraceEventModel(
            run_id=event.run_id,
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
            actor_id=actor_id,
            agent_id=agent_id,
            step=event.step,
            status=event.status,
            duration_ms=event.duration_ms,
            ts=event.ts,
            safe_metadata_json=scrubbed if scrubbed else None,
            event_id=event_id,
            sequence_number=sequence_number,
            trace_id=trace_id,
            identity_source="uuid_v4" if event_id else None,
        )

        try:
            with self._sync_session_factory() as session:
                session.add(record)
                session.commit()
        except Exception as e:
            # Phase A1A Gate 3.3 — record the failure on the run_history
            # row so audits can see which runs lost trace events. The
            # caller's run is allowed to continue (a trace gap should
            # not abort a successful agent run), but the failure is no
            # longer silent: it is (a) logged at ERROR level with the
            # full error + run_id + step, (b) recorded on run_history
            # via mark_trace_capture_failed, and (c) — when
            # settings.RUNTRACE_FAIL_CLOSED=True — re-raised so the
            # caller can decide whether to fail the run.
            #
            # Phase A1A Gate 3R.3 — fail-closed is now decided by the
            # deployment profile (REQUIRED_DB) instead of the raw
            # RUNTRACE_FAIL_CLOSED flag. The two stay in sync via
            # DeploymentProfileResolver; the profile is the canonical
            # source so future additions (e.g. PARTIAL_DB) don't
            # require touching this call site.
            logger.error(
                "run_trace DB write failed: %s (run_id=%s step=%s)",
                e, event.run_id, event.step,
            )
            from app.services.trace_capture_state import TraceCaptureState
            try:
                _mark_trace_capture_status(
                    event.run_id, TraceCaptureState.FAILED, reason=str(e)[:250],
                )
            except Exception as mark_err:  # pragma: no cover — defensive
                logger.error(
                    "run_trace status mark also failed: %s (run_id=%s)",
                    mark_err, event.run_id,
                )
            if _should_fail_closed():
                raise
            return

        # Success: stamp CAPTURED on the run_history row. Best-effort
        # — if the row doesn't exist yet (record_run_start hasn't
        # fired) the UPDATE is a no-op. Once record_run_start writes
        # the row, subsequent trace events will find it.
        #
        # Phase A1A Gate 3R.3 — canonical state name is CAPTURED (the
        # Gate 3.3-era literal "PERSISTED" is kept as a deprecated
        # alias for backwards compat with rows written before 3R.3).
        # Migration 020 will rewrite existing PERSISTED rows; until
        # then, readers use TraceCaptureState.normalize to treat both
        # literals identically.
        try:
            from app.services.trace_capture_state import TraceCaptureState
            _mark_trace_capture_status(event.run_id, TraceCaptureState.CAPTURED)
        except Exception as mark_err:  # pragma: no cover — defensive
            logger.debug(
                "run_trace CAPTURED mark skipped: %s (run_id=%s)",
                mark_err, event.run_id,
            )

    def _rows_to_events(self, rows) -> list[RunTraceEvent]:
        events: list[RunTraceEvent] = []
        for row in rows:
            events.append(RunTraceEvent(
                run_id=row.run_id,
                step=row.step,
                status=row.status,
                ts=row.ts or 0.0,
                duration_ms=row.duration_ms or 0.0,
                safe_metadata=row.safe_metadata_json or {},
            ))
        return events

    def get_run(self, run_id: str) -> list[RunTraceEvent]:
        self._ensure_engine()
        from sqlalchemy import select
        from app.models.run_trace import RunTraceEventModel

        with self._sync_session_factory() as session:
            stmt = (
                select(RunTraceEventModel)
                .where(RunTraceEventModel.run_id == run_id)
                .order_by(RunTraceEventModel.created_at)
            )
            rows = session.execute(stmt).scalars().all()
            return self._rows_to_events(rows)

    def get_run_scoped(self, run_id: str, organization_id: Optional[str]) -> list[RunTraceEvent]:
        """Org-scoped read. Returns [] if run exists but belongs to a different org
        (don't leak cross-org run existence)."""
        self._ensure_engine()
        from sqlalchemy import select
        from app.models.run_trace import RunTraceEventModel

        with self._sync_session_factory() as session:
            stmt = (
                select(RunTraceEventModel)
                .where(RunTraceEventModel.run_id == run_id)
                .order_by(RunTraceEventModel.created_at)
            )
            if organization_id is not None:
                stmt = stmt.where(RunTraceEventModel.organization_id == organization_id)
            rows = session.execute(stmt).scalars().all()
            return self._rows_to_events(rows)

    def clear(self) -> None:
        """Test hook — wipe all events. Dev mode only."""
        self._ensure_engine()
        from sqlalchemy import delete
        from app.models.run_trace import RunTraceEventModel

        with self._sync_session_factory() as session:
            session.execute(delete(RunTraceEventModel))
            session.commit()


# Module-level singletons — one per backend type.
_DEFAULT_IN_MEMORY_STORE = RunTraceStore()
_DEFAULT_DB_STORE: Optional[DbRunTraceStore] = None


# Phase A1A Gate 3R.4 — per-process trace sequence counters.
# Keyed by trace_id (or run_id when trace_id is None). Incremented
# atomically on each emit so events carry a monotonic 1-indexed
# sequence number within the trace. Counters are process-local;
# cross-worker ordering relies on DB-side sort by created_at when
# sequence_number is ambiguous (rare in practice — within a single
# run, events are emitted by one orchestrator process).
_TRACE_SEQUENCE_COUNTERS: dict[str, int] = {}


def _assign_event_identity(
    run_id: str,
    trace_id: Optional[str],
) -> tuple[Optional[str], Optional[int]]:
    """Phase A1A Gate 3R.4 — generate (event_id, sequence_number).

    Returns (None, None) if UUID generation fails (extremely unlikely
    with uuid4). The caller treats None as "identity not assigned";
    the row still writes successfully with NULL identity columns,
    falling back to the legacy (run_id, step, ts) identity.

    ``sequence_number`` is 1-indexed within (trace_id or run_id).
    """
    try:
        import uuid
        event_id = str(uuid.uuid4())
    except Exception as uuid_err:  # pragma: no cover — defensive
        logger.debug("uuid4 generation failed: %s", uuid_err)
        return (None, None)

    counter_key = trace_id or run_id
    try:
        _TRACE_SEQUENCE_COUNTERS[counter_key] = (
            _TRACE_SEQUENCE_COUNTERS.get(counter_key, 0) + 1
        )
        sequence_number = _TRACE_SEQUENCE_COUNTERS[counter_key]
    except Exception:  # pragma: no cover — defensive
        sequence_number = None

    return (event_id, sequence_number)


def _reset_trace_sequence_counter(key: str) -> None:
    """Test hook — reset the per-trace sequence counter for ``key``.

    Production callers don't need this; tests use it so emit order
    is deterministic across runs of the same test.
    """
    _TRACE_SEQUENCE_COUNTERS.pop(key, None)


def _should_fail_closed() -> bool:
    """Phase A1A Gate 3R.3 — consult the deployment profile, not the raw flag.

    Returns True iff the resolved profile is REQUIRED_DB. This routes
    any DB write failure through the caller as a raised exception so
    compliance environments get strict "no trace left behind" semantics.

    Best-effort: if the profile can't be resolved (e.g. settings not
    yet initialized at import time), fall back to the legacy
    ``RUNTRACE_FAIL_CLOSED`` flag so the Gate 3.3 behaviour is
    preserved exactly.
    """
    try:
        from app.services.deployment_profile import get_current_profile
        profile = get_current_profile()
        from app.services.deployment_profile import DeploymentProfile
        return DeploymentProfile.is_fail_closed(profile)
    except Exception:  # pragma: no cover — defensive
        return bool(getattr(settings, "RUNTRACE_FAIL_CLOSED", False))


def get_default_store() -> RunTraceStore | DbRunTraceStore:
    """Return the process-wide default store.

    Selection: ``settings.RUNTRACE_STORE``.
      - ``"memory"`` (default) — RunTraceStore, no DB dependency.
      - ``"db"`` — DbRunTraceStore, persists to run_trace_events table.

    Tests can mutate this in isolation by passing ``store=`` to
    ``emit_trace_event``; production code reads.
    """
    if settings.RUNTRACE_STORE == "db":
        global _DEFAULT_DB_STORE
        if _DEFAULT_DB_STORE is None:
            _DEFAULT_DB_STORE = DbRunTraceStore()
        return _DEFAULT_DB_STORE
    return _DEFAULT_IN_MEMORY_STORE


# ── Phase A1A Gate 3.3 §2 — run_history trace_capture_status marker ──────


def _mark_trace_capture_status(
    run_id: str,
    status: str,
    *,
    reason: Optional[str] = None,
) -> None:
    """Best-effort UPDATE run_history.trace_capture_status for one run.

    Called from ``DbRunTraceStore.append`` on both success (PERSISTED)
    and failure (FAILED). Called from ``RunTraceStore.append`` with
    FALLBACK_MEMORY so audits can tell memory-mode runs from
    DB-persisted runs.

    Why "best-effort"? Because ``record_run_start`` may not have fired
    yet when the first trace event is emitted — the run_history row
    doesn't exist. In that case the UPDATE matches zero rows, which is
    fine: the next event that fires after record_run_start will land
    its UPDATE on the now-existing row.

    Uses a fresh sync session so it can be called from sync emit
    contexts (the inbound handler / dispatcher are sync). The session
    is disposed each call — this is acceptable because the call rate
    is bounded (9 events per run, not thousands).
    """
    from sqlalchemy import create_engine, update
    from sqlalchemy.orm import sessionmaker

    url = settings.DATABASE_URL
    for async_driver in ("+aiosqlite", "+asyncpg", "+psycopg"):
        url = url.replace(async_driver, "")
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    engine = create_engine(url, connect_args=connect_args, echo=False)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        from app.models.run_history import RunHistoryModel
        with Session() as session:
            stmt = update(RunHistoryModel).where(
                RunHistoryModel.run_id == run_id
            ).values(
                trace_capture_status=status,
                trace_capture_failure_reason=reason,
            )
            session.execute(stmt)
            session.commit()
    finally:
        engine.dispose()


def emit_trace_event(
    run_id: str,
    step: str,
    *,
    status: str = RunTraceStatus.OK,
    duration_ms: float = 0.0,
    safe_metadata: dict[str, Any] | None = None,
    store: RunTraceStore | DbRunTraceStore | None = None,
    ts: float | None = None,
) -> RunTraceEvent:
    """Emit one trace event to the store.

    Args:
        run_id: The run identifier (from the A2A envelope or
            orchestrator run context).
        step: One of ``RunTraceStep.*``.
        status: ``ok`` / ``failed`` / ``skipped``.
        duration_ms: How long this step took (0 if instantaneous).
        safe_metadata: Display-safe fields only. The caller is
            responsible for scrubbing — the store does a defensive
            scan but the emit site is the primary safety net.
            For Auth steps, use ``{"redacted_view": ...,
            "required_scopes": [...], "granted_scopes": [...]}``.
            For org/project/user context, stash as
            ``{"_organization_id": ..., "_project_id": ...,
            "_user_id": ..., "_actor_id": ...}`` — DbRunTraceStore
            pops these out before persisting safe_metadata.
        store: Optional override (tests inject a fresh store).
        ts: Optional override for ``time.time`` (tests inject).

    Returns:
        The emitted RunTraceEvent (so the caller can chain).
    """
    target_store = store or get_default_store()
    event = RunTraceEvent(
        run_id=run_id,
        step=step,
        status=status,
        ts=ts if ts is not None else time.time(),
        duration_ms=duration_ms,
        safe_metadata=dict(safe_metadata) if safe_metadata else {},
    )
    target_store.append(event)
    logger.debug(
        "run_trace emit: run=%s step=%s status=%s",
        run_id, step, status,
    )
    return event


# ── Phase 4-A: Agent Backend Provider metadata helper ──────────────────


def emit_backend_metadata_event(
    run_id: str,
    *,
    backend_provider: str,
    backend_type: str,
    provider_latency_ms: int = 0,
    provider_status: str = "complete",
    provider_deterministic: bool = False,
    supports_tool_calling: bool = False,
    fallback_used: bool = False,
    output_contract: str = "",
    tool_rounds: int = 0,
    step: str = RunTraceStep.OUTPUT_GENERATED,
    store: RunTraceStore | DbRunTraceStore | None = None,
) -> RunTraceEvent:
    """Emit a RunTrace event carrying Agent Backend Provider metadata.

    Phase 4-A Task 8 (2026-07-07): every provider invocation should
    emit one of these so ``RunTracePage`` can render a "Backend
    Provider" summary panel (``backend_provider`` / ``backend_type``
    / ``provider_latency_ms`` / ``provider_status`` /
    ``provider_deterministic`` / ``supports_tool_calling`` /
    ``fallback_used`` / ``output_contract``).

    All keys are in ``_SAFE_KEYS`` so the defensive redaction scan
    leaves them intact (Task 8 requirement #2: redaction-before-write).
    The provider_id is a stable string (no PHI); backend_type is one
    of 8 known literals; provider_status is one of 9 status literals;
    the booleans and ints are display-safe by construction.
    """
    safe_metadata: dict[str, Any] = {
        "backend_provider": backend_provider,
        "backend_type": backend_type,
        "provider_latency_ms": int(provider_latency_ms),
        "provider_status": str(provider_status),
        "provider_deterministic": bool(provider_deterministic),
        "supports_tool_calling": bool(supports_tool_calling),
        "fallback_used": bool(fallback_used),
        "output_contract": str(output_contract),
        "tool_rounds": int(tool_rounds),
    }
    return emit_trace_event(
        run_id, step,
        status=RunTraceStatus.OK,
        duration_ms=float(provider_latency_ms),
        safe_metadata=safe_metadata,
        store=store,
    )


__all__ = [
    "RunTraceStep",
    "RunTraceStatus",
    "RunTraceEvent",
    "RunTraceStore",
    "DbRunTraceStore",
    "get_default_store",
    "emit_trace_event",
    "emit_backend_metadata_event",
]
