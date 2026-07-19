"""Phase A1A Gate 3.1 §2 — Evidence-based legacy tenancy attribution.

Replaces the Migration 016 "latest membership wins" heuristic with a
proper evidence collector + classifier. Used by Migration 017 to
re-classify the 430 historical ``LEGACY_TENANT_KNOWN`` rows into the
seven-class taxonomy (charter §3.1 §3):

  MODERN                    — modern write path
  MODERN_SYSTEM             — intentional system-scope row
  LEGACY_TENANT_VERIFIED    — strong request-level evidence pins to 1 org
  LEGACY_TENANT_INFERRED    — exactly 1 candidate org via membership
  LEGACY_TENANT_AMBIGUOUS   — multiple plausible candidate orgs
  LEGACY_TENANT_UNKNOWN     — no candidate org
  QUARANTINED               — operator-flagged (not auto-set)

Evidence priority (highest first):

  1. ``api_client_id`` → ``oauth_clients.organization_id``
  2. ``embedded_app_id`` → ``oauth_clients.organization_id`` (via
     the embedded_app_id column on oauth_clients)
  3. ``session_id`` → ``runtime_sessions.organization_id`` (if table
     exists and row is present)
  4. ``context_id`` → ``runtime_sessions.organization_id`` (same)
  5. ``request_id`` → ``runtime_audit_records.organization_id`` (same)
  6. ``user_id`` at record time → membership snapshot
  7. ``user_id`` total membership history (single-org fallback)

System events (audit rows with ``user_id IS NULL`` and a security
``action`` like ``api_client.authentication_rejected``) classify as
``MODERN_SYSTEM`` regardless of other fields — they are intentionally
system-scope and must never be tenant-backfilled.

This module is pure-Python + SQLAlchemy; the migration imports it and
runs the classifier once. Runtime code (write paths) does NOT call
this module — fresh writes always go through the modern write path
(``classify_modern_write``) and get ``MODERN`` / ``MODERN_SYSTEM``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Sequence

from sqlalchemy import text as sa_text
from sqlalchemy.engine import Connection

from app.middleware.tenancy_guard import (
    CLASS_LEGACY_AMBIGUOUS,
    CLASS_LEGACY_INFERRED,
    CLASS_LEGACY_VERIFIED,
    CLASS_MODERN_SYSTEM,
)

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────


# Action namespace that is intentionally system-scope (no owning org).
# Charter §3.6 §3: "System Event 不能通过通用布尔参数任意绕过组织门禁".
# This allowlist replaces the ``allow_null_org=True`` boolean bypass for
# historical classification; new system actions must be added here AND
# route through app.services.system_audit (Gate 3.6).
SYSTEM_AUDIT_ACTIONS: frozenset[str] = frozenset({
    "api_client.authentication_rejected",
    "system.startup",
    "system.shutdown",
    "system.config_change",
    "system.migration",
    "system.secret_rotation",
    # Phase A1A Gate 3.6 §2 — extended action namespace. Routes
    # through app.services.system_audit; never through log_action.
    "security_admin.access",
    "sse.denied.org_mismatch",
    "sse.denied.invisible_classification",
    "trace.read.denied.org_mismatch",
    "trace.read.denied.invisible_classification",
    "run.cancel",
    "run.timeout",
    "run.complete",
    "run.failed",
    "idempotency.dedup",
    "context.clear",
    "api_client.rotate",
})

# Source string values, mirrored in model column comments.
SOURCE_MODERN_WRITE_PATH = "modern_write_path"
SOURCE_API_CLIENT = "api_client_binding"
SOURCE_EMBEDDED_APP = "embedded_app_binding"
SOURCE_SESSION = "session_binding"
SOURCE_CONTEXT = "context_binding"
SOURCE_REQUEST = "request_correlation"
SOURCE_MEMBERSHIP_LATEST = "user_membership_latest"
SOURCE_MEMBERSHIP_AT_TIME = "user_membership_at_time"
SOURCE_SINGLE_MEMBERSHIP_HISTORY = "user_single_membership_history"
SOURCE_SECURITY_EVENT = "security_event"
SOURCE_NO_USER_NO_CANDIDATE = "no_user_id_no_candidate"
SOURCE_USER_NO_MEMBERSHIP = "user_id_no_membership"

# Confidence values.
CONF_VERIFIED = "verified"
CONF_INFERRED = "inferred"
CONF_AMBIGUOUS = "ambiguous"
CONF_NONE = "none"


# ── Dataclasses ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttributionEvidence:
    """Evidence collected for one row."""

    # Identity fields from the row itself
    row_id: str
    user_id: Optional[str]
    api_client_id: Optional[str]
    embedded_app_id: Optional[str]
    session_id: Optional[str]
    context_id: Optional[str]
    request_id: Optional[str]
    created_at: Optional[datetime]
    action: Optional[str]  # audit_logs only; None for run_history

    # Strong-evidence lookups (filled in by the collector)
    org_from_api_client: Optional[str] = None
    org_from_embedded_app: Optional[str] = None
    org_from_session: Optional[str] = None
    org_from_context: Optional[str] = None
    org_from_request: Optional[str] = None

    # Candidate orgs from user membership (at-time snapshot + history)
    membership_orgs_at_time: frozenset[str] = field(default_factory=frozenset)
    membership_orgs_history: frozenset[str] = field(default_factory=frozenset)
    membership_min_created_at: Optional[datetime] = None


@dataclass(frozen=True)
class AttributionDecision:
    """The classifier's verdict for one row."""

    classification: str
    organization_id: Optional[str]
    source: str
    confidence: str
    candidate_count: int
    original_org_id: Optional[str]
    note: str = ""


# ── Collector ───────────────────────────────────────────────────────────


def _safe_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def collect_evidence_for_row(
    conn: Connection,
    *,
    table: str,
    row_id: str,
) -> AttributionEvidence:
    """Pull the row plus all join-able strong-evidence fields.

    ``table`` is ``"run_history"`` or ``"audit_logs"``. The function
    issues parameterized SQL; no f-string interpolation of ``row_id``.

    Schema-defensive: queries that reference optional correlation
    columns / tables are skipped silently if the column / table is
    absent. This keeps the classifier working as the schema evolves
    (e.g. when ``runtime_sessions.context_id`` does not exist yet).
    """
    if table == "run_history":
        row_sql = sa_text(
            "SELECT id, user_id, api_client_id, embedded_app_id, session_id, "
            "       context_id, request_id, created_at, NULL AS action "
            "FROM run_history WHERE id = :rid"
        )
    elif table == "audit_logs":
        row_sql = sa_text(
            "SELECT id, user_id, NULL AS api_client_id, NULL AS embedded_app_id, "
            "       NULL AS session_id, NULL AS context_id, NULL AS request_id, "
            "       created_at, action "
            "FROM audit_logs WHERE id = :rid"
        )
    else:
        raise ValueError(f"unsupported table {table!r}")

    row = conn.execute(row_sql, {"rid": row_id}).mappings().first()
    if row is None:
        raise ValueError(f"{table} row {row_id!r} not found")

    user_id = _safe_str(row.get("user_id"))
    api_client_id = _safe_str(row.get("api_client_id"))
    embedded_app_id = _safe_str(row.get("embedded_app_id"))
    session_id = _safe_str(row.get("session_id"))
    context_id = _safe_str(row.get("context_id"))
    request_id = _safe_str(row.get("request_id"))
    created_at = row.get("created_at")
    action = _safe_str(row.get("action"))

    ev = AttributionEvidence(
        row_id=row_id,
        user_id=user_id,
        api_client_id=api_client_id,
        embedded_app_id=embedded_app_id,
        session_id=session_id,
        context_id=context_id,
        request_id=request_id,
        created_at=created_at,
        action=action,
    )

    # Strong-evidence lookups. Each helper probes the schema first so a
    # missing column / table degrades gracefully to "no evidence".
    if api_client_id:
        ev = _replace(ev, org_from_api_client=_lookup_org_id(
            conn,
            sql="SELECT organization_id FROM oauth_clients "
                "WHERE client_id = :v AND organization_id IS NOT NULL",
            value=api_client_id,
        ))
    if embedded_app_id:
        ev = _replace(ev, org_from_embedded_app=_lookup_org_id(
            conn,
            sql="SELECT organization_id FROM oauth_clients "
                "WHERE embedded_app_id = :v AND organization_id IS NOT NULL",
            value=embedded_app_id,
            required_column=("oauth_clients", "embedded_app_id"),
        ))
    if session_id:
        ev = _replace(ev, org_from_session=_lookup_org_id(
            conn,
            sql="SELECT organization_id FROM runtime_sessions "
                "WHERE id = :v AND organization_id IS NOT NULL",
            value=session_id,
            required_table="runtime_sessions",
        ))
    if context_id:
        # runtime_sessions does NOT have context_id today; skip the lookup
        # unless the column appears. Future schema can add it without
        # breaking the classifier.
        ev = _replace(ev, org_from_context=_lookup_org_id(
            conn,
            sql="SELECT organization_id FROM runtime_sessions "
                "WHERE context_id = :v AND organization_id IS NOT NULL",
            value=context_id,
            required_column=("runtime_sessions", "context_id"),
        ))
    if request_id:
        ev = _replace(ev, org_from_request=_lookup_org_id(
            conn,
            sql="SELECT organization_id FROM runtime_audit_records "
                "WHERE request_id = :v AND organization_id IS NOT NULL",
            value=request_id,
            required_column=("runtime_audit_records", "request_id"),
        ))

    # User membership snapshot at record time + history.
    if user_id:
        rows = conn.execute(
            sa_text(
                "SELECT organization_id, created_at FROM organization_members "
                "WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).all()
        history = frozenset(
            _safe_str(r[0]) for r in rows if _safe_str(r[0]) is not None
        )
        at_time = frozenset(
            _safe_str(r[0])
            for r in rows
            if _safe_str(r[0]) is not None
            and (r[1] is None or created_at is None or r[1] <= created_at)
        )
        min_created = min(
            (r[1] for r in rows if r[1] is not None), default=None
        )
        ev = _replace(
            ev,
            membership_orgs_at_time=at_time,
            membership_orgs_history=history,
            membership_min_created_at=min_created,
        )

    return ev


def _replace(ev: AttributionEvidence, **kwargs) -> AttributionEvidence:
    """Frozen-dataclass replacement that tolerates unset fields."""
    return ev.__class__(**{**ev.__dict__, **kwargs})


def _table_exists(conn: Connection, table: str) -> bool:
    """Dialect-aware table existence probe.

    SQLite: query sqlite_master. PostgreSQL/MySQL: query
    information_schema. The classifier only needs a boolean; we probe
    one then the other and treat any error as "not found".
    """
    for sql in (
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = :t",
        "SELECT table_name FROM information_schema.tables WHERE table_name = :t",
    ):
        try:
            r = conn.execute(sa_text(sql), {"t": table}).first()
            if r is not None:
                return True
        except Exception:
            continue
    return False


def _column_exists(conn: Connection, table: str, column: str) -> bool:
    """Dialect-aware column existence probe.

    SQLite: PRAGMA table_info. PostgreSQL: information_schema.columns.
    """
    # Try SQLite PRAGMA first (cheap, no round-trip).
    try:
        for row in conn.execute(sa_text(f"PRAGMA table_info({table})")).all():
            if len(row) >= 2 and row[1] == column:
                return True
    except Exception:
        pass
    # Fall back to information_schema (PostgreSQL / MySQL).
    try:
        r = conn.execute(
            sa_text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).first()
        if r is not None:
            return True
    except Exception:
        pass
    return False


def _lookup_org_id(
    conn: Connection,
    *,
    sql: str,
    value: str,
    required_table: Optional[str] = None,
    required_column: Optional[tuple[str, str]] = None,
) -> Optional[str]:
    """Run a strong-evidence lookup, returning None if the schema is
    missing the required table/column or the lookup returns no row.

    All conditional lookups funnel through here so the schema-defensive
    guard lives in exactly one place.
    """
    if required_table and not _table_exists(conn, required_table):
        return None
    if required_column and not _column_exists(conn, required_column[0], required_column[1]):
        return None
    try:
        r = conn.execute(sa_text(sql), {"v": value}).first()
    except Exception as e:
        logger.debug("legacy_tenancy_attribution: lookup failed (%s): %s", sql, e)
        return None
    return _safe_str(r[0]) if r else None


# ── Classifier ─────────────────────────────────────────────────────────


def _strong_evidence_orgs(ev: AttributionEvidence) -> set[str]:
    """Return the set of orgs pinned by request-level evidence."""
    out: set[str] = set()
    for v in (
        ev.org_from_api_client,
        ev.org_from_embedded_app,
        ev.org_from_session,
        ev.org_from_context,
        ev.org_from_request,
    ):
        if v:
            out.add(v)
    return out


def classify(evidence: AttributionEvidence, *, current_org_id: Optional[str]) -> AttributionDecision:
    """Apply the charter §3.1 §3 taxonomy to one row's evidence.

    ``current_org_id`` is the ``organization_id`` currently stamped on
    the row (i.e. what Migration 016 may already have backfilled). The
    classifier may keep, change, or null-out this value depending on
    the evidence.
    """
    original_org_id = _safe_str(current_org_id)

    # 1. System-scope audit events: MODERN_SYSTEM regardless of other fields.
    if evidence.action in SYSTEM_AUDIT_ACTIONS and evidence.user_id is None:
        return AttributionDecision(
            classification=CLASS_MODERN_SYSTEM,
            organization_id=None,
            source=SOURCE_SECURITY_EVENT,
            confidence=CONF_VERIFIED,
            candidate_count=0,
            original_org_id=original_org_id,
            note="System-scope security event; no owning tenant.",
        )

    # 2. Strong request-level evidence.
    strong = _strong_evidence_orgs(evidence)
    if len(strong) == 1:
        org = next(iter(strong))
        return AttributionDecision(
            classification=CLASS_LEGACY_VERIFIED,
            organization_id=org,
            source=SOURCE_API_CLIENT if evidence.org_from_api_client
            else SOURCE_EMBEDDED_APP if evidence.org_from_embedded_app
            else SOURCE_SESSION if evidence.org_from_session
            else SOURCE_CONTEXT if evidence.org_from_context
            else SOURCE_REQUEST,
            confidence=CONF_VERIFIED,
            candidate_count=1,
            original_org_id=original_org_id,
            note="Single-candidate strong evidence.",
        )
    if len(strong) > 1:
        # Conflicting strong evidence — do not silently pick one.
        # Null out the org and route to quarantine via AMBIGUOUS.
        return AttributionDecision(
            classification=CLASS_LEGACY_AMBIGUOUS,
            organization_id=None,
            source=SOURCE_API_CLIENT,  # primary source of the conflict
            confidence=CONF_AMBIGUOUS,
            candidate_count=len(strong),
            original_org_id=original_org_id,
            note=f"Conflicting strong evidence across {len(strong)} orgs.",
        )

    # 3. Fall back to membership.
    # 3a. Membership at record time (created_at) is the most precise.
    at_time = set(evidence.membership_orgs_at_time)
    history = set(evidence.membership_orgs_history)

    if not at_time and not history:
        # No membership at all. Was there a user_id?
        if evidence.user_id is None:
            return AttributionDecision(
                classification="LEGACY_TENANT_UNKNOWN",
                organization_id=None,
                source=SOURCE_NO_USER_NO_CANDIDATE,
                confidence=CONF_NONE,
                candidate_count=0,
                original_org_id=original_org_id,
                note="No user_id and no other correlation id.",
            )
        return AttributionDecision(
            classification="LEGACY_TENANT_UNKNOWN",
            organization_id=None,
            source=SOURCE_USER_NO_MEMBERSHIP,
            confidence=CONF_NONE,
            candidate_count=0,
            original_org_id=original_org_id,
            note="user_id present but no organization_members row.",
        )

    # 3b. Exactly one candidate across at-time + history → INFERRED.
    all_candidates = at_time or history
    if len(all_candidates) == 1:
        org = next(iter(all_candidates))
        source = (
            SOURCE_MEMBERSHIP_AT_TIME if at_time
            else SOURCE_SINGLE_MEMBERSHIP_HISTORY if len(history) == 1
            else SOURCE_MEMBERSHIP_LATEST
        )
        return AttributionDecision(
            classification=CLASS_LEGACY_INFERRED,
            organization_id=org,
            source=source,
            confidence=CONF_INFERRED,
            candidate_count=1,
            original_org_id=original_org_id,
            note=(
                "Single-candidate inferred via membership "
                f"(at_time={len(at_time)} history={len(history)})."
            ),
        )

    # 3c. Multiple candidates. Prefer at-time snapshot if it pins one.
    if len(at_time) == 1:
        org = next(iter(at_time))
        return AttributionDecision(
            classification=CLASS_LEGACY_INFERRED,
            organization_id=org,
            source=SOURCE_MEMBERSHIP_AT_TIME,
            confidence=CONF_INFERRED,
            candidate_count=len(all_candidates),
            original_org_id=original_org_id,
            note=(
                f"{len(all_candidates)} historical candidates but "
                "membership at record time pins one org."
            ),
        )

    # 3d. Genuinely ambiguous.
    return AttributionDecision(
        classification=CLASS_LEGACY_AMBIGUOUS,
        organization_id=None,
        source=SOURCE_MEMBERSHIP_LATEST,
        confidence=CONF_AMBIGUOUS,
        candidate_count=len(all_candidates),
        original_org_id=original_org_id,
        note=(
            f"{len(all_candidates)} candidate orgs; cannot pick one "
            "without request-level evidence."
        ),
    )


# ── Batch driver (used by migration) ────────────────────────────────────


def reclassify_table(
    conn: Connection,
    *,
    table: str,
    batch_size: int = 200,
) -> dict[str, int]:
    """Re-classify every legacy row in ``table``.

    Idempotent: MODERN and MODERN_SYSTEM rows are preserved as-is
    (their organization_id was set by the modern write path and the
    classifier has no business overriding that). LEGACY rows are
    re-evaluated so the migration can be re-run after evidence changes
    (e.g. when a runtime_sessions row is added retroactively).

    Returns a counts dict.
    """
    if table not in {"run_history", "audit_logs"}:
        raise ValueError(f"unsupported table {table!r}")

    id_col = "id"  # both tables use 'id'
    rows = conn.execute(
        sa_text(
            f"SELECT {id_col}, organization_id, tenancy_classification "
            f"FROM {table} ORDER BY {id_col}"
        )
    ).all()

    counts: dict[str, int] = {}
    update_sql = sa_text(
        f"UPDATE {table} SET organization_id = :org, "
        f"tenancy_classification = :cls, "
        f"tenancy_attribution_source = :src, "
        f"tenancy_attribution_confidence = :conf, "
        f"tenancy_attribution_migration = :mig, "
        f"tenancy_attributed_at = :ts, "
        f"tenancy_original_org_id = :orig, "
        f"tenancy_candidate_count = :cc "
        f"WHERE {id_col} = :rid"
    )

    now = datetime.utcnow()
    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]
        for row in batch:
            row_id = row[0]
            current_org = _safe_str(row[1])
            current_cls = _safe_str(row[2])

            # Preserve MODERN / MODERN_SYSTEM rows — the modern write
            # path already supplied the correct organization_id and the
            # classifier's heuristic must not override it.
            if current_cls in {"MODERN", "MODERN_SYSTEM"}:
                counts.setdefault(f"preserved_{current_cls.lower()}", 0)
                counts[f"preserved_{current_cls.lower()}"] += 1
                continue

            evidence = collect_evidence_for_row(conn, table=table, row_id=row_id)
            decision = classify(evidence, current_org_id=current_org)

            conn.execute(
                update_sql,
                {
                    "org": decision.organization_id,
                    "cls": decision.classification,
                    "src": decision.source,
                    "conf": decision.confidence,
                    "mig": "017",
                    "ts": now,
                    "orig": decision.original_org_id,
                    "cc": decision.candidate_count,
                    "rid": row_id,
                },
            )
            counts.setdefault(decision.classification, 0)
            counts[decision.classification] += 1

    return counts


__all__ = [
    "SYSTEM_AUDIT_ACTIONS",
    "AttributionEvidence",
    "AttributionDecision",
    "collect_evidence_for_row",
    "classify",
    "reclassify_table",
]
