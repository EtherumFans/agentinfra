"""MCP auth DataPart extractor — A1B-AE.5.

Corti public docs §9 (clean-room re-captured under A1B-AE.3 evidence)
defines the auth DataPart schema:

    {
      "kind": "data",
      "data": {
        "type": "token" | "credentials",   # case-insensitive; normalized
        "mcp_name": "crm-mcp",             # case-SENSITIVE; trimmed
        "token": "eyJhbGciOi...",          # required when type=token
        "client_id": "abc",                # required when type=credentials
        "client_secret": "def"             # required when type=credentials
      }
    }

Processing rules (Corti public §9 exhaustive):

1. ``type`` is normalized to lowercase; only ``token`` and ``credentials``
   are extracted. Unknown types are LEFT IN the message (not silently
   dropped; not fatal).
2. DataParts do NOT change the MCP server authorizationType — the
   DataPart type MUST match the server configuration.
3. ``mcp_name`` MUST be unique per message; duplicates return
   ``mcp_auth_duplicate_name``.
4. Missing fields return ``mcp_auth_missing_name`` /
   ``mcp_auth_missing_token`` / ``mcp_auth_missing_credentials``.
5. If ``mcp_name`` does not match any configured server, the DataPart
   is ignored.
6. MCP tools are registered when a new thread is created (the first
   message). Auth DataParts MUST be on that first message. Later
   messages on the same thread do NOT re-register tools.
7. In the API flow, extracted auth DataParts are REMOVED from the
   message before it is stored or sent to reasoning — defensive
   against accidental token logging.

This module is hermetic and side-effect-free: callers pass in a
list of parts and get back a tuple (extracted_auth, remaining_parts).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .errors import (
    A2AError,
    A2AErrorCode,
    mcp_auth_duplicate_name,
    mcp_auth_missing_credentials,
    mcp_auth_missing_name,
    mcp_auth_missing_token,
)


AuthType = Literal["token", "credentials"]


@dataclass
class ExtractedMcpAuth:
    """One extracted auth entry. ``raw_data`` is kept for debugging only."""

    mcp_name: str
    auth_type: AuthType
    token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of extracting auth DataParts from a message.

    ``remaining_parts`` is what should be persisted / sent to reasoning
    — auth DataParts are stripped per Corti public §9 rule 7.
    """

    auth_entries: list[ExtractedMcpAuth] = field(default_factory=list)
    remaining_parts: list[dict[str, Any]] = field(default_factory=list)
    ignored_unknown_type_count: int = 0


def _is_auth_datapart(part: dict[str, Any]) -> bool:
    """True iff ``part`` is shaped like an MCP auth DataPart.

    The check is conservative — the part must be kind=data, and the
    data dict must contain a ``type`` field with value 'token' or
    'credentials' (case-insensitive).
    """
    if part.get("kind") != "data":
        return False
    data = part.get("data") or {}
    if not isinstance(data, dict):
        return False
    type_value = data.get("type")
    if not isinstance(type_value, str):
        return False
    return type_value.lower() in ("token", "credentials")


def extract_mcp_auth(parts: list[dict[str, Any]]) -> ExtractionResult:
    """Extract + validate MCP auth DataParts.

    Raises :class:`A2AError` with one of the 4 ``mcp_auth_*`` codes on
    validation failure. Caller is expected to convert the A2AError to
    the wire envelope via ``error.to_envelope_error()``.

    Per Corti public §9 rule 7, extracted auth DataParts are NOT
    included in ``remaining_parts`` — caller should persist
    ``remaining_parts`` only.

    Unknown auth DataParts (type not in token/credentials) are LEFT
    IN ``remaining_parts`` per rule 1 — they are not silently dropped.
    """
    result = ExtractionResult()
    seen_names: set[str] = set()

    for part in parts:
        if not _is_auth_datapart(part):
            result.remaining_parts.append(part)
            continue

        data = part.get("data") or {}
        # mcp_name: required, case-sensitive, trimmed
        raw_name = data.get("mcp_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise mcp_auth_missing_name(
                details="auth DataPart missing 'mcp_name' field",
                spec_ref="https://docs.corti.ai/agentic/mcp-authentication",
            )
        mcp_name = raw_name.strip()
        if mcp_name in seen_names:
            raise mcp_auth_duplicate_name(name=mcp_name)
        seen_names.add(mcp_name)

        # type: normalized to lowercase
        type_norm = (data.get("type") or "").lower()

        if type_norm == "token":
            token = data.get("token")
            if not isinstance(token, str) or not token:
                raise mcp_auth_missing_token(name=mcp_name)
            result.auth_entries.append(
                ExtractedMcpAuth(
                    mcp_name=mcp_name,
                    auth_type="token",
                    token=token,
                    raw_data=dict(data),
                )
            )
        elif type_norm == "credentials":
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            if not isinstance(client_id, str) or not client_id:
                raise mcp_auth_missing_credentials(name=mcp_name)
            if not isinstance(client_secret, str) or not client_secret:
                raise mcp_auth_missing_credentials(name=mcp_name)
            result.auth_entries.append(
                ExtractedMcpAuth(
                    mcp_name=mcp_name,
                    auth_type="credentials",
                    client_id=client_id,
                    client_secret=client_secret,
                    raw_data=dict(data),
                )
            )
        else:
            # Unknown auth type — leave in remaining_parts per rule 1.
            # This branch should be unreachable given _is_auth_datapart's
            # conservative filter, but defensive.
            result.remaining_parts.append(part)
            result.ignored_unknown_type_count += 1

    return result


__all__ = [
    "AuthType",
    "ExtractedMcpAuth",
    "ExtractionResult",
    "extract_mcp_auth",
]
