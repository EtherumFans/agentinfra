"""A2A Part types (SPEC §5).

Three part kinds:

- **TextPart** — natural language text.
- **DataPart** — structured JSON, with ``schema`` identifier + ``value``.
- **FilePart** — binary content (Phase 1 NOT implemented per Q-A9).

Strict spec compliance (Q-A1): unknown ``kind`` or ``kind: "file"``
returns INVALID_REQUEST (-32602) at parse time.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import A2AError, A2AErrorCode, invalid_params


class PartKind(str, Enum):
    """A2A v0.3 Part kinds (SPEC §5.4)."""

    TEXT = "text"
    DATA = "data"
    FILE = "file"  # Phase 1: parse-time rejection per Q-A9.


# ---------------------------------------------------------------------------
# Part models
# ---------------------------------------------------------------------------


class _PartBase(BaseModel):
    """Base for all part types. ``kind`` discriminates the union."""

    model_config = ConfigDict(extra="allow")

    kind: str


class TextPart(_PartBase):
    """TextPart — ``{"kind": "text", "text": "..."}``."""

    kind: Literal["text"] = "text"
    text: str

    @field_validator("text")
    @classmethod
    def _text_must_be_nonempty(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("text must be a string")
        return v


class DataPart(_PartBase):
    """DataPart — ``{"kind": "data", "data": {"schema": "...", "value": {...}}}``.

    Per SPEC §5.2 ``data`` carries a ``schema`` identifier (URI-style
    string) and a ``value``. The schema is opaque to A2A — iCoDer
    resolves it through :mod:`a2a.schema_registry`.
    """

    kind: Literal["data"] = "data"
    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def _data_must_have_schema_and_value(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("data.data must be an object")
        if "schema" not in v:
            raise ValueError("data.data must have a 'schema' field")
        if not isinstance(v["schema"], str) or not v["schema"]:
            raise ValueError("data.data.schema must be a non-empty string")
        return v


class FilePart(_PartBase):
    """FilePart — ``{"kind": "file", "file": {...}}``.

    Phase 1 NOT implemented per Q-A9. Defined here so type-checkers
    recognize the union; :func:`parse_part` rejects any attempt to
    instantiate it from inbound payloads.
    """

    kind: Literal["file"] = "file"
    file: dict[str, Any]


# Union — Pydantic v2 discriminates by ``kind``.
Part = Annotated[
    Union[TextPart, DataPart, FilePart],
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Parse / serialize helpers
# ---------------------------------------------------------------------------


def parse_part(obj: Any) -> TextPart | DataPart:
    """Validate and parse a single Part from inbound JSON.

    Returns a :class:`TextPart` or :class:`DataPart`. Rejects
    :class:`FilePart` with INVALID_PARAMS (-32602) per Q-A9.

    Strict: unknown ``kind`` → INVALID_PARAMS. Missing ``kind`` →
    INVALID_PARAMS. Wrong shape (non-dict) → INVALID_PARAMS.
    """
    if not isinstance(obj, dict):
        raise _invalid("part must be a JSON object")

    kind = obj.get("kind")
    if not isinstance(kind, str) or not kind:
        raise _invalid("part missing 'kind' field")

    if kind == PartKind.FILE.value:
        raise _invalid(
            "FilePart not supported in Phase 1 (binary uploads deferred to Phase 4)",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )

    if kind == PartKind.TEXT.value:
        try:
            return TextPart.model_validate(obj)
        except Exception as e:
            raise _invalid(f"invalid TextPart: {e}", a2a_code=A2AErrorCode.INVALID_PARAMS) from e

    if kind == PartKind.DATA.value:
        try:
            return DataPart.model_validate(obj)
        except Exception as e:
            raise _invalid(f"invalid DataPart: {e}", a2a_code=A2AErrorCode.INVALID_PARAMS) from e

    raise _invalid(
        f"unknown part kind {kind!r}; expected one of: text, data",
        a2a_code=A2AErrorCode.INVALID_PARAMS,
    )


def parse_parts(parts: Any) -> list[TextPart | DataPart]:
    """Validate and parse a list of parts. Empty list is allowed."""
    if parts is None:
        return []
    if not isinstance(parts, list):
        raise _invalid("parts must be an array", a2a_code=A2AErrorCode.INVALID_PARAMS)
    if len(parts) == 0:
        raise _invalid(
            "parts must contain at least one element",
            a2a_code=A2AErrorCode.INVALID_PARAMS,
        )
    return [parse_part(p) for p in parts]


def part_to_envelope_dict(part: TextPart | DataPart) -> dict[str, Any]:
    """Serialize a part back to its wire dict via ``model_dump``."""
    return part.model_dump(exclude_none=False)


def parts_to_envelope_dicts(parts: list[TextPart | DataPart]) -> list[dict[str, Any]]:
    """Serialize a list of parts to wire dicts."""
    return [part_to_envelope_dict(p) for p in parts]


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _invalid(details: str, a2a_code: str = A2AErrorCode.INVALID_REQUEST) -> A2AError:
    """Build an :class:`A2AError` for part-validation failures."""
    return A2AError(code=a2a_code, details=details)


__all__ = [
    "DataPart",
    "FilePart",
    "Part",
    "PartKind",
    "TextPart",
    "parse_part",
    "parse_parts",
    "part_to_envelope_dict",
    "parts_to_envelope_dicts",
]