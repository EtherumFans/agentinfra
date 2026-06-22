"""C1 — context_id generation + validation."""

from __future__ import annotations

import re
import uuid

import pytest

from app.icoder.agent_runtime.context.context_id import (
    generate_context_id,
    is_valid_context_id,
    parse_context_id,
)

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_generate_returns_canonical_uuid_v4():
    cid = generate_context_id()
    assert _UUID_V4_RE.match(cid), f"not canonical UUID v4: {cid!r}"
    assert cid == str(uuid.UUID(cid))


def test_generate_produces_unique_values():
    ids = {generate_context_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_generate_does_not_reuse_seed():
    a = generate_context_id()
    b = generate_context_id()
    assert a != b


def test_is_valid_accepts_canonical_uuid_v4():
    assert is_valid_context_id("550e8400-e29b-41d4-a716-446655440000")


def test_is_valid_accepts_freshly_generated_id():
    assert is_valid_context_id(generate_context_id())


def test_is_valid_rejects_uuid_v1():
    assert not is_valid_context_id("12345678-1234-1234-1234-123456789012")


def test_is_valid_rejects_uppercase():
    assert not is_valid_context_id("550E8400-E29B-41D4-A716-446655440000")


def test_is_valid_rejects_extra_chars():
    assert not is_valid_context_id("550e8400-e29b-41d4-a716-4466554400000")
    assert not is_valid_context_id("x550e8400-e29b-41d4-a716-446655440000")


def test_is_valid_rejects_empty_and_non_string():
    assert not is_valid_context_id("")
    assert not is_valid_context_id(None)
    assert not is_valid_context_id(123)


def test_parse_returns_uuid_object():
    cid = "550e8400-e29b-41d4-a716-446655440000"
    parsed = parse_context_id(cid)
    assert isinstance(parsed, uuid.UUID)
    assert parsed.version == 4
    assert str(parsed) == cid


def test_parse_raises_on_invalid():
    with pytest.raises(ValueError):
        parse_context_id("not-a-uuid")
    with pytest.raises(ValueError):
        parse_context_id("")
    with pytest.raises(ValueError):
        parse_context_id("550e8400-e29b-11d4-a716-446655440000")  # v1, not v4


def test_client_supplied_id_validation_is_strict():
    """Client may supply an id, but it MUST be canonical UUID v4 if present."""
    assert not is_valid_context_id("../../etc/passwd")
    assert not is_valid_context_id("<script>")
    assert not is_valid_context_id("DROP TABLE contexts;--")