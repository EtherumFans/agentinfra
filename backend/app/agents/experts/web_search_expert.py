"""Web Search Expert — Corti public §3.2 key 6 of 9 (A1B-AE.7 policy gate).

Corti public docs describe this Expert as searching and retrieving
up-to-date web content. iCoDer's default policy is DISABLED — live web
egress introduces PHI-leak risk (search engines log queries) and is
not needed for the medical-coding/CDI/DRG-DIP core flows.

A1B-AE.7 lands:

1. canonical_key='web-search' with corti_alignment='CORTI_REFERENCE'.
2. A 3-value policy gate: DISABLED_BY_DEFAULT / OPT_IN_PER_PROVIDER /
   ENABLED_FOR_TENANT. Default = DISABLED_BY_DEFAULT.
3. An offline stub that returns empty + policy indicator. No live web
   call is made in A1B-AE.7.

Charter §6 egress policy is enforced centrally by
``external_expert_gate.py`` so individual Experts don't each re-implement
the region/egress check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    """Offline-first Web Search stub.

    Policy resolution (first non-None wins):
    1. Explicit ``policy`` argument.
    2. ``WEB_SEARCH_POLICY_ENABLED`` if both tenant_opt_in and provider_opt_in.
    3. ``WEB_SEARCH_POLICY_OPT_IN`` if exactly one is set.
    4. ``WEB_SEARCH_POLICY_DISABLED`` (default).

    A1B-AE.7 NEVER performs a live web call. Even when policy resolves
    to ENABLED_FOR_TENANT, ``live_search_performed`` stays False — the
    real web-search integration is a future enhancement. The policy
    field tells the caller what *would* be allowed.
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
            "STUB: live web search integration deferred (A1B-AE.7 scope = "
            "Expert Registry entry + policy gate). Default policy is "
            "DISABLED_BY_DEFAULT — live web egress is a PHI-leak risk and "
            "is not needed for core coding/CDI/DRG-DIP flows. Future "
            "enhancement: wire to a privacy-preserving search provider when "
            "policy != DISABLED_BY_DEFAULT, gated by the External-Expert Gate."
        ),
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
]
