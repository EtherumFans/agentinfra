"""MCP Auth — Phase 3-C1 (2026-07-05).

Implements the 4 MCP 2025-03-26 auth types per ICODER_V1_MCP_SPEC §11.6:

  - ``none``     — internal stub tools, no Authorization header
  - ``bearer``   — static token via ``secret_ref`` (CredentialVault)
  - ``inherit``  — inherit auth from project / session / studio / runtime context
  - ``oauth2.0`` — OAuth2.0 client_credentials grant with token cache + refresh

The token resolution lives in :mod:`app.icoder.mcp.auth_resolver`
(B3) so the config schema (B2) is independently testable.

Redaction contract: ``redacted_view`` is the only field that may
appear in logs / error payloads. Raw ``token`` / ``client_secret``
never leave the resolver.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field, ValidationError, field_validator


# ── Auth types ──────────────────────────────────────────────────────────


AuthType = Literal["none", "bearer", "inherit", "oauth2.0"]
InheritSource = Literal["project", "session", "studio", "runtime"]


class NoneAuthConfig(BaseModel):
    """No auth — internal stub tools (search_icd / verify_code / etc.)."""

    type: Literal["none"] = "none"
    redacted_view: str | None = None


class BearerAuthConfig(BaseModel):
    """Static bearer token resolved via CredentialVault.

    ``secret_ref`` is a ``secret://mcp/{provider}/{key}`` URL — the
    resolver fetches the raw token from CredentialVault at runtime.
    The raw token never appears in logs; ``redacted_view`` (e.g.
    ``"Bearer ••••1234"``) is the only thing logged.
    """

    type: Literal["bearer"] = "bearer"
    secret_ref: str
    redacted_view: str | None = None

    @field_validator("secret_ref")
    @classmethod
    def _validate_secret_ref(cls, v: str) -> str:
        if not v or not v.startswith("secret://"):
            raise ValueError(
                "bearer.secret_ref must start with 'secret://' "
                "(see CredentialVault)"
            )
        return v


class InheritAuthConfig(BaseModel):
    """Inherit auth from a higher-level context.

    The resolver pulls the bearer token from
    ``RunContext.auth_context.{source}`` where ``source`` is one of
    ``project`` / ``session`` / ``studio`` / ``runtime``. This lets
    an MCP tool call ride on the parent's auth without re-exchanging.
    """

    type: Literal["inherit"] = "inherit"
    inherit_from: InheritSource
    redacted_view: str | None = None


class OAuth2ClientCredentialsConfig(BaseModel):
    """OAuth2.0 client_credentials grant configuration.

    Token lifecycle:
      1. Check in-memory cache (key = ``provider_url + client_id +
         scopes_hash`` — NO secret in the key).
      2. If cache miss or within 60s of expiry, POST
         ``{token_url}`` with ``grant_type=client_credentials``,
         ``client_id``, ``client_secret``, ``scope`` (space-joined),
         optional ``audience``.
      3. Cache the response (``access_token`` + ``expires_at``).
      4. Return ``Authorization: Bearer <access_token>``.

    Clock skew: the resolver treats a token as expired if
    ``now + 60s >= expires_at`` so downstream services don't see a
    stale token due to clock drift.
    """

    token_url: str
    client_id_ref: str = Field(
        ..., description="secret_ref for client_id (secret://mcp/.../client_id)"
    )
    client_secret_ref: str = Field(
        ..., description="secret_ref for client_secret (secret://mcp/.../client_secret)"
    )
    scopes: list[str] = Field(default_factory=list)
    audience: str | None = None
    cache_ttl_seconds: int = 3600

    @field_validator("token_url")
    @classmethod
    def _validate_token_url(cls, v: str) -> str:
        if not v or not v.startswith(("http://", "https://")):
            raise ValueError(
                "oauth2.0.token_url must be a http(s):// URL"
            )
        return v

    @field_validator("client_id_ref", "client_secret_ref")
    @classmethod
    def _validate_secret_refs(cls, v: str) -> str:
        if not v or not v.startswith("secret://"):
            raise ValueError(
                "oauth2.0 secret_ref must start with 'secret://'"
            )
        return v


class OAuth2AuthConfig(BaseModel):
    """OAuth2.0 wrapper — carries the grant config + display metadata."""

    type: Literal["oauth2.0"] = "oauth2.0"
    oauth: OAuth2ClientCredentialsConfig
    redacted_view: str | None = None


# Discriminated union — `type` field selects the variant.
MCPAuthConfig = Union[
    NoneAuthConfig,
    BearerAuthConfig,
    InheritAuthConfig,
    OAuth2AuthConfig,
]


# ── Resolved auth header ────────────────────────────────────────────────


class AuthHeader:
    """Resolved auth header — what the MCP client injects into the
    outbound HTTP request to the MCP server.

    ``kind="none"`` → no Authorization header (internal stub tools).
    ``kind="bearer"`` → ``Authorization: Bearer <token>``.

    The raw ``token`` is held here ONLY in-memory, in the calling
    thread, for the duration of a single MCP tool call. It is never
    logged, never serialized to JSON, never written to disk.
    """

    __slots__ = ("kind", "token", "redacted_view")

    def __init__(
        self,
        *,
        kind: Literal["none", "bearer"],
        token: str = "",
        redacted_view: str = "",
    ) -> None:
        self.kind = kind
        self.token = token
        self.redacted_view = redacted_view

    def to_header(self) -> str | None:
        """Return the HTTP Authorization header value, or None for
        ``kind="none"``.
        """
        if self.kind == "none":
            return None
        return f"Bearer {self.token}"

    def __repr__(self) -> str:
        return f"AuthHeader(kind={self.kind!r}, redacted_view={self.redacted_view!r})"


# ── Config factory ──────────────────────────────────────────────────────


def parse_mcp_auth_config(raw: dict) -> MCPAuthConfig:
    """Parse a raw dict into the discriminated MCPAuthConfig union.

    Raises ``ValidationError`` if ``type`` is missing or unknown, or
    if required fields for the variant are absent. The caller should
    catch ``ValidationError`` and surface it as
    ``mcp_auth_invalid_oauth_config`` (wire code -32010) for oauth2.0
    configs, or ``INVALID_PARAMS`` (-32602) for other variants.
    """
    if not isinstance(raw, dict) or "type" not in raw:
        raise ValueError("MCP auth config must be a dict with a 'type' field")
    t = raw["type"]
    if t == "none":
        return NoneAuthConfig.model_validate(raw)
    if t == "bearer":
        return BearerAuthConfig.model_validate(raw)
    if t == "inherit":
        return InheritAuthConfig.model_validate(raw)
    if t == "oauth2.0":
        return OAuth2AuthConfig.model_validate(raw)
    raise ValueError(f"Unknown MCP auth type: {t!r}")


__all__ = [
    "AuthHeader",
    "AuthType",
    "BearerAuthConfig",
    "InheritAuthConfig",
    "InheritSource",
    "MCPAuthConfig",
    "NoneAuthConfig",
    "OAuth2AuthConfig",
    "OAuth2ClientCredentialsConfig",
    "parse_mcp_auth_config",
]
