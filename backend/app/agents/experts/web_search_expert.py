"""Web Search Expert compatibility API and governed live adapter.

Corti public docs describe this Expert as searching and retrieving
up-to-date web content. iCoDer's default policy is DISABLED — live web
egress introduces PHI-leak risk (search engines log queries) and is
not needed for the medical-coding/CDI/DRG-DIP core flows.

A1B-AE.7 lands:

1. canonical_key='web-search' with corti_alignment='CORTI_REFERENCE'.
2. A 3-value policy gate: DISABLED_BY_DEFAULT / OPT_IN_PER_PROVIDER /
   ENABLED_FOR_TENANT. Default = DISABLED_BY_DEFAULT.
3. A non-networking compatibility function plus ``search_async`` for the
   privacy-governed, dual-opt-in Registry provider.

Charter §6 egress policy is enforced centrally by
``external_expert_gate.py`` so individual Experts don't each re-implement
the region/egress check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services.connector_executor import ConnectorInvocation


WEB_SEARCH_EXPERT_CANONICAL_KEY = "web-search"
WEB_SEARCH_EXPERT_NAME = "Web Search Expert"

WEB_SEARCH_POLICY_DISABLED = "DISABLED_BY_DEFAULT"
WEB_SEARCH_POLICY_OPT_IN = "OPT_IN_PER_PROVIDER"
WEB_SEARCH_POLICY_ENABLED = "ENABLED_FOR_TENANT"
WEB_SEARCH_POLICY_VALUES = (
    WEB_SEARCH_POLICY_DISABLED,
    WEB_SEARCH_POLICY_OPT_IN,
    WEB_SEARCH_POLICY_ENABLED,
)


@dataclass
class WebSearchResult:
    query: str
    results: list[dict[str, Any]] = field(default_factory=list)
    live_search_performed: bool = False
    policy: str = WEB_SEARCH_POLICY_DISABLED
    notes: str = ""


def search(
    query: str,
    *,
    policy: str | None = None,
    tenant_opt_in: bool = False,
    provider_opt_in: bool = False,
) -> WebSearchResult:
    """Non-networking Web Search policy compatibility call.

    Policy resolution (first non-None wins):
    1. Explicit ``policy`` argument.
    2. ``WEB_SEARCH_POLICY_ENABLED`` if both tenant_opt_in and provider_opt_in.
    3. ``WEB_SEARCH_POLICY_OPT_IN`` if exactly one is set.
    4. ``WEB_SEARCH_POLICY_DISABLED`` (default).

    Live execution is explicit via ``search_async`` so a synchronous caller
    can never accidentally exfiltrate a query merely by changing a flag.
    """
    resolved_policy = _resolve_policy(policy, tenant_opt_in, provider_opt_in)

    if not query or not query.strip():
        return WebSearchResult(
            query=query,
            results=[],
            live_search_performed=False,
            policy=resolved_policy,
            notes="empty query",
        )

    return WebSearchResult(
        query=query.strip(),
        results=[],
        live_search_performed=False,
        policy=resolved_policy,
        notes=(
            "OFFLINE_COMPATIBILITY: no network call was requested. Use "
            "search_async through the governed Agent Connector runtime; "
            "provider and tenant opt-in remain mandatory."
        ),
    )


async def search_async(
    query: str,
    *,
    organization_id: str,
    provider: Callable[[str, ConnectorInvocation], Awaitable[dict[str, Any]]],
    max_results: int = 5,
) -> WebSearchResult:
    """Execute the dual-opt-in privacy search gateway."""

    output = await provider("web-search", ConnectorInvocation(
        organization_id=organization_id,
        agent_id="web-search",
        connector_id="web-search",
        operation="search",
        arguments={"query": query, "max_results": max_results},
        data_classification="deidentified",
        purpose_of_use="treatment",
    ))
    results = output.get("results")
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise RuntimeError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    return WebSearchResult(
        query=query.strip(),
        results=results,
        live_search_performed=bool(output.get("live_external_performed")),
        policy=WEB_SEARCH_POLICY_ENABLED,
        notes="privacy-governed Registry gateway; source verification required",
    )


def _resolve_policy(
    policy: str | None,
    tenant_opt_in: bool,
    provider_opt_in: bool,
) -> str:
    if policy is not None:
        if policy not in WEB_SEARCH_POLICY_VALUES:
            raise ValueError(
                f"policy must be one of {WEB_SEARCH_POLICY_VALUES}; got {policy!r}"
            )
        return policy
    if tenant_opt_in and provider_opt_in:
        return WEB_SEARCH_POLICY_ENABLED
    if tenant_opt_in or provider_opt_in:
        return WEB_SEARCH_POLICY_OPT_IN
    return WEB_SEARCH_POLICY_DISABLED


__all__ = [
    "WEB_SEARCH_EXPERT_CANONICAL_KEY",
    "WEB_SEARCH_EXPERT_NAME",
    "WEB_SEARCH_POLICY_DISABLED",
    "WEB_SEARCH_POLICY_OPT_IN",
    "WEB_SEARCH_POLICY_ENABLED",
    "WEB_SEARCH_POLICY_VALUES",
    "WebSearchResult",
    "search",
    "search_async",
]
