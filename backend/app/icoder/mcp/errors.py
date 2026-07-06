"""MCP error codes (JSON-RPC 2.0 + 5 custom + 7 auth).

Per the plan, M2 ships 5 standard JSON-RPC 2.0 codes (the ones reserved
by the spec) plus 5 custom codes in the ``-32001..-32005`` range for
iCoDer-specific failure modes. The mapping is exposed via
:meth:`MCPErrorCode.envelope` so handlers can build the JSON-RPC error
payload uniformly.

Phase 3-C1 (2026-07-05) adds 7 MCP auth error codes (``-32006..-32012``)
per ICODER_V1_MCP_SPEC §6.3 / §11.6, covering the 4 auth types
(none / bearer / inherit / oauth2.0). The :class:`MCPAuthError`
subclass enforces redaction — raw tokens / client_secrets never leak
into ``data.details``.

Why custom codes:
  - The spec defines standard codes for protocol-level errors but leaves
    application-level error semantics to the implementer.
  - iCoDer MCP tools surface 5 distinct failure modes (catalog miss,
    retriever unavailable, LLM timeout, PHI redaction failed, production
    writeback blocked) that downstream ISV agents need to distinguish
    programmatically. Collapsing them into ``-32603 Internal Error``
    would force clients to parse ``message`` strings.
  - Auth failures need their own envelope so clients can distinguish
    "config was wrong" (4xx, retryable=False) from "token exchange
    failed" (401, retryable=True) from "token valid but scope
    insufficient" (403, retryable=False).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Secrets that must never appear in error data payloads. The
# :class:`MCPAuthError` constructor uses this to scrub its ``data``
# before raising.
_REDACTED_TOKEN_SUBSTRINGS = (
    "Bearer ",
    "access_token",
    "client_secret",
    "refresh_token",
    "token\":",
    "'token':",
)

# Keys that may safely survive redaction even if their values look
# alphanumeric (e.g., a symbolic constant like "MCP_AUTH_FORBIDDEN"
# would otherwise match the token-blob heuristic). These are
# display / classification keys, never secrets.
_SAFE_KEYS = {
    "mcp_error_code", "a2a_error_code", "code", "tool_name", "status",
    "reason", "redacted_view", "stage", "kind", "type", "method",
    "provider", "scope", "scopes", "audience",
}

# A long (16+ char) run of base64 / hex / alphanumeric characters
# without whitespace or underscores — looks like a token, not a sentence
# or snake_case identifier. Underscores are excluded so tool names like
# ``get_differentiation_hint`` (23 chars) don't trip the heuristic.
_TOKEN_BLOB_PATTERN = re.compile(r"[A-Za-z0-9\-]{16,}")


def _looks_like_token_blob(value: str) -> bool:
    """Heuristic — does this string look like a raw token / secret
    blob (rather than a normal English/Chinese description)?

    Triggers if the string contains a 16+ char alphanumeric run
    with no spaces — that pattern doesn't appear in normal prose
    but is the signature of JWTs, opaque tokens, base64-encoded
    secrets, and hex strings.

    Exceptions:
      - UPPER_SNAKE_CASE symbolic constants (e.g.,
        ``MCP_AUTH_FORBIDDEN``) — these match the alphanumeric-run
        pattern but are classification strings, not secrets. Caller
        must whitelist them via the ``_SAFE_KEYS`` set.
    """
    if not value or len(value) < 16:
        return False
    # Skip UPPER_SNAKE_CASE constants — they look like blobs but
    # are symbolic names. Allow A-Z, 0-9, _ only; must contain at
    # least one underscore; no lowercase.
    if (
        value.replace("_", "").isalnum()
        and "_" in value
        and value.upper() == value
        and not any(c.islower() for c in value)
    ):
        return False
    # Find the longest alphanumeric run; if it's 16+ chars, treat
    # the whole string as a potential token leak.
    m = _TOKEN_BLOB_PATTERN.findall(value)
    return any(len(run) >= 16 for run in m)


def _redact_secret(value: Any, _key: str = "") -> Any:
    """Walk a data structure and replace any string that looks like
    a token / secret with ``"<redacted>"``. Returns a new structure
    (does not mutate the input)."""
    if isinstance(value, str):
        # Known token-indicator substrings.
        if any(s in value for s in _REDACTED_TOKEN_SUBSTRINGS):
            # Redacted_view is a display string like "Bearer ••••12"
            # — it's MEANT to be shown, do not scrub.
            if _key.lower() == "redacted_view":
                return value
            return "<redacted>"
        # Long alphanumeric blob (JWT / opaque token / base64 secret).
        if _looks_like_token_blob(value):
            return "<redacted>"
        return value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            kl = k.lower() if isinstance(k, str) else k
            if kl in (
                "token", "access_token", "refresh_token",
                "client_secret", "client_id", "authorization",
                "secret", "password",
            ):
                # Never expose known-secret keys; show only ``<redacted>``.
                out[k] = "<redacted>"
            elif kl in _SAFE_KEYS:
                # Display / classification key — preserve as-is.
                out[k] = v
            else:
                out[k] = _redact_secret(v, _key=str(k))
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_secret(v, _key=_key) for v in value]
    return value


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

    # ── MCP Auth codes (Phase 3-C1, 2026-07-05) ─────────────────
    # Per ICODER_V1_MCP_SPEC §6.3 / §11.6 — 7 codes covering the
    # 4 auth types (none / bearer / inherit / oauth2.0).
    MCP_AUTH_DUPLICATE_NAME = -32006
    MCP_AUTH_MISSING_NAME = -32007
    MCP_AUTH_MISSING_TOKEN = -32008
    MCP_AUTH_MISSING_CREDENTIALS = -32009
    MCP_AUTH_INVALID_OAUTH_CONFIG = -32010
    MCP_AUTH_TOKEN_EXCHANGE_FAILED = -32011
    MCP_AUTH_FORBIDDEN = -32012

    # Reverse-lookup table — avoids the dir() scan in name().
    _NAMES: dict[int, str] = {
        PARSE_ERROR: "PARSE_ERROR",
        INVALID_REQUEST: "INVALID_REQUEST",
        METHOD_NOT_FOUND: "METHOD_NOT_FOUND",
        INVALID_PARAMS: "INVALID_PARAMS",
        INTERNAL_ERROR: "INTERNAL_ERROR",
        CATALOG_MISS: "CATALOG_MISS",
        RETRIEVER_UNAVAILABLE: "RETRIEVER_UNAVAILABLE",
        LLM_TIMEOUT: "LLM_TIMEOUT",
        PHI_REDACTION_FAILED: "PHI_REDACTION_FAILED",
        PRODUCTION_WRITEBACK_BLOCKED: "PRODUCTION_WRITEBACK_BLOCKED",
        MCP_AUTH_DUPLICATE_NAME: "MCP_AUTH_DUPLICATE_NAME",
        MCP_AUTH_MISSING_NAME: "MCP_AUTH_MISSING_NAME",
        MCP_AUTH_MISSING_TOKEN: "MCP_AUTH_MISSING_TOKEN",
        MCP_AUTH_MISSING_CREDENTIALS: "MCP_AUTH_MISSING_CREDENTIALS",
        MCP_AUTH_INVALID_OAUTH_CONFIG: "MCP_AUTH_INVALID_OAUTH_CONFIG",
        MCP_AUTH_TOKEN_EXCHANGE_FAILED: "MCP_AUTH_TOKEN_EXCHANGE_FAILED",
        MCP_AUTH_FORBIDDEN: "MCP_AUTH_FORBIDDEN",
    }

    # HTTP status mapping — used when the MCP error must propagate as
    # an HTTP response (e.g., the MCP HTTP transport).
    HTTP_STATUS: dict[int, int] = {
        PARSE_ERROR: 400,
        INVALID_REQUEST: 400,
        METHOD_NOT_FOUND: 404,
        INVALID_PARAMS: 400,
        INTERNAL_ERROR: 500,
        CATALOG_MISS: 500,
        RETRIEVER_UNAVAILABLE: 503,
        LLM_TIMEOUT: 504,
        PHI_REDACTION_FAILED: 500,
        PRODUCTION_WRITEBACK_BLOCKED: 403,
        MCP_AUTH_DUPLICATE_NAME: 400,
        MCP_AUTH_MISSING_NAME: 400,
        MCP_AUTH_MISSING_TOKEN: 401,
        MCP_AUTH_MISSING_CREDENTIALS: 401,
        MCP_AUTH_INVALID_OAUTH_CONFIG: 400,
        MCP_AUTH_TOKEN_EXCHANGE_FAILED: 401,
        MCP_AUTH_FORBIDDEN: 403,
    }

    @staticmethod
    def name(code: int) -> str:
        """Reverse lookup — code → human-readable name."""
        return MCPErrorCode._NAMES.get(code, f"CODE_{code}")

    @staticmethod
    def http_status(code: int) -> int:
        """Return the HTTP status code for a given MCP error code."""
        return MCPErrorCode.HTTP_STATUS.get(code, 500)

    @staticmethod
    def envelope(code: int, message: str, *, data: dict[str, Any] | None = None) -> dict:
        """Build a JSON-RPC 2.0 error envelope.

        Shape per spec:
          ``{"code": int, "message": str, "data"?: object}``

        If ``data`` is supplied, it is redacted via :func:`_redact_secret`
        before being attached — so any token / client_secret that
        accidentally lands in ``data.details`` is replaced with
        ``"<redacted>"``.
        """
        out: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            out["data"] = _redact_secret(data)
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


@dataclass
class MCPAuthError(MCPError):
    """MCP auth-specific error.

    Phase 3-C1 (2026-07-05) — 7 codes covering the 4 auth types
    (none / bearer / inherit / oauth2.0). See ICODER_V1_MCP_SPEC §6.3.

    The constructor scrubs ``data`` via :func:`_redact_secret` so
    raw tokens / client_secrets never leak into JSON-RPC error
    payloads. The ``redacted_view`` field (e.g., ``"Bearer ••••12"``)
    is the only auth-display value that survives redaction.
    """

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        redacted_view: str | None = None,
    ) -> None:
        safe_data = dict(data) if data else {}
        # Always attach redacted_view if provided — never the raw token.
        if redacted_view:
            safe_data["redacted_view"] = redacted_view
        # Scrub any accidentally-included secrets.
        safe_data = _redact_secret(safe_data)
        # Attach the symbolic mcp_error_code for client-side branching.
        safe_data.setdefault("mcp_error_code", MCPErrorCode.name(code))
        super().__init__(code=code, message=message, data=safe_data)


__all__ = [
    "MCPAuthError",
    "MCPError",
    "MCPErrorCode",
]