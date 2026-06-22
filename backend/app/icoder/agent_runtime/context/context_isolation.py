"""Context isolation errors + invariants (SPEC §6.5)."""

from __future__ import annotations


class ContextIsolationError(Exception):
    """Raised when a repository operation would violate contextId isolation.

    Always carries the offending contextId for diagnostics.
    """

    def __init__(self, message: str, *, context_id: str | None = None) -> None:
        super().__init__(message)
        self.context_id = context_id


class ContextNotFoundError(ContextIsolationError):
    """Referenced contextId does not exist."""