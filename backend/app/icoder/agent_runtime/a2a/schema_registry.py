"""iCoDer Schema Registry (SPEC §9.3).

A2A DataPart carries ``{"schema": "icoder/.../v1", "value": {...}}``.
The schema identifier is opaque to A2A — iCoDer defines its own
namespace. This module is the lookup table.

Phase 1: 5 identifiers, each with a minimal reference JSON schema.
Future phases add more identifiers and full schema definitions.
"""

from __future__ import annotations

from typing import Any, Final

from .icoder_metadata import (
    ALL_ICODER_SCHEMAS,
    SCHEMA_COMPLIANCE_OUTPUT,
    SCHEMA_DRG_GROUPING_OUTPUT,
    SCHEMA_EVIDENCE_SPAN,
    SCHEMA_MEDICAL_CODING_INPUT,
    SCHEMA_MEDICAL_CODING_OUTPUT,
)

# ---------------------------------------------------------------------------
# Reference schemas — minimal JSON Schemas per identifier
# ---------------------------------------------------------------------------


_REFERENCE_SCHEMAS: Final[dict[str, dict[str, Any]]] = {
    SCHEMA_MEDICAL_CODING_OUTPUT: {
        "type": "object",
        "properties": {
            "primary_diagnosis": {"type": "object"},
            "secondary_diagnoses": {"type": "array"},
            "procedures": {"type": "array"},
            "issues_found": {"type": "array"},
            "drg_suggestion": {"type": "string"},
        },
    },
    SCHEMA_MEDICAL_CODING_INPUT: {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    },
    SCHEMA_DRG_GROUPING_OUTPUT: {
        "type": "object",
        "properties": {
            "drg_code": {"type": "string"},
            "drg_name": {"type": "string"},
            "dip_code": {"type": "string"},
        },
    },
    SCHEMA_COMPLIANCE_OUTPUT: {
        "type": "object",
        "properties": {
            "violations": {"type": "array"},
            "warnings": {"type": "array"},
        },
    },
    SCHEMA_EVIDENCE_SPAN: {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "text": {"type": "string"},
            "start": {"type": "integer"},
            "end": {"type": "integer"},
            "confidence": {"type": "number"},
        },
        "required": ["code", "text", "start", "end"],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_schema(schema_id: str) -> dict[str, Any] | None:
    """Return the reference schema for ``schema_id``, or ``None`` if unknown."""
    return _REFERENCE_SCHEMAS.get(schema_id)


def known_schema(schema_id: str) -> bool:
    """True iff ``schema_id`` is a known iCoDer schema identifier."""
    return schema_id in _REFERENCE_SCHEMAS


def list_schemas() -> tuple[str, ...]:
    """Return all known schema identifiers."""
    return ALL_ICODER_SCHEMAS


__all__ = [
    "known_schema",
    "list_schemas",
    "resolve_schema",
]