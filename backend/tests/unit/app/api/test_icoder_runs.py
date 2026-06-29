"""Tests for ``GET /api/icoder/runs*`` (P1.0-E).

Covers:
* 200 on list with empty envelope
* 200 on list with history populated (uses recorded fixture)
* 200 on single-run get
* 404 on unknown run_id (RUN_NOT_FOUND error_code)
* history_available flag flips correctly
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_history(tmp_path, monkeypatch):
    """Write a couple of fake run entries to ``app.state.run_history``
    so the list / get endpoints have something to return."""
    history_file = tmp_path / "run_history.jsonl"
    entries = [
        {
            "schema_version": "1.0",
            "timestamp": "2026-06-28T10:00:00Z",
            "run_id": "run-test-001",
            "agent_ref": "icoder/medcoder-coding-review-agent@1.0.0",
            "status": "completed",
            "processing_time_ms": 1234,
            "primary_diagnosis_code": "I50.900",
            "primary_diagnosis_description": "心力衰竭",
            "review_conclusion": "auto-approved",
            "issues_count": 0,
            "errors": [],
        },
        {
            "schema_version": "1.0",
            "timestamp": "2026-06-28T10:01:00Z",
            "run_id": "run-test-002",
            "agent_ref": "icoder/medcoder-coding-review-agent@1.0.0",
            "status": "needs_review",
            "processing_time_ms": 2300,
            "primary_diagnosis_code": "O82.0",
            "primary_diagnosis_description": "剖宫产术",
            "review_conclusion": "low_confidence",
            "issues_count": 1,
            "errors": [],
        },
    ]
    with open(history_file, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return history_file, entries


class TestListRuns:
    def test_returns_envelope_with_history_available(self, client):
        body = client.get("/api/icoder/runs").json()
        assert "runs" in body
        assert "total" in body
        assert "history_available" in body
        assert isinstance(body["runs"], list)

    def test_filter_by_agent_ref(self, client, fake_history):
        from app.main import app

        history_file, entries = fake_history
        # Replace the run_history file with our fixture by swapping the
        # storage dir on the existing store.
        history = app.state.run_history
        history._file = history_file
        body = client.get(
            "/api/icoder/runs",
            params={"agent_ref": "icoder/medcoder-coding-review-agent@1.0.0"},
        ).json()
        assert body["history_available"] is True
        assert body["total"] == 2

    def test_empty_history_returns_zero(self, client):
        from app.main import app

        history = app.state.run_history
        original = history._file
        try:
            from pathlib import Path
            empty = Path(history._file.parent) / "_empty_for_test.jsonl"
            empty.touch()
            history._file = empty
            body = client.get("/api/icoder/runs").json()
            assert body == {"runs": [], "total": 0, "history_available": True}
        finally:
            history._file = original


class TestGetRun:
    def test_known_run_returns_entry(self, client, fake_history):
        from app.main import app

        history_file, entries = fake_history
        history = app.state.run_history
        original = history._file
        try:
            history._file = history_file
            r = client.get("/api/icoder/runs/run-test-001")
            assert r.status_code == 200
            body = r.json()
            assert body["run_id"] == "run-test-001"
            assert body["status"] == "completed"
            assert body["primary_diagnosis_code"] == "I50.900"
        finally:
            history._file = original

    def test_unknown_run_returns_404(self, client):
        r = client.get("/api/icoder/runs/totally-not-a-real-run-id")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "RUN_NOT_FOUND"
        assert "totally-not-a-real-run-id" in detail["run_id"]