"""Development gate for the exact local Code Validation catalogs."""

from __future__ import annotations

import pytest


def test_pinned_development_catalogs_match_manifest_and_expected_counts():
    from official_agents.code_validation.catalog_validation import (
        verify_catalog_health,
    )

    evidence = verify_catalog_health()
    assert evidence["integrity_verified"] is True
    assert evidence["catalog_counts"] == {
        "ICD-10-CN": 37897,
        "ICD-9-CM-3": 13617,
    }
    assets = {item["asset_id"]: item for item in evidence["assets"]}
    assert set(assets) == {"cn.icd10cn.catalog", "cn.icd9cm3.catalog"}
    assert all(
        item["version"] == "observed-local-2026-05-19"
        for item in assets.values()
    )
    assert all(
        item["authority_status"] == "source_unverified"
        for item in assets.values()
    )
    assert all(
        item["license_status"] == "external_review_required"
        for item in assets.values()
    )
    assert all(item["billing_authoritative"] is False for item in assets.values())
    assert all(item["manual_review_required"] is True for item in assets.values())


def test_unverified_catalog_is_rejected_for_cloud_use(monkeypatch):
    from app.config import settings
    from app.services.clinical_asset_governance import (
        ClinicalAssetGovernanceError,
    )
    from official_agents.code_validation.catalog_validation import (
        _governance_and_loader,
    )

    monkeypatch.setattr(settings, "ICODER_DEPLOYMENT_MODE", "cloud")
    with pytest.raises(ClinicalAssetGovernanceError, match="not verified for cloud"):
        _governance_and_loader("ICD-10-CN")
