"""POSOS Expert compatibility API and governed live adapter.

Corti public docs describe this Expert as providing medication guidance
and prescribing decision support backed by the POSOS commercial service.

iCoDer keeps a non-networking compatibility function and provides
``guide_async`` for the configured, governed enterprise gateway.

1. Registers under canonical_key='posos' with
   corti_alignment='CORTI_REFERENCE' (no POSOS licence; live lookup
   deferred).

2. Returns an offline-empty result.

3. NEVER falls back to an LLM for prescribing guidance — same
   patient-safety red line as DrugBank.

Gated behind the External-Expert Gate (``external_expert_gate.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services.connector_executor import ConnectorInvocation


POSOS_EXPERT_CANONICAL_KEY = "posos"
POSOS_EXPERT_NAME = "POSOS Expert"
POSOS_LICENCE_REQUIRED = True
POSOS_LLM_FALLBACK_ALLOWED = False


@dataclass
class PososResult:
    query: str
    guidance: dict[str, Any] = field(default_factory=dict)
    live_lookup_performed: bool = False
    licence_present: bool = False
    notes: str = ""


def guide(
    query: str,
    *,
    licence_token: str | None = None,
) -> PososResult:
    """Non-networking compatibility path for POSOS guidance.

    Returns empty with ``live_lookup_performed=False``. Caller MUST
    check the flag before clinical use. No LLM fallback (same red line
    as DrugBank — prescribing guidance requires a licensed source).
    """
    if not query or not query.strip():
        return PososResult(query=query, notes="empty query")

    return PososResult(
        query=query.strip(),
        guidance={},
        live_lookup_performed=False,
        licence_present=bool(licence_token),
        notes=(
            "OFFLINE_COMPATIBILITY: no network call was requested. Use "
            "guide_async through the governed Agent Connector runtime for "
            "licensed POSOS gateway data. No LLM fallback is permitted."
        ),
    )


async def guide_async(
    query: str,
    *,
    organization_id: str,
    provider: Callable[[str, ConnectorInvocation], Awaitable[dict[str, Any]]],
    max_results: int = 5,
) -> PososResult:
    """Execute the configured POSOS gateway through the governed provider."""

    output = await provider("posos", ConnectorInvocation(
        organization_id=organization_id,
        agent_id="posos",
        connector_id="posos",
        operation="guide",
        arguments={"query": query, "max_results": max_results},
        data_classification="deidentified",
        purpose_of_use="treatment",
    ))
    guidance = output.get("guidance")
    if not isinstance(guidance, list):
        raise RuntimeError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    first = guidance[0] if guidance and isinstance(guidance[0], dict) else {}
    return PososResult(
        query=query.strip(),
        guidance=first,
        live_lookup_performed=bool(output.get("live_external_performed")),
        licence_present=True,
        notes="licensed governed Registry gateway; clinician review required",
    )


__all__ = [
    "POSOS_EXPERT_CANONICAL_KEY",
    "POSOS_EXPERT_NAME",
    "POSOS_LICENCE_REQUIRED",
    "POSOS_LLM_FALLBACK_ALLOWED",
    "PososResult",
    "guide",
    "guide_async",
]
