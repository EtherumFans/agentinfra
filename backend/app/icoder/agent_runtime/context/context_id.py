"""Server-issued UUID v4 contextId generation and canonical validation.

Clients omit the ID on the first turn and may reuse the returned ID on later
turns. The transport validates tenant, agent and lifecycle before reuse.
"""

from __future__ import annotations

import re
import uuid

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def generate_context_id() -> str:
    """Server-side fresh contextId (UUID v4, canonical lowercase)."""
    return str(uuid.uuid4())


def is_valid_context_id(value: str) -> bool:
    """Accept UUID v4 in canonical 8-4-4-4-12 lowercase hex form."""
    return isinstance(value, str) and bool(_UUID_V4_RE.match(value))


def parse_context_id(value: str) -> uuid.UUID:
    """Parse a contextId string into a uuid.UUID.

    Raises ValueError if the value is not a canonical UUID v4.
    """
    if not is_valid_context_id(value):
        raise ValueError(f"invalid contextId: {value!r}")
    return uuid.UUID(value)
