"""POSOS Expert — Corti public §3.2 key 5 of 9 (A1B-AE.7 stub).

Corti public docs describe this Expert as providing medication guidance
and prescribing decision support backed by the POSOS commercial service.

iCoDer's A1B-AE.7 scope mirrors the DrugBank stub pattern:

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
from typing import Any


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
    """Offline stub for POSOS prescribing guidance.

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
            "STUB: POSOS live lookup deferred (A1B-AE.7 scope = Expert "
            "Registry entry only). No LLM fallback — prescribing guidance "
            "requires a licensed source. Future enhancement: wire to POSOS "
            "API when a Provider supplies credentials, gated by the "
            "External-Expert Gate."
        ),
    )


__all__ = [
    "POSOS_EXPERT_CANONICAL_KEY",
    "POSOS_EXPERT_NAME",
    "POSOS_LICENCE_REQUIRED",
    "POSOS_LLM_FALLBACK_ALLOWED",
    "PososResult",
    "guide",
]
