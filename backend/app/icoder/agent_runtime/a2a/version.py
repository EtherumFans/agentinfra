"""A2A Protocol Version (SPEC §10).

Strict spec compliance (Q-A2): the ``A2A-Protocol-Version`` header is
**required** for inbound requests. Missing or unknown version returns
INVALID_REQUEST (-32600) + HTTP 400.

Phase 1 implements A2A v0.3 only. Future versions (v0.4+) require
spec updates + matching tests.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

A2A_PROTOCOL_VERSION: Final[str] = "0.3"
"""Current A2A protocol version. Match A2A v0.3 spec (Linux Foundation)."""

A2A_PROTOCOL_HEADER: Final[str] = "A2A-Protocol-Version"
"""HTTP header carrying the protocol version."""

SUPPORTED_VERSIONS: Final[tuple[str, ...]] = ("0.3",)
"""Versions this server understands. Strict — no negotiation in Phase 1."""

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class A2AVersionError(Exception):
    """Raised when the inbound version header is missing or unsupported.

    The Inbound route catches this and returns a JSON-RPC error envelope
    with code -32600 (Invalid Request) + HTTP 400 (SPEC §6.1).
    """

    def __init__(self, message: str, *, received: str | None = None) -> None:
        super().__init__(message)
        self.received = received


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_version_header(headers: dict[str, str] | None) -> str:
    """Validate the ``A2A-Protocol-Version`` header.

    Returns the validated version string on success. Raises
    :class:`A2AVersionError` on missing or unsupported values.

    Per Q-A2 the header is mandatory; per Q-A1 the check is strict
    (no silent fallback to "0.3").
    """
    if not headers:
        raise A2AVersionError(
            f"missing required header {A2A_PROTOCOL_HEADER!r}",
            received=None,
        )
    # Header lookup is case-insensitive per RFC 7230 §3.2.
    raw: str | None = None
    for k, v in headers.items():
        if k.lower() == A2A_PROTOCOL_HEADER.lower():
            raw = v
            break
    if raw is None or raw == "":
        raise A2AVersionError(
            f"missing required header {A2A_PROTOCOL_HEADER!r}",
            received=None,
        )
    if raw not in SUPPORTED_VERSIONS:
        raise A2AVersionError(
            f"A2A protocol version {raw!r} not supported "
            f"(supported: {', '.join(SUPPORTED_VERSIONS)})",
            received=raw,
        )
    return raw


def negotiate_version(client_version: str | None) -> str:
    """Pick a mutually-supported version.

    Phase 1 is strict: the client must declare exactly "0.3". This
    function exists so a future spec bump can plug in real negotiation
    without changing call sites.

    Raises :class:`A2AVersionError` on unsupported input.
    """
    if client_version is None or client_version == "":
        raise A2AVersionError(
            f"missing required header {A2A_PROTOCOL_HEADER!r}",
            received=None,
        )
    if client_version not in SUPPORTED_VERSIONS:
        raise A2AVersionError(
            f"A2A protocol version {client_version!r} not supported "
            f"(supported: {', '.join(SUPPORTED_VERSIONS)})",
            received=client_version,
        )
    return client_version


__all__ = [
    "A2A_PROTOCOL_HEADER",
    "A2A_PROTOCOL_VERSION",
    "A2AVersionError",
    "SUPPORTED_VERSIONS",
    "negotiate_version",
    "validate_version_header",
]