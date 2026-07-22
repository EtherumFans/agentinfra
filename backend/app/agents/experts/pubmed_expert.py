"""PubMed Expert — Corti public §3.2 key 7 of 9 (A1B-AE.6 stub).

Corti public docs describe this Expert as searching PubMed for
biomedical literature. iCoDer's A1B-AE.6 scope is a STUB that:

1. Registers under canonical_key='pubmed' with corti_alignment=
   'CORTI_REFERENCE' (Expert Registry entry exists; live PubMed
   API integration is deferred).
2. Returns a deterministic offline result indicating that live
   search has NOT been performed. Caller MUST treat results as
   empty for clinical decision-making.

The stub deliberately does NOT call the live PubMed E-utilities API.
Reasons:
- No API key is configured in dev/CI environments.
- Live external API egress requires Charter §6 region-routing
  compliance (not yet wired through this Expert).
- A1B-AE.6 is about landing the Expert Registry entries; live
  integration is a tech-debt item.

Future enhancement: when live integration lands, swap the stub body
for a real E-utilities fetch. The Expert Registry canonical_key
stays 'pubmed'; the corti_alignment upgrades from CORTI_REFERENCE
to CORTI_ALIGNED at that point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PUBMED_EXPERT_CANONICAL_KEY = "pubmed"
PUBMED_EXPERT_NAME = "PubMed Expert"


@dataclass
class PubMedResult:
    query: str
    articles: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    live_search_performed: bool = False
    notes: str = ""


def search(query: str, max_results: int = 10) -> PubMedResult:
    """Offline stub for PubMed search.

    Returns an empty result with live_search_performed=False. Caller
    MUST check this flag before treating results as actionable.
    """
    if not query or not query.strip():
        return PubMedResult(
            query=query,
            articles=[],
            total=0,
            live_search_performed=False,
            notes="empty query",
        )

    return PubMedResult(
        query=query.strip(),
        articles=[],
        total=0,
        live_search_performed=False,
        notes=(
            "STUB: live PubMed E-utilities integration deferred (A1B-AE.6 "
            "scope = Expert Registry entry only). Treat result as empty "
            "for clinical decision-making. Future enhancement: wire to "
            "NCBI E-utilities with region-aware egress per Charter §6."
        ),
    )


__all__ = [
    "PUBMED_EXPERT_CANONICAL_KEY",
    "PUBMED_EXPERT_NAME",
    "PubMedResult",
    "search",
]
