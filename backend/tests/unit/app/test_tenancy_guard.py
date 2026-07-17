"""A1A Gate 2 §3 — Cloud-mode fail-closed tenancy guard tests.

Validates that ``assert_tenancy_for_write`` refuses NULL org_id writes
in cloud mode but allows them in local mode. Also covers the
``classify_modern_write`` helper that stamps ``tenancy_classification``
on every NEW row so historical NULLs are unambiguous.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.middleware.tenancy_guard import (  # noqa: E402
    CLASS_MODERN_SYSTEM,
    TenancyViolationError,
    assert_tenancy_for_write,
    classify_modern_write,
)


def test_local_mode_allows_null_org_id(monkeypatch):
    """Local mode = single-tenant dev workflow; NULL org_id is OK."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    # No exception for any of these:
    assert_tenancy_for_write(None, "run_history")
    assert_tenancy_for_write("", "audit_logs")
    assert_tenancy_for_write("   ", "idempotency_records")
    assert_tenancy_for_write("org-abc", "preview_sessions")


def test_cloud_mode_allows_non_empty_org_id(monkeypatch):
    """Cloud mode happy path: caller supplied a real org_id."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    assert_tenancy_for_write("org-abc", "run_history")
    assert_tenancy_for_write("tenant-001", "audit_logs")


def test_cloud_mode_rejects_null_org_id(monkeypatch):
    """Cloud mode + NULL org_id → TenancyViolationError."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(TenancyViolationError, match="run_history"):
        assert_tenancy_for_write(None, "run_history")


def test_cloud_mode_rejects_empty_string_org_id(monkeypatch):
    """Cloud mode + empty string org_id → reject (treated as NULL)."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(TenancyViolationError, match="audit_logs"):
        assert_tenancy_for_write("", "audit_logs")


def test_cloud_mode_rejects_whitespace_only_org_id(monkeypatch):
    """Cloud mode + whitespace-only org_id → reject after strip()."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(TenancyViolationError, match="idempotency_records"):
        assert_tenancy_for_write("   ", "idempotency_records")


def test_cloud_mode_allows_null_with_allow_flag(monkeypatch):
    """Cloud mode + system-scope row (allow_null_org=True) → OK."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    # System bootstrap / health check rows legitimately have no org.
    assert_tenancy_for_write(
        None, "audit_logs", allow_null_org=True,
    )


def test_violation_error_message_contains_table_and_hint(monkeypatch):
    """Error message surfaces the table + remediation hint."""
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(TenancyViolationError) as exc_info:
        assert_tenancy_for_write(None, "preview_sessions")
    msg = str(exc_info.value)
    assert "preview_sessions" in msg
    assert "NULL organization_id" in msg
    assert "current_org" in msg  # remediation hint


# ── classify_modern_write ──────────────────────────────────────────


def test_classify_modern_write_returns_modern_for_org_id():
    """Non-empty org_id → MODERN."""
    assert classify_modern_write("org-abc") == "MODERN"
    assert classify_modern_write("tenant-001") == "MODERN"


def test_classify_modern_write_returns_system_for_allowed_null(monkeypatch):
    """System-scope row → MODERN_SYSTEM (distinct from historical NULL)."""
    assert classify_modern_write(None, allow_null_org=True) == CLASS_MODERN_SYSTEM
    assert classify_modern_write("", allow_null_org=True) == CLASS_MODERN_SYSTEM


def test_classify_modern_write_returns_none_for_local_mode_null():
    """Local mode without allow_null_org → None (column stays NULL).

    This preserves the single-tenant dev workflow: local mode doesn't
    force callers to assert allow_null_org for every NULL write.
    """
    assert classify_modern_write(None) is None
    assert classify_modern_write("") is None


def test_classify_modern_write_cloud_mode_null_without_allow_raises(monkeypatch):
    """Cloud mode + NULL + no allow_null_org → never reaches classify.

    The guard fires first; this test documents that the classifier is
    safe to call only after the guard has passed.
    """
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(TenancyViolationError):
        assert_tenancy_for_write(None, "run_history")
    # In practice the caller calls assert_tenancy_for_write() FIRST,
    # then classify_modern_write(). The guard ensures we never get
    # to classify with an un-allowed NULL.
