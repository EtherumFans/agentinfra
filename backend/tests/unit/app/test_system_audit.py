"""Phase A1A Gate 3.6 — system_audit service tests.

Charter §3.6 coverage:

1. ``system_audit`` writes rows with ``organization_id=NULL`` +
   ``tenancy_classification=MODERN_SYSTEM``.
2. ``system_audit`` rejects actions outside the allowlist with
   ``ValueError`` (cannot smuggle tenant events through the
   system path).
3. ``ALL_SYSTEM_AUDIT_ACTIONS`` includes every charter-mandated
   action: ``security_admin.access``, ``trace.read.denied.*``,
   ``sse.denied.*``, ``run.cancel/timeout/complete/failed``,
   ``idempotency.dedup``, ``context.clear``, ``api_client.rotate``.
4. The classifier in ``legacy_tenancy_attribution`` recognises
   every new action as ``MODERN_SYSTEM``.
"""
from __future__ import annotations

import pytest


# ── §1 Allowlist coverage ─────────────────────────────────────────


def test_all_system_audit_actions_includes_required_events():
    """Charter §3.6 §1 action list."""
    from app.services.system_audit import ALL_SYSTEM_AUDIT_ACTIONS
    required = {
        # Existing (legacy_tenancy_attribution)
        "api_client.authentication_rejected",
        "system.startup",
        "system.shutdown",
        "system.config_change",
        "system.migration",
        "system.secret_rotation",
        # Gate 3.2
        "security_admin.access",
        # Gate 3.4
        "sse.denied.org_mismatch",
        "sse.denied.invisible_classification",
        # Gate 3.5
        "trace.read.denied.org_mismatch",
        "trace.read.denied.invisible_classification",
        # Gate 3.6
        "run.cancel",
        "run.timeout",
        "run.complete",
        "run.failed",
        "idempotency.dedup",
        "context.clear",
        "api_client.rotate",
    }
    missing = required - ALL_SYSTEM_AUDIT_ACTIONS
    assert not missing, f"system_audit allowlist missing: {missing}"


# ── §2 Rejects unknown actions ────────────────────────────────────


@pytest.mark.asyncio
async def test_system_audit_rejects_unknown_action(tmp_path, monkeypatch):
    """A tenant-style action like 'user.login' must be refused —
    callers can't smuggle tenant events through the system path."""
    from app.services.system_audit import system_audit
    # Point at an in-memory DB.
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path.as_posix()}/audit_test.db",
    )
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from app.database import Base
    from app.models.audit_log import AuditLog
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path.as_posix()}/audit_test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[AuditLog.__table__])
    async with AsyncSession(engine) as db:
        with pytest.raises(ValueError, match="allowlist"):
            await system_audit(
                db,
                action="user.login",   # tenant action — must be refused
                resource_type="user",
                resource_id="u-1",
            )
    await engine.dispose()


# ── §3 Writes MODERN_SYSTEM row with NULL org ─────────────────────


@pytest.mark.asyncio
async def test_system_audit_writes_modern_system_row(tmp_path, monkeypatch):
    """Successful emit creates an audit row with the expected shape."""
    monkeypatch.setattr(
        "app.config.settings.DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path.as_posix()}/audit_test2.db",
    )
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy import select
    from app.database import Base
    from app.models.audit_log import AuditLog
    from app.services.system_audit import system_audit
    from app.middleware.tenancy_guard import CLASS_MODERN_SYSTEM

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path.as_posix()}/audit_test2.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[AuditLog.__table__])
    async with AsyncSession(engine) as db:
        await system_audit(
            db,
            action="system.startup",
            resource_type="system",
            resource_id=None,
            details={"version": "0.1.0"},
        )
        await db.commit()

    async with AsyncSession(engine) as db:
        rows = (await db.execute(select(AuditLog))).scalars().all()
    await engine.dispose()

    assert len(rows) == 1
    row = rows[0]
    assert row.organization_id is None
    assert row.tenancy_classification == CLASS_MODERN_SYSTEM
    assert row.action == "system.startup"
    assert row.tenancy_attribution_source == "security_event"
    assert row.tenancy_attribution_confidence == "verified"


# ── §4 Classifier recognises new actions as MODERN_SYSTEM ─────────


def test_classifier_recognises_gate36_actions():
    """The legacy_tenancy_attribution classifier must recognise
    every new action in ALL_SYSTEM_AUDIT_ACTIONS as MODERN_SYSTEM
    so consistency is maintained between runtime writes and
    historical reclassification."""
    from app.services.legacy_tenancy_attribution import (
        SYSTEM_AUDIT_ACTIONS, classify,
        AttributionEvidence,
    )
    from app.middleware.tenancy_guard import CLASS_MODERN_SYSTEM
    from app.services.system_audit import ALL_SYSTEM_AUDIT_ACTIONS

    # Every action in ALL_SYSTEM_AUDIT_ACTIONS must be in the
    # classifier's SYSTEM_AUDIT_ACTIONS too.
    diff = ALL_SYSTEM_AUDIT_ACTIONS - SYSTEM_AUDIT_ACTIONS
    assert not diff, (
        f"actions in system_audit but not in classifier: {diff}"
    )

    # Spot-check: classify() returns MODERN_SYSTEM for a sample action.
    ev = AttributionEvidence(
        row_id="x",
        user_id=None,
        api_client_id=None,
        embedded_app_id=None,
        session_id=None,
        context_id=None,
        request_id=None,
        created_at=None,
        action="run.cancel",
    )
    decision = classify(ev, current_org_id=None)
    assert decision.classification == CLASS_MODERN_SYSTEM, (
        f"classifier returned {decision.classification} for run.cancel"
    )
