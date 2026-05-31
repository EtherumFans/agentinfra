"""Credential Vault — isolate secrets from Agent and Harness.

Inspired by Anthropic Managed Agents: credentials live in a Vault,
never reach the sandbox, and are injected at the proxy level.

Design:
- Vault reads from environment variables (dev) or cloud secrets manager (prod)
- llm_service and expert_runner call vault.resolve(service) to get credentials
- Credentials are NEVER logged, NEVER serialized in audit events, NEVER in LLM context
- Agent and Harness only see service names (e.g. "deepseek", "pubmed"), never keys
"""

import os
import logging

logger = logging.getLogger(__name__)


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

    def __init__(self):
        self._cache: dict[str, str] = {}

    def resolve(self, service: str) -> str:
        """Resolve a credential for a named service.

        Never logs the actual credential value — only the service name.

        Service naming convention:
        - "llm" → DeepSeek API key
        - "drugbank" → DrugBank API key
        - "pubmed" → PubMed/NCBI API key
        - "posos" → POSOS medication database key
        - "clinical_trials" → ClinicalTrials.gov API key
        - "mcp_<name>" → MCP server credentials

        Environment variable format: ICODER_CREDENTIAL_{SERVICE_UPPER}
        """
        if service in self._cache:
            return self._cache[service]

        env_key = f"ICODER_CREDENTIAL_{service.upper()}"
        value = os.environ.get(env_key, "")

        if not value:
            raise CredentialNotFound(service)

        self._cache[service] = value
        logger.info(f"Credential resolved for service '{service}'")
        return value

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
        optional = ["drugbank", "pubmed", "posos", "clinical_trials"]

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
credential_vault = CredentialVault()
