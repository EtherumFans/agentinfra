"""MCP Auth Resolver — Phase 3-C1 (2026-07-05).

Resolves an :class:`MCPAuthConfig` into an :class:`AuthHeader` ready
for an outbound MCP HTTP call. Per ICODER_V1_MCP_SPEC §11.6:

  - ``none``     → ``AuthHeader(kind="none")`` (no header injected)
  - ``bearer``   → resolve ``secret_ref`` via CredentialVault, return
                   ``AuthHeader(kind="bearer", token=<raw>)``
  - ``inherit``  → pull token from ``RunContext.auth_context.{source}``
  - ``oauth2.0`` → check in-memory cache; if miss or near-expiry, do
                   client_credentials grant via httpx, cache, return.

Cache safety:
  - Cache key = ``f"{token_url}|{client_id}|{scopes_hash}"`` — NO
    ``client_secret`` in the key. Verified by
    ``test_mcp_auth_cache_key_excludes_secret``.
  - Cache value = ``(access_token, expires_at)`` — in-memory only,
    process exit clears it.
  - Clock skew: a token is treated as expired if
    ``now + 60s >= expires_at`` so downstream services don't see a
    stale token due to drift.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

from app.icoder.mcp.auth import (
    AuthHeader,
    BearerAuthConfig,
    InheritAuthConfig,
    InheritSource,
    MCPAuthConfig,
    NoneAuthConfig,
    OAuth2AuthConfig,
    OAuth2ClientCredentialsConfig,
)
from app.icoder.mcp.errors import MCPAuthError, MCPErrorCode

logger = logging.getLogger(__name__)


# ── CredentialVault abstraction ─────────────────────────────────────────
#
# The real CredentialVault lives in app.services.credential_vault. To
# keep this module testable without importing the whole vault, we take
# a callable ``secret_resolver`` that takes a ``secret_ref`` and
# returns the secret string (or raises). The default resolver tries
# the real vault; tests inject a fake.

SecretResolver = Callable[[str], str]


def _default_secret_resolver(secret_ref: str) -> str:
    """Default resolver — delegates to app.services.credential_vault.

    Raises ``MCPAuthError`` (mcp_auth_missing_credentials) if the
    vault can't resolve the ref. The vault itself logs the resolution
    path; we don't repeat that here.
    """
    try:
        from app.services.credential_vault import vault
    except ImportError as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
            f"CredentialVault not available: {e}",
            data={"secret_ref": secret_ref},
        )
    try:
        return vault.resolve(secret_ref)
    except Exception as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
            f"Failed to resolve secret_ref {secret_ref!r}: {e}",
            data={"secret_ref": secret_ref},
        )


# ── RunContext (lightweight) ────────────────────────────────────────────


@dataclass
class RunAuthContext:
    """The auth context extracted from a RunContext.

    The MCP resolver checks the configured ``inherit_from`` source
    first, then walks down the priority chain (project > session >
    studio > runtime) as a fallback.
    """

    project: str = ""
    session: str = ""
    studio: str = ""
    runtime: str = ""


# ── OAuth2 token cache ──────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    access_token: str
    expires_at: float  # epoch seconds
    token_type: str = "Bearer"


def _scopes_hash(scopes: list[str]) -> str:
    """Stable hash of scopes — used in the cache key. Sorted so
    ``["a", "b"]`` and ``["b", "a"]`` produce the same hash."""
    if not scopes:
        return "none"
    h = hashlib.sha256(" ".join(sorted(scopes)).encode("utf-8")).hexdigest()[:16]
    return h


def _cache_key(cfg: OAuth2ClientCredentialsConfig, client_id: str) -> str:
    """Build the cache key. **MUST NOT** contain the client_secret
    or the raw access_token — only public identifiers.

    Verified by ``test_mcp_auth_cache_key_excludes_secret``.
    """
    return f"{cfg.token_url}|{client_id}|{_scopes_hash(cfg.scopes)}"


# Clock skew buffer — token treated as expired if now + 60s >= expires_at.
_CLOCK_SKEW_SECONDS = 60.0


# ── Resolver ────────────────────────────────────────────────────────────


async def resolve_mcp_auth(
    auth_config: MCPAuthConfig,
    *,
    context: RunAuthContext | None = None,
    secret_resolver: SecretResolver | None = None,
    http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    clock: Callable[[], float] = time.time,
) -> AuthHeader:
    """Resolve an MCPAuthConfig into an AuthHeader.

    Args:
        auth_config: One of NoneAuthConfig / BearerAuthConfig /
            InheritAuthConfig / OAuth2AuthConfig.
        context: The RunContext auth context (required for
            ``inherit`` type; ignored by others).
        secret_resolver: Optional override for CredentialVault
            (tests inject a fake).
        http_client_factory: Optional override for the httpx client
            used in oauth2.0 token exchange (tests inject a
            MockTransport-backed client).
        clock: Optional override for ``time.time`` (tests inject a
            fake to test expiry).

    Returns:
        AuthHeader — ``kind="none"`` for NoneAuthConfig, otherwise
        ``kind="bearer"`` with the resolved token.

    Raises:
        MCPAuthError: with the appropriate auth error code on
            resolution failure.
    """
    if isinstance(auth_config, NoneAuthConfig):
        return AuthHeader(
            kind="none",
            redacted_view=auth_config.redacted_view or "none",
        )

    if isinstance(auth_config, BearerAuthConfig):
        return _resolve_bearer(
            auth_config,
            secret_resolver=secret_resolver or _default_secret_resolver,
        )

    if isinstance(auth_config, InheritAuthConfig):
        return _resolve_inherit(auth_config, context=context)

    if isinstance(auth_config, OAuth2AuthConfig):
        return await _resolve_oauth2(
            auth_config.oauth,
            secret_resolver=secret_resolver or _default_secret_resolver,
            http_client_factory=http_client_factory,
            clock=clock,
        )

    # Should be unreachable — pydantic validation rejects unknown types
    # at parse time. Defensive guard.
    raise MCPAuthError(
        MCPErrorCode.MCP_AUTH_INVALID_OAUTH_CONFIG,
        f"Unknown auth config type: {type(auth_config).__name__}",
    )


# ── Bearer ──────────────────────────────────────────────────────────────


def _resolve_bearer(
    cfg: BearerAuthConfig,
    *,
    secret_resolver: SecretResolver,
) -> AuthHeader:
    """Resolve a static bearer token via CredentialVault."""
    try:
        token = secret_resolver(cfg.secret_ref)
    except MCPAuthError:
        raise
    except Exception as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
            f"Bearer secret_ref resolution failed: {e}",
            data={"secret_ref": cfg.secret_ref},
            redacted_view=cfg.redacted_view,
        )
    if not token:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_TOKEN,
            f"Bearer secret_ref resolved empty: {cfg.secret_ref!r}",
            data={"secret_ref": cfg.secret_ref},
            redacted_view=cfg.redacted_view,
        )
    return AuthHeader(
        kind="bearer",
        token=token,
        redacted_view=cfg.redacted_view or _default_bearer_redaction(token),
    )


def _default_bearer_redaction(token: str) -> str:
    """Build a default ``redacted_view`` from a raw token.

    Shows the last 4 chars only — enough for an operator to confirm
    which token was used without exposing the full value.
    """
    if len(token) <= 4:
        return "Bearer ••••"
    return f"Bearer ••••{token[-4:]}"


# ── Inherit ─────────────────────────────────────────────────────────────


_INHERIT_PRIORITY: tuple[InheritSource, ...] = (
    "project", "session", "studio", "runtime"
)


def _resolve_inherit(
    cfg: InheritAuthConfig,
    *,
    context: RunAuthContext | None,
) -> AuthHeader:
    """Inherit a bearer token from the RunContext."""
    ctx = context or RunAuthContext()
    # Try the configured source first.
    token = getattr(ctx, cfg.inherit_from, "") or ""
    if token:
        return AuthHeader(
            kind="bearer",
            token=token,
            redacted_view=cfg.redacted_view or _default_bearer_redaction(token),
        )
    # Fall back through the priority chain.
    for source in _INHERIT_PRIORITY:
        if source == cfg.inherit_from:
            continue
        token = getattr(ctx, source, "") or ""
        if token:
            logger.info(
                "MCP inherit auth: %s source empty, falling back to %s",
                cfg.inherit_from, source,
            )
            return AuthHeader(
                kind="bearer",
                token=token,
                redacted_view=cfg.redacted_view or _default_bearer_redaction(token),
            )
    raise MCPAuthError(
        MCPErrorCode.MCP_AUTH_MISSING_TOKEN,
        f"Inherit auth: no token in {cfg.inherit_from!r} or any fallback source",
        data={"inherit_from": cfg.inherit_from, "tried": list(_INHERIT_PRIORITY)},
        redacted_view=cfg.redacted_view,
    )


# ── OAuth2.0 client_credentials ─────────────────────────────────────────


# Module-level cache — keyed by (token_url, client_id, scopes_hash).
# Process-lifetime only; no disk persistence.
_OAUTH_TOKEN_CACHE: dict[str, _CacheEntry] = {}


def _clear_oauth_cache() -> None:
    """Test hook — wipe the cache between tests."""
    _OAUTH_TOKEN_CACHE.clear()


async def _resolve_oauth2(
    cfg: OAuth2ClientCredentialsConfig,
    *,
    secret_resolver: SecretResolver,
    http_client_factory: Callable[[], httpx.AsyncClient] | None,
    clock: Callable[[], float],
) -> AuthHeader:
    """Resolve an OAuth2.0 access token via client_credentials grant."""
    # Validate config minimally — pydantic already enforced field
    # presence / URL schemes, but check empty scopes list separately
    # for clearer error messaging.
    if not cfg.token_url or not cfg.client_id_ref or not cfg.client_secret_ref:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_INVALID_OAUTH_CONFIG,
            "oauth2.0 config missing required field",
            data={
                "has_token_url": bool(cfg.token_url),
                "has_client_id_ref": bool(cfg.client_id_ref),
                "has_client_secret_ref": bool(cfg.client_secret_ref),
            },
        )

    # Resolve client_id and client_secret via CredentialVault.
    try:
        client_id = secret_resolver(cfg.client_id_ref)
        client_secret = secret_resolver(cfg.client_secret_ref)
    except MCPAuthError:
        raise
    except Exception as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
            f"OAuth2.0 credential resolution failed: {e}",
            data={
                "client_id_ref": cfg.client_id_ref,
                "client_secret_ref": cfg.client_secret_ref,
            },
        )
    if not client_id or not client_secret:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
            "OAuth2.0 client_id / client_secret resolved empty",
            data={
                "client_id_ref": cfg.client_id_ref,
                "client_secret_ref": cfg.client_secret_ref,
            },
        )

    # Check cache.
    key = _cache_key(cfg, client_id)
    now = clock()
    cached = _OAUTH_TOKEN_CACHE.get(key)
    if cached is not None:
        # Treat as expired if now + 60s >= expires_at (clock skew).
        if now + _CLOCK_SKEW_SECONDS < cached.expires_at:
            return AuthHeader(
                kind="bearer",
                token=cached.access_token,
                redacted_view=_default_bearer_redaction(cached.access_token),
            )
        # else: fall through to refresh.

    # Exchange.
    token = await _do_oauth_exchange(
        cfg,
        client_id=client_id,
        client_secret=client_secret,
        http_client_factory=http_client_factory,
    )

    # Cache.
    expires_in = token.get("expires_in", cfg.cache_ttl_seconds)
    expires_at = now + float(expires_in)
    _OAUTH_TOKEN_CACHE[key] = _CacheEntry(
        access_token=token["access_token"],
        expires_at=expires_at,
        token_type=token.get("token_type", "Bearer"),
    )

    return AuthHeader(
        kind="bearer",
        token=token["access_token"],
        redacted_view=_default_bearer_redaction(token["access_token"]),
    )


async def _do_oauth_exchange(
    cfg: OAuth2ClientCredentialsConfig,
    *,
    client_id: str,
    client_secret: str,
    http_client_factory: Callable[[], httpx.AsyncClient] | None,
) -> dict:
    """POST to token_url with client_credentials grant.

    Returns the parsed JSON response (must contain ``access_token``
    and ``expires_in``). Raises ``MCPAuthError`` on any non-200 or
    JSON parse failure.
    """
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if cfg.scopes:
        data["scope"] = " ".join(cfg.scopes)
    if cfg.audience:
        data["audience"] = cfg.audience

    client_kwargs: dict[str, Any] = {"timeout": 30.0}
    if http_client_factory is not None:
        client = http_client_factory()
    else:
        client = httpx.AsyncClient(**client_kwargs)

    try:
        resp = await client.post(cfg.token_url, data=data)
    except httpx.HTTPError as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_TOKEN_EXCHANGE_FAILED,
            f"OAuth2.0 token exchange network error: {e}",
            data={"token_url": cfg.token_url},
        )
    finally:
        # Always close if we made the client. If the caller injected a
        # factory, they own the lifecycle — but closing is idempotent.
        try:
            await client.aclose()
        except Exception:
            pass

    if resp.status_code != 200:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_TOKEN_EXCHANGE_FAILED,
            f"OAuth2.0 token exchange failed: HTTP {resp.status_code}",
            data={
                "token_url": cfg.token_url,
                "status_code": resp.status_code,
                # Don't echo the response body — might contain hints.
            },
        )

    try:
        body = resp.json()
    except Exception as e:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_TOKEN_EXCHANGE_FAILED,
            f"OAuth2.0 token exchange returned non-JSON: {e}",
            data={"token_url": cfg.token_url},
        )

    if "access_token" not in body:
        raise MCPAuthError(
            MCPErrorCode.MCP_AUTH_TOKEN_EXCHANGE_FAILED,
            "OAuth2.0 token response missing access_token",
            data={"token_url": cfg.token_url, "keys": list(body.keys())},
        )

    return body


__all__ = [
    "RunAuthContext",
    "resolve_mcp_auth",
    "_clear_oauth_cache",
    "_cache_key",
    "_OAUTH_TOKEN_CACHE",
]
