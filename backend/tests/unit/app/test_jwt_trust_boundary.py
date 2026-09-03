from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.api.oauth import _create_oauth_token
from app.config import settings
from app.middleware.auth import (
    create_access_token,
    create_delegation_token,
    create_refresh_token,
    decode_token,
)


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _foreign_token(**overrides) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "foreign-user",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        **overrides,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def test_every_locally_issued_jwt_is_bound_to_issuer_and_audience() -> None:
    tokens = [
        create_access_token("u1", "alice", "admin", "org-1"),
        create_refresh_token("u1", "org-1"),
        create_delegation_token("u1", "alice", "agent-1", "account-1", ["run"], "org-1"),
        _create_oauth_token("client-1", "agents:run", "u1", 300, org_id="org-1"),
    ]

    for token in tokens:
        claims = _claims(token)
        assert claims["iss"] == settings.JWT_ISSUER
        assert claims["aud"] == settings.JWT_AUDIENCE
        assert isinstance(claims["iat"], int)
        assert decode_token(token)["type"] == claims["type"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "urn:another:api"},
        {"iss": "urn:another:issuer"},
        {"aud": [settings.JWT_AUDIENCE, "urn:another:api"]},
    ],
)
def test_signed_token_with_wrong_or_ambiguous_trust_binding_is_rejected(overrides) -> None:
    with pytest.raises(HTTPException) as error:
        decode_token(_foreign_token(**overrides))
    assert error.value.status_code == 401


@pytest.mark.parametrize("missing", ["iss", "aud", "iat", "exp", "sub", "type"])
def test_signed_token_missing_required_registered_claim_is_rejected(missing: str) -> None:
    token = _foreign_token()
    payload = _claims(token)
    payload.pop(missing)
    malformed = jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(HTTPException) as error:
        decode_token(malformed)
    assert error.value.status_code == 401


def test_issuer_and_audience_must_be_distinct(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JWT_ISSUER", "urn:icoder:same")
    monkeypatch.setattr(settings, "JWT_AUDIENCE", "urn:icoder:same")
    with pytest.raises(RuntimeError, match="must be distinct"):
        create_access_token("u1", "alice", "admin")
