"""DrugBank Expert — Corti public §3.2 key 4 of 9 (A1B-AE.7 stub).

Corti public docs describe this Expert as providing drug information and
interaction lookups backed by the DrugBank commercial knowledge base.

iCoDer's A1B-AE.7 scope is a STUB that:

1. Registers under canonical_key='drugbank' with
   corti_alignment='CORTI_REFERENCE' (iCoDer has no DrugBank licence;
   live lookup is deferred until a Provider supplies credentials).

2. Returns a deterministic offline result indicating that no live
   lookup was performed. Caller MUST treat results as empty.

3. NEVER falls back to an LLM to "invent" drug interactions. A
   hallucinated interaction is worse than no answer — silent LLM
   fallback for drug-interaction queries is a patient-safety footgun.

The stub is gated behind the External-Expert Gate (see
``external_expert_gate.py``) which enforces the licence-required +
egress-policy checks before any live call would be allowed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    """Offline stub for DrugBank lookup.

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
            "STUB: DrugBank live lookup deferred (A1B-AE.7 scope = Expert "
            "Registry entry only). No LLM fallback — drug interaction data "
            "requires a licensed source. Future enhancement: wire to "
            "DrugBank API when a Provider supplies credentials, gated by "
            "the External-Expert Gate (Charter §6 egress policy)."
        ),
    )


__all__ = [
    "DRUGBANK_EXPERT_CANONICAL_KEY",
    "DRUGBANK_EXPERT_NAME",
    "DRUGBANK_LICENCE_REQUIRED",
    "DRUGBANK_LLM_FALLBACK_ALLOWED",
    "DrugBankResult",
    "lookup",
]
