"""A1D.2 — A1C-B-018 ICODER_AUDIT_WRITE_PAUSED flag.

Predecessor state (Phase A1C.9): ``app/middleware/audit.py::log_action``
always commits a row to ``audit_logs``. RB-3 PITR rollback needs the
operator to be able to PAUSE audit writes during the recovery window
without stopping the whole service — otherwise the rolled-back DB
collects audit rows that point at operations that were undone.

Phase A1D.2 (A1C-B-018) adds:
  - ``ICODER_AUDIT_WRITE_PAUSED`` env flag (default ``false``)
  - ``log_action`` short-circuits when the flag is set: warns + skips
    ``db.add`` but STILL enforces the tenancy guard (fail-closed must
    fire even when audit is paused — never bypass tenancy).

Coverage:
  - paused + valid tenancy → no DB row, warning logged
  - not paused → row written (regression)
  - paused + invalid tenancy → still raises (fail-closed survives pause)
  - paused + system-scope event → also skipped (allow_null_org path)

Tests are SYNC (use ``asyncio.run`` to drive the async ``log_action``)
so they do NOT trigger the autouse session-scoped DB setup fixture in
``conftest.py``. This keeps them hermetic to the pre-existing duplicate-
index infra issue (A1C-B-002 / A1D.5 backlog).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _FakeDB:
    """Minimal stand-in for AsyncSession — captures .add() calls."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)


@pytest.fixture
def paused_audit_env(monkeypatch):
    """Set ICODER_AUDIT_WRITE_PAUSED=true for one test."""
    monkeypatch.setenv("ICODER_AUDIT_WRITE_PAUSED", "true")
    yield


@pytest.fixture
def unpaused_audit_env(monkeypatch):
    """Explicitly clear ICODER_AUDIT_WRITE_PAUSED (default state)."""
    monkeypatch.delenv("ICODER_AUDIT_WRITE_PAUSED", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────
# §1 paused flag short-circuits the DB write
# ─────────────────────────────────────────────────────────────────────


def test_log_action_skips_db_write_when_paused(paused_audit_env, caplog):
    """When ICODER_AUDIT_WRITE_PAUSED=true, no AuditLog row is added."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    with caplog.at_level(logging.WARNING, logger="app.middleware.audit"):
        asyncio.run(log_action(
            db=db,
            user_id="u-test",
            username="tester",
            action="test.action",
            resource_type="test_resource",
            resource_id="r-1",
            organization_id="org-test",
            allow_null_org=False,
        ))

    assert db.added == [], "no AuditLog row should be added when paused"
    pause_logs = [r for r in caplog.records if "pause" in r.message.lower()]
    assert pause_logs, "expected a WARNING log mentioning the pause"


def test_log_action_writes_when_not_paused(unpaused_audit_env):
    """Regression: when the flag is clear, log_action writes the row."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id="u-test",
        username="tester",
        action="test.action",
        resource_type="test_resource",
        resource_id="r-1",
        organization_id="org-test",
        allow_null_org=False,
    ))

    assert len(db.added) == 1, "row should be written when not paused"


# ─────────────────────────────────────────────────────────────────────
# §2 fail-closed tenancy guard STILL fires when paused
# ─────────────────────────────────────────────────────────────────────


def test_log_action_pause_does_not_bypass_tenancy_guard(paused_audit_env, monkeypatch):
    """PAUSED must NOT bypass the cloud-mode fail-closed tenancy guard.

    A paused audit would be a perfect data-leak vector if it skipped the
    tenancy check — the row that would have failed tenancy now silently
    drops. The guard fires BEFORE the pause short-circuit.
    """
    from app.middleware.audit import log_action

    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    db = _FakeDB()

    with pytest.raises(Exception):  # noqa: B017 — broad on purpose
        asyncio.run(log_action(
            db=db,
            user_id=None,
            username=None,
            action="system.test",
            resource_type="system",
            resource_id=None,
            organization_id=None,
            allow_null_org=False,
        ))


# ─────────────────────────────────────────────────────────────────────
# §3 allow_null_org=True system-scope events also respect pause
# ─────────────────────────────────────────────────────────────────────


def test_log_action_pause_with_system_scope_event_skips_db_write(paused_audit_env):
    """System-scope events (allow_null_org=True) also respect pause."""
    from app.middleware.audit import log_action

    db = _FakeDB()
    asyncio.run(log_action(
        db=db,
        user_id=None,
        username=None,
        action="system.startup",
        resource_type="system",
        resource_id=None,
        organization_id=None,
        allow_null_org=True,
    ))

    assert db.added == [], "system-scope events must also respect pause"
