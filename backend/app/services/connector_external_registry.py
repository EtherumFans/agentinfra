"""Governed enterprise gateways for licensed and privacy-sensitive registries.

The runtime deliberately does not guess vendor-specific DrugBank, POSOS or web
search APIs. Operators deploy or purchase an adapter implementing the versioned
iCoDer gateway contract, configure its fixed HTTPS URL, and place its bearer
credential in the credential vault. Only deidentified, bounded queries cross
this boundary and only a minimal provider-specific projection is returned.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

from app.agents.experts.external_expert_gate import evaluate
from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation


EXTERNAL_REGISTRY_KEYS = frozenset({"drugbank", "posos", "web-search"})
GATEWAY_REQUEST_CONTRACT = "icoder.external-registry.gateway-request/v1"
GATEWAY_RESPONSE_CONTRACT = "icoder.external-registry.gateway-response/v1"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 20
_DRUGBANK_ID_RE = re.compile(r"^DB\d{5}$")


class ExternalRegistryJSONTransport(Protocol):
    async def post_json(
        self,
        *,
        base_url: str,
        expected_host: str,
        headers: dict[str, str],
        body: dict[str, Any],
        connect_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 15.0,
        max_response_bytes: int = 512 * 1024,
    ) -> dict[str, Any]: ...


CredentialResolver = Callable[[str], str | None]
HostAuthorizer = Callable[[str], bool]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _csv_set(value: str | None) -> frozenset[str]:
    return frozenset(
        item.strip() for item in (value or "").split(",") if item.strip()
    )


def _text(value: object, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        if required:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        return ""
    result = " ".join(value.split())[:maximum]
    if required and not result:
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    return result


def _string_list(value: object, *, items: int, chars: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > items:
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    return [text for item in value if (text := _text(item, chars))]


def _safe_reference_url(value: object, *, required: bool = False) -> str:
    raw = _text(value, 2048, required=required)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


class GovernedExternalRegistryProvider:
    """Execute configured commercial/search gateways with fail-closed policy."""

    def __init__(
        self,
        transport: ExternalRegistryJSONTransport,
        *,
        credential_resolver: CredentialResolver,
        host_authorizer: HostAuthorizer | None = None,
        endpoints: dict[str, str] | None = None,
        region: str | None = None,
        web_provider_opt_in: bool | None = None,
        web_tenant_opt_in_organizations: frozenset[str] | None = None,
        allow_loopback_http_for_testing: bool = False,
    ) -> None:
        self._transport = transport
        self._credential_resolver = credential_resolver
        self._host_authorizer = host_authorizer or (lambda _host: True)
        configured = endpoints or {}
        self._endpoints = {
            "drugbank": configured.get(
                "drugbank", os.environ.get("ICODER_DRUGBANK_GATEWAY_URL", ""),
            ).strip(),
            "posos": configured.get(
                "posos", os.environ.get("ICODER_POSOS_GATEWAY_URL", ""),
            ).strip(),
            "web-search": configured.get(
                "web-search", os.environ.get("ICODER_WEB_SEARCH_GATEWAY_URL", ""),
            ).strip(),
        }
        self._region = (
            region if region is not None else os.environ.get("ICODER_REGION", "")
        ).strip().upper()
        self._web_provider_opt_in = (
            web_provider_opt_in
            if web_provider_opt_in is not None
            else _truthy(os.environ.get("ICODER_WEB_SEARCH_PROVIDER_OPT_IN"))
        )
        self._web_tenant_opt_ins = (
            web_tenant_opt_in_organizations
            if web_tenant_opt_in_organizations is not None
            else _csv_set(
                os.environ.get("ICODER_WEB_SEARCH_TENANT_OPT_IN_ORGANIZATIONS")
            )
        )
        self._allow_loopback_http_for_testing = bool(
            allow_loopback_http_for_testing
        )

    async def __call__(
        self,
        registry_key: str,
        invocation: ConnectorInvocation,
    ) -> dict[str, Any]:
        if registry_key not in EXTERNAL_REGISTRY_KEYS:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ENTRY_UNAVAILABLE")
        query, max_results = self._validate_invocation(registry_key, invocation)
        endpoint, host = self._validated_endpoint(registry_key)
        token = self._credential(registry_key)
        tenant_opt_in = invocation.organization_id in self._web_tenant_opt_ins
        decision = evaluate(
            registry_key,
            licence_tokens=[token] if registry_key in {"drugbank", "posos"} else None,
            region=self._region or None,
            egress_enabled=self._host_authorizer(host) is True,
            provider_opt_in=self._web_provider_opt_in,
            tenant_opt_in=tenant_opt_in,
        )
        if not self._region:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_REGION_NOT_CONFIGURED")
        if not decision.permitted:
            mapping = {
                "LICENCE_REQUIRED": "CONNECTOR_REGISTRY_LICENSE_REQUIRED",
                "EGRESS_DISABLED": "CONNECTOR_EGRESS_NOT_APPROVED",
                "REGION_BLOCKED": "CONNECTOR_REGISTRY_REGION_BLOCKED",
                "PROVIDER_OPT_IN_MISSING": "CONNECTOR_REGISTRY_OPT_IN_REQUIRED",
            }
            raise ConnectorExecutionError(
                mapping.get(decision.reason, "CONNECTOR_REGISTRY_POLICY_DENIED")
            )

        response = await self._transport.post_json(
            base_url=endpoint,
            expected_host=host,
            headers={"Authorization": f"Bearer {token}"},
            body={
                "contract": GATEWAY_REQUEST_CONTRACT,
                "provider": registry_key,
                "operation": invocation.operation,
                "query": query,
                "max_results": max_results,
                "region": self._region,
            },
            total_timeout_seconds=15.0,
            max_response_bytes=512 * 1024,
        )
        results, total_available = self._validate_envelope(
            registry_key, response, max_results,
        )
        if registry_key == "drugbank":
            return self._project_drugbank(query, results, total_available, host)
        if registry_key == "posos":
            return self._project_posos(query, results, total_available, host)
        return self._project_web_search(query, results, total_available, host)

    @staticmethod
    def _validate_invocation(
        registry_key: str,
        invocation: ConnectorInvocation,
    ) -> tuple[str, int]:
        expected_operation = {
            "drugbank": "lookup", "posos": "guide", "web-search": "search",
        }[registry_key]
        if invocation.operation != expected_operation:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")
        arguments = invocation.arguments
        if not isinstance(arguments, dict) or set(arguments) - {"query", "max_results"}:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        query = arguments.get("query")
        max_results = arguments.get("max_results", 5)
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > MAX_QUERY_CHARS
            or any(char in query for char in "\r\n\x00")
            or not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or not 1 <= max_results <= MAX_RESULTS
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        if invocation.data_classification != "deidentified":
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED"
            )
        try:
            redaction = redact_payload(query)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_CHECK_FAILED"
            ) from exc
        if redaction.redaction_applied or "<REDACTED:" in query.upper():
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED"
            )
        return query.strip(), max_results

    def _validated_endpoint(self, registry_key: str) -> tuple[str, str]:
        endpoint = self._endpoints[registry_key]
        if not endpoint:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            )
        try:
            parsed = urlsplit(endpoint)
            host = (parsed.hostname or "").rstrip(".").casefold()
            port = parsed.port
        except ValueError as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            ) from exc
        loopback_test = (
            self._allow_loopback_http_for_testing
            and parsed.scheme.casefold() == "http"
            and host in {"127.0.0.1", "localhost", "::1"}
            and port is not None
            and 1024 <= port <= 65535
        )
        if (
            not host
            or (parsed.scheme.casefold() != "https" and not loopback_test)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (not loopback_test and port not in (None, 443))
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            )
        return endpoint, host

    def _credential(self, registry_key: str) -> str:
        service = "web_search" if registry_key == "web-search" else registry_key
        try:
            token = self._credential_resolver(service)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            ) from exc
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or any(char in token for char in "\r\n\x00")
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            )
        return token

    @staticmethod
    def _validate_envelope(
        registry_key: str,
        response: dict[str, Any],
        max_results: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if set(response) - {"contract", "provider", "total_available", "results"}:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        results = response.get("results")
        total = response.get("total_available")
        if (
            response.get("contract") != GATEWAY_RESPONSE_CONTRACT
            or response.get("provider") != registry_key
            or not isinstance(results, list)
            or len(results) > max_results
            or any(not isinstance(item, dict) for item in results)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or total < len(results)
            or total > 1_000_000_000
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        return results, total

    @staticmethod
    def _project_drugbank(
        query: str,
        results: list[dict[str, Any]],
        total: int,
        host: str,
    ) -> dict[str, Any]:
        drugs: list[dict[str, Any]] = []
        for item in results:
            drugbank_id = _text(item.get("drugbank_id"), 16, required=True)
            if _DRUGBANK_ID_RE.fullmatch(drugbank_id) is None:
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
            interactions_raw = item.get("interactions", [])
            if not isinstance(interactions_raw, list) or len(interactions_raw) > 20:
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
            interactions = []
            for interaction in interactions_raw:
                if not isinstance(interaction, dict):
                    raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
                interactions.append({
                    "drug": _text(interaction.get("drug"), 300, required=True),
                    "severity": _text(interaction.get("severity"), 64),
                    "description": _text(interaction.get("description"), 2000),
                    "source_url": _safe_reference_url(interaction.get("source_url")),
                })
            drugs.append({
                "drugbank_id": drugbank_id,
                "name": _text(item.get("name"), 300, required=True),
                "description": _text(item.get("description"), 3000),
                "indication": _text(item.get("indication"), 3000),
                "interactions": interactions,
                "source_url": _safe_reference_url(item.get("source_url")),
            })
        return GovernedExternalRegistryProvider._output(
            provider="DrugBank licensed gateway", query=query, total=total,
            key="drugs", results=drugs, host=host,
            clinical_use="licensed_drug_reference_clinician_review_required",
        )

    @staticmethod
    def _project_posos(
        query: str,
        results: list[dict[str, Any]],
        total: int,
        host: str,
    ) -> dict[str, Any]:
        guidance = []
        for item in results:
            citations_raw = item.get("citations", [])
            if not isinstance(citations_raw, list) or len(citations_raw) > 20:
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
            citations = []
            for citation in citations_raw:
                if not isinstance(citation, dict):
                    raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
                citations.append({
                    "title": _text(citation.get("title"), 500, required=True),
                    "url": _safe_reference_url(citation.get("url"), required=True),
                })
            guidance.append({
                "medication": _text(item.get("medication"), 300, required=True),
                "summary": _text(item.get("summary"), 4000, required=True),
                "contraindications": _string_list(
                    item.get("contraindications", []), items=30, chars=1000,
                ),
                "interactions": _string_list(
                    item.get("interactions", []), items=30, chars=1000,
                ),
                "citations": citations,
            })
        return GovernedExternalRegistryProvider._output(
            provider="POSOS licensed gateway", query=query, total=total,
            key="guidance", results=guidance, host=host,
            clinical_use="licensed_medication_guidance_clinician_review_required",
        )

    @staticmethod
    def _project_web_search(
        query: str,
        results: list[dict[str, Any]],
        total: int,
        host: str,
    ) -> dict[str, Any]:
        projected = [{
            "title": _text(item.get("title"), 1000, required=True),
            "url": _safe_reference_url(item.get("url"), required=True),
            "snippet": _text(item.get("snippet"), 3000),
            "source": _text(item.get("source"), 300),
            "published": _text(item.get("published"), 64),
        } for item in results]
        return GovernedExternalRegistryProvider._output(
            provider="privacy-governed web search gateway", query=query,
            total=total, key="results", results=projected, host=host,
            clinical_use="web_reference_clinician_verification_required",
        )

    @staticmethod
    def _output(
        *,
        provider: str,
        query: str,
        total: int,
        key: str,
        results: list[dict[str, Any]],
        host: str,
        clinical_use: str,
    ) -> dict[str, Any]:
        return {
            "provider": provider,
            "query": query,
            "total_available": total,
            "returned": len(results),
            key: results,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "authoritative": False,
            "clinical_use": clinical_use,
            "live_external_performed": True,
            "gateway_host": host,
            "disclaimer": (
                "Reference output from a configured external provider; verify the "
                "licensed source record and obtain qualified clinician review."
            ),
        }

    def status(self) -> dict[str, Any]:
        providers: dict[str, dict[str, Any]] = {}
        for key in sorted(EXTERNAL_REGISTRY_KEYS):
            endpoint_valid = False
            host = ""
            try:
                _, host = self._validated_endpoint(key)
                endpoint_valid = True
            except ConnectorExecutionError:
                pass
            service = "web_search" if key == "web-search" else key
            try:
                credential_configured = bool(self._credential_resolver(service))
            except Exception:
                credential_configured = False
            egress_approved = bool(host and self._host_authorizer(host) is True)
            tenant_opt_in_count = (
                len(self._web_tenant_opt_ins) if key == "web-search" else None
            )
            policy_ready = (
                self._web_provider_opt_in and bool(self._web_tenant_opt_ins)
                if key == "web-search" else True
            )
            providers[key] = {
                "configured": bool(
                    endpoint_valid
                    and credential_configured
                    and egress_approved
                    and self._region
                    and policy_ready
                ),
                "endpoint_configured": endpoint_valid,
                "credential_configured": credential_configured,
                "egress_approved": egress_approved,
                "region_configured": bool(self._region),
                "commercial_licence_required": key in {"drugbank", "posos"},
                "provider_opt_in": (
                    self._web_provider_opt_in if key == "web-search" else None
                ),
                "tenant_opt_in_count": tenant_opt_in_count,
            }
        return {
            "keys": sorted(EXTERNAL_REGISTRY_KEYS),
            "contract": GATEWAY_RESPONSE_CONTRACT,
            "deidentified_queries_only": True,
            "live_external_verified": False,
            "providers": providers,
        }


__all__ = [
    "EXTERNAL_REGISTRY_KEYS",
    "GATEWAY_REQUEST_CONTRACT",
    "GATEWAY_RESPONSE_CONTRACT",
    "GovernedExternalRegistryProvider",
]
