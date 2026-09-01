from dataclasses import replace

import pytest

from app.services.audit_integrity import (
    GENESIS_HASH,
    HMACAuditSigner,
    canonical_json,
    create_envelope,
    verify_envelopes,
)


@pytest.fixture
def signer() -> HMACAuditSigner:
    return HMACAuditSigner(b"a" * 32, key_id="test-key-v7")


def test_canonical_json_is_stable_for_key_order_and_unicode() -> None:
    assert canonical_json({"诊断": "高血压", "a": 1}) == canonical_json(
        {"a": 1, "诊断": "高血压"}
    )


def test_two_event_chain_verifies(signer: HMACAuditSigner) -> None:
    first = create_envelope(
        {"schema": "icoder.audit-archive.v1", "audit_log_id": "a1"},
        stream_id="org-1", sequence=1, previous_hash=GENESIS_HASH,
        signer=signer,
    )
    second = create_envelope(
        {"schema": "icoder.audit-archive.v1", "audit_log_id": "a2"},
        stream_id="org-1", sequence=2, previous_hash=first.chain_hash,
        signer=signer,
    )
    verify_envelopes([first, second], signer=signer)
    assert second.signing_key_id == "test-key-v7"
    assert second.previous_hash == first.chain_hash


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda row: replace(row, payload={**row.payload, "status": "altered"}), "payload"),
        (lambda row: replace(row, signature="invalid"), "signature"),
        (lambda row: replace(row, sequence=9), "sequence"),
    ],
)
def test_verifier_detects_tampering(signer, mutation, match) -> None:
    original = create_envelope(
        {"audit_log_id": "a1", "status": "success"}, stream_id="system",
        sequence=1, previous_hash=GENESIS_HASH, signer=signer,
    )
    with pytest.raises(ValueError, match=match):
        verify_envelopes([mutation(original)], signer=signer)


def test_signing_key_is_minimum_32_bytes() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HMACAuditSigner(b"short", key_id="bad")

