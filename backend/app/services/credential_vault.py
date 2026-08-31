"""Credential Vault — isolate secrets from Agent and Harness.

Inspired by Anthropic Managed Agents: credentials live in a Vault,
never reach the sandbox, and are injected at the proxy level.

Design:
- Vault reads from environment variables (dev) or cloud secrets manager (prod)
- llm_service and expert_runner call vault.resolve(service) to get credentials
- Credentials are NEVER logged, NEVER serialized in audit events, NEVER in LLM context
- Agent and Harness only see service names (e.g. "deepseek", "pubmed"), never keys

Phase A1D.4 (A1C-B-008) — KMS rotation + cache invalidation:
  - ``invalidate(service=None)`` flushes cache entries (operator-initiated).
  - ``invalidate_all()`` is the no-arg alias.
  - Optional ``kms_version_token`` stamps each cache entry with the token's
    current value; on lookup, stale-stamped entries are re-read from env /
    secrets manager. Production Pilot wires the token to the cloud KMS
    rotation hook (the hook calls ``token.bump()`` post-rotation).
"""

import os
import logging

from icoder_runtime.core.kms_version_token import KMSVersionToken

logger = logging.getLogger(__name__)


def get_global_kms_version_token():
    """Return the process-wide KMSVersionToken.

    Phase A1D.7 — exposes the singleton token so the admin rotation
    endpoint and any future cloud-KMS adapter can ``bump()`` it without
    reaching into the vault's private state.
    """
    return _kms_version_token


class CredentialNotFound(Exception):
    """Raised when a requested credential is not configured."""

    def __init__(self, service: str):
        super().__init__(f"Credential not found for service '{service}'. "
                         f"Set environment variable ICODER_CREDENTIAL_{service.upper()}")


class CredentialVault:
    """Secure credential store — reads from environment, designed for cloud secrets migration.

    In production, this would be backed by:
    - AWS Secrets Manager / GCP Secret Manager / Azure Key Vault
    - HashiCorp Vault
    - Kubernetes secrets

    The interface stays the same regardless of backing store.
    """

    def __init__(self, kms_version_token=None):
        self._cache: dict[str, str] = {}
        # Phase A1D.4 — version stamps for stale-entry detection.
        # When kms_version_token is None, no stamping occurs (legacy behavior).
        self._kms_token = kms_version_token
        self._cache_stamps: dict[str, int] = {}

    def resolve(self, service: str) -> str:
        """Resolve a credential for a named service.

        Never logs the actual credential value — only the service name.

        Service naming convention:
        - "llm" → DeepSeek API key
        - "drugbank" → DrugBank API key
        - "pubmed" → PubMed/NCBI API key
        - "posos" → POSOS medication database key
        - "web_search" → privacy-preserving web-search gateway key
        - "memory_semantic" → isolated semantic-memory embedding service key
        - "clinical_trials" → ClinicalTrials.gov API key
        - "mcp_<name>" → MCP server credentials

        Environment variable format: ICODER_CREDENTIAL_{SERVICE_UPPER}

        Phase A1D.4: when kms_version_token is set, stale-stamped entries
        are re-read from env/secrets manager instead of being returned
        stale.
        """
        # Phase A1D.4 — KMS rotation stale-stamp check
        if self._kms_token is not None and service in self._cache_stamps:
            if self._kms_token.is_stale(self._cache_stamps[service]):
                logger.info(
                    "Credential cache stale for service '%s' (KMS token advanced); re-reading",
                    service,
                )
                self._cache.pop(service, None)
                self._cache_stamps.pop(service, None)

        if service in self._cache:
            return self._cache[service]

        env_key = f"ICODER_CREDENTIAL_{service.upper()}"
        value = os.environ.get(env_key, "")

        if not value:
            raise CredentialNotFound(service)

        self._cache[service] = value
        if self._kms_token is not None:
            self._cache_stamps[service] = self._kms_token.current
        logger.info(f"Credential resolved for service '{service}'")
        return value

    def invalidate(self, service: str | None = None) -> None:
        """Phase A1D.4 — flush one or all cached credentials.

        Use cases:
          - Operator-initiated flush after manual KMS key rotation.
          - Test isolation between subtests.
          - Recovery from a known-stale cache state.

        With ``service=None`` (default), flushes the entire cache.
        With ``service="llm"``, flushes only that entry.
        Flushing an unknown service is a no-op (no error).
        """
        if service is None:
            n = len(self._cache)
            self._cache.clear()
            self._cache_stamps.clear()
            if n:
                logger.info("Credential cache invalidated all (%d entries)", n)
        else:
            if service in self._cache:
                self._cache.pop(service, None)
                self._cache_stamps.pop(service, None)
                logger.info("Credential cache invalidated for service '%s'", service)

    def invalidate_all(self) -> None:
        """Phase A1D.4 — alias for ``invalidate()`` (flush entire cache)."""
        self.invalidate()

    def resolve_optional(self, service: str) -> str | None:
        """Resolve a credential, returning None if not configured (for optional services)."""
        try:
            return self.resolve(service)
        except CredentialNotFound:
            return None

    def inject_headers(self, service: str, headers: dict) -> dict:
        """Inject authentication headers for a service call.

        The caller provides a headers dict; the vault injects the credential
        into the Authorization header. The caller never sees the credential.
        """
        credential = self.resolve(service)
        return {
            **headers,
            "Authorization": f"Bearer {credential}",
        }

    def list_available_services(self) -> list[str]:
        """List all configured credential services (for admin debugging).

        Returns service names only — never the credential values.
        """
        available = []
        for key, value in os.environ.items():
            if key.startswith("ICODER_CREDENTIAL_"):
                service = key[len("ICODER_CREDENTIAL_"):].lower()
                available.append(service)
        return sorted(available)

    def health_check(self) -> dict:
        """Check which services have credentials configured."""
        required = ["llm"]
        optional = [
            "drugbank", "pubmed", "posos", "clinical_trials", "web_search",
            "memory_semantic",
        ]

        result = {"required": {}, "optional": {}}
        for svc in required:
            try:
                self.resolve(svc)
                result["required"][svc] = "configured"
            except CredentialNotFound:
                result["required"][svc] = "missing"

        for svc in optional:
            try:
                self.resolve(svc)
                result["optional"][svc] = "configured"
            except CredentialNotFound:
                result["optional"][svc] = "not_configured"

        return result


# Global singleton
# Phase A1D.7 (Pilot Prep Step 5a) — wire the global vault with a shared
# KMSVersionToken so the admin rotation endpoint
# (POST /api/admin/kms/rotate) can drive cache invalidation app-wide.
# Without this wiring, KMSVersionToken instances existed only in tests.
_kms_version_token = KMSVersionToken()
credential_vault = CredentialVault(kms_version_token=_kms_version_token)
