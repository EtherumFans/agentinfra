"""Phase A1D.4 (A1C-B-008) — KMS rotation version token.

Closes the A1C.9 blocker A1C-B-008: ``CredentialVault`` caches decrypted
secrets in process memory after first ``resolve()``. When the cloud KMS
rotates a key (operator-driven, scheduled, or compromise-response), the
cached value is stale but the cache returns it indefinitely.

This module provides a monotonic version token. The token starts at 1
and only ever increments. The cache stamps entries with the current
token; on lookup, if the entry's stamp is stale (entry stamp < current
token), the cache re-reads from the secrets manager.

Production wiring (Pilot env):
  - Operator rotates KMS key via cloud console.
  - Post-rotation hook (cloud function / k8s sidecar / cron) calls
    ``kms_version_token.bump()`` on each app instance.
  - Next ``vault.resolve(service)`` detects stale stamp, re-reads,
    restamps with new token.

Local / dev / test wiring:
  - Tests can construct a token, populate the cache, then call ``bump()``
    to simulate rotation.
"""
from __future__ import annotations

import threading


class KMSVersionToken:
    """Monotonic counter; never decreases.

    Thread-safe — ``bump()`` and ``current`` can be called from any thread
    (the cloud rotation hook may run on a sidecar thread).
    """

    def __init__(self, initial: int = 1) -> None:
        if initial < 1:
            raise ValueError(f"KMSVersionToken initial must be >= 1, got {initial}")
        self._value = initial
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        with self._lock:
            return self._value

    def bump(self) -> int:
        """Atomically increment the version and return the new value."""
        with self._lock:
            self._value += 1
            return self._value

    def is_stale(self, stamp: int) -> bool:
        """Return True if the given stamp predates the current version."""
        with self._lock:
            return stamp < self._value

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"KMSVersionToken(current={self.current})"


__all__ = ["KMSVersionToken"]
