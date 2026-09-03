"""DrugBank Expert compatibility API and governed live adapter.

Corti public docs describe this Expert as providing drug information and
interaction lookups backed by the DrugBank commercial knowledge base.

iCoDer exposes two deliberately distinct paths:

1. Registers under canonical_key='drugbank' with
   corti_alignment='CORTI_REFERENCE' (iCoDer has no DrugBank licence;
   live lookup is deferred until a Provider supplies credentials).

2. ``lookup`` is a deterministic, non-networking compatibility call.
   ``lookup_async`` executes the configured governed Registry provider.

3. NEVER falls back to an LLM to "invent" drug interactions. A
   hallucinated interaction is worse than no answer — silent LLM
   fallback for drug-interaction queries is a patient-safety footgun.

The live path is gated by the Agent Connector runtime, which enforces a
commercial credential, fixed HTTPS egress, region policy, deidentification,
bounded responses and audit logging. No vendor API shape is invented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services.connector_executor import ConnectorInvocation


DRUGBANK_EXPERT_CANONICAL_KEY = "drugbank"
DRUGBANK_EXPERT_NAME = "DrugBank Expert"
DRUGBANK_LICENCE_REQUIRED = True
DRUGBANK_LLM_FALLBACK_ALLOWED = False  # patient-safety red line


@dataclass
class DrugBankResult:
    query: str
    drug_info: dict[str, Any] = field(default_factory=dict)
    interactions: list[dict[str, Any]] = field(default_factory=list)
    live_lookup_performed: bool = False
    licence_present: bool = False
    notes: str = ""


def lookup(
    query: str,
    *,
    licence_token: str | None = None,
) -> DrugBankResult:
    """Non-networking compatibility lookup.

    Returns an empty result with ``live_lookup_performed=False``. The
    caller MUST check this flag before treating results as actionable.

    A1B-AE.7 explicitly does NOT implement an LLM fallback. Drug
    interaction data must come from a licensed source; an LLM-guessed
    interaction list is a patient-safety footgun and is forbidden by
    Charter §6 (external-data egress) + the Coding Expert red lines.
    """
    if not query or not query.strip():
        return DrugBankResult(
            query=query,
            notes="empty query",
        )

    return DrugBankResult(
        query=query.strip(),
        drug_info={},
        interactions=[],
        live_lookup_performed=False,
        licence_present=bool(licence_token),
        notes=(
            "OFFLINE_COMPATIBILITY: no network call was requested. Use "
            "lookup_async through the governed Agent Connector runtime for "
            "licensed DrugBank gateway data. No LLM fallback is permitted."
        ),
    )


async def lookup_async(
    query: str,
    *,
    organization_id: str,
    provider: Callable[[str, ConnectorInvocation], Awaitable[dict[str, Any]]],
    max_results: int = 5,
) -> DrugBankResult:
    """Execute the configured DrugBank gateway through the governed provider."""

    output = await provider("drugbank", ConnectorInvocation(
        organization_id=organization_id,
        agent_id="drugbank",
        connector_id="drugbank",
        operation="lookup",
        arguments={"query": query, "max_results": max_results},
        data_classification="deidentified",
        purpose_of_use="treatment",
    ))
    drugs = output.get("drugs")
    if not isinstance(drugs, list):
        raise RuntimeError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    first = drugs[0] if drugs and isinstance(drugs[0], dict) else {}
    interactions = first.get("interactions", [])
    if not isinstance(interactions, list):
        raise RuntimeError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
    return DrugBankResult(
        query=query.strip(),
        drug_info={key: value for key, value in first.items() if key != "interactions"},
        interactions=interactions,
        live_lookup_performed=bool(output.get("live_external_performed")),
        licence_present=True,
        notes="licensed governed Registry gateway; clinician review required",
    )


__all__ = [
    "DRUGBANK_EXPERT_CANONICAL_KEY",
    "DRUGBANK_EXPERT_NAME",
    "DRUGBANK_LICENCE_REQUIRED",
    "DRUGBANK_LLM_FALLBACK_ALLOWED",
    "DrugBankResult",
    "lookup",
    "lookup_async",
]
