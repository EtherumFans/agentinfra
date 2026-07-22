"""Coding Expert — Corti public §3.2 key 2 of 9 (A1B-AE.7 wrapper).

Corti public docs describe this Expert as assigning diagnosis and procedure
codes from clinical notes. iCoDer already ships ``icoder/medical-coding-agent@2.0.0``
as a certified Pack (Phase 5 Track C/D). A1B-AE.7 lands a thin Expert
wrapper that:

1. Registers under canonical_key='coding-expert' with
   corti_alignment='CORTI_ALIGNED' (iCoDer's medical-coding-agent is
   evidence-first, rule-validated, human-review-required — matches Corti's
   public Expert description at the contract surface).

2. Delegates execution to the existing Pack via the Agent Runner /
   Coding Compliance Orchestrator. No clinical logic is duplicated here.

3. Surfaces the same output contract (MedicalCodingAgentOutputV2) that
   the Pack exposes, so Expert consumers and Pack consumers see the same
   artifact.

This wrapper does NOT re-implement the MedCodER 5-stage pipeline. The
pipeline lives in ``icoder_runtime.providers.medical_coding`` and is
invoked via the Pack's runtime modes (``corti_like_fast`` /
``medcoder_deep``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CODING_EXPERT_CANONICAL_KEY = "coding-expert"
CODING_EXPERT_NAME = "Coding Expert"
CODING_EXPERT_DELEGATES_TO = "icoder/medical-coding-agent@2.0.0"
CODING_EXPERT_OUTPUT_CONTRACT = "icoder/MedicalCodingAgentOutputV2/v1"


@dataclass
class CodingExpertDelegation:
    """Descriptor of a Coding Expert delegation call.

    The Coding Expert itself does not run any model. It captures the
    delegation target + runtime mode so consumers (Agent runtime, audit
    log) can verify that the call is routed to the right Pack.
    """

    input_text: str
    delegates_to: str = CODING_EXPERT_DELEGATES_TO
    runtime_mode: str = "corti_like_fast"
    output_contract: str = CODING_EXPERT_OUTPUT_CONTRACT
    human_review_required: bool = True
    phi_redacted: bool = True
    production_writeback_blocked: bool = True
    notes: str = ""


@dataclass
class CodingExpertResult:
    """Result of a Coding Expert call.

    The Coding Expert returns the delegated Pack's raw output plus a
    provenance block. Callers MUST honour ``human_review_required`` —
    Corti §3.2 coding-expert is NEVER auto-writeback.
    """

    delegation: CodingExpertDelegation
    pack_output: dict[str, Any] = field(default_factory=dict)
    extracted_from_pack: bool = False
    notes: str = ""


def delegate(
    input_text: str,
    *,
    runtime_mode: str = "corti_like_fast",
    pack_output: dict[str, Any] | None = None,
) -> CodingExpertResult:
    """Wrap a call to ``icoder/medical-coding-agent@2.0.0``.

    The wrapper is deliberately thin: A1B-AE.7's scope is to land the
    Expert Registry row for Corti §3.2 key 2/9 and document the
    delegation surface. The actual clinical logic runs inside the Pack
    (see ``official_agents/medical_coding/agent_pack.json``) and is
    invoked by the Agent Runner when a consumer routes a task to this
    Expert.

    If the caller supplies ``pack_output`` (e.g. from an already-run
    Agent Runner invocation), the wrapper surfaces it verbatim with
    ``extracted_from_pack=True``. If not, the wrapper returns an empty
    ``pack_output`` with a note that the caller must drive the Pack
    execution separately.
    """
    delegation = CodingExpertDelegation(
        input_text=input_text,
        runtime_mode=runtime_mode,
        notes=(
            "Delegates to icoder/medical-coding-agent@2.0.0 via the Agent "
            "Runner. Corti §3.2 coding-expert contract surface matches "
            "iCoDer Pack output_contract icoder/MedicalCodingAgentOutputV2/v1."
        ),
    )

    if pack_output is None:
        return CodingExpertResult(
            delegation=delegation,
            pack_output={},
            extracted_from_pack=False,
            notes=(
                "Wrapper only — Pack execution is the caller's "
                "responsibility (invoke AgentRunner with "
                "icoder/medical-coding-agent@2.0.0)."
            ),
        )

    return CodingExpertResult(
        delegation=delegation,
        pack_output=pack_output,
        extracted_from_pack=True,
        notes="Pack output surfaced verbatim through Coding Expert wrapper.",
    )


__all__ = [
    "CODING_EXPERT_CANONICAL_KEY",
    "CODING_EXPERT_NAME",
    "CODING_EXPERT_DELEGATES_TO",
    "CODING_EXPERT_OUTPUT_CONTRACT",
    "CodingExpertDelegation",
    "CodingExpertResult",
    "delegate",
]
