"""CDI Core Agent runtime (Phase 5 Track D).

Public modules:
    nlq_gate       — Non-leading Query gate (NLQ-001..009)
    orchestrator   — CDI Orchestrator (encounter_synthesis → ... → specialist_trace)
    domain         — Domain models (DocumentationGap, ProviderQuery, CDICase, etc.)

Imported by:
    backend/app/icoder/agent_runtime/a2a_facade.py (CDI A2A dispatch)
    backend/app/api/cdi.py (REST API, Track D Gate 9)
    backend/tests/unit/icoder/test_phase5_track_d_*.py
"""

from .domain import (  # noqa: F401
    CDICase,
    CodingSpecificityItem,
    DocumentType,
    DocumentationGap,
    EncounterSummary,
    EvidenceSpan,
    GapType,
    ProviderQuery,
    ResponseOption,
    ResponseOptionCategory,
    RiskFlag,
    RiskFlagCategory,
    SpecialistTraceEntry,
    claim_evidence_alignment_score,
    classify_gap_type,
    classify_gap_type_with_confidence,
    classify_response_option,
)
from .nlq_gate import (  # noqa: F401
    NLQGateResult,
    ProviderQueryForGate,
    RuleResult,
    evaluate as evaluate_nlq,
)
from .orchestrator import (  # noqa: F401
    STAGES,
    CDIOrchestrator,
    StageRunner,
    stub_runner,
)
from .real_runner import (  # noqa: F401
    RealCDIRunner,
    StageTrace,
)
from .clinician_response import (  # noqa: F401
    ClinicianResponseValue,
    DocumentDiff,
    RevalidationOutcome,
    RevalidationResult,
    compute_document_diff,
    process_clinician_response,
    revalidate_gap,
)
from .nlq_semantic import (  # noqa: F401
    SemanticReviewResult,
    review_query as review_query_semantic,
)
from .clinician_view import (  # noqa: F401
    is_safe_for_clinician,
    strip_codes_from_text,
    to_clinician_view,
)

__all__ = [
    # domain
    "CDICase",
    "CodingSpecificityItem",
    "DocumentType",
    "DocumentationGap",
    "EncounterSummary",
    "EvidenceSpan",
    "GapType",
    "ProviderQuery",
    "ResponseOption",
    "ResponseOptionCategory",
    "RiskFlag",
    "RiskFlagCategory",
    "SpecialistTraceEntry",
    "claim_evidence_alignment_score",
    "classify_gap_type",
    "classify_gap_type_with_confidence",
    "classify_response_option",
    # nlq gate
    "NLQGateResult",
    "ProviderQueryForGate",
    "RuleResult",
    "evaluate_nlq",
    # orchestrator
    "CDIOrchestrator",
    "STAGES",
    "StageRunner",
    "stub_runner",
    # real runner (Phase 5 Track D P0 Gate 2)
    "RealCDIRunner",
    "StageTrace",
    # clinician response workflow
    "ClinicianResponseValue",
    "DocumentDiff",
    "RevalidationOutcome",
    "RevalidationResult",
    "compute_document_diff",
    "process_clinician_response",
    "revalidate_gap",
    # nlq semantic reviewer (Phase 5 Track D P0 Gate 4 Step 5)
    "SemanticReviewResult",
    "review_query_semantic",
    # clinician view de-coding transform (Phase 5 Track D P0 Gate 4 / PDF §A6)
    "is_safe_for_clinician",
    "strip_codes_from_text",
    "to_clinician_view",
]
