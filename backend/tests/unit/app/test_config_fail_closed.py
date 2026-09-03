"""A1A Gate 1 Step 4 — Fail-closed env policy tests.

Validates that Settings() refuses to boot in cloud mode when required
secrets are missing or carry known-weak defaults. Local mode remains
permissive.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


def test_phase1_stub_switch_is_ignored_outside_pytest_module(monkeypatch) -> None:
    import sys

    from app.main import _test_fail_closed_a2a_mode_enabled

    monkeypatch.setenv("ICODER_PHASE1_STUB_LLM", "1")
    pytest_module = sys.modules.pop("pytest", None)
    try:
        assert _test_fail_closed_a2a_mode_enabled() is False
    finally:
        if pytest_module is not None:
            sys.modules["pytest"] = pytest_module

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _reload_settings(monkeypatch, env_overrides: dict[str, str]):
    """Build an isolated Settings object with the given env overrides.

    Reloading ``app.config`` replaces its process-global ``settings`` while
    already imported modules retain the old instance.  That makes later tests
    order-dependent, so exercise the same boot policy without mutating global
    application configuration.
    """
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)
    import app.config
    return SimpleNamespace(settings=app.config.Settings())


def _clear_env(monkeypatch, keys: list[str]):
    for k in keys:
        monkeypatch.delenv(k, raising=False)


CLOUD_KEYS = [
    "ICODER_DEPLOYMENT_MODE",
    "ICODER_SECRET_KEY",
    "ICODER_HOSTED_URL",
    "ICODER_ENVIRONMENT",
    "ICODER_REGION",
    "ICODER_TENANT_ID",
    "ICODER_API_CLIENT_ID",
    "ICODER_API_CLIENT_SECRET",
    "ICODER_METRICS_BEARER_TOKEN",
    "SEED_ON_STARTUP",
    "DEBUG",
    "ICODER_DATABASE_SQL_ECHO",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "ICODER_PHI_REDACTION_MODE",
    "ICODER_AUDIT_SINK",
    "ICODER_SINGLE_TENANT_ORG_ID",
    "ICODER_ASSET_BUCKET",
    "ICODER_CREDENTIAL_LLM",
    "LLM_PROVIDER",
    "APP_ENV",
    "ICODER_STREAM_MEDIA_VALIDATION_MODE",
    "ICODER_STREAM_MEDIA_DECODER_PATH",
    "ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS",
    "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY",
    "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS",
    "OAUTH_REQUIRE_TENANT_HEADER",
    "MEDCODER_RETRIEVER_URL",
    "MEDCODER_RETRIEVER_TOKEN",
    "MEDCODER_RETRIEVER_ALLOW_HTTP",
    "MEDCODER_RETRIEVER_TIMEOUT_SECONDS",
    "ICODER_MEMORY_SEMANTIC_URL",
    "ICODER_CREDENTIAL_MEMORY_SEMANTIC",
    "ICODER_MEMORY_SEMANTIC_REQUIRED",
    "ICODER_RUN_HISTORY_TTL_DAYS",
    "ICODER_RUN_TRACE_EVENTS_TTL_DAYS",
    "ICODER_INVITE_DELIVERY_MODE",
    "ICODER_INVITE_WEBHOOK_URL",
    "ICODER_INVITE_WEBHOOK_BEARER_TOKEN",
    "ICODER_INVITE_ALLOWED_EMAIL_DOMAINS",
    "ICODER_INVITE_MAX_ATTEMPTS",
    "ICODER_INVITE_RETRY_BASE_SECONDS",
    "ICODER_INVITE_CLAIM_TIMEOUT_SECONDS",
    "ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS",
    "ICODER_CONNECTOR_EGRESS_ALLOWLIST",
    "ICODER_CONNECTOR_ALLOW_PHI",
    "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST",
    "ICODER_NCBI_CONTACT_EMAIL",
]


def _valid_cloud_env() -> dict[str, str]:
    return {
        "ICODER_DEPLOYMENT_MODE": "cloud",
        "ICODER_SECRET_KEY": "strong-key-for-test-only-not-real-48-chars-abc",
        "ICODER_HOSTED_URL": "https://api.icoder.cloud",
        "ICODER_ENVIRONMENT": "cn",
        "ICODER_REGION": "cn-hangzhou",
        "ICODER_TENANT_ID": "tenant-test-001",
        "ICODER_API_CLIENT_ID": "client-test-001",
        "ICODER_API_CLIENT_SECRET": "secret-test-001-not-real",
        "ICODER_METRICS_BEARER_TOKEN": "test-metrics-token-at-least-32-characters",
        "SEED_ON_STARTUP": "false",
        "DEBUG": "false",
        "ICODER_DATABASE_SQL_ECHO": "false",
        "JWT_ISSUER": "https://auth.icoder.cloud",
        "JWT_AUDIENCE": "https://api.icoder.cloud",
        # Phase A1D.5 — Gate 4 added ICODER_PHI_ENCRYPTION_KEY as a
        # cloud-mode requirement (Fernet envelope for at-rest PHI).
        # Gate 3R added RUNTRACE_DEPLOYMENT_PROFILE=BEST_EFFORT_DB as a
        # cloud-mode requirement (memory store loses trace on restart).
        "ICODER_PHI_ENCRYPTION_KEY": "3PARkxUUNU68P58uuahocRIqiSHbx7ACY_JHkaKt3v4=",  # test-only Fernet key
        "RUNTRACE_DEPLOYMENT_PROFILE": "BEST_EFFORT_DB",
        "DATABASE_URL": "postgresql+asyncpg://test:test@db:5432/icoder",
        "CORS_ORIGINS": '["https://app.icoder.cloud"]',
        "ICODER_PHI_REDACTION_MODE": "edge",
        "ICODER_AUDIT_SINK": "cloud_audit",
        "ICODER_SINGLE_TENANT_ORG_ID": "",
        "ICODER_ASSET_BUCKET": "icoder-assets-cn-hangzhou",
        "ICODER_CREDENTIAL_LLM": "kms-test-credential-not-real",
        "LLM_PROVIDER": "deepseek",
        "APP_ENV": "cloud",
        "OAUTH_REQUIRE_TENANT_HEADER": "true",
        "MEDCODER_RETRIEVER_URL": "https://medcoder.internal",
        "MEDCODER_RETRIEVER_TOKEN": "test-medcoder-service-token-32-characters",
        "MEDCODER_RETRIEVER_ALLOW_HTTP": "false",
        "MEDCODER_RETRIEVER_TIMEOUT_SECONDS": "15",
        "ICODER_MEMORY_SEMANTIC_URL": "https://memory.internal/v1/embed",
        "ICODER_CREDENTIAL_MEMORY_SEMANTIC": (
            "test-memory-semantic-token-32-characters"
        ),
        "ICODER_MEMORY_SEMANTIC_REQUIRED": "true",
        "ICODER_CONNECTOR_EGRESS_ALLOWLIST": "memory.internal",
        "ICODER_INVITE_DELIVERY_MODE": "webhook",
        "ICODER_INVITE_WEBHOOK_URL": "https://notification.internal/invitations",
        "ICODER_INVITE_WEBHOOK_BEARER_TOKEN": "test-invite-webhook-token-32-characters",
        "ICODER_INVITE_ALLOWED_EMAIL_DOMAINS": '["hospital.example.cn"]',
    }


def test_local_mode_boots_with_empty_secret(monkeypatch):
    """Local mode auto-generates a random SECRET_KEY — must not raise."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    cfg = _reload_settings(monkeypatch, {})
    assert cfg.settings.ICODER_DEPLOYMENT_MODE == "local"
    assert len(cfg.settings.SECRET_KEY) > 0


def test_cloud_mode_boots_with_all_required_vars(monkeypatch):
    """Cloud mode with all required vars set — must not raise."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    cfg = _reload_settings(monkeypatch, _valid_cloud_env())
    assert cfg.settings.ICODER_DEPLOYMENT_MODE == "cloud"
    assert cfg.settings.ICODER_ENVIRONMENT == "cn"


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("JWT_ISSUER", "", "JWT_ISSUER"),
        ("JWT_AUDIENCE", "", "JWT_AUDIENCE"),
        ("JWT_AUDIENCE", "https://auth.icoder.cloud", "must be distinct"),
    ],
)
def test_cloud_mode_requires_distinct_jwt_trust_boundary(
    monkeypatch, key, value, message,
) -> None:
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        (
            "ICODER_STREAM_MEDIA_VALIDATION_MODE",
            "header_only",
            "VALIDATION_MODE=decoder",
        ),
        ("ICODER_STREAM_MEDIA_DECODER_PATH", "", "DECODER_PATH"),
        ("ICODER_STREAM_MEDIA_DECODER_PATH", "ffmpeg\nunsafe", "DECODER_PATH"),
        ("ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS", "0.1", "TIMEOUT_SECONDS"),
        ("ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS", "11", "TIMEOUT_SECONDS"),
        ("ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY", "0", "MAX_CONCURRENCY"),
        ("ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY", "17", "MAX_CONCURRENCY"),
        ("ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS", "0.01", "QUEUE_TIMEOUT"),
        ("ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS", "6", "QUEUE_TIMEOUT"),
    ],
)
def test_cloud_mode_requires_bounded_stream_media_decoder(
    monkeypatch,
    key,
    value,
    message,
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"ICODER_CONNECTOR_ALLOW_PHI": "true"},
            "requires a non-empty",
        ),
        (
            {
                "ICODER_CONNECTOR_EGRESS_ALLOWLIST": "api.example.cn",
                "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST": "phi.example.cn",
            },
            "must be a subset",
        ),
        (
            {"ICODER_CONNECTOR_EGRESS_ALLOWLIST": "*.example.cn"},
            "exact ASCII hostnames",
        ),
        (
            {"ICODER_NCBI_CONTACT_EMAIL": "not-an-operational-email"},
            "valid operational email",
        ),
    ],
)
def test_cloud_mode_refuses_unsafe_connector_egress(
    monkeypatch, overrides, message,
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env.update(overrides)
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_rejects_trace_retention_longer_than_run_history(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_RUN_HISTORY_TTL_DAYS"] = "30"
    env["ICODER_RUN_TRACE_EVENTS_TTL_DAYS"] = "90"
    with pytest.raises(RuntimeError, match="must not exceed"):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("MEDCODER_RETRIEVER_URL", "", "MEDCODER_RETRIEVER_URL"),
        ("MEDCODER_RETRIEVER_URL", "http://medcoder.internal", "absolute HTTPS"),
        ("MEDCODER_RETRIEVER_TOKEN", "weak", "32 to 512"),
        ("MEDCODER_RETRIEVER_ALLOW_HTTP", "true", "ALLOW_HTTP"),
        ("MEDCODER_RETRIEVER_TIMEOUT_SECONDS", "121", "TIMEOUT_SECONDS"),
    ],
)
def test_cloud_mode_refuses_unsafe_remote_retriever(
    monkeypatch, key, value, message
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ICODER_MEMORY_SEMANTIC_URL", "", "MEMORY_SEMANTIC_URL"),
        (
            "ICODER_MEMORY_SEMANTIC_URL",
            "http://memory.internal/v1/embed",
            "absolute HTTPS",
        ),
        (
            "ICODER_MEMORY_SEMANTIC_URL",
            "https://memory.internal:8443/v1/embed",
            "port 443",
        ),
        ("ICODER_CREDENTIAL_MEMORY_SEMANTIC", "weak", "32 to 512"),
        ("ICODER_MEMORY_SEMANTIC_REQUIRED", "false", "REQUIRED=true"),
        (
            "ICODER_CONNECTOR_EGRESS_ALLOWLIST",
            "different.internal",
            "must be present",
        ),
    ],
)
def test_cloud_mode_refuses_unsafe_semantic_memory(
    monkeypatch, key, value, message
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ICODER_INVITE_DELIVERY_MODE", "manual", "DELIVERY_MODE=webhook"),
        ("ICODER_INVITE_WEBHOOK_URL", "http://notification.internal/invitations", "absolute HTTPS"),
        ("ICODER_INVITE_WEBHOOK_URL", "https://127.0.0.1/invitations", "private or reserved"),
        ("ICODER_INVITE_WEBHOOK_BEARER_TOKEN", "weak", "32 to 512"),
        ("ICODER_INVITE_ALLOWED_EMAIL_DOMAINS", "[]", "non-empty"),
        ("ICODER_INVITE_ALLOWED_EMAIL_DOMAINS", '["*.example.cn"]', "exact-domain"),
        ("ICODER_INVITE_ALLOWED_EMAIL_DOMAINS", '["bad-.example.cn"]', "exact-domain"),
        ("ICODER_INVITE_MAX_ATTEMPTS", "0", "between 1 and 20"),
        ("ICODER_INVITE_CLAIM_TIMEOUT_SECONDS", "9", "between 10 and 3600"),
        ("ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS", "0", "between 0.1 and 60"),
    ],
)
def test_cloud_mode_refuses_unsafe_invitation_delivery(
    monkeypatch, key, value, message
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_weak_secret_change_me(monkeypatch):
    """Cloud mode + SECRET_KEY=change-me-in-production → RuntimeError."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_SECRET_KEY"] = "change-me-in-production"
    with pytest.raises(RuntimeError, match="SECRET_KEY is empty, shorter than 32 bytes"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_short_hs256_secret(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_SECRET_KEY"] = "unique-but-too-short"
    with pytest.raises(RuntimeError, match="shorter than 32 bytes"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_empty_secret(monkeypatch):
    """Cloud mode + empty SECRET_KEY → RuntimeError."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_SECRET_KEY"] = ""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_missing_hosted_url(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_HOSTED_URL"] = ""
    with pytest.raises(RuntimeError, match="ICODER_HOSTED_URL"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_invalid_environment(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_ENVIRONMENT"] = "mars"
    with pytest.raises(RuntimeError, match="ICODER_ENVIRONMENT"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_missing_tenant_id(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_TENANT_ID"] = ""
    with pytest.raises(RuntimeError, match="ICODER_TENANT_ID"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_seed_on_startup(monkeypatch):
    """Cloud mode must NEVER auto-seed admin/admin123."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["SEED_ON_STARTUP"] = "true"
    with pytest.raises(RuntimeError, match="SEED_ON_STARTUP=true is forbidden"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_debug_true(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["DEBUG"] = "true"
    with pytest.raises(RuntimeError, match="DEBUG=true is forbidden"):
        _reload_settings(monkeypatch, env)


def test_cloud_mode_refuses_database_sql_echo(monkeypatch):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_DATABASE_SQL_ECHO"] = "true"
    with pytest.raises(
        RuntimeError,
        match="ICODER_DATABASE_SQL_ECHO=true is forbidden",
    ):
        _reload_settings(monkeypatch, env)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("DATABASE_URL", "sqlite+aiosqlite:///./data/icoder.db", "DATABASE_URL"),
        ("CORS_ORIGINS", '["http://localhost:5173"]', "CORS_ORIGINS"),
        ("ICODER_PHI_REDACTION_MODE", "disabled", "ICODER_PHI_REDACTION_MODE"),
        ("ICODER_AUDIT_SINK", "local", "ICODER_AUDIT_SINK"),
        ("ICODER_SINGLE_TENANT_ORG_ID", "org_default1", "ICODER_SINGLE_TENANT_ORG_ID"),
        ("ICODER_ASSET_BUCKET", "", "ICODER_ASSET_BUCKET"),
        ("ICODER_CREDENTIAL_LLM", "", "ICODER_CREDENTIAL_LLM"),
        ("LLM_PROVIDER", "mock", "LLM_PROVIDER=mock"),
        ("APP_ENV", "development", "APP_ENV=cloud"),
        ("OAUTH_REQUIRE_TENANT_HEADER", "false", "OAUTH_REQUIRE_TENANT_HEADER"),
        ("ICODER_HOSTED_URL", "http://api.icoder.cloud", "must use https"),
        ("ICODER_REGION", "us-virginia", "does not belong"),
        ("ICODER_METRICS_BEARER_TOKEN", "too-short", "32 to 512"),
    ],
)
def test_cloud_mode_refuses_local_or_cross_region_runtime_settings(
    monkeypatch, key, value, message,
):
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env[key] = value
    with pytest.raises(RuntimeError, match=message):
        _reload_settings(monkeypatch, env)


def test_weak_secret_literals_covered_by_blocklist(monkeypatch):
    """Sanity: all documented weak literals are in the blocklist."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    import app.config as _cfg
    expected = {"", "change-me", "change-me-in-production", "changeme",
                "secret", "test", "dev", "development"}
    actual = _cfg._WEAK_SECRET_KEY_LITERALS
    assert expected.issubset(actual), f"missing: {expected - actual}"
