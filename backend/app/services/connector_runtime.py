"""Application wiring for the governed Connector execution boundary."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from app.config import settings
from app.models.agent_connector import AgentConnector, ConnectorCredential
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
)
from app.services.connector_http_transport import GovernedConnectorHTTPTransport
from app.services.connector_external_registry import GovernedExternalRegistryProvider
from app.services.connector_memory_semantic import GovernedMemoryEmbeddingProvider
from app.services.connector_local_adapters import (
    GovernedInternalAgentAdapter,
    GovernedRegistryAdapter,
)
from app.services.connector_public_registry import GovernedPublicRegistryProvider
from app.services.connector_memory_store import GovernedMemoryStore
from app.services.credential_vault import credential_vault


def _exact_allowlist(name: str) -> frozenset[str]:
    return frozenset(
        item.strip().rstrip(".").casefold()
        for item in os.environ.get(name, "").split(",")
        if item.strip()
    )


def connector_host_authorizer(host: str) -> bool:
    """Require an exact egress allowlist in cloud and every CN profile."""

    restricted = (
        os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().casefold()
        == "cloud"
        or os.environ.get("ICODER_ENVIRONMENT", "").strip().casefold() == "cn"
    )
    if not restricted:
        return True
    return host.rstrip(".").casefold() in _exact_allowlist(
        "ICODER_CONNECTOR_EGRESS_ALLOWLIST"
    )


def connector_data_policy_authorizer(
    connector: AgentConnector,
    invocation: ConnectorInvocation,
) -> bool:
    """Minimum-necessary outbound data policy used by the live runtime."""

    if invocation.purpose_of_use not in {
        "treatment",
        "payment",
        "healthcare_operations",
        "quality_improvement",
        "research",
        "public_health",
        "system_operations",
    }:
        return False
    if invocation.data_classification in {"non_phi", "deidentified"}:
        return not (
            invocation.purpose_of_use == "research"
            and invocation.data_classification != "deidentified"
        )
    if invocation.data_classification not in {"phi", "restricted"}:
        return False
    if os.environ.get("ICODER_CONNECTOR_ALLOW_PHI", "0").strip().casefold() not in {
        "1", "true", "yes",
    }:
        return False
    host = (urlsplit(connector.normalized_url or "").hostname or "").casefold()
    return bool(host) and host in _exact_allowlist(
        "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST"
    )


SecretResolver = Callable[[str], str]


class ConnectorCredentialAdapter:
    """Resolve bound credential metadata without exposing values to Agents."""

    def __init__(
        self,
        transport: GovernedConnectorHTTPTransport,
        *,
        secret_resolver: SecretResolver = credential_vault.resolve,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._secret_resolver = secret_resolver
        self._clock = clock
        self._oauth_cache: dict[tuple[str, int], tuple[str, float]] = {}

    async def __call__(self, credential: ConnectorCredential) -> dict[str, str]:
        service = f"connector_{credential.fingerprint.casefold()}"
        try:
            raw = self._secret_resolver(service)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_CREDENTIAL_RESOLUTION_FAILED"
            ) from exc
        if (
            not isinstance(raw, str)
            or not raw
            or len(raw) > 32 * 1024
            or "\x00" in raw
        ):
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_RESOLUTION_FAILED")
        if credential.secret_type == "bearer":
            self._validate_header_value(raw)
            return {"Authorization": f"Bearer {raw}"}
        if credential.secret_type == "api-key":
            self._validate_header_value(raw)
            return {"X-API-Key": raw}
        if credential.secret_type == "oauth2-client":
            return await self._resolve_oauth(credential, raw)
        raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_TYPE_UNSUPPORTED")

    async def _resolve_oauth(
        self,
        credential: ConnectorCredential,
        raw: str,
    ) -> dict[str, str]:
        key = (credential.fingerprint.casefold(), int(credential.version))
        now = self._clock()
        cached = self._oauth_cache.get(key)
        if cached is not None and now + 60.0 < cached[1]:
            return {"Authorization": f"Bearer {cached[0]}"}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConnectorExecutionError("CONNECTOR_OAUTH_CREDENTIAL_INVALID") from exc
        if not isinstance(payload, dict) or set(payload) - {
            "token_url", "client_id", "client_secret", "scope",
        }:
            raise ConnectorExecutionError("CONNECTOR_OAUTH_CREDENTIAL_INVALID")
        if not all(
            isinstance(payload.get(field), str) and payload[field]
            for field in ("token_url", "client_id", "client_secret")
        ) or not isinstance(payload.get("scope", ""), str):
            raise ConnectorExecutionError("CONNECTOR_OAUTH_CREDENTIAL_INVALID")
        try:
            token, lifetime = await self._transport.exchange_oauth2_client_credentials(
                token_url=payload["token_url"],
                client_id=payload["client_id"],
                client_secret=payload["client_secret"],
                scope=payload.get("scope", ""),
            )
        except ConnectorExecutionError:
            raise
        except Exception as exc:
            raise ConnectorExecutionError("CONNECTOR_OAUTH_EXCHANGE_FAILED") from exc
        self._oauth_cache[key] = (token, now + lifetime)
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _validate_header_value(value: str) -> None:
        if len(value) > 8192 or "\r" in value or "\n" in value:
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_RESOLUTION_FAILED")


@dataclass(frozen=True)
class ConnectorRuntime:
    executor: ConnectorExecutor
    transport: GovernedConnectorHTTPTransport
    public_registry_provider: GovernedPublicRegistryProvider
    external_registry_provider: GovernedExternalRegistryProvider
    memory_embedding_provider: GovernedMemoryEmbeddingProvider
    registry_adapter: GovernedRegistryAdapter
    agent_adapter: GovernedInternalAgentAdapter | None

    async def aclose(self) -> None:
        await self.transport.aclose()

    def status(self) -> dict[str, object]:
        restricted = (
            os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().casefold()
            == "cloud"
            or os.environ.get("ICODER_ENVIRONMENT", "").strip().casefold() == "cn"
        )
        return {
            "configured": True,
            "mcp_transport": "streamable-http",
            "a2a_protocol_version": "1.0",
            "a2a_bindings": ["JSONRPC", "HTTP+JSON"],
            "dns_socket_pinning": True,
            "os_proxy_inheritance": False,
            "tls_trust": "isolated-certifi",
            "http_versions": ["HTTP/1.1"],
            "redirect_default": "deny",
            "external_phi_default": "deny",
            "egress_mode": "exact-host-allowlist" if restricted else "public-https-dev",
            "live_external_verified": False,
            "registry_adapter": self.registry_adapter.status(),
            "internal_agent_adapter": (
                self.agent_adapter.status() if self.agent_adapter is not None else None
            ),
        }


def build_connector_runtime(app: Any | None = None) -> ConnectorRuntime:
    transport = GovernedConnectorHTTPTransport(
        host_authorizer=connector_host_authorizer,
    )
    env_ncbi_contact = os.environ.get("ICODER_NCBI_CONTACT_EMAIL")
    public_registry_provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email=(
            env_ncbi_contact
            if env_ncbi_contact is not None
            else settings.ICODER_NCBI_CONTACT_EMAIL
        ),
        host_authorizer=connector_host_authorizer,
    )
    external_registry_provider = GovernedExternalRegistryProvider(
        transport,
        credential_resolver=credential_vault.resolve_optional,
        host_authorizer=connector_host_authorizer,
    )
    memory_embedding_provider = GovernedMemoryEmbeddingProvider(
        transport,
        credential_resolver=credential_vault.resolve_optional,
        host_authorizer=connector_host_authorizer,
    )
    registry_adapter = GovernedRegistryAdapter(
        app,
        public_registry_provider=public_registry_provider,
        external_registry_provider=external_registry_provider,
        memory_store=GovernedMemoryStore(
            semantic_provider=memory_embedding_provider,
        ),
    )
    agent_adapter = GovernedInternalAgentAdapter(app) if app is not None else None
    executor = ConnectorExecutor(
        remote_transport=transport,
        credential_resolver=ConnectorCredentialAdapter(transport),
        contextual_registry_invoker=registry_adapter,
        contextual_agent_invoker=agent_adapter,
        policy_authorizer=connector_data_policy_authorizer,
    )
    return ConnectorRuntime(
        executor=executor,
        transport=transport,
        public_registry_provider=public_registry_provider,
        external_registry_provider=external_registry_provider,
        memory_embedding_provider=memory_embedding_provider,
        registry_adapter=registry_adapter,
        agent_adapter=agent_adapter,
    )


__all__ = [
    "ConnectorCredentialAdapter",
    "ConnectorRuntime",
    "build_connector_runtime",
    "connector_data_policy_authorizer",
    "connector_host_authorizer",
]
