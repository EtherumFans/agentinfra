"""M3-0 Hospital Pilot Gate — DeepSeek hard-fail on missing credential.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 1.

The ``POST /api/icoder/coding-review/run`` endpoint must refuse to start a
pipeline when ``ICODER_CREDENTIAL_LLM`` (DeepSeek API key) is unset. The
degraded path that echoes user-supplied codes back as a "result" is not safe
for a hospital pilot reviewer — they cannot tell echo from inference by
glancing at the result table.

Behavior contract:

* No key + ``ICODER_ALLOW_DEGRADED_NO_KEY != "1"``  →  503 ``llm_credential_missing``
* No key + ``ICODER_ALLOW_DEGRADED_NO_KEY == "1"``  →  200, ``degraded=True``
* Key set                                              →  200, real inference path reached
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
# Phase D3 (2026-06-26): canonical constants now live in the SSOT
# ``icoder_runtime.constants.coding_review_constants``. The legacy
# ``homepage-coding-review`` 14-stage shim is gone. The re-export
# aliases in app.api.icoder_coding_review remain for back-compat.
from icoder_runtime.constants.coding_review_constants import (
    AGENT_REF,
    AGENT_CATEGORY,
    PIPELINE_STAGES,
)


@pytest.fixture
def client():
    return TestClient(app)


SAMPLE_INPUT = {
    "encounter_text": "患者男 65 岁, 因持续胸痛 6 小时入院",
    "case_id": "c-no-key-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I21.401",
    "other_disease_codes": "",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}


def test_no_credential_no_opt_in_returns_503(client, monkeypatch):
    """Production path: no key, no dev opt-in → 503 with reason=llm_credential_missing."""
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)

    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)

    assert r.status_code == 503, f"expected 503, got {r.status_code}: {r.text}"
    body = r.json()
    # FastAPI wraps HTTPException(detail=...) under "detail"
    assert "detail" in body
    detail = body["detail"]
    assert detail.get("reason") == "llm_credential_missing", detail
    # The hint should mention both the production env-var and the dev opt-in
    hint = detail.get("hint", "")
    assert "ICODER_CREDENTIAL_LLM" in hint
    assert "ICODER_ALLOW_DEGRADED_NO_KEY" in hint
    # No key was set, so no run record should have been produced (we never
    # get past the 503). _RUNS_STORE is empty.
    from app.api import icoder_coding_review
    assert "c-no-key-001" not in str(icoder_coding_review._RUNS_STORE.values())


def test_no_credential_with_opt_in_returns_200_degraded(client, monkeypatch):
    """Dev path: no key, but ICODER_ALLOW_DEGRADED_NO_KEY=1 → 200 with degraded=True.

    The 14-stage homepage-coding-review pipeline still runs through the
    degraded-echo path so the e2e workbench flow remains exercisable
    without a DeepSeek key. (Phase B / M2b will collapse the API layer
    to the canonical MedCodER 5 stages; that refactor is out of scope
    for Phase A.)
    """
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.setenv("ICODER_ALLOW_DEGRADED_NO_KEY", "1")

    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)

    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["degraded"] is True, f"degraded must be True under no-key echo, got {body}"
    assert body["agent_ref"] == AGENT_REF
    assert body["agent_category"] == AGENT_CATEGORY
    # 14 阶段至少包含核心推理链路 (实际是 14 个)
    observed = body["pipeline_stages_observed"]
    assert len(observed) >= 8, f"observed stages too few: {observed}"
    assert "high_risk_coding_point_checker" in observed
    assert "risk_router" in observed
    assert "medical_safety_gate" in observed
    # reason 字段透出 "no LLM gateway" 或类似
    assert "no LLM gateway" in body["reason"] or "degraded" in body["reason"].lower() or "platform_gateway" in body["reason"]


def test_empty_credential_treated_as_missing(client, monkeypatch):
    """Whitespace-only ICODER_CREDENTIAL_LLM is treated as missing (not bypassed)."""
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "   ")
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)

    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)

    assert r.status_code == 503, f"whitespace-only key should not bypass the gate: {r.text}"
    body = r.json()
    assert body["detail"]["reason"] == "llm_credential_missing"


def test_credential_set_passes_gate(client, monkeypatch):
    """Real path: ICODER_CREDENTIAL_LLM set (any non-empty value) → 503 NOT raised.

    The pipeline then runs through the real inference branch. The exact
    inference outcome depends on whether a real DeepSeek key is configured,
    but we only need to verify the gate is no longer the blocker. With the
    test harness, the gateway is still not initialized, so the run returns
    a degraded result — that's fine; we are not testing the model here.
    """
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "sk-test-credential-not-real")
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)

    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)

    # The 503 must not fire. The downstream inference path may still produce
    # a degraded result (no real LLM gateway in test harness), but the gate
    # has clearly passed.
    assert r.status_code != 503, f"503 must not fire when credential is set: {r.text}"
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
