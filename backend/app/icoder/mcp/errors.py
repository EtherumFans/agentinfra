"""MCP error codes (JSON-RPC 2.0 + 5 custom).

Per the plan, M2 ships 5 standard JSON-RPC 2.0 codes (the ones reserved
by the spec) plus 5 custom codes in the ``-32001..-32005`` range for
iCoDer-specific failure modes. The mapping is exposed via
:meth:`MCPErrorCode.envelope` so handlers can build the JSON-RPC error
payload uniformly.

Why custom codes:
  - The spec defines standard codes for protocol-level errors but leaves
    application-level error semantics to the implementer.
  - iCoDer MCP tools surface 5 distinct failure modes (catalog miss,
    retriever unavailable, LLM timeout, PHI redaction failed, production
    writeback blocked) that downstream ISV agents need to distinguish
    programmatically. Collapsing them into ``-32603 Internal Error``
    would force clients to parse ``message`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MCPErrorCode:
    """JSON-RPC 2.0 + iCoDer MCP error code constants.

    Standard JSON-RPC 2.0 reserved range (per spec):
      -32700 .. -32600 — pre-defined error codes
      -32099 .. -32000 — implementation-defined server errors
    """

    # ── Standard JSON-RPC 2.0 reserved codes ─────────────────────
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # ── iCoDer MCP custom codes (server errors) ─────────────────
    CATALOG_MISS = -32001
    RETRIEVER_UNAVAILABLE = -32002
    LLM_TIMEOUT = -32003
    PHI_REDACTION_FAILED = -32004
    PRODUCTION_WRITEBACK_BLOCKED = -32005

    @staticmethod
    def name(code: int) -> str:
        """Reverse lookup — code → human-readable name."""
        for attr in dir(MCPErrorCode):
            if attr.isupper() and getattr(MCPErrorCode, attr) == code:
                return attr
        return f"CODE_{code}"

    @staticmethod
    def envelope(code: int, message: str, *, data: dict[str, Any] | None = None) -> dict:
        """Build a JSON-RPC 2.0 error envelope.

        Shape per spec:
          ``{"code": int, "message": str, "data"?: object}``
        """
        out: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            out["data"] = data
        return out


@dataclass
class MCPError(Exception):
    """Typed MCP error. Carries a JSON-RPC code + optional structured data.

    Handlers raise :class:`MCPError` to signal a tool failure. The
    server's dispatcher catches it and serializes the envelope via
    :meth:`MCPErrorCode.envelope`. Anything else bubbles as
    ``-32603 Internal Error``.
    """

    code: int
    message: str
    data: dict[str, Any] | None = None

    def to_envelope(self) -> dict:
        return MCPErrorCode.envelope(self.code, self.message, data=self.data)


__all__ = ["MCPErrorCode", "MCPError"]