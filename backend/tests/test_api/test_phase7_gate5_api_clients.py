"""Phase 7 Gate 5 — API Client CRUD + attribution tests.

Covers §10.1-§10.4:

§10.1 RunHistory attribution
  - api_client_id + embedded_app_id + session_id + context_id +
    request_id + idempotency_key columns exist
  - An agent_run with api_client_id writes a row with the field set

§10.2 CRUD
  - Create (returns plaintext secret ONCE)
  - List (org-scoped)
  - View (single)
  - Disable / Enable
  - Rotate secret (new plaintext, old hash replaced)
  - Update scopes
  - Update allowed_origins
  - Test connection
  - Cross-org access returns 404 (don't leak existence)

§10.3 Secret rules
  - Plaintext shown only on create / rotate
  - View never returns secret
  - Disabled client → /token returns 401

§10.4 Scope enforcement
  - Unknown scope rejected at create time
  - Scopes stored verbatim, ready for runtime enforcement
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


# ────────────────────────────────────────────────────────────────────
# §10.2 Create + §10.3 Secret shown once
# ────────────────────────────────────────────────────────────────────


def test_create_returns_plaintext_secret_once(client: TestClient) -> None:
    """POST /api/clients returns client_id + plaintext secret."""
    resp = client.post("/api/clients", json={
        "name": "Partner Hospital A",
        "description": "EMR backend integration",
        "scopes": "agents:run runs:read traces:read usage:read",
        "allowed_origins": ["https://emr.partner-a.example"],
        "allowed_agent_ids": ["diagnosis-extractor"],
        "allowed_purposes": ["treatment"],
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["client_id"].startswith("icoder-")
    assert data["client_secret"].startswith("ics_")
    assert len(data["client_secret"]) > 40  # ics_ + 64 hex chars
    assert data["is_active"] is True
    assert data["allowed_origins"] == ["https://emr.partner-a.example"]
    assert data["allowed_agent_ids"] == ["diagnosis-extractor"]
    assert data["allowed_purposes"] == ["treatment"]
    assert data["secret_shown_at"]


def test_view_never_returns_secret(client: TestClient) -> None:
    """GET must never include the secret field."""
    create = client.post("/api/clients", json={
        "name": "View Test",
        "scopes": "agents:run",
        "allowed_origins": [],
    })
    client_id = create.json()["client_id"]

    # GET single
    resp = client.get(f"/api/clients/{client_id}")
    assert resp.status_code == 200
    assert "client_secret" not in resp.json()

    # GET list
    resp = client.get("/api/clients")
    assert resp.status_code == 200
    for c in resp.json():
        assert "client_secret" not in c


# ────────────────────────────────────────────────────────────────────
# §10.2 List / View + cross-org 404
# ────────────────────────────────────────────────────────────────────


def test_list_returns_org_clients(client: TestClient) -> None:
    """List returns the clients created in this org."""
    client.post("/api/clients", json={"name": "L1", "scopes": "agents:run"})
    client.post("/api/clients", json={"name": "L2", "scopes": "runs:read"})
    resp = client.get("/api/clients")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "L1" in names
    assert "L2" in names


def test_get_unknown_returns_404(client: TestClient) -> None:
    """Unknown client_id → 404 (don't leak existence)."""
    resp = client.get("/api/clients/icoder-does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "CLIENT_NOT_FOUND"


# ────────────────────────────────────────────────────────────────────
# §10.2 + §10.3 Disable / Enable
# ────────────────────────────────────────────────────────────────────


def test_disable_then_enable_round_trip(client: TestClient) -> None:
    """Disable flips is_active=False; enable flips it back."""
    create = client.post("/api/clients", json={"name": "DE", "scopes": "agents:run"})
    client_id = create.json()["client_id"]

    resp = client.post(f"/api/clients/{client_id}/disable")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = client.post(f"/api/clients/{client_id}/enable")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


# ────────────────────────────────────────────────────────────────────
# §10.3 Rotate secret
# ────────────────────────────────────────────────────────────────────


def test_rotate_returns_new_plaintext(client: TestClient) -> None:
    """Rotate returns a new plaintext secret; old hash is replaced."""
    create = client.post("/api/clients", json={"name": "Rot", "scopes": "agents:run"})
    client_id = create.json()["client_id"]
    old_secret = create.json()["client_secret"]

    resp = client.post(f"/api/clients/{client_id}/rotate")
    assert resp.status_code == 200
    new_secret = resp.json()["client_secret"]
    assert new_secret != old_secret
    assert new_secret.startswith("ics_")


def test_disabled_client_token_rejected(client: TestClient) -> None:
    """§10.3: disabled client → /token returns 401."""
    create = client.post("/api/clients", json={"name": "DisTok", "scopes": "agents:run"})
    client_id = create.json()["client_id"]
    secret = create.json()["client_secret"]

    # Token works pre-disable
    resp = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": "agents:run",
        },
    )
    assert resp.status_code == 200

    # Disable
    client.post(f"/api/clients/{client_id}/disable")

    # Token fails post-disable
    resp = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
            "scope": "agents:run",
        },
    )
    assert resp.status_code == 401


# ────────────────────────────────────────────────────────────────────
# §10.4 Scope enforcement (validation at write time)
# ────────────────────────────────────────────────────────────────────


def test_unknown_scope_rejected_at_create(client: TestClient) -> None:
    """§10.4: unknown scopes are rejected — typo protection."""
    resp = client.post("/api/clients", json={
        "name": "Bad",
        "scopes": "agents:run bogus:scope",
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "UNKNOWN_SCOPE"
    assert "bogus:scope" in resp.json()["detail"]["unknown"]


def test_update_scopes(client: TestClient) -> None:
    """PATCH /scopes updates granted scopes with validation."""
    create = client.post("/api/clients", json={"name": "SC", "scopes": "agents:run"})
    client_id = create.json()["client_id"]

    resp = client.patch(
        f"/api/clients/{client_id}/scopes",
        json={"scopes": "agents:run runs:read traces:read"},
    )
    assert resp.status_code == 200
    assert "runs:read" in resp.json()["scopes"]


# ────────────────────────────────────────────────────────────────────
# §11.1 Allowed Origins validation
# ────────────────────────────────────────────────────────────────────


def test_wildcard_origin_forbidden(client: TestClient) -> None:
    """§11.1: '*' is forbidden when client_credentials is enabled."""
    resp = client.post("/api/clients", json={
        "name": "W",
        "scopes": "agents:run",
        "allowed_origins": ["*"],
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "WILDCARD_ORIGIN_FORBIDDEN"


def test_origin_must_have_scheme(client: TestClient) -> None:
    """§11.1: Origin must include scheme."""
    resp = client.post("/api/clients", json={
        "name": "S",
        "scopes": "agents:run",
        "allowed_origins": ["emr.partner.example"],  # missing scheme
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "BAD_ORIGIN"


def test_update_origins(client: TestClient) -> None:
    """PATCH /allowed-origins updates the list."""
    create = client.post("/api/clients", json={"name": "O", "scopes": "agents:run"})
    client_id = create.json()["client_id"]
    resp = client.patch(
        f"/api/clients/{client_id}/allowed-origins",
        json={"allowed_origins": ["https://emr.partner.example", "http://localhost:3000"]},
    )
    assert resp.status_code == 200
    origins = resp.json()["allowed_origins"]
    assert "https://emr.partner.example" in origins
    assert "http://localhost:3000" in origins


# ────────────────────────────────────────────────────────────────────
# §10.2 Test connection
# ────────────────────────────────────────────────────────────────────


def test_connection_active_client(client: TestClient) -> None:
    """POST /test requires complete machine delegation for Agent Run."""
    create = client.post("/api/clients", json={
        "name": "T",
        "scopes": "agents:run",
        "allowed_agent_ids": ["diagnosis-extractor"],
        "allowed_purposes": ["treatment"],
    })
    client_id = create.json()["client_id"]
    resp = client.post(f"/api/clients/{client_id}/test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "agents:run" in data["granted_scopes"]
    assert data["allowed_agent_ids"] == ["diagnosis-extractor"]
    assert data["allowed_purposes"] == ["treatment"]


def test_connection_agent_run_defaults_to_deny_without_delegation(
    client: TestClient,
) -> None:
    create = client.post(
        "/api/clients", json={"name": "Unconfigured", "scopes": "agents:run"},
    )
    resp = client.post(f"/api/clients/{create.json()['client_id']}/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert resp.json()["message"] == (
        "Agent Run delegation requires Agent and purpose grants."
    )


@pytest.mark.parametrize(
    "body,code",
    [
        ({"allowed_agent_ids": ["*"], "allowed_purposes": ["treatment"]},
         "INVALID_AGENT_GRANT"),
        ({"allowed_agent_ids": ["unknown-agent"], "allowed_purposes": ["treatment"]},
         "UNKNOWN_AGENT_GRANT"),
        ({"allowed_agent_ids": ["diagnosis-extractor"],
          "allowed_purposes": ["system_operations"]},
         "INVALID_PURPOSE_GRANT"),
    ],
)
def test_delegation_rejects_wildcard_unknown_agent_and_reserved_purpose(
    client: TestClient, body: dict, code: str,
) -> None:
    resp = client.post(
        "/api/clients", json={"name": "Bad delegation", "scopes": "agents:run", **body},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == code


def test_delegation_can_be_replaced_and_immediately_revoked(
    client: TestClient,
) -> None:
    create = client.post(
        "/api/clients", json={"name": "Delegation patch", "scopes": "agents:run"},
    )
    client_id = create.json()["client_id"]
    granted = client.patch(
        f"/api/clients/{client_id}/delegation",
        json={
            "allowed_agent_ids": ["diagnosis-extractor"],
            "allowed_purposes": ["treatment", "payment"],
        },
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["allowed_agent_ids"] == ["diagnosis-extractor"]
    assert granted.json()["allowed_purposes"] == ["payment", "treatment"]

    revoked = client.patch(
        f"/api/clients/{client_id}/delegation",
        json={"allowed_agent_ids": [], "allowed_purposes": []},
    )
    assert revoked.status_code == 200
    assert revoked.json()["allowed_agent_ids"] == []
    assert revoked.json()["allowed_purposes"] == []


def test_connection_disabled_client(client: TestClient) -> None:
    """Disabled client → ok=False with a clear message."""
    create = client.post("/api/clients", json={"name": "TD", "scopes": "agents:run"})
    client_id = create.json()["client_id"]
    client.post(f"/api/clients/{client_id}/disable")
    resp = client.post(f"/api/clients/{client_id}/test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


# ────────────────────────────────────────────────────────────────────
# §10.1 Attribution — agent_run writes api_client_id to run_history
# ────────────────────────────────────────────────────────────────────


def test_agent_run_rejects_body_api_client_id_as_attribution(client: TestClient) -> None:
    """Only verified client-credentials auth may attribute an Embedded Run."""
    api_client_id = "icoder-test-attribution"
    resp = client.post(
        "/api/v1/agents/medical-coding-agent/run",
        json={
            "input": {"text": "attribution test"},
            "runtime_mode": "corti_like_fast",
            "api_client_id": api_client_id,
        },
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    # GET /runs/{id} reads the row — verify api_client_id persisted.
    resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200
    # The full row shape includes the attribution fields (we expose
    # them in the GET response so partners can self-attribute).
    # For now, the existing GET response model doesn't include
    # api_client_id — that's an extension for this gate. Verify the
    # run_history DB row directly instead.
    import sqlite3
    test_db_path = os.environ.get("ICODER_TEST_DB_PATH", "data/test.db")
    assert test_db_path, "SQLite test database is required for this assertion"
    conn = sqlite3.connect(test_db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT api_client_id FROM run_history WHERE run_id = ?",
        (run_id,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, "run_history row must exist"
    assert row[0] is None, (
        f"request-body api_client_id must be ignored; got {row[0]!r}"
    )
