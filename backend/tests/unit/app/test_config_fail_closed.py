"""A1A Gate 1 Step 4 — Fail-closed env policy tests.

Validates that Settings() refuses to boot in cloud mode when required
secrets are missing or carry known-weak defaults. Local mode remains
permissive.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _reload_settings(monkeypatch, env_overrides: dict[str, str]):
    """Reload app.config.settings with the given env overrides."""
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)
    import importlib
    import app.config
    importlib.reload(app.config)
    return app.config


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
    "SEED_ON_STARTUP",
    "DEBUG",
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
        "SEED_ON_STARTUP": "false",
        "DEBUG": "false",
        # Phase A1D.5 — Gate 4 added ICODER_PHI_ENCRYPTION_KEY as a
        # cloud-mode requirement (Fernet envelope for at-rest PHI).
        # Gate 3R added RUNTRACE_DEPLOYMENT_PROFILE=BEST_EFFORT_DB as a
        # cloud-mode requirement (memory store loses trace on restart).
        "ICODER_PHI_ENCRYPTION_KEY": "3PARkxUUNU68P58uuahocRIqiSHbx7ACY_JHkaKt3v4=",  # test-only Fernet key
        "RUNTRACE_DEPLOYMENT_PROFILE": "BEST_EFFORT_DB",
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


def test_cloud_mode_refuses_weak_secret_change_me(monkeypatch):
    """Cloud mode + SECRET_KEY=change-me-in-production → RuntimeError."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    env = _valid_cloud_env()
    env["ICODER_SECRET_KEY"] = "change-me-in-production"
    with pytest.raises(RuntimeError, match="SECRET_KEY is empty or a known-weak literal"):
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


def test_weak_secret_literals_covered_by_blocklist(monkeypatch):
    """Sanity: all documented weak literals are in the blocklist."""
    _clear_env(monkeypatch, CLOUD_KEYS)
    import app.config as _cfg
    expected = {"", "change-me", "change-me-in-production", "changeme",
                "secret", "test", "dev", "development"}
    actual = _cfg._WEAK_SECRET_KEY_LITERALS
    assert expected.issubset(actual), f"missing: {expected - actual}"
