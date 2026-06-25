"""M3-0 Hospital Pilot — PHI redaction at report export + version metadata.

Plan reference: docs/M3_HOSPITAL_PILOT_READINESS_PLAN.md Commit 8.

The ``GET /api/icoder/coding-review/{run_id}/report`` endpoint must:

1. Apply ``PIIRedactor`` to ``encounter_text``, ``review_note``, and
   ``reason_code`` before they reach the HTML / JSON report. The raw
   text must NOT appear in the export.
2. Read version metadata (model_version, code_dict_version, rule_version,
   agent_version, data_asset_version) from ``app.state.icoder_versions``,
   populated once at lifespan startup from ``data/versions.json``.
3. The live workbench view (``GET /{run_id}``) still returns the raw
   ``encounter_text`` to the authenticated coder — only the EXPORT is
   de-identified.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

# 必须在 import app.main 之前设置
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_PII_REDACTION_REQUIRED", "1")


@pytest.fixture
def client():
    return TestClient(app := __import__("app.main", fromlist=["app"]).app)


# Sample encounter with embedded PII: a Chinese name, an ID card, a phone.
PHI_TEXT = (
    "患者张三, 男 65 岁, 身份证 110101199001011234, "
    "联系电话 13800138000, 因持续胸痛 6 小时入院。"
)


SAMPLE_INPUT = {
    "encounter_text": PHI_TEXT,
    "case_id": "c-phi-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I50.900",
    "other_disease_codes": "",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}


# ── 1. Versions are loaded at lifespan ──────────────────────────────────


def test_versions_loaded_in_app_state(client):
    """app.state.icoder_versions is populated from data/versions.json."""
    # Trigger lifespan via TestClient
    with client as c:
        from app.main import app
        versions = app.state.icoder_versions
        assert isinstance(versions, dict), f"versions not dict: {versions}"
        for key in ("model_version", "code_dict_version", "rule_version",
                    "agent_version", "data_asset_version"):
            assert key in versions, f"missing version key: {key}"
        # The model version is the M3-0 interim DeepSeek identifier
        assert "deepseek" in versions["model_version"].lower() or \
            "M3-0" in versions["model_version"] or \
            versions["model_version"] != "unknown", (
            f"model_version not loaded: {versions['model_version']!r}"
        )


# ── 2. JSON report has the version metadata ─────────────────────────────


def test_json_report_has_version_metadata(client):
    """The JSON report's top-level fields include the version metadata."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200, f"run failed: {r.text}"
    run_id = r.json()["run_id"]

    j = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    assert j.status_code == 200
    report = json.loads(j.json()["content"])
    for key in ("model_version", "code_dict_version", "rule_version",
                "agent_version", "data_asset_version"):
        assert key in report, f"missing version key in JSON report: {key}"
        assert report[key] and report[key] != "unknown", (
            f"{key} is empty: {report[key]!r}"
        )


# ── 3. HTML report has the version metadata ────────────────────────────


def test_html_report_has_version_metadata(client):
    """The HTML report mentions the agent version (not 'unknown')."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    h = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert h.status_code == 200
    body = h.text
    # The agent version appears in the §1 section
    assert "medcoder-coding-review-agent" in body, (
        f"agent_version not in HTML report"
    )


# ── 4. Encounter text in JSON report has PHI redacted ───────────────────


def test_json_report_redacts_encounter_text_phi(client):
    """The JSON report's encounter_text has PHI placeholders, not raw PII."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    j = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    assert j.status_code == 200
    report = json.loads(j.json()["content"])
    encounter = report.get("encounter_text", "")
    # PHI placeholders from PIIRedactor:
    # - "[身份证号已脱敏]" for ID card
    # - "[手机号已脱敏]" for phone
    assert "已脱敏" in encounter or "[REDACTED" in encounter, (
        f"PHI not redacted in JSON report: {encounter!r}"
    )
    # The raw ID card and phone digits must NOT appear in the report
    assert "110101199001011234" not in encounter, "raw ID card leaked to JSON report"
    assert "13800138000" not in encounter, "raw phone leaked to JSON report"
    # phi_redaction_applied flag
    assert report.get("phi_redaction_applied") is True, (
        f"phi_redaction_applied should be True: {report.get('phi_redaction_applied')}"
    )


# ── 5. Encounter text in HTML report has PHI redacted ───────────────────


def test_html_report_redacts_encounter_text_phi(client):
    """The HTML report's encounter section has PHI placeholders."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    h = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert h.status_code == 200
    body = h.text
    # Raw ID card and phone must NOT appear anywhere in the HTML
    assert "110101199001011234" not in body, "raw ID card leaked to HTML report"
    assert "13800138000" not in body, "raw phone leaked to HTML report"


# ── 6. Live workbench view still shows raw encounter text ───────────────


def test_workbench_view_shows_raw_encounter_text(client):
    """GET /{run_id} (workbench view) does NOT redact the encounter text.

    Only the EXPORT is de-identified; the live workbench view must show
    the raw text to the authenticated coder.
    """
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    w = client.get(f"/api/icoder/coding-review/{run_id}")
    assert w.status_code == 200
    rec = w.json()
    raw = rec.get("input", {}).get("encounter_text", "")
    # The raw text must still be present in the live view
    assert "110101199001011234" in raw, (
        f"workbench view should NOT redact — raw ID card missing: {raw!r}"
    )
    assert "13800138000" in raw, (
        f"workbench view should NOT redact — raw phone missing: {raw!r}"
    )


# ── 7. Human-review records are redacted in the report ──────────────────


def test_human_review_records_redacted_in_report(client):
    """A human-review record with PHI in review_note / reason_code is
    redacted in the exported report."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    # Submit a human-review action with PHI in the note
    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept",
        "target_code": "I50.900",
        "target_role": "primary_disease",
        "reason_code": "R007 患者张三 110101199001011234",
        "reviewer": "dr.li",
        "reviewer_role": "coder",
        "review_note": "联系家属 13800138000 确认",
    })
    assert h.status_code == 200, f"human review failed: {h.text}"

    # Now check the JSON report
    j = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    report = json.loads(j.json()["content"])
    records = report.get("human_review_records") or []
    assert records, "no human_review_records in report"
    for r2 in records:
        # The ID card and phone in the note / reason_code must be redacted
        if r2.get("review_note"):
            assert "13800138000" not in r2["review_note"], (
                f"raw phone in review_note: {r2['review_note']!r}"
            )
        if r2.get("reason_code"):
            assert "110101199001011234" not in r2["reason_code"], (
                f"raw ID card in reason_code: {r2['reason_code']!r}"
            )
