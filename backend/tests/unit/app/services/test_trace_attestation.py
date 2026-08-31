from __future__ import annotations

import pytest

from app.config import settings
from app.services import trace_attestation as module


@pytest.fixture(autouse=True)
def signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "SECRET_KEY",
        "trace-attestation-pytest-only-key-20260823-not-production",
    )


def _events() -> list[dict]:
    return [
        {
            "step": "provider.completed",
            "status": "ok",
            "safe_metadata": {
                "backend_provider": "icoder.pure-llm.v1",
                "model_provider": "deepseek",
                "model_name": "deepseek-chat",
            },
        }
    ]


def test_trace_attestation_binds_exact_run_tenant_and_events() -> None:
    token = module.issue_trace_attestation(
        run_id="run-1",
        organization_id="org-1",
        events=_events(),
    )
    claims = module.verify_trace_attestation(
        token,
        expected_run_id="run-1",
        expected_organization_id="org-1",
        events=_events(),
    )
    assert claims.run_id == "run-1"
    assert claims.organization_id == "org-1"
    assert len(claims.events_sha256) == 64


@pytest.mark.parametrize(
    "run_id,organization_id,events",
    [
        ("run-2", "org-1", _events()),
        ("run-1", "org-2", _events()),
        ("run-1", "org-1", []),
    ],
)
def test_trace_attestation_rejects_identity_or_event_tampering(
    run_id: str,
    organization_id: str,
    events: list[dict],
) -> None:
    token = module.issue_trace_attestation(
        run_id="run-1",
        organization_id="org-1",
        events=_events(),
    )
    with pytest.raises(module.TraceAttestationMismatch):
        module.verify_trace_attestation(
            token,
            expected_run_id=run_id,
            expected_organization_id=organization_id,
            events=events,
        )


def test_trace_attestation_rejects_forged_signature() -> None:
    token = module.issue_trace_attestation(
        run_id="run-1",
        organization_id="org-1",
        events=_events(),
    )
    payload, _signature = token.split(".", 1)
    with pytest.raises(module.TraceAttestationMismatch, match="signature"):
        module.verify_trace_attestation(
            f"{payload}.forged",
            expected_run_id="run-1",
            expected_organization_id="org-1",
            events=_events(),
        )


def test_trace_attestation_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.time, "time", lambda: 1000.0)
    token = module.issue_trace_attestation(
        run_id="run-1",
        organization_id="org-1",
        events=_events(),
        ttl_seconds=1,
    )
    monkeypatch.setattr(module.time, "time", lambda: 1002.0)
    with pytest.raises(module.TraceAttestationExpired):
        module.verify_trace_attestation(
            token,
            expected_run_id="run-1",
            expected_organization_id="org-1",
            events=_events(),
        )


def test_trace_attestation_rejects_non_object_events() -> None:
    with pytest.raises(module.TraceAttestationMalformed):
        module.issue_trace_attestation(
            run_id="run-1",
            organization_id="org-1",
            events=["not-an-object"],  # type: ignore[list-item]
        )

