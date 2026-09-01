"""P1 contracts for database-session tenant authority."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def test_direct_core_table_sessions_install_tenant_authority() -> None:
    protected_markers = {
        "PatientContext",
        "RunTraceEventModel",
        "RunHistoryModel",
        "Transaction",
        "ContextRow",
        "MemoryConsent",
        "ConversationMemory",
    }
    session_markers = {
        "AsyncSessionLocal(",
        "async_session_factory(",
        "create_engine(",
        "Session(engine)",
    }
    violations: list[str] = []
    for root in (BACKEND_ROOT / "app", BACKEND_ROOT / "scripts"):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if not any(marker in source for marker in protected_markers):
                continue
            if not any(marker in source for marker in session_markers):
                continue
            if "bind_tenant_to_" not in source:
                violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert violations == []


def test_indirect_core_runtime_sessions_bind_before_service_calls() -> None:
    required = (
        "app/api/runs.py",
        "app/icoder/agent_runtime/provider_a2a_handler.py",
        "app/icoder/agent_runtime/tenant_clone_a2a_dispatch_handler.py",
        "app/icoder/agent_runtime/a2a/v1/task_runtime.py",
    )
    for relative in required:
        source = (BACKEND_ROOT / relative).read_text(encoding="utf-8")
        assert "bind_tenant_to_transaction" in source, relative


def test_postgresql_purge_clis_require_explicit_tenant() -> None:
    for relative in (
        "scripts/purge_retention.py",
        "scripts/purge_agent_feedback.py",
    ):
        source = (BACKEND_ROOT / relative).read_text(encoding="utf-8")
        assert 'dialect.name == "postgresql"' in source
        assert "requires --organization-id" in source
        assert "bind_tenant_to_transaction" in source


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@pytest.mark.asyncio
async def test_live_membership_is_required_before_user_tenant_binding(
    monkeypatch,
) -> None:
    from app.middleware import auth

    db = SimpleNamespace(execute=AsyncMock(return_value=_Result("membership-id")))
    binder = AsyncMock()
    monkeypatch.setattr(auth, "bind_tenant_to_transaction", binder)

    assert await auth._bind_live_user_membership(
        db, user_id="user-1", organization_id="org-1", required=True
    )
    binder.assert_awaited_once_with(db, "org-1")


@pytest.mark.asyncio
async def test_stale_membership_never_becomes_database_authority(
    monkeypatch,
) -> None:
    from app.middleware import auth

    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(None)))
    binder = AsyncMock()
    monkeypatch.setattr(auth, "bind_tenant_to_transaction", binder)

    assert not await auth._bind_live_user_membership(
        db, user_id="user-1", organization_id="org-1"
    )
    binder.assert_not_awaited()
    with pytest.raises(HTTPException) as exc:
        await auth._bind_live_user_membership(
            db, user_id="user-1", organization_id="org-1", required=True
        )
    assert exc.value.status_code == 403
