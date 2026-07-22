"""Clinical Trials Expert — Corti public §3.2 key 8 of 9 (A1B-AE.6 stub).

Corti public docs describe this Expert as searching clinicaltrials.gov
for active trials. iCoDer's A1B-AE.6 scope mirrors the PubMed stub
pattern: register the Expert, return an empty offline result, flag
live_search_performed=False.

Future enhancement: wire to clinicaltrials.gov API v2 with
region-aware egress.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CLINICAL_TRIALS_EXPERT_CANONICAL_KEY = "clinical-trials"
CLINICAL_TRIALS_EXPERT_NAME = "Clinical Trials Expert"


@dataclass
class ClinicalTrialsResult:
    query: str
    trials: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    live_search_performed: bool = False
    notes: str = ""


def search(
    query: str,
    *,
    condition: str | None = None,
    location: str | None = None,
    max_results: int = 10,
) -> ClinicalTrialsResult:
    """Offline stub for clinicaltrials.gov search.

    Returns empty result with live_search_performed=False. Caller
    MUST check this flag before treating results as actionable.
    """
    if not query or not query.strip():
        return ClinicalTrialsResult(
            query=query,
            trials=[],
            total=0,
            live_search_performed=False,
            notes="empty query",
        )

    return ClinicalTrialsResult(
        query=query.strip(),
        trials=[],
        total=0,
        live_search_performed=False,
        notes=(
            "STUB: live clinicaltrials.gov integration deferred (A1B-AE.6 "
            "scope = Expert Registry entry only). Treat result as empty "
            "for trial matching. Future enhancement: wire to CT.gov API v2 "
            "with region-aware egress per Charter §6."
        ),
    )


__all__ = [
    "CLINICAL_TRIALS_EXPERT_CANONICAL_KEY",
    "CLINICAL_TRIALS_EXPERT_NAME",
    "ClinicalTrialsResult",
    "search",
]
