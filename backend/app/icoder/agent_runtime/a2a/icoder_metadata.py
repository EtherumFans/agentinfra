"""iCoDer-specific metadata fields (SPEC §9).

All iCoDer extensions live in the A2A ``metadata`` namespace per Q2
(no private protocol extensions). Two distinct directions:

1. **RunMetadata** — Orchestrator → Client (response).
2. **DelegationMetadata** — Orchestrator → Expert (outbound request).

These are dataclasses (not Pydantic) — they're wire-shape helpers,
not HTTP-boundary types.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# RunMetadata — Orchestrator → Client
# ---------------------------------------------------------------------------


@dataclass
class RunMetadata:
    """Per-run metadata returned to the client (SPEC §9.2).

    Fields per spec:

    - ``run_id``: M2aRecorder run ID
    - ``trace_id``: M2aRecorder trace ID
    - ``trace_url``: full URL to the trace (e.g., ``/api/m2a/runs/{run_id}``)
    - ``phi_redacted``: bool — true means LLM saw redacted text
    - ``production_writeback_blocked``: bool — always true
    - ``state_history``: list of state-machine states traversed
    - ``expert_invocations``: list of per-expert call records (id, latency_ms, status)
    - ``llm_model``: actual model used (e.g., ``deepseek-v4-flash``)
    - ``total_duration_ms``: total run latency
    - ``interaction_id``: optional client correlation ID
    - ``agent_id``: which agent handled the request
    """

    run_id: str
    trace_id: str
    trace_url: str
    phi_redacted: bool = True
    production_writeback_blocked: bool = True
    state_history: list[str] = field(default_factory=list)
    expert_invocations: list[dict[str, Any]] = field(default_factory=list)
    llm_model: str = ""
    total_duration_ms: int = 0
    interaction_id: str = ""
    agent_id: str = ""

    def to_envelope(self) -> dict[str, Any]:
        """Serialize to wire dict. Drops empty values."""
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
            "phi_redacted": self.phi_redacted,
            "production_writeback_blocked": self.production_writeback_blocked,
            "state_history": list(self.state_history),
        }
        if self.expert_invocations:
            out["expert_invocations"] = list(self.expert_invocations)
        if self.llm_model:
            out["llm_model"] = self.llm_model
        if self.total_duration_ms:
            out["total_duration_ms"] = self.total_duration_ms
        if self.interaction_id:
            out["interaction_id"] = self.interaction_id
        if self.agent_id:
            out["agent_id"] = self.agent_id
        return out

    @classmethod
    def from_envelope(cls, data: dict[str, Any]) -> "RunMetadata":
        """Parse from wire dict. Tolerant of missing optional fields."""
        return cls(
            run_id=str(data.get("run_id", "")),
            trace_id=str(data.get("trace_id", "")),
            trace_url=str(data.get("trace_url", "")),
            phi_redacted=bool(data.get("phi_redacted", True)),
            production_writeback_blocked=bool(
                data.get("production_writeback_blocked", True)
            ),
            state_history=list(data.get("state_history", [])),
            expert_invocations=list(data.get("expert_invocations", [])),
            llm_model=str(data.get("llm_model", "")),
            total_duration_ms=int(data.get("total_duration_ms", 0)),
            interaction_id=str(data.get("interaction_id", "")),
            agent_id=str(data.get("agent_id", "")),
        )


# ---------------------------------------------------------------------------
# DelegationMetadata — Orchestrator → Expert (outbound)
# ---------------------------------------------------------------------------


@dataclass
class DelegationMetadata:
    """Per-delegation metadata sent to an Expert (SPEC §9.1).

    Fields per spec:

    - ``delegated_by``: format ``orchestrator-{run_id}``
    - ``expert_required``: true = critical, false = best-effort
    - ``tool_constraints``: list of MCP tool names the Expert may call
    - ``timeout_ms``: per-expert timeout (default 30000)
    - ``retry_policy``: per-expert retry policy (Phase 1 not honored)
    """

    delegated_by: str
    expert_required: bool = True
    tool_constraints: list[str] = field(default_factory=list)
    timeout_ms: int = 30000
    retry_policy: dict[str, Any] = field(default_factory=dict)

    def to_envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "delegated_by": self.delegated_by,
            "expert_required": self.expert_required,
        }
        if self.tool_constraints:
            out["tool_constraints"] = list(self.tool_constraints)
        if self.timeout_ms:
            out["timeout_ms"] = self.timeout_ms
        if self.retry_policy:
            out["retry_policy"] = dict(self.retry_policy)
        return out

    @classmethod
    def from_envelope(cls, data: dict[str, Any]) -> "DelegationMetadata":
        return cls(
            delegated_by=str(data.get("delegated_by", "")),
            expert_required=bool(data.get("expert_required", True)),
            tool_constraints=list(data.get("tool_constraints", [])),
            timeout_ms=int(data.get("timeout_ms", 30000)),
            retry_policy=dict(data.get("retry_policy", {})),
        )


# ---------------------------------------------------------------------------
# Schema identifier constants — referenced in DataPart.data.schema
# ---------------------------------------------------------------------------


SCHEMA_MEDICAL_CODING_OUTPUT = "icoder/MedicalCodingOutputSchema/v1"
SCHEMA_MEDICAL_CODING_INPUT = "icoder/MedicalCodingInputSchema/v1"
SCHEMA_DRG_GROUPING_OUTPUT = "icoder/DrgGroupingOutputSchema/v1"
SCHEMA_COMPLIANCE_OUTPUT = "icoder/ComplianceOutputSchema/v1"
SCHEMA_EVIDENCE_SPAN = "icoder/EvidenceSpan/v1"

ALL_ICODER_SCHEMAS: tuple[str, ...] = (
    SCHEMA_MEDICAL_CODING_OUTPUT,
    SCHEMA_MEDICAL_CODING_INPUT,
    SCHEMA_DRG_GROUPING_OUTPUT,
    SCHEMA_COMPLIANCE_OUTPUT,
    SCHEMA_EVIDENCE_SPAN,
)


__all__ = [
    "ALL_ICODER_SCHEMAS",
    "DelegationMetadata",
    "RunMetadata",
    "SCHEMA_COMPLIANCE_OUTPUT",
    "SCHEMA_DRG_GROUPING_OUTPUT",
    "SCHEMA_EVIDENCE_SPAN",
    "SCHEMA_MEDICAL_CODING_INPUT",
    "SCHEMA_MEDICAL_CODING_OUTPUT",
    "asdict",
]