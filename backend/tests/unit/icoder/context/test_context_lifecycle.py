"""C6 — ContextLifecycle state-machine logic (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.icoder.agent_runtime.context.context_lifecycle import (
    ContextLifecycleError,
)


def test_lifecycle_error_carries_context_id_and_current_status():
    from app.icoder.agent_runtime.context.context_status import ContextStatus

    err = ContextLifecycleError(
        "no",
        context_id="550e8400-e29b-41d4-a716-446655440000",
        current_status=ContextStatus.COMPLETED,
    )
    assert err.context_id == "550e8400-e29b-41d4-a716-446655440000"
    assert err.current_status == ContextStatus.COMPLETED
    assert "no" in str(err)
    assert isinstance(err, Exception)


def test_lifecycle_error_is_exception():
    assert issubclass(ContextLifecycleError, Exception)