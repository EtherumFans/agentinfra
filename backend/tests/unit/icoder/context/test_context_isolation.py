"""C5 (early) — ContextIsolationError + ContextNotFoundError dataclass logic."""

from __future__ import annotations

from app.icoder.agent_runtime.context.context_isolation import (
    ContextIsolationError,
    ContextNotFoundError,
)


def test_isolation_error_carries_context_id():
    err = ContextIsolationError("bad", context_id="ctx-1")
    assert err.context_id == "ctx-1"
    assert "bad" in str(err)


def test_isolation_error_context_id_optional():
    err = ContextIsolationError("bad")
    assert err.context_id is None
    assert "bad" in str(err)


def test_not_found_is_subclass_of_isolation_error():
    err = ContextNotFoundError("missing", context_id="ctx-x")
    assert isinstance(err, ContextIsolationError)
    assert err.context_id == "ctx-x"


def test_isolation_error_is_exception():
    assert issubclass(ContextIsolationError, Exception)
    assert issubclass(ContextNotFoundError, Exception)