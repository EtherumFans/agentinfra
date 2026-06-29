"""Tests for ``GET /api/icoder/doctor`` (P1.0-C, extended P1.1-E).

Covers:
* 200 with full 21-check report on the list endpoint
* 200 with single check on the ``/{check_id}`` endpoint (full id + short prefix)
* 404 on unknown check id (no fake data)
* Verdict always present + in {OK, WARN, FAIL}
* P1.1-E: check 21 (loader_classification) shape + surfaces the 16-pack
  breakdown via ``compute_compatibility()``
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
        # P1.1-E: 20 → 21 checks (added loader_classification)
        assert body["summary"]["total"] == 21
        assert len(body["checks"]) == 21

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


# ── P1.1-E — Loader-driven doctor checks ──────────────────────────────────


class TestLoaderClassificationCheck:
    """P1.1-E: check 21 reports the Loader-compat surface (compute_compatibility)
    so the front-end Doctor UI can show "10 executable / 6 metadata_only /
    0 invalid" instead of treating all packs uniformly.
    """

    def test_check_21_present(self, client):
        r = client.get("/api/icoder/doctor/21.loader_classification")
        assert r.status_code == 200
        body = r.json()
        assert "check" in body
        ch = body["check"]
        assert ch["id"] == "21.loader_classification"
        assert ch["status"] in ("OK", "WARN", "FAIL", "SKIP")
        # detail carries the Loader-compat breakdown
        d = ch["detail"]
        for k in ("total_discovered", "executable", "metadata_only", "invalid",
                  "by_status", "by_type", "by_format"):
            assert k in d, f"missing detail.{k}"

    def test_check_21_real_packs_surface(self, client):
        """Asserts the breakdown on this checkout is sane (avoid hardcoding
        the exact 16-pack count so adding/removing packs doesn't break the
        test). Loader discovers ≥ 1 pack; at least one is executable or
        metadata_only; no pack should be both at once.
        """
        r = client.get("/api/icoder/doctor/21")
        assert r.status_code == 200
        d = r.json()["check"]["detail"]
        assert d["total_discovered"] >= 1
        # executable + metadata_only + invalid = total_discovered
        # (this is the Loader's classification invariant)
        sum_ = d["executable"] + d["metadata_only"] + d["invalid"]
        assert sum_ == d["total_discovered"], (
            f"classification invariant broken: {d['executable']} + "
            f"{d['metadata_only']} + {d['invalid']} != {d['total_discovered']}"
        )
        # at least one of executable / metadata_only must be > 0 (a checkout
        # with only invalid packs would be broken in a different way)
        assert d["executable"] + d["metadata_only"] >= 1
        # verdict is consistent with the breakdown
        status = r.json()["check"]["status"]
        if d["invalid"] > 0:
            assert status == "FAIL"
        elif d["metadata_only"] > 0:
            assert status == "WARN"
        else:
            assert status == "OK"

    def test_check_21_short_prefix(self, client):
        """Users type ``/doctor/21`` not the full id."""
        r = client.get("/api/icoder/doctor/21")
        assert r.status_code == 200
        body = r.json()
        assert body["check"]["id"] == "21.loader_classification"


class TestLoaderDrivenPackFilesCheck:
    """P1.1-E: check 09 refactored to use load_packs_from_dir.
    Asserts the new shape (by_status + agent_refs) and that the
    Loader discovered at least one pack.
    """

    def test_check_09_uses_loader(self, client):
        r = client.get("/api/icoder/doctor/09")
        assert r.status_code == 200
        d = r.json()["check"]["detail"]
        # New shape: by_status breakdown + agent_refs list
        assert "by_status" in d
        assert "agent_refs" in d
        assert "total" in d
        assert d["total"] >= 1
        assert isinstance(d["by_status"], dict)
        assert isinstance(d["agent_refs"], list)
        # No raw "packs" list (the P1.0-C shape) — replaced by agent_refs
        assert "packs" not in d


class TestLoaderDrivenRequiredFieldsCheck:
    """P1.1-E: check 10 refactored to iterate NormalizedPack.raw.
    """

    def test_check_10_loads_packs(self, client):
        r = client.get("/api/icoder/doctor/10")
        assert r.status_code == 200
        ch = r.json()["check"]
        # Should be OK on this checkout (all 16 packs have required fields)
        assert ch["status"] == "OK"
        d = ch["detail"]
        assert "inspected" in d
        assert d["inspected"] >= 1