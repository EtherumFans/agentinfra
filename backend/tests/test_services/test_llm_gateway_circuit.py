"""Unit tests for circuit breaker re-export + helper in llm_gateway.

Covers Commit 1: re-export of llm_circuit_breaker, _check_circuit_or_raise helper.
"""
import pytest

from icoder_runtime.circuit_breaker import CircuitBreaker
from icoder_runtime.core.errors import ProviderError
from icoder_runtime.core.llm_gateway import (
    _check_circuit_or_raise,
    gateway_circuit_breaker,
)


def test_gateway_circuit_breaker_is_canonical_singleton():
    """The re-exported name should point at the same singleton as llm_circuit_breaker."""
    from icoder_runtime.circuit_breaker import llm_circuit_breaker
    assert gateway_circuit_breaker is llm_circuit_breaker
    assert isinstance(gateway_circuit_breaker, CircuitBreaker)
    assert gateway_circuit_breaker.name == "llm"


def test_check_circuit_passes_when_closed():
    """A fresh circuit (CLOSED state) does not raise."""
    cb = CircuitBreaker(name="test-closed", failure_threshold=3, recovery_timeout=30.0)
    assert cb.is_open is False
    # Should not raise
    _check_circuit_or_raise(cb)


def test_check_circuit_raises_when_open():
    """After enough failures the circuit opens; _check_circuit_or_raise raises."""
    cb = CircuitBreaker(name="test-open", failure_threshold=3, recovery_timeout=30.0)
    # Force the circuit open by recording failures past the threshold
    for _ in range(5):
        cb.record_failure()
    assert cb.is_open is True
    with pytest.raises(ProviderError, match="(?i)circuit.*open"):
        _check_circuit_or_raise(cb)


def test_check_circuit_recovers_after_recovery_timeout(monkeypatch):
    """After recovery_timeout elapses, the circuit probes (HALF_OPEN)."""
    cb = CircuitBreaker(name="test-recover", failure_threshold=2, recovery_timeout=10.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open is True
    # Simulate the recovery timeout elapsing
    monkeypatch.setattr(cb, "_opened_at", 0.0)
    # Next call should be allowed (HALF_OPEN, not blocking)
    assert cb.is_open is False
    _check_circuit_or_raise(cb)  # no raise
