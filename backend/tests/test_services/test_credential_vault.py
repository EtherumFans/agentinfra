"""Test Credential Vault and Audit Chain Integrity"""
import os
import pytest
from app.services.credential_vault import CredentialVault, CredentialNotFound
from app.services.runtime import AuditChain


class TestCredentialVault:
    def test_resolve_from_env(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-api-key-123")
        vault = CredentialVault()
        assert vault.resolve("llm") == "test-api-key-123"

    def test_resolve_not_found(self):
        vault = CredentialVault()
        os.environ.pop("ICODER_CREDENTIAL_NONEXISTENT", None)
        with pytest.raises(CredentialNotFound):
            vault.resolve("nonexistent")

    def test_resolve_optional_missing(self):
        vault = CredentialVault()
        os.environ.pop("ICODER_CREDENTIAL_DRUGBANK", None)
        assert vault.resolve_optional("drugbank") is None

    def test_resolve_optional_present(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_PUBMED", "pubmed-key")
        vault = CredentialVault()
        assert vault.resolve_optional("pubmed") == "pubmed-key"

    def test_inject_headers(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-abc")
        vault = CredentialVault()
        headers = vault.inject_headers("llm", {"Content-Type": "application/json"})
        assert headers["Authorization"] == "Bearer key-abc"
        assert headers["Content-Type"] == "application/json"

    def test_list_available_services(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "k1")
        monkeypatch.setenv("ICODER_CREDENTIAL_PUBMED", "k2")
        monkeypatch.setenv("SOME_OTHER_VAR", "ignore-me")
        vault = CredentialVault()
        services = vault.list_available_services()
        assert "llm" in services
        assert "pubmed" in services
        assert "some_other_var" not in services

    def test_health_check(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "k1")
        vault = CredentialVault()
        health = vault.health_check()
        assert health["required"]["llm"] == "configured"
        # Optional services without keys should be "not_configured"
        assert health["optional"]["drugbank"] == "not_configured"

    def test_caching(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-1")
        vault = CredentialVault()
        assert vault.resolve("llm") == "key-1"
        # Change env var — cached value should still be old
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "key-2")
        assert vault.resolve("llm") == "key-1"


class TestAuditChainIntegrity:
    def test_verify_integrity_empty(self):
        chain = AuditChain("test-case")
        assert chain.verify_integrity() is True

    def test_verify_integrity_with_events(self):
        chain = AuditChain("test-case")
        chain.record("step_1", actor="agent", payload={"action": "extract"})
        chain.record("step_2", actor="agent", payload={"action": "code"})
        assert chain.verify_integrity() is True

    def test_replay(self):
        chain = AuditChain("test-case")
        chain.record("step_1", actor="agent", payload={"action": "extract"})
        chain.record("step_2", actor="agent", payload={"action": "code"})
        events = chain.replay()
        assert len(events) == 2
        assert events[0]["event_type"] == "step_1"
        assert events[1]["event_type"] == "step_2"

    def test_get_recent(self):
        chain = AuditChain("test-case")
        for i in range(15):
            chain.record(f"step_{i}", actor="system")
        recent = chain.get_recent(5)
        assert len(recent) == 5
        assert recent[-1]["event_type"] == "step_14"
