"""RuntimeRunResult — unified structured output from AgentRunner and PlatformRuntime.

Every agent execution returns this schema. Callers (API layer, ReviewCodingService,
shadow diff) depend on these fields being present.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RuntimeRunResult:
    """Unified structured result from any agent execution.

    Fields:
        run_id: unique run identifier (hex string)
        agent_ref: canonical agent reference (publisher/name@version)
        status: "success" | "error" | "timeout" | "fallback"
        output: raw LLM/provider output text
        structured: parsed structured output (dict), if the agent returned JSON
        primary_diagnosis: {"code": str, "description": str, "confidence": float}
        secondary_diagnoses: list of {code, description, confidence}
        procedures: list of {code, description, confidence}
        issues_found: list of {severity, message, code, suggestion}
        audit_trail: list of {step, result, duration_ms}
        processing_time_ms: total wall-clock time
        token_usage: {"input_tokens": int, "output_tokens": int}
        errors: list of structured error dicts
        metadata: arbitrary extra fields
    """

    run_id: str = ""
    agent_ref: str = ""
    status: str = "success"  # success | error | timeout | fallback

    # Output
    output: str = ""
    structured: dict[str, Any] | None = None

    # Medical coding specific
    primary_diagnosis: dict[str, Any] = field(default_factory=dict)
    secondary_diagnoses: list[dict[str, Any]] = field(default_factory=list)
    procedures: list[dict[str, Any]] = field(default_factory=list)
    issues_found: list[dict[str, Any]] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    # Metrics
    processing_time_ms: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    # Errors (empty list = no errors)
    errors: list[dict[str, Any]] = field(default_factory=list)

    # Extensible
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runner_output(cls, runner_result: dict, agent_ref: str = "") -> "RuntimeRunResult":
        """Build from AgentRunner.run() return dict."""
        output = runner_result.get("output", "")
        structured = None
        try:
            import json
            structured = json.loads(output) if isinstance(output, str) and output.strip().startswith("{") else None
        except Exception:
            pass

        return cls(
            run_id=runner_result.get("review_id", ""),
            agent_ref=agent_ref,
            status="success" if runner_result.get("review_id") else "error",
            output=output,
            structured=structured,
            primary_diagnosis=structured.get("primary_diagnosis", {}) if structured else {},
            secondary_diagnoses=structured.get("secondary_diagnoses", []) if structured else [],
            procedures=structured.get("procedures", []) if structured else [],
            issues_found=structured.get("issues_found", []) if structured else [],
            audit_trail=runner_result.get("state_log", {}).get("entries", []) if runner_result.get("state_log") else [],
            processing_time_ms=runner_result.get("processing_time_ms", 0),
            token_usage={"input_tokens": 0, "output_tokens": 0},
            errors=[],
            metadata={
                "agent_name": runner_result.get("agent_name", ""),
                "agent_version": runner_result.get("agent_version", ""),
                "chain_valid": runner_result.get("state_log", {}).get("chain_valid", True) if runner_result.get("state_log") else True,
            },
        )

    @classmethod
    def error_result(cls, agent_ref: str, error_code: str, message: str, run_id: str = "") -> "RuntimeRunResult":
        """Build an error result."""
        return cls(
            run_id=run_id or "error",
            agent_ref=agent_ref,
            status="error",
            errors=[{"code": error_code, "message": message}],
            processing_time_ms=0,
        )

    @classmethod
    def fallback_result(cls, agent_ref: str, message: str, run_id: str = "") -> "RuntimeRunResult":
        """Build a fallback result."""
        return cls(
            run_id=run_id or "fallback",
            agent_ref=agent_ref,
            status="fallback",
            output=message,
            metadata={"fallback_reason": message},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_api_response(self) -> dict[str, Any]:
        """API-friendly response (excludes internal fields)."""
        d = self.to_dict()
        d.pop("metadata", None)
        return d
