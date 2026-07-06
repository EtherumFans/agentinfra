"""Phase 3-C1 — MCP Auth 11-test matrix.

Per ICODER_V1_MCP_SPEC §11.6 (2026-07-05), 11 cases cover the 4 auth types
(none / bearer / inherit / oauth2.0) + cache safety + redaction + forbidden:

  1. none type → no Authorization header
  2. bearer resolves via CredentialVault → ``Authorization: Bearer <token>``
  3. bearer missing secret_ref → ``mcp_auth_missing_credentials``
  4. inherit from project context
  5. oauth2.0 happy path: exchange → cache (single httpx call)
  6. oauth2.0 expires → refresh (clock skew -60s)
  7. oauth2.0 invalid config → ``mcp_auth_invalid_oauth_config``
  8. oauth2.0 exchange failure (4xx) → ``mcp_auth_token_exchange_failed``
  9. cache key excludes ``client_secret``
  10. redacted_view is the only auth-display value in logs / errors
  11. forbidden on insufficient scope → ``mcp_auth_forbidden``

Cache safety is enforced by ``_cache_key()`` returning
``f"{token_url}|{client_id}|{scopes_hash}"`` — NO ``client_secret`` in the
key (verified by case 9). ``redacted_view`` is the only auth-display
value that survives redaction (case 10).

Clock skew: a token is treated as expired if ``now + 60s >= expires_at``
(case 6).
"""

from __future__ import annotations

import asyncio
import httpx
import pytest
from pydantic import ValidationError

from app.icoder.mcp.auth import (
    BearerAuthConfig,
    InheritAuthConfig,
    NoneAuthConfig,
    OAuth2AuthConfig,
    OAuth2ClientCredentialsConfig,
    parse_mcp_auth_config,
)
from app.icoder.mcp.auth_resolver import (
    RunAuthContext,
    _cache_key,
    _clear_oauth_cache,
    resolve_mcp_auth,
)
from app.icoder.mcp.errors import MCPAuthError, MCPErrorCode


# ── Fixtures ─────────────────────────────────────────────────────────────


def _fake_vault():
    """A CredentialVault fake mapping secret_refs → raw secrets.

    Mirrors the real ``app.services.credential_vault.vault.resolve`` contract
    — raises ``KeyError`` for unknown refs. ``_resolve_bearer`` and
    ``_resolve_oauth2`` wrap generic exceptions into ``MCPAuthError``.
    """
    table = {
        "secret://mcp/provider-a/token": "tok-abc123",
        "secret://mcp/oauth/client_id": "cid-xyz",
        "secret://mcp/oauth/client_secret": "sec-789",
    }

    def resolve(secret_ref: str) -> str:
        if secret_ref not in table:
            raise KeyError(secret_ref)
        return table[secret_ref]

    return resolve


def _make_oauth_cfg() -> OAuth2ClientCredentialsConfig:
    return OAuth2ClientCredentialsConfig(
        token_url="https://oauth.example.com/token",
        client_id_ref="secret://mcp/oauth/client_id",
        client_secret_ref="secret://mcp/oauth/client_secret",
        scopes=["read"],
        cache_ttl_seconds=3600,
    )


class _CountingTransport:
    """httpx MockTransport that counts calls + returns a fresh access_token
    each invocation so we can assert cache hit vs refresh.
    """

    def __init__(self, *, status_code: int = 200, expires_in: int = 3600):
        self.calls = 0
        self._status_code = status_code
        self._expires_in = expires_in

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self._status_code != 200:
            return httpx.Response(
                self._status_code,
                content=b'{"error": "invalid_client"}',
                headers={"content-type": "application/json"},
            )
        body = (
            b'{"access_token": "tok-'
            + str(self.calls).encode()
            + b'", "expires_in": '
            + str(self._expires_in).encode()
            + b', "token_type": "Bearer"}'
        )
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "application/json"},
        )


def _client_factory(transport: _CountingTransport):
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(transport))

    return factory


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """Wipe the module-level OAuth2 cache before + after each test."""
    _clear_oauth_cache()
    yield
    _clear_oauth_cache()


# ── 1. none type ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_none_type_no_header():
    """none type → ``AuthHeader(kind="none")`` → ``to_header() is None``."""
    h = await resolve_mcp_auth(NoneAuthConfig(), secret_resolver=_fake_vault())
    assert h.kind == "none"
    assert h.to_header() is None


# ── 2. bearer resolves ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_bearer_resolves_secret_ref():
    """bearer: vault lookup → ``Authorization: Bearer <token>``."""
    h = await resolve_mcp_auth(
        BearerAuthConfig(secret_ref="secret://mcp/provider-a/token"),
        secret_resolver=_fake_vault(),
    )
    assert h.kind == "bearer"
    assert h.token == "tok-abc123"
    assert h.to_header() == "Bearer tok-abc123"


# ── 3. bearer missing ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_bearer_missing_secret_ref_raises():
    """Bearer secret_ref not in vault → ``mcp_auth_missing_credentials``
    (per spec §6.3 — wraps the underlying vault failure into an auth error
    so clients can distinguish "config was wrong" from "token exchange
    failed").
    """
    with pytest.raises(MCPAuthError) as ei:
        await resolve_mcp_auth(
            BearerAuthConfig(secret_ref="secret://mcp/missing"),
            secret_resolver=_fake_vault(),
        )
    assert ei.value.code == MCPErrorCode.MCP_AUTH_MISSING_CREDENTIALS
    # Redacted view should be empty (no token was resolved).
    assert "raw_token" not in (ei.value.data or {})


# ── 4. inherit from project context ──────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_inherit_from_project_context():
    """inherit: pull token from ``RunAuthContext.project``."""
    ctx = RunAuthContext(project="proj-token-xyz", session="", studio="", runtime="")
    h = await resolve_mcp_auth(
        InheritAuthConfig(inherit_from="project"),
        context=ctx,
    )
    assert h.kind == "bearer"
    assert h.token == "proj-token-xyz"
    assert h.to_header() == "Bearer proj-token-xyz"


@pytest.mark.asyncio
async def test_mcp_auth_inherit_falls_back_through_priority_chain():
    """inherit: configured source empty → fall back to session → studio → runtime."""
    ctx = RunAuthContext(project="", session="sess-token-abc", studio="", runtime="")
    h = await resolve_mcp_auth(
        InheritAuthConfig(inherit_from="project"),
        context=ctx,
    )
    assert h.token == "sess-token-abc"


@pytest.mark.asyncio
async def test_mcp_auth_inherit_all_sources_empty_raises():
    """inherit: no token anywhere in the priority chain → ``mcp_auth_missing_token``."""
    with pytest.raises(MCPAuthError) as ei:
        await resolve_mcp_auth(
            InheritAuthConfig(inherit_from="project"),
            context=RunAuthContext(),
        )
    assert ei.value.code == MCPErrorCode.MCP_AUTH_MISSING_TOKEN


# ── 5. oauth2.0 happy + cache ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_oauth2_exchanges_then_caches():
    """First call exchanges; second call hits cache → httpx called once."""
    transport = _CountingTransport()
    cfg = _make_oauth_cfg()
    h1 = await resolve_mcp_auth(
        OAuth2AuthConfig(oauth=cfg),
        secret_resolver=_fake_vault(),
        http_client_factory=_client_factory(transport),
    )
    h2 = await resolve_mcp_auth(
        OAuth2AuthConfig(oauth=cfg),
        secret_resolver=_fake_vault(),
        http_client_factory=_client_factory(transport),
    )
    assert h1.token == h2.token == "tok-1"
    assert transport.calls == 1, f"expected 1 exchange, got {transport.calls}"


# ── 6. oauth2.0 expires + refresh ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_oauth2_expires_then_refreshes():
    """Token expires; clock-skew -60s window triggers refresh on next call.

    Token issued at t=1000, expires_in=3600 → expires_at=4600.
    Resolver treats as expired if ``now + 60 >= expires_at`` → refresh
    triggers at ``now >= 4540``.
    """
    transport = _CountingTransport()
    cfg = _make_oauth_cfg()
    fake_time = [1000.0]

    def clock() -> float:
        return fake_time[0]

    h1 = await resolve_mcp_auth(
        OAuth2AuthConfig(oauth=cfg),
        secret_resolver=_fake_vault(),
        http_client_factory=_client_factory(transport),
        clock=clock,
    )
    assert h1.token == "tok-1"
    assert transport.calls == 1

    # Move clock past the skew buffer (now=4541 → 4541+60 >= 4600).
    fake_time[0] = 4541.0
    h2 = await resolve_mcp_auth(
        OAuth2AuthConfig(oauth=cfg),
        secret_resolver=_fake_vault(),
        http_client_factory=_client_factory(transport),
        clock=clock,
    )
    assert h2.token == "tok-2"
    assert transport.calls == 2


# ── 7. oauth2.0 invalid config ───────────────────────────────────────────


def test_mcp_auth_oauth2_invalid_config_raises():
    """Pydantic rejects empty ``client_id_ref`` / ``client_secret_ref`` /
    non-http ``token_url`` at construction — caller surfaces as
    ``mcp_auth_invalid_oauth_config`` (per spec §6.3).
    """
    with pytest.raises(ValidationError):
        OAuth2ClientCredentialsConfig(
            token_url="https://oauth.example.com/token",
            client_id_ref="",
            client_secret_ref="",
        )
    with pytest.raises(ValidationError):
        OAuth2ClientCredentialsConfig(
            token_url="not-a-url",
            client_id_ref="secret://mcp/oauth/client_id",
            client_secret_ref="secret://mcp/oauth/client_secret",
        )


def test_mcp_auth_parse_mcp_auth_config_rejects_unknown_type():
    """``parse_mcp_auth_config`` rejects unknown ``type`` field."""
    with pytest.raises(ValueError):
        parse_mcp_auth_config({"type": "kerberos"})


# ── 8. oauth2.0 exchange failure ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_oauth2_exchange_failure_raises():
    """Token endpoint returns 401 → ``mcp_auth_token_exchange_failed``."""
    transport = _CountingTransport(status_code=401)
    cfg = _make_oauth_cfg()
    with pytest.raises(MCPAuthError) as ei:
        await resolve_mcp_auth(
            OAuth2AuthConfig(oauth=cfg),
            secret_resolver=_fake_vault(),
            http_client_factory=_client_factory(transport),
        )
    assert ei.value.code == MCPErrorCode.MCP_AUTH_TOKEN_EXCHANGE_FAILED
    # Response body must not leak into the error data.
    assert "invalid_client" not in str(ei.value.data)


# ── 9. cache key excludes secret ─────────────────────────────────────────


def test_mcp_auth_cache_key_excludes_secret():
    """Cache key contains ``token_url`` + ``client_id`` + ``scopes_hash`` —
    **MUST NOT** contain ``client_secret``.

    This is the headline cache-safety invariant: if the secret leaked into
    the key, it would be visible in any cache dump / debug log.
    """
    cfg = _make_oauth_cfg()
    key = _cache_key(cfg, "cid-xyz")
    assert "sec-789" not in key, f"client_secret leaked into cache key: {key}"
    assert "cid-xyz" in key
    assert "oauth.example.com/token" in key


def test_mcp_auth_cache_key_stable_under_scope_reordering():
    """``["a", "b"]`` and ``["b", "a"]`` produce the same cache key."""
    cfg_a = OAuth2ClientCredentialsConfig(
        token_url="https://oauth.example.com/token",
        client_id_ref="secret://mcp/oauth/client_id",
        client_secret_ref="secret://mcp/oauth/client_secret",
        scopes=["a", "b"],
    )
    cfg_b = OAuth2ClientCredentialsConfig(
        token_url="https://oauth.example.com/token",
        client_id_ref="secret://mcp/oauth/client_id",
        client_secret_ref="secret://mcp/oauth/client_secret",
        scopes=["b", "a"],
    )
    assert _cache_key(cfg_a, "cid") == _cache_key(cfg_b, "cid")


# ── 10. redacted_view in logs / errors ───────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_auth_redacted_view_in_logs():
    """``redacted_view`` is the only auth-display value that survives
    redaction. Raw token never appears in ``MCPAuthError.data`` or
    ``MCPErrorCode.envelope()`` output.
    """
    h = await resolve_mcp_auth(
        BearerAuthConfig(secret_ref="secret://mcp/provider-a/token"),
        secret_resolver=_fake_vault(),
    )
    # redacted_view is non-empty + doesn't contain the raw token.
    assert h.redacted_view
    assert "tok-abc123" not in h.redacted_view

    # Construct an MCPAuthError that accidentally includes the raw token in
    # ``data`` — verify the redactor scrubs it.
    err = MCPAuthError(
        code=MCPErrorCode.MCP_AUTH_MISSING_TOKEN,
        message="simulate accidental leak",
        data={
            "secret_ref": "secret://mcp/provider-a/token",
            "token": "tok-abc123",
            "details": "Bearer tok-abc123 used here",
        },
        redacted_view=h.redacted_view,
    )
    env = err.to_envelope()
    assert env["data"]["token"] == "<redacted>"
    assert "tok-abc123" not in str(env)
    # redacted_view survives.
    assert env["data"]["redacted_view"] == h.redacted_view
    # mcp_error_code symbolic name survives (it's a classification string,
    # not a secret).
    assert env["data"]["mcp_error_code"] == "MCP_AUTH_MISSING_TOKEN"


def test_mcp_auth_redaction_doesnt_clobber_symbolic_constants():
    """Symbolic constants like ``MCP_AUTH_FORBIDDEN`` look like 16+ char
    alphanumeric runs but are classification strings, not secrets — they
    must survive redaction.
    """
    err = MCPAuthError(
        code=MCPErrorCode.MCP_AUTH_FORBIDDEN,
        message="test",
        data={"reason": "MCP_AUTH_FORBIDDEN scope mismatch"},
    )
    env = err.to_envelope()
    assert env["data"]["reason"] == "MCP_AUTH_FORBIDDEN scope mismatch"


# ── 11. forbidden on insufficient scope ──────────────────────────────────


def test_mcp_auth_forbidden_on_insufficient_scope():
    """Token valid but scope mismatch → caller raises ``mcp_auth_forbidden``
    (HTTP 403, retryable=False per spec §6.3).

    The resolver itself doesn't enforce scope — that's the MCP server's
    job after the call lands. Here we verify the error code exists + has
    the right HTTP status + redaction behavior.
    """
    err = MCPAuthError(
        code=MCPErrorCode.MCP_AUTH_FORBIDDEN,
        message="token missing required scope: codable:write",
        data={
            "required_scope": "codable:write",
            "presented_scopes": ["codable:read"],
        },
    )
    assert err.code == MCPErrorCode.MCP_AUTH_FORBIDDEN
    assert MCPErrorCode.http_status(err.code) == 403
    assert MCPErrorCode.name(err.code) == "MCP_AUTH_FORBIDDEN"
    # data survives (no secrets in this case).
    env = err.to_envelope()
    assert env["data"]["required_scope"] == "codable:write"
    assert env["data"]["presented_scopes"] == ["codable:read"]
    assert env["data"]["mcp_error_code"] == "MCP_AUTH_FORBIDDEN"


# ── Bonus: error code catalog completeness ───────────────────────────────


def test_mcp_auth_error_catalog_complete():
    """All 7 MCP auth codes (-32006..-32012) are registered with name + HTTP
    status mapping. This is the contract spec §6.3 promises to clients.
    """
    expected = {
        -32006: ("MCP_AUTH_DUPLICATE_NAME", 400),
        -32007: ("MCP_AUTH_MISSING_NAME", 400),
        -32008: ("MCP_AUTH_MISSING_TOKEN", 401),
        -32009: ("MCP_AUTH_MISSING_CREDENTIALS", 401),
        -32010: ("MCP_AUTH_INVALID_OAUTH_CONFIG", 400),
        -32011: ("MCP_AUTH_TOKEN_EXCHANGE_FAILED", 401),
        -32012: ("MCP_AUTH_FORBIDDEN", 403),
    }
    for code, (name, http) in expected.items():
        assert MCPErrorCode.name(code) == name, f"{code} → {MCPErrorCode.name(code)}"
        assert MCPErrorCode.http_status(code) == http, f"{code} → {MCPErrorCode.http_status(code)}"
