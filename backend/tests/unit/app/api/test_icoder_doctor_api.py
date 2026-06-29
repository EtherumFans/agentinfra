"""Tests for ``GET /api/icoder/doctor`` (P1.0-C).

Covers:
* 200 with full 20-check report on the list endpoint
* 200 with single check on the ``/{check_id}`` endpoint (full id + short prefix)
* 404 on unknown check id (no fake data)
* Verdict always present + in {OK, WARN, FAIL}
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


class TestDoctorList:
    def test_full_report_returns_200(self, client):
        r = client.get("/api/icoder/doctor")
        assert r.status_code == 200
        body = r.json()
        assert body["verdict"] in ("OK", "WARN", "FAIL")
        assert body["summary"]["total"] == 20
        assert len(body["checks"]) == 20

    def test_summary_counts_add_up(self, client):
        body = client.get("/api/icoder/doctor").json()
        s = body["summary"]
        assert s["passed"] + s["warned"] + s["failed"] + s["skipped"] == s["total"]

    def test_each_check_has_required_fields(self, client):
        body = client.get("/api/icoder/doctor").json()
        for ch in body["checks"]:
            for k in ("id", "title", "status"):
                assert k in ch, f"check {ch.get('id')} missing {k}"
            assert ch["status"] in ("OK", "WARN", "FAIL", "SKIP")


class TestDoctorSingleCheck:
    def test_known_full_id(self, client):
        r = client.get("/api/icoder/doctor/19.fewshot_flag_default_off")
        assert r.status_code == 200
        body = r.json()
        assert "check" in body
        assert body["check"]["id"] == "19.fewshot_flag_default_off"

    def test_short_prefix(self, client):
        """Users type ``/doctor/19`` not the full id."""
        r = client.get("/api/icoder/doctor/19")
        assert r.status_code == 200
        body = r.json()
        assert body["check"]["id"].startswith("19.")

    def test_unknown_id_returns_404(self, client):
        r = client.get("/api/icoder/doctor/totally-not-a-check")
        assert r.status_code == 404
        detail = r.json()["detail"]
        assert detail["error_code"] == "DOCTOR_CHECK_NOT_FOUND"