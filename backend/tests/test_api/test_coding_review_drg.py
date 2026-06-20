"""M3-0 Hospital Pilot — DRG wiring + drg_route field.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 7.

The ``POST /api/icoder/coding-review/run`` endpoint must:

1. Call ``app.services.drg_grouper.group_drg`` after the 14-stage pipeline
   when a primary diagnosis is present. The result is exposed as the
   ``drg_route`` field on the response, with the standard CHS-DRG 1.1
   fields (mdc, adrg, drg, drg_name, cc_level, coverage, …).
2. Return ``drg_route = None`` when no primary diagnosis is available.
3. Persist the route to the ``CodingReviewRun.drg_route`` JSON column so
   the value survives a server restart.
4. Surface the route in the HTML report (Commit 7 §6.5) and the JSON
   report (``drg_route`` key).
5. Wrap the call in try/except — DRG must never block the response.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# 必须在 import app.main 之前设置
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


@pytest.fixture
def client():
    with TestClient(app := __import__("app.main", fromlist=["app"]).app) as c:
        yield c


SAMPLE_INPUT_PRIMARY = {
    "encounter_text": "患者男 65 岁, 因持续胸痛 6 小时入院",
    "case_id": "c-drg-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I50.900",
    "other_disease_codes": "",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}

SAMPLE_INPUT_NO_DX = {
    "encounter_text": "no dx here",
    "case_id": "c-drg-002",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "",
    "other_disease_codes": "",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}


# ── 1. drg_route is None when there is no primary diagnosis ──────────────


def test_drg_route_is_none_when_no_primary(client):
    """A request with empty primary_disease_codes returns drg_route=None."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_NO_DX)
    # The empty case may 4xx if the API rejects it; we only assert on the
    # 200 path's drg_route.
    if r.status_code == 200:
        body = r.json()
        assert body.get("drg_route") is None, (
            f"expected drg_route=None when no primary dx, got {body.get('drg_route')!r}"
        )


# ── 2. drg_route is populated when primary is present ──────────────────


def test_drg_route_populated_when_primary_present(client):
    """A request with primary_disease_codes=I50.900 produces a non-None drg_route."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_PRIMARY)
    assert r.status_code == 200, f"run failed: {r.text}"
    body = r.json()
    drg = body.get("drg_route")
    # The pipeline may run in degraded mode (no LLM) — primary_diagnosis
    # is then taken from user-supplied codes. Either way, the DRG route
    # should be non-None.
    assert drg is not None, f"expected drg_route, got None"
    # Standard fields must exist
    for field in ("mdc", "adrg", "drg", "drg_name", "cc_level", "coverage"):
        assert field in drg, f"missing drg_route.{field}: {drg}"
    # is_medical_or_surgical derived field must exist
    assert "is_medical_or_surgical" in drg, f"missing is_medical_or_surgical: {drg}"


# ── 3. drg_route has standard CHS-DRG 1.1 fields ────────────────────────


def test_drg_route_has_mdc_f_or_unknown(client):
    """I50.900 (心力衰竭) is in MDC F (循环系统). MDC should be F or F-related."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_PRIMARY)
    assert r.status_code == 200
    drg = r.json().get("drg_route")
    assert drg is not None
    # The MDC letter for circulatory system diseases is F; allow either
    # the bare letter or the full MDC code.
    mdc = drg.get("mdc", "")
    assert "F" in mdc or mdc == "MDCF", f"unexpected MDC for I50.900: {mdc!r}"


# ── 4. drg_route is persisted to the DB ────────────────────────────────


def test_drg_route_persisted_to_db(client):
    """After the run, the CodingReviewRun.drg_route row has the same value."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_PRIMARY)
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    api_drg = r.json().get("drg_route")

    # GET /{run_id} should return the same drg_route
    r2 = client.get(f"/api/icoder/coding-review/{run_id}")
    assert r2.status_code == 200
    rec = r2.json()
    persisted = rec.get("result", {}).get("drg_route")
    assert persisted == api_drg, (
        f"persisted drg_route differs from API response: "
        f"api={api_drg!r} vs persisted={persisted!r}"
    )


# ── 5. drg_route appears in HTML report (no crash, section rendered) ─────


def test_drg_route_in_html_report(client):
    """The HTML report includes the DRG section without raising."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_PRIMARY)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    h = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert h.status_code == 200, f"report failed: {h.text}"
    body = h.text
    # The new §6.5 section is in the report
    assert "6.5" in body or "DRG" in body, (
        f"DRG section not present in HTML report"
    )


# ── 6. drg_route appears in JSON report ─────────────────────────────────


def test_drg_route_in_json_report(client):
    """The JSON report exposes drg_route as a top-level key."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT_PRIMARY)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    j = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    assert j.status_code == 200
    import json as json_mod
    report = json_mod.loads(j.json()["content"])
    assert "drg_route" in report, f"missing drg_route in JSON report: keys={list(report.keys())}"
