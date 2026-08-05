"""A1D.4 — A1C-B-008 KMS key rotation + cache invalidation.

Predecessor state (Phase A1C.9): ``CredentialVault`` caches credentials
in a process-local ``_cache: dict[str, str]`` after first ``resolve()``.
When the cloud KMS rotates a key (operator-driven rotation, scheduled
rotation, or compromise-response rotation), the cached value is stale
but the cache returns it indefinitely — no invalidation signal.

A1D.4 closes the gap by:
  - ``kms_version_token.py`` — a version token abstraction. The token
    changes whenever KMS rotates; the cache stamps entries with the
    current token and refuses to return entries whose token is stale.
  - ``CredentialVault.invalidate(service=None)`` — operator-initiated
    cache flush. Without args, flushes all entries; with a service,
    flushes only that entry.
  - ``CredentialVault.invalidate_all()`` — convenience alias.
  - ``KMS_ROTATION_REPORT.md`` — operator runbook (separate file).

The version-token mechanism is what production Pilot will use: the KMS
rotation hook bumps the token, and the next ``resolve()`` call re-reads
from the secrets manager instead of returning the stale cached value.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 KMSVersionToken — monotonic, comparable
# ─────────────────────────────────────────────────────────────────────


def test_kms_version_token_initial_value() -> None:
    """Fresh KMSVersionToken starts at version 1."""
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    assert tok.current == 1


def test_kms_version_token_bump_increments() -> None:
    """bump() advances the version by 1."""
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    assert tok.bump() == 2
    assert tok.current == 2
    assert tok.bump() == 3


def test_kms_version_token_is_stale_detects_old_entries() -> None:
    """is_stale returns True for entries stamped with an older token."""
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    old_stamp = tok.current
    tok.bump()
    assert tok.is_stale(old_stamp) is True
    assert tok.is_stale(tok.current) is False


# ─────────────────────────────────────────────────────────────────────
# §2 CredentialVault — cache invalidation by service
# ─────────────────────────────────────────────────────────────────────


def test_credential_vault_invalidate_flushes_single_service(monkeypatch) -> None:
    """invalidate(service) drops that service from the cache; others survive."""
    from app.services.credential_vault import CredentialVault
    v = CredentialVault()
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    monkeypatch.setenv("ICODER_CREDENTIAL_PUBMED", "pubmed-v1")
    # Populate cache
    assert v.resolve("llm") == "key-v1"
    assert v.resolve("pubmed") == "pubmed-v1"
    # Mutate env (simulating KMS rotation of LLM only)
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2")
    # Without invalidation, cache returns stale
    assert v.resolve("llm") == "key-v1"
    # Invalidate LLM only
    v.invalidate("llm")
    # Now resolve re-reads env
    assert v.resolve("llm") == "key-v2"
    # PubMed cache untouched
    assert v.resolve("pubmed") == "pubmed-v1"


def test_credential_vault_invalidate_no_arg_flushes_all(monkeypatch) -> None:
    """invalidate() with no args flushes the entire cache."""
    from app.services.credential_vault import CredentialVault
    v = CredentialVault()
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    monkeypatch.setenv("ICODER_CREDENTIAL_PUBMED", "pubmed-v1")
    v.resolve("llm")
    v.resolve("pubmed")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2")
    monkeypatch.setenv("ICODER_CREDENTIAL_PUBMED", "pubmed-v2")
    v.invalidate()
    assert v.resolve("llm") == "key-v2"
    assert v.resolve("pubmed") == "pubmed-v2"


def test_credential_vault_invalidate_all_alias(monkeypatch) -> None:
    """invalidate_all() is an alias for invalidate()."""
    from app.services.credential_vault import CredentialVault
    v = CredentialVault()
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    v.resolve("llm")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2")
    v.invalidate_all()
    assert v.resolve("llm") == "key-v2"


def test_credential_vault_invalidate_unknown_service_is_noop(monkeypatch) -> None:
    """invalidate('unknown-service') is a no-op (no error, no cache mutation)."""
    from app.services.credential_vault import CredentialVault
    v = CredentialVault()
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    v.resolve("llm")
    # Unknown service — should not raise
    v.invalidate("never-resolved")
    # Known service still cached
    assert v.resolve("llm") == "key-v1"


# ─────────────────────────────────────────────────────────────────────
# §3 KMS rotation hook — bumping the token invalidates the cache
# ─────────────────────────────────────────────────────────────────────


def test_credential_vault_attaches_to_kms_version_token(monkeypatch) -> None:
    """Vault constructed with a KMSVersionToken stamps entries with the token."""
    from app.services.credential_vault import CredentialVault
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    v = CredentialVault(kms_version_token=tok)
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    v.resolve("llm")
    # Internal cache entry carries the version stamp
    assert v._cache_stamps["llm"] == 1


def test_kms_token_bump_invalidates_stale_cache_entries(monkeypatch) -> None:
    """After KMSVersionToken.bump(), stale cache entries are re-read on next resolve()."""
    from app.services.credential_vault import CredentialVault
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    v = CredentialVault(kms_version_token=tok)
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    assert v.resolve("llm") == "key-v1"
    # KMS rotation hook bumps the token
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2")
    tok.bump()
    # Next resolve detects stale stamp and re-reads env
    assert v.resolve("llm") == "key-v2"


def test_kms_token_bump_only_invalidates_stale_entries(monkeypatch) -> None:
    """Entries resolved after the bump are NOT invalidated by subsequent resolves."""
    from app.services.credential_vault import CredentialVault
    from icoder_runtime.core.kms_version_token import KMSVersionToken
    tok = KMSVersionToken()
    v = CredentialVault(kms_version_token=tok)
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v1")
    v.resolve("llm")  # stamped with token=1
    tok.bump()        # now token=2
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v2")
    assert v.resolve("llm") == "key-v2"  # re-read, stamped with token=2
    # Subsequent resolve() should NOT re-read — entry is current
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-v3-should-not-load")
    assert v.resolve("llm") == "key-v2"
