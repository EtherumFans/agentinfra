from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.corti_parity.validate_corti_prebuilt_agent_parity import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_CATALOG,
    EXPECTED_CORTI_AGENTS,
    validate_catalog,
)


def test_repository_corti_prebuilt_catalog_passes_development_gate() -> None:
    report = validate_catalog()

    assert report["passed"] is True
    assert report["catalog_errors"] == []
    assert report["failed_agents"] == []
    assert report["summary"] == {
        "expected_corti_agents": 20,
        "catalog_entries": 20,
        "catalog_mapped": 20,
        "development_verified": 20,
        "china_profile_declared": 20,
        "clinical_quality_verified": 0,
        "production_ready_verified": 0,
    }
    assert all(item["remaining_capability_gap"] for item in report["agents"])


def test_gate_cannot_promote_clinical_or_production_claims(tmp_path: Path) -> None:
    catalog = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))
    catalog["verification_boundaries"]["clinical_quality_verified"] = True
    catalog["verification_boundaries"]["production_ready_verified"] = True
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    report = validate_catalog(path, DEFAULT_AGENTS_DIR)

    assert report["passed"] is False
    assert any("clinical_quality_verified" in error for error in report["catalog_errors"])
    assert any("production_ready_verified" in error for error in report["catalog_errors"])
    assert all(item["clinical_quality_verified"] is False for item in report["agents"])
    assert all(item["production_ready_verified"] is False for item in report["agents"])


def test_gate_fails_on_catalog_identity_mapping_and_localization_drift(
    tmp_path: Path,
) -> None:
    catalog = json.loads(DEFAULT_CATALOG.read_text(encoding="utf-8"))
    broken = copy.deepcopy(catalog)
    broken["agents"][0]["corti_name"] = "Renamed without observation"
    broken["agents"][1]["icoder_agent_id"] = broken["agents"][0]["icoder_agent_id"]
    broken["agents"][2]["china_adaptation"]["required_markers"] = [
        "marker-that-does-not-exist"
    ]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    report = validate_catalog(path, DEFAULT_AGENTS_DIR)

    assert report["passed"] is False
    assert len(EXPECTED_CORTI_AGENTS) == 20
    assert "catalog identities/order differ" in report["catalog_errors"][0]
    assert "iCoDer mappings must be one-to-one" in report["catalog_errors"]
    compliance = next(
        item for item in report["agents"] if item["corti_agent_id"] == "compliance-guardrail"
    )
    assert compliance["china_profile_declared"] is False
    assert any("marker not found" in error for error in compliance["errors"])
