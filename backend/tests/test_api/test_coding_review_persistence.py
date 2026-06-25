"""M3-0 Hospital Pilot — CodingReviewRun DB persistence tests.

Verifies that ``/api/icoder/coding-review/*`` writes to the
``coding_review_runs`` SQL table (Commit 3) and that the read paths
(GET ``/{run_id}``, GET ``/{run_id}/report``, POST ``/{run_id}/human-review``)
serve rows from the DB, not the in-memory ``_RUNS_STORE``.

Coverage:
  * POST /run inserts a row into the DB (row visible via SELECT)
  * GET /{run_id} returns the DB row, not just the in-memory mirror
  * GET /{run_id}/report renders from the DB row
  * POST /{run_id}/human-review appends to the DB row's
    ``human_review_records`` JSON list
  * GET / (list) returns rows from the DB in reverse-chronological order
  * Missing run_id still returns 404
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.database import async_session_factory
from app.models.coding_review_run import CodingReviewRun


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


SAMPLE_INPUT = {
    "encounter_text": "患者男 65 岁, 因持续胸痛 6 小时入院",
    "case_id": "c-persist-001",
    "input_source": "manual",
    "mode": "link_validation",
    "primary_disease_codes": "I21.401",
    "other_disease_codes": "I10.x00",
    "primary_surgery_codes": "",
    "other_surgery_codes": "",
}


# ── Test 1: POST /run writes to DB ───────────────────────────────────────


def test_post_run_inserts_row_in_db(client):
    """After POST /run, the CodingReviewRun SQL table has a matching row."""
    r = client.post("/api/icoder/coding-review/run", json=SAMPLE_INPUT)
    assert r.status_code == 200, f"run failed: {r.text}"
    run_id = r.json()["run_id"]

    # Verify row is in the DB (not just _RUNS_STORE)
    import asyncio
    rows = asyncio.get_event_loop().run_until_complete(_load_run(run_id))
    assert rows is not None, f"run_id={run_id} not found in CodingReviewRun table"
    row = rows
    assert row.id == run_id
    assert row.case_id == "c-persist-001"
    assert row.agent_ref == "icoder/medcoder-coding-review-agent@1.0.0"
    assert row.prediction_mode == "link_validation"
    assert row.input_source == "manual"
    assert row.encounter_text == SAMPLE_INPUT["encounter_text"]


# ── Test 2: GET /{run_id} reads from DB ─────────────────────────────────


def test_get_run_id_reads_from_db(client):
    """GET /{run_id} resolves the row from DB even if _RUNS_STORE is empty."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-get-001",
    })
    run_id = r.json()["run_id"]

    # Drop the in-memory mirror to prove the read goes to DB
    from app.api import icoder_coding_review
    icoder_coding_review._RUNS_STORE.pop(run_id, None)

    # Re-fetch via GET — must still resolve from DB
    g = client.get(f"/api/icoder/coding-review/{run_id}")
    assert g.status_code == 200
    body = g.json()
    assert body["run_id"] == run_id
    assert body["trace_id"]  # non-empty
    assert body["agent_ref"] == "icoder/medcoder-coding-review-agent@1.0.0"


# ── Test 3: GET /{run_id}/report reads from DB ─────────────────────────


def test_get_report_reads_from_db(client):
    """GET /{run_id}/report renders from the DB row, not the in-memory mirror."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-report-001",
    })
    run_id = r.json()["run_id"]

    # Drop the in-memory mirror
    from app.api import icoder_coding_review
    icoder_coding_review._RUNS_STORE.pop(run_id, None)

    rep = client.get(f"/api/icoder/coding-review/{run_id}/report?format=html")
    assert rep.status_code == 200
    html = rep.text
    # 18 节 + disclaimer
    assert "18. 免责声明" in html
    assert "Pipeline Validation" in html

    # JSON format too
    rep_json = client.get(f"/api/icoder/coding-review/{run_id}/report?format=json")
    assert rep_json.status_code == 200
    body = rep_json.json()
    assert body["run_id"] == run_id


# ── Test 4: POST /{run_id}/human-review appends to DB row ──────────────


def test_human_review_appends_to_db_row(client):
    """human-review entry lands in the DB row's human_review_records JSON list."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-hr-001",
    })
    run_id = r.json()["run_id"]

    h = client.post(f"/api/icoder/coding-review/{run_id}/human-review", json={
        "action": "accept",
        "target_code": "I21.401",
        "target_role": "primary_disease",
        "reason_code": "R007",
        "reviewer": "dr.li",
        "reviewer_role": "coder",
    })
    assert h.status_code == 200
    h_body = h.json()
    assert h_body["accepted"] is True
    record_id = h_body["record_id"]

    # Drop the in-memory mirror, then re-fetch from DB
    from app.api import icoder_coding_review
    icoder_coding_review._RUNS_STORE.pop(run_id, None)

    # Now the second GET should still see the human-review record, served from DB
    g = client.get(f"/api/icoder/coding-review/{run_id}")
    assert g.status_code == 200
    # human_review_records is preserved in the helper shape
    records = g.json().get("human_review_records", [])
    assert len(records) == 1
    assert records[0]["record_id"] == record_id
    assert records[0]["target_code"] == "I21.401"
    assert records[0]["action"] == "accept"


# ── Test 5: GET / (list) returns DB rows in reverse-chronological order ─


def test_list_runs_returns_db_rows_in_reverse_chrono(client):
    """GET / returns CodingReviewRun rows ordered by created_at DESC.

    We assert the property by querying the DB directly for the created_at
    of the first 3 returned run_ids and checking they descend.
    """
    import asyncio
    case_ids = [f"c-list-{i:03d}" for i in range(3)]
    run_ids_in_insert_order = []
    for case_id in case_ids:
        r = client.post("/api/icoder/coding-review/run", json={
            **SAMPLE_INPUT, "case_id": case_id,
        })
        assert r.status_code == 200
        run_ids_in_insert_order.append(r.json()["run_id"])

    lst = client.get("/api/icoder/coding-review/")
    assert lst.status_code == 200
    body = lst.json()

    # The 3 new run_ids appear in the result (in some position)
    returned_ids = [r["run_id"] for r in body["runs"]]
    for rid in run_ids_in_insert_order:
        assert rid in returned_ids, f"run_id={rid} missing from list response"

    # The 3 run_ids we just inserted should appear in REVERSE insertion order
    # (last inserted is newest → first in DESC list)
    expected = list(reversed(run_ids_in_insert_order))
    positions = [returned_ids.index(rid) for rid in expected]
    assert positions == sorted(positions), (
        f"inserted runs must appear in reverse-chronological order: "
        f"expected positions ascending {positions}, got order {returned_ids}"
    )

    # Cross-check: directly query created_at and assert it's DESC across the list
    rows_by_id = asyncio.get_event_loop().run_until_complete(
        _load_runs_by_ids(returned_ids)
    )
    by_id = {r.id: r.created_at for r in rows_by_id}
    created_ats_in_list_order = [by_id[rid] for rid in returned_ids]
    assert created_ats_in_list_order == sorted(created_ats_in_list_order, reverse=True), (
        f"runs must be ordered reverse-chronologically by created_at: "
        f"{created_ats_in_list_order}"
    )


# ── Test 6: Missing run_id returns 404 ──────────────────────────────────


def test_get_unknown_run_id_returns_404(client):
    g = client.get("/api/icoder/coding-review/does-not-exist-12345")
    assert g.status_code == 404


def test_get_report_unknown_run_id_returns_404(client):
    g = client.get("/api/icoder/coding-review/does-not-exist-12345/report")
    assert g.status_code == 404


def test_human_review_unknown_run_id_returns_404(client):
    h = client.post(
        "/api/icoder/coding-review/does-not-exist-12345/human-review",
        json={"action": "accept", "reason_code": "R007", "reviewer": "dr.li"},
    )
    assert h.status_code == 404


# ── Test 7: Row survives across TestClient instances (simulated restart) ─


def test_row_survives_simulated_restart(client):
    """A new TestClient (different FastAPI invocation) still sees the DB row."""
    r = client.post("/api/icoder/coding-review/run", json={
        **SAMPLE_INPUT, "case_id": "c-restart-001",
    })
    run_id = r.json()["run_id"]

    # Simulate a restart: new TestClient + drop in-memory mirror
    from app.api import icoder_coding_review
    icoder_coding_review._RUNS_STORE.pop(run_id, None)
    new_client = TestClient(app)

    g = new_client.get(f"/api/icoder/coding-review/{run_id}")
    assert g.status_code == 200, f"row did not survive restart: {g.text}"
    assert g.json()["run_id"] == run_id


# ── Helpers (async DB) ──────────────────────────────────────────────────


async def _load_run(run_id: str):
    async with async_session_factory() as session:
        stmt = select(CodingReviewRun).where(CodingReviewRun.id == run_id)
        return (await session.execute(stmt)).scalar_one_or_none()


async def _load_runs_by_ids(run_ids: list[str]):
    async with async_session_factory() as session:
        stmt = select(CodingReviewRun).where(CodingReviewRun.id.in_(run_ids))
        return (await session.execute(stmt)).scalars().all()
