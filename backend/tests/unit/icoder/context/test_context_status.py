"""C1 — ContextStatus lifecycle enum."""

from __future__ import annotations

from app.icoder.agent_runtime.context.context_status import ContextStatus


def test_status_has_four_states():
    names = {s.name for s in ContextStatus}
    assert names == {"ACTIVE", "COMPLETED", "FAILED", "EXPIRED"}


def test_status_string_values_match_spec():
    assert ContextStatus.ACTIVE.value == "active"
    assert ContextStatus.COMPLETED.value == "completed"
    assert ContextStatus.FAILED.value == "failed"
    assert ContextStatus.EXPIRED.value == "expired"


def test_status_compares_to_plain_string():
    assert ContextStatus.ACTIVE == "active"
    assert ContextStatus.FAILED != "completed"


def test_status_is_str_subclass():
    assert isinstance(ContextStatus.ACTIVE, str)


def test_status_iteration_yields_all():
    values = [s.value for s in ContextStatus]
    assert values == ["active", "completed", "failed", "expired"]