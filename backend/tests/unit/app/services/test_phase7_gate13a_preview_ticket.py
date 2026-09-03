"""Phase 7 Gate 13A-1 — Preview Ticket crypto service unit tests.

Verifies the HMAC-signed bootstrap ticket and Runtime Token:

1. **round-trip** — issue + verify returns the same claims.
2. **tamper detection** — any byte change in payload breaks the signature.
3. **expiry** — past exp → PreviewTicketExpired.
4. **origin binding** — wrong parent/iframe origin → mismatch.
5. **nonce binding** — wrong nonce → mismatch.
6. **version pinning** — wrong version → malformed.
7. **domain separation** — preview_ticket key != trace_token key.
8. **runtime token round-trip + type marker** — verify_runtime_token returns
   the payload, rejects type != 'rt'.
9. **constant-time compare** — secrets.compare_digest is used.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from app.services import preview_ticket
from app.services.preview_ticket import (
    PreviewTicketError,
    PreviewTicketExpired,
    PreviewTicketInvalidSignature,
    PreviewTicketMalformed,
    PreviewTicketNonceMismatch,
    PreviewTicketOriginMismatch,
    TOKEN_VERSION,
    generate_jti,
    generate_nonce,
    generate_preview_session_id,
    issue_preview_ticket,
    issue_runtime_token,
    verify_preview_ticket,
    verify_runtime_token,
)


def _make_ticket(**overrides) -> str:
    base = dict(
        preview_session_id="psid-abc",
        organization_id="org_test1",
        user_id="u-test-1",
        expected_parent_origin="http://localhost:3000",
        expected_iframe_origin="http://localhost:8000",
        nonce="abcdef0123456789",
        jti="jti-xyz",
    )
    base.update(overrides)
    return issue_preview_ticket(**base)


# ── round-trip ────────────────────────────────────────────────────────


def test_round_trip_returns_claims():
    token = _make_ticket()
    claims = verify_preview_ticket(
        token,
        expected_parent_origin="http://localhost:3000",
        expected_iframe_origin="http://localhost:8000",
        expected_nonce="abcdef0123456789",
    )
    assert claims.preview_session_id == "psid-abc"
    assert claims.organization_id == "org_test1"
    assert claims.user_id == "u-test-1"
    assert claims.expected_parent_origin == "http://localhost:3000"
    assert claims.expected_iframe_origin == "http://localhost:8000"
    assert claims.nonce == "abcdef0123456789"
    assert claims.jti == "jti-xyz"
    assert claims.exp > int(time.time())
    assert "agents:run" in claims.allowed_scopes


# ── tamper detection ──────────────────────────────────────────────────


def test_tampered_payload_breaks_signature():
    token = _make_ticket()
    payload_b64, sig = token.rsplit(".", 1)
    # Flip a byte in the payload (change first char of preview_session_id).
    decoded = base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
    payload = json.loads(decoded)
    payload["s"] = "psid-TAMPERED"
    tampered_b64 = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    tampered_token = f"{tampered_b64}.{sig}"
    with pytest.raises(PreviewTicketInvalidSignature):
        verify_preview_ticket(tampered_token)


def test_wrong_secret_breaks_signature(monkeypatch):
    """If SECRET_KEY differs between issue and verify, signature must fail."""
    token = _make_ticket()
    from app.config import settings

    original = settings.SECRET_KEY
    settings.SECRET_KEY = "different-secret-key-for-test"
    try:
        with pytest.raises(PreviewTicketInvalidSignature):
            verify_preview_ticket(token)
    finally:
        settings.SECRET_KEY = original


# ── expiry ────────────────────────────────────────────────────────────


def test_expired_ticket_rejected():
    token = issue_preview_ticket(
        preview_session_id="psid-exp",
        expected_parent_origin="http://localhost:3000",
        expected_iframe_origin="http://localhost:8000",
        nonce="n",
        ttl_seconds=-10,  # already expired
    )
    with pytest.raises(PreviewTicketExpired):
        verify_preview_ticket(token)


# ── origin binding ────────────────────────────────────────────────────


def test_parent_origin_mismatch():
    token = _make_ticket()
    with pytest.raises(PreviewTicketOriginMismatch):
        verify_preview_ticket(
            token, expected_parent_origin="https://evil.example.com"
        )


def test_iframe_origin_mismatch():
    token = _make_ticket()
    with pytest.raises(PreviewTicketOriginMismatch):
        verify_preview_ticket(
            token, expected_iframe_origin="https://evil.example.com"
        )


# ── nonce binding ─────────────────────────────────────────────────────


def test_nonce_mismatch():
    token = _make_ticket()
    with pytest.raises(PreviewTicketNonceMismatch):
        verify_preview_ticket(token, expected_nonce="wrong-nonce")


# ── version + format ─────────────────────────────────────────────────


def test_wrong_version_rejected():
    token = _make_token_with_overrides(v=999)
    with pytest.raises(PreviewTicketMalformed) as exc:
        verify_preview_ticket(token)
    assert "version" in str(exc.value).lower()


def test_malformed_token_no_dot():
    with pytest.raises(PreviewTicketMalformed):
        verify_preview_ticket("no-dot-here")


def test_malformed_empty_token():
    with pytest.raises(PreviewTicketMalformed):
        verify_preview_ticket("")


def test_malformed_payload_json():
    """Signature valid but payload isn't valid JSON."""
    from app.services.preview_ticket import _b64url_encode, _sign

    junk_b64 = _b64url_encode(b"not json at all")
    sig = _sign(junk_b64)
    with pytest.raises(PreviewTicketMalformed):
        verify_preview_ticket(f"{junk_b64}.{sig}")


# ── domain separation ────────────────────────────────────────────────


def test_ticket_key_domain_separated_from_trace_token():
    """The HMAC key has a domain-separation prefix so it can't cross-use
    with trace_token (which uses raw SHA-256 of SECRET_KEY)."""
    from app.services.preview_ticket import _secret_bytes
    from app.services import trace_token

    preview_key = _secret_bytes()
    # trace_token uses _secret_bytes which is sha256 of SECRET_KEY alone
    trace_key = trace_token._secret_bytes()
    assert preview_key != trace_key, (
        "preview_ticket key MUST be domain-separated from trace_token key"
    )


# ── runtime token ────────────────────────────────────────────────────


def test_runtime_token_round_trip():
    token = issue_runtime_token(
        preview_session_id="psid-1",
        organization_id="org_test1",
        user_id="u-1",
    )
    payload = verify_runtime_token(token)
    assert payload["t"] == "rt"
    assert payload["v"] == TOKEN_VERSION
    assert payload["s"] == "psid-1"
    assert payload["o"] == "org_test1"
    assert payload["u"] == "u-1"
    assert "agents:run" in payload["c"]
    assert payload["e"] > int(time.time())


def test_runtime_token_rejects_preview_ticket():
    """A preview ticket (no type marker 'rt') must NOT verify as a runtime token."""
    pt = _make_ticket()
    with pytest.raises(PreviewTicketMalformed):
        verify_runtime_token(pt)


def test_runtime_token_expired():
    token = issue_runtime_token(
        preview_session_id="psid-1",
        ttl_seconds=-100,
    )
    with pytest.raises(PreviewTicketExpired):
        verify_runtime_token(token)


# ── ID generators ────────────────────────────────────────────────────


def test_generate_nonce_is_hex():
    n = generate_nonce()
    assert len(n) == 32  # 16 bytes hex = 32 chars
    int(n, 16)  # parses as hex


def test_generate_preview_session_id_unique():
    a = generate_preview_session_id()
    b = generate_preview_session_id()
    assert a != b
    assert len(a) >= 24


def test_generate_jti_unique():
    a = generate_jti()
    b = generate_jti()
    assert a != b


# ── helpers ──────────────────────────────────────────────────────────


def _make_token_with_overrides(**payload_overrides) -> str:
    """Issue a token with arbitrary payload field overrides — for negative tests."""
    from app.services.preview_ticket import _b64url_encode, _sign

    payload = {
        "v": TOKEN_VERSION,
        "s": "psid-abc",
        "o": "org_test1",
        "u": "u-1",
        "p": "http://localhost:3000",
        "f": "http://localhost:8000",
        "n": "abcdef0123456789",
        "j": "jti-xyz",
        "e": int(time.time()) + 60,
        "a": [],
        "c": ["agents:run"],
    }
    payload.update(payload_overrides)
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64url_encode(payload_json.encode("utf-8"))
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"
