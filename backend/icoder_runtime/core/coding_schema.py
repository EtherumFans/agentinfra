"""*** DEPRECATED — moved to official_agents/medical_coding/schema.py ***

MedicalCodingOutputSchema is NOT a Runtime Core concept.
It belongs to the Medical Coding Official Agent Pack.

This file silently re-exports for backward compatibility.
New code should import from: official_agents.medical_coding.schema
TODO(v2.1): Remove this file after all callers are migrated.
"""

# Silent re-export for backward compat
from official_agents.medical_coding.schema import (
    MedicalCodingOutputSchema,
    DiagnosisEntry,
    ProcedureEntry,
    CodingIssue,
    CodingEngineAdapter,
    PromptLLMAdapter,
)

__all__ = [
    "MedicalCodingOutputSchema",
    "DiagnosisEntry",
    "ProcedureEntry",
    "CodingIssue",
    "CodingEngineAdapter",
    "PromptLLMAdapter",
]
