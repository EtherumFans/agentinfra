"""C7 — context_audit: hash + retention calculation (no DB)."""

from __future__ import annotations

import hashlib

from app.icoder.agent_runtime.context.context_audit import hash_original_input


def test_hash_is_sha256_hex_64_chars():
    h = hash_original_input("hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert h == hashlib.sha256(b"hello").hexdigest()


def test_hash_deterministic():
    assert hash_original_input("x") == hash_original_input("x")


def test_hash_different_inputs_differ():
    assert hash_original_input("x") != hash_original_input("y")


def test_hash_handles_unicode():
    h = hash_original_input("病人张三 13012345678")
    assert len(h) == 64
    expected = hashlib.sha256("病人张三 13012345678".encode("utf-8")).hexdigest()
    assert h == expected


def test_hash_handles_empty():
    h = hash_original_input("")
    assert h == hashlib.sha256(b"").hexdigest()